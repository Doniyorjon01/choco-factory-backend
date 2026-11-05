"""
Reversal (STR, "storno"): the only way to fix a wrong document.

Nothing is deleted. A new STR document writes the opposite movements, and
both documents stay in the ledger, linked to each other.

Rules:
- admin only, a reason is required;
- a document can be reversed only once;
- a reversal cannot be reversed;
- if the reversal would make some stock negative (for example, the produced
  chocolate was already scrapped), it is rejected with NEGATIVE_BALANCE.
"""

from datetime import datetime

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from errors import generate_error
from models import Document, DocumentType, User
from schemas.documents import ReversalCreate
from services.documents import find_replay, load_products, lock_stock, post_document, product_ref, request_hash
from translations import Msg


def reverse_document(
    db: Session, document_id: int, data: ReversalCreate, user: User, *, created_at: datetime | None = None
) -> tuple[Document, bool]:
    req_hash = request_hash(DocumentType.REVERSAL, user, data, extra={"document_id": document_id})
    existing = find_replay(db, data.request_id, req_hash)
    if existing:
        return existing, True

    # Lock the original document row: two admins cannot reverse it at the same time.
    # (This is a row lock only; the document itself is never updated.)
    original = db.scalars(
        select(Document)
        .where(Document.id == document_id)
        .with_for_update(of=Document)
        .execution_options(populate_existing=True)
    ).first()
    if original is None:
        raise generate_error(Msg.DOCUMENT_NOT_FOUND, status.HTTP_404_NOT_FOUND)
    if original.doc_type == DocumentType.REVERSAL:
        raise generate_error(Msg.CANNOT_REVERSE_REVERSAL, status.HTTP_409_CONFLICT)

    already = db.scalars(select(Document).where(Document.reverses_id == original.id)).first()
    if already is not None:
        raise generate_error(
            Msg.ALREADY_REVERSED,
            status.HTTP_409_CONFLICT,
            params={"number": already.number},
            data={"reversal": {"id": already.id, "number": already.number}},
        )

    moves = {entry.product_id: -entry.qty_delta for entry in original.entries}
    stock = lock_stock(db, moves.keys())
    products = load_products(db, moves.keys())

    negative = [
        {
            "product": product_ref(products[pid]),
            "current": stock[pid],
            "delta": delta,
            "would_be": stock[pid] + delta,
        }
        for pid, delta in sorted(moves.items())
        if stock[pid] + delta < 0
    ]
    if negative:
        raise generate_error(Msg.NEGATIVE_BALANCE, status.HTTP_409_CONFLICT, data={"lines": negative})

    document = post_document(
        db,
        doc_type=DocumentType.REVERSAL,
        user=user,
        request_id=data.request_id,
        req_hash=req_hash,
        moves=moves,
        stock=stock,
        created_at=created_at,
        reverses_id=original.id,
        product_id=original.product_id,
        reason="manual",
        note=data.reason,
    )
    db.commit()
    return document, False