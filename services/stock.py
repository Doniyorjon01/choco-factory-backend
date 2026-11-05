"""
Qoldiqlar va ishlab chiqarish imkoniyati — faqat o'qish.

Yozish (qoldiq o'zgarishi) faqat hujjat tranzaksiyalarida bo'ladi (2-qism).
"""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from models import (
    Document,
    DocumentType,
    LedgerEntry,
    Product,
    ProductKind,
    RecipeStatus,
    RecipeVersion,
    StockBalance,
)
from utils.timeutils import local_days_range_utc

CONSUMPTION_WINDOW_DAYS = 7


def stock_level(qty: int, min_qty: int) -> str:
    if qty == 0:
        return "out"
    if qty < min_qty:
        return "low"
    return "ok"


def consumption(db: Session, days: int = CONSUMPTION_WINDOW_DAYS) -> dict[int, int]:
    """Oxirgi `days` kunda (bugun bilan) ishlab chiqarishga sarflangan xomashyo, mahsulot bo'yicha.
    Storno qilingan ishlab chiqarishlar hisobga olinmaydi."""
    start, end = local_days_range_utc(days)
    reversed_ids = select(Document.reverses_id).where(Document.reverses_id.is_not(None))
    rows = db.execute(
        select(LedgerEntry.product_id, func.sum(-LedgerEntry.qty_delta))
        .join(Document, Document.id == LedgerEntry.document_id)
        .where(
            Document.doc_type == DocumentType.PRODUCTION,
            Document.id.not_in(reversed_ids),
            LedgerEntry.qty_delta < 0,
            LedgerEntry.created_at >= start,
            LedgerEntry.created_at < end,
        )
        .group_by(LedgerEntry.product_id)
    )
    return {product_id: int(total) for product_id, total in rows}


def stock_list(db: Session, kind: str | None = None, level: str | None = None, q: str | None = None) -> list[dict]:
    stmt = (
        select(Product, StockBalance.qty)
        .join(StockBalance, StockBalance.product_id == Product.id)
        .where(Product.is_archived.is_(False))
    )
    if kind:
        stmt = stmt.where(Product.kind == kind)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Product.code.ilike(like), Product.name_uz.ilike(like), Product.name_ru.ilike(like)))
    stmt = stmt.order_by(Product.kind.desc(), Product.code)

    used = consumption(db)
    items = []
    for product, qty in db.execute(stmt).unique():
        lvl = stock_level(qty, product.min_qty)
        if level and lvl != level:
            continue
        is_raw = product.kind == ProductKind.RAW
        consumed = used.get(product.id, 0) if is_raw else None
        days_left = (qty * CONSUMPTION_WINDOW_DAYS) // consumed if consumed else None
        items.append(
            {
                "product_id": product.id,
                "code": product.code,
                "name_uz": product.name_uz,
                "name_ru": product.name_ru,
                "kind": product.kind,
                "unit": product.unit,
                "qty": qty,
                "min_qty": product.min_qty,
                "target_qty": product.target_qty,
                "level": lvl,
                "consumed_7d": consumed,
                "days_left": days_left,
            }
        )
    return items


def capacity(db: Session, product_id: int | None = None) -> list[dict]:
    """
    Har bir faol retsept uchun: joriy qoldiqdan maksimal nechta dona chiqadi
    va qaysi xomashyo cheklaydi. Qulf olinmaydi — bu ko'rsatkich; aniq tekshiruv
    ishlab chiqarish tranzaksiyasi ichida qayta bajariladi.
    """
    stmt = (
        select(RecipeVersion)
        .join(Product, Product.id == RecipeVersion.product_id)
        .where(RecipeVersion.status == RecipeStatus.ACTIVE, Product.is_archived.is_(False))
        .order_by(Product.code)
    )
    if product_id is not None:
        stmt = stmt.where(RecipeVersion.product_id == product_id)
    versions = list(db.scalars(stmt).unique())

    raw_ids = {line.raw_product_id for v in versions for line in v.lines}
    stock = (
        dict(
            db.execute(
                select(StockBalance.product_id, StockBalance.qty).where(StockBalance.product_id.in_(raw_ids))
            ).all()
        )
        if raw_ids
        else {}
    )

    result = []
    for v in versions:
        lines = []
        max_possible: int | None = None
        limiting = None
        for line in v.lines:
            have = stock.get(line.raw_product_id, 0)
            by_this = have // line.qty_per_unit
            # Arxivlangan xomashyo bo'lsa, bu retsept bo'yicha ishlab chiqarib bo'lmaydi
            if line.raw_product.is_archived:
                by_this = 0
            lines.append(
                {
                    "raw_product": line.raw_product,
                    "qty_per_unit": line.qty_per_unit,
                    "stock_qty": have,
                    "max_by_this": by_this,
                }
            )
            if max_possible is None or by_this < max_possible:
                max_possible, limiting = by_this, line.raw_product
        result.append(
            {
                "product": v.product,
                "recipe_version_id": v.id,
                "recipe_version": v.version,
                "max_possible": max_possible or 0,
                "limiting": limiting,
                "lines": lines,
            }
        )
    return result
