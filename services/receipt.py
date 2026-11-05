"""
Receipt (KRM): raw materials come into the warehouse.

One receipt can have many lines (one supplier invoice). Only raw materials:
finished products appear only through production.
"""

from datetime import datetime

from fastapi import status
from sqlalchemy.orm import Session

from errors import generate_error
from models import Document, DocumentType, ProductKind, User
from schemas.documents import ReceiptCreate
from services.documents import find_replay, load_products, lock_stock, post_document, product_ref, request_hash
from translations import Msg
from utils.timeutils import local_today


def create_receipt(
    db: Session, data: ReceiptCreate, user: User, *, created_at: datetime | None = None
) -> tuple[Document, bool]:
    req_hash = request_hash(DocumentType.RECEIPT, user, data)
    existing = find_replay(db, data.request_id, req_hash)
    if existing:
        return existing, True

    ids = [line.product_id for line in data.lines]
    if len(ids) != len(set(ids)):
        raise generate_error(Msg.DUPLICATE_LINE, status.HTTP_422_UNPROCESSABLE_CONTENT)

    # The supplier's date is only written down for the record. It cannot be in
    # the future (business day in Tashkent). The ledger uses the server time.
    if data.supplier_doc_date and data.supplier_doc_date > local_today():
        raise generate_error(Msg.SUPPLIER_DATE_IN_FUTURE, status.HTTP_422_UNPROCESSABLE_CONTENT)

    stock = lock_stock(db, ids)
    products = load_products(db, ids)
    for product in products.values():
        if product.kind != ProductKind.RAW:
            raise generate_error(
                Msg.RECEIPT_RAW_ONLY, status.HTTP_422_UNPROCESSABLE_CONTENT, data={"product": product_ref(product)}
            )

    document = post_document(
        db,
        doc_type=DocumentType.RECEIPT,
        user=user,
        request_id=data.request_id,
        req_hash=req_hash,
        moves={line.product_id: line.qty for line in data.lines},
        stock=stock,
        created_at=created_at,
        supplier_name=data.supplier_name or None,
        supplier_doc_no=data.supplier_doc_no or None,
        supplier_doc_date=data.supplier_doc_date,
        note=data.note or None,
    )
    db.commit()
    return document, False