"""
Adjustment (TZT): stocktaking. The user counts the real amount; the system
writes the difference (counted - current) into the ledger.

The client also sends the stock it SAW while counting (expected_qty).
If the stock changed in the meantime (for example a production was written),
we stop with STOCK_CHANGED: the user must recount or confirm the new difference.
Otherwise the correction would silently cancel someone else's document.
"""

from datetime import datetime

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from errors import generate_error
from models import Document, DocumentType, LedgerEntry, User
from schemas.documents import AdjustmentCreate
from services.documents import (
    find_replay,
    load_products,
    lock_stock,
    post_document,
    request_hash,
    require_note,
)
from translations import Msg


def _last_movement(db: Session, product_id: int) -> dict | None:
    row = db.execute(
        select(Document.id, Document.number, Document.doc_type, Document.created_at)
        .join(LedgerEntry, LedgerEntry.document_id == Document.id)
        .where(LedgerEntry.product_id == product_id)
        .order_by(LedgerEntry.id.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return {"id": row.id, "number": row.number, "doc_type": row.doc_type, "created_at": row.created_at.isoformat()}


def create_adjustment(
    db: Session, data: AdjustmentCreate, user: User, *, created_at: datetime | None = None
) -> tuple[Document, bool]:
    req_hash = request_hash(DocumentType.ADJUSTMENT, user, data)
    existing = find_replay(db, data.request_id, req_hash)
    if existing:
        return existing, True

    require_note(data.reason, data.note)

    stock = lock_stock(db, [data.product_id])
    load_products(db, [data.product_id])
    current = stock[data.product_id]

    if current != data.expected_qty:
        raise generate_error(
            Msg.STOCK_CHANGED,
            status.HTTP_409_CONFLICT,
            data={
                "expected_qty": data.expected_qty,
                "current_qty": current,
                "new_diff": data.counted_qty - current,
                "last_document": _last_movement(db, data.product_id),
            },
        )

    diff = data.counted_qty - current
    if diff == 0:
        raise generate_error(Msg.ADJUSTMENT_NO_DIFF, status.HTTP_422_UNPROCESSABLE_CONTENT)

    document = post_document(
        db,
        doc_type=DocumentType.ADJUSTMENT,
        user=user,
        request_id=data.request_id,
        req_hash=req_hash,
        moves={data.product_id: diff},
        stock=stock,
        created_at=created_at,
        product_id=data.product_id,
        quantity=data.counted_qty,
        reason=data.reason,
        note=data.note or None,
    )
    db.commit()
    return document, False