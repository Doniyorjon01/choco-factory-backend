"""
Scrap (BRK): write off damaged goods.

- warehouse and admin: raw materials and finished products;
- operator: finished products only.
The reason must fit the product kind; reason "other" needs a note.
"""

from datetime import datetime

from fastapi import status
from sqlalchemy.orm import Session

from errors import generate_error
from models import Document, DocumentType, ProductKind, User, UserRole
from schemas.documents import FINISHED_SCRAP_REASONS, RAW_SCRAP_REASONS, ScrapCreate
from services.documents import (
    find_replay,
    load_products,
    lock_stock,
    post_document,
    product_ref,
    request_hash,
    require_note,
)
from translations import Msg


def create_scrap(
    db: Session, data: ScrapCreate, user: User, *, created_at: datetime | None = None
) -> tuple[Document, bool]:
    req_hash = request_hash(DocumentType.SCRAP, user, data)
    existing = find_replay(db, data.request_id, req_hash)
    if existing:
        return existing, True

    require_note(data.reason, data.note)

    stock = lock_stock(db, [data.product_id])
    product = load_products(db, [data.product_id])[data.product_id]

    if user.role == UserRole.OPERATOR and product.kind != ProductKind.FINISHED:
        raise generate_error(Msg.SCRAP_KIND_FORBIDDEN, status.HTTP_403_FORBIDDEN)

    allowed = RAW_SCRAP_REASONS if product.kind == ProductKind.RAW else FINISHED_SCRAP_REASONS
    if data.reason not in allowed:
        raise generate_error(
            Msg.INVALID_REASON, status.HTTP_422_UNPROCESSABLE_CONTENT, data={"allowed": sorted(allowed)}
        )

    available = stock[data.product_id]
    if data.qty > available:
        raise generate_error(
            Msg.INSUFFICIENT_STOCK,
            status.HTTP_409_CONFLICT,
            data={"product": product_ref(product), "requested": data.qty, "available": available},
        )

    document = post_document(
        db,
        doc_type=DocumentType.SCRAP,
        user=user,
        request_id=data.request_id,
        req_hash=req_hash,
        moves={data.product_id: -data.qty},
        stock=stock,
        created_at=created_at,
        product_id=data.product_id,
        quantity=data.qty,
        reason=data.reason,
        note=data.note or None,
    )
    db.commit()
    return document, False