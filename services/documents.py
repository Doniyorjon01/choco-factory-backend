"""
Shared building blocks for every document type (receipt, production,
adjustment, scrap, reversal).

Every document is written the same way, inside ONE transaction:

    1. idempotency: the same request_id returns the first document
    2. lock the stock rows of all touched products (ordered by product_id)
    3. check the business rules against the locked (= current) stock
    4. take the next document number (gapless counter)
    5. insert the document, update stock_balance, insert ledger entries
    6. COMMIT  — or, on any error, nothing is written at all

Lock order is the same everywhere: recipe version (share) -> stock rows by
product_id -> document counter. Because of this, two documents never wait
for each other in a circle (no deadlocks).
"""

import hashlib
import json
import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from fastapi import status
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from errors import generate_error
from models import Document, DocumentType, LedgerEntry, Product, StockBalance, User
from services.numbering import next_number
from translations import Msg


def product_ref(product: Product) -> dict[str, Any]:
    """Small product description for error payloads."""
    return {
        "id": product.id,
        "code": product.code,
        "name_uz": product.name_uz,
        "name_ru": product.name_ru,
        "unit": product.unit,
    }


# --------------------------------------------------------------------- #
# Idempotency
# --------------------------------------------------------------------- #


def request_hash(doc_type: DocumentType, user: User, payload: BaseModel, extra: dict | None = None) -> str:
    """Fingerprint of the request body. Same request_id + different body = conflict."""
    body = payload.model_dump(mode="json", exclude={"request_id"})
    raw = json.dumps(
        {"type": str(doc_type), "user": user.id, "body": body, "extra": extra or {}},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def find_replay(db: Session, request_id: uuid.UUID, req_hash: str) -> Document | None:
    """
    Returns the already created document for this request_id, or None.

    An advisory lock on the request_id makes two identical requests (double
    click, network retry) run one after another. The second one then simply
    finds the document of the first one.
    """
    db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(str(request_id), 0))))
    existing = db.scalars(select(Document).where(Document.request_id == request_id)).first()
    if existing is None:
        return None
    if existing.request_hash != req_hash:
        raise generate_error(Msg.IDEMPOTENCY_CONFLICT, status.HTTP_422_UNPROCESSABLE_CONTENT)
    return existing


# --------------------------------------------------------------------- #
# Locking and validation
# --------------------------------------------------------------------- #


def lock_stock(db: Session, product_ids: Iterable[int]) -> dict[int, int]:
    """
    Locks stock rows (always in product_id order) and returns {product_id: qty}.
    Values are read AFTER the lock is taken, so they are the real current stock.
    """
    ids = sorted(set(product_ids))
    rows = db.execute(
        select(StockBalance.product_id, StockBalance.qty)
        .where(StockBalance.product_id.in_(ids))
        .order_by(StockBalance.product_id)
        .with_for_update()
    ).all()
    stock = {pid: qty for pid, qty in rows}
    missing = [pid for pid in ids if pid not in stock]
    if missing:
        raise generate_error(Msg.PRODUCT_NOT_FOUND, status.HTTP_404_NOT_FOUND, data={"product_id": missing[0]})
    return stock


def load_products(db: Session, product_ids: Iterable[int], *, allow_archived: bool = False) -> dict[int, Product]:
    """
    Loads products after their stock rows are locked.

    Archiving a product also locks its stock row, so here we always see the
    final archived flag: a document and an archive action cannot overlap.
    """
    ids = sorted(set(product_ids))
    products = {
        p.id: p
        for p in db.scalars(
            select(Product).where(Product.id.in_(ids)).execution_options(populate_existing=True)
        ).unique()
    }
    for pid in ids:
        product = products.get(pid)
        if product is None:
            raise generate_error(Msg.PRODUCT_NOT_FOUND, status.HTTP_404_NOT_FOUND, data={"product_id": pid})
        if product.is_archived and not allow_archived:
            raise generate_error(
                Msg.PRODUCT_ARCHIVED,
                status.HTTP_409_CONFLICT,
                params={"name": f"{product.code} {product.name_uz}"},
                data={"product": product_ref(product)},
            )
    return products


def require_note(reason: str, note: str | None) -> None:
    if reason == "other" and not (note and note.strip()):
        raise generate_error(Msg.NOTE_REQUIRED, status.HTTP_422_UNPROCESSABLE_CONTENT)


# --------------------------------------------------------------------- #
# Writing
# --------------------------------------------------------------------- #


def post_document(
    db: Session,
    *,
    doc_type: DocumentType,
    user: User,
    request_id: uuid.UUID,
    req_hash: str,
    moves: dict[int, int],
    stock: dict[int, int],
    created_at: datetime | None = None,
    **fields: Any,
) -> Document:
    """
    Inserts the document, changes stock_balance and writes ledger entries.

    `moves` is {product_id: signed delta}. `stock` must come from lock_stock()
    in the same transaction. The caller has already checked the business rules;
    the negative check below is only a safety net (the database CHECK is another one).

    `created_at` is only for the seed script (historical data). In the API it
    is always the server clock, taken after the locks, so ledger time order
    matches the order of qty_after values.
    """
    ts = created_at or db.scalar(select(func.clock_timestamp()))
    number = next_number(db, doc_type)

    document = Document(
        number=number,
        doc_type=doc_type,
        created_at=ts,
        created_by_id=user.id,
        request_id=request_id,
        request_hash=req_hash,
        **fields,
    )
    db.add(document)
    db.flush()

    for product_id in sorted(moves):
        delta = moves[product_id]
        if delta == 0:
            continue
        new_qty = stock[product_id] + delta
        if new_qty < 0:
            raise generate_error(Msg.INSUFFICIENT_STOCK, status.HTTP_409_CONFLICT)
        db.execute(
            update(StockBalance).where(StockBalance.product_id == product_id).values(qty=new_qty, updated_at=func.now())
        )
        stock[product_id] = new_qty
        db.add(
            LedgerEntry(
                document_id=document.id,
                product_id=product_id,
                qty_delta=delta,
                qty_after=new_qty,
                created_at=ts,
            )
        )
    db.flush()
    return document