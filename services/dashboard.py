"""
Numbers for the admin / warehouse home page. Read only, no locks.

Days are business days in Tashkent time. Reversed productions are not counted:
after a reversal the chocolate was "never produced".
"""

from datetime import date, timedelta

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from config import settings
from database.db_documents import document_options
from models import Document, DocumentType, Product, ProductKind
from services import stock as stock_service
from utils.timeutils import local_day_start_utc, local_today

DAYS = 7
RECENT_DOCUMENTS = 5


def _production_by_day(db: Session, start_day: date) -> dict[tuple[date, int], int]:
    reversed_ids = select(Document.reverses_id).where(Document.reverses_id.is_not(None))
    local_day = cast(func.timezone(settings.TIMEZONE, Document.created_at), Date)
    rows = db.execute(
        select(local_day, Document.product_id, func.sum(Document.quantity))
        .where(
            Document.doc_type == DocumentType.PRODUCTION,
            Document.id.not_in(reversed_ids),
            Document.created_at >= local_day_start_utc(start_day),
        )
        .group_by(local_day, Document.product_id)
    )
    return {(day, product_id): int(total) for day, product_id, total in rows}


def build_dashboard(db: Session) -> dict:
    today = local_today()
    days = [today - timedelta(days=DAYS - 1 - i) for i in range(DAYS)]
    produced = _production_by_day(db, days[0])

    finished = list(
        db.scalars(
            select(Product)
            .where(Product.kind == ProductKind.FINISHED, Product.is_archived.is_(False))
            .order_by(Product.code)
        ).unique()
    )

    series = []
    for product in finished:
        values = [produced.get((day, product.id), 0) for day in days]
        series.append({"product": product, "values": values, "total": sum(values)})

    today_items = [{"product": s["product"], "qty": s["values"][-1]} for s in series if s["values"][-1] > 0]

    documents_today = db.scalar(
        select(func.count()).select_from(Document).where(Document.created_at >= local_day_start_utc(today))
    )

    recent = list(
        db.scalars(
            select(Document)
            .options(*document_options())
            .order_by(Document.created_at.desc(), Document.id.desc())
            .limit(RECENT_DOCUMENTS)
        ).unique()
    )

    low = [item for item in stock_service.stock_list(db) if item["level"] in ("low", "out")]

    return {
        "today": {
            "produced": today_items,
            "produced_total": sum(i["qty"] for i in today_items),
            "documents_count": documents_today or 0,
        },
        "low_stock": low,
        "capacity": stock_service.capacity(db),
        "production_7d": {
            "days": days,
            "series": series,
            "total": sum(s["total"] for s in series),
        },
        "recent_documents": recent,
    }