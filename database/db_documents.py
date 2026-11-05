"""
Read side of documents and the ledger (lists, filters, one document).
Writing lives in services/ because it is a multi-table transaction.
"""

from datetime import date, timedelta

from fastapi import status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload, noload, selectinload

from errors import generate_error
from models import Document, LedgerEntry, User, UserRole
from translations import Msg
from utils.timeutils import local_day_start_utc


def document_options() -> list:
    """Everything DocumentOut needs, loaded in a fixed number of queries (no N+1)."""
    return [
        selectinload(Document.entries),
        selectinload(Document.snapshot),
        selectinload(Document.recipe_version).raiseload("*"),
        selectinload(Document.reverses).raiseload("*"),
        selectinload(Document.reversed_by).raiseload("*"),
    ]


def get_document(db: Session, pk: int, user: User | None = None) -> Document:
    document = db.scalars(
        select(Document).where(Document.id == pk).options(*document_options()).execution_options(populate_existing=True)
    ).first()
    # An operator sees only own documents. For others we answer "not found",
    # so the operator cannot even learn that the document exists.
    if document is None or (user is not None and user.role == UserRole.OPERATOR and document.created_by_id != user.id):
        raise generate_error(Msg.DOCUMENT_NOT_FOUND, status.HTTP_404_NOT_FOUND)
    return document


def _date_range(stmt: Select, column, date_from: date | None, date_to: date | None) -> Select:
    # Dates are business days in Tashkent time; the database stores UTC.
    if date_from:
        stmt = stmt.where(column >= local_day_start_utc(date_from))
    if date_to:
        stmt = stmt.where(column < local_day_start_utc(date_to + timedelta(days=1)))
    return stmt


def documents_query(
    user: User,
    doc_type: str | None = None,
    product_id: int | None = None,
    created_by_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = None,
) -> Select[tuple[Document]]:
    stmt = select(Document).options(*document_options())
    if user.role == UserRole.OPERATOR:
        stmt = stmt.where(Document.created_by_id == user.id)
    elif created_by_id:
        stmt = stmt.where(Document.created_by_id == created_by_id)
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    if product_id:
        stmt = stmt.where(Document.id.in_(select(LedgerEntry.document_id).where(LedgerEntry.product_id == product_id)))
    if q:
        stmt = stmt.where(Document.number.ilike(f"%{q.strip()}%"))
    stmt = _date_range(stmt, Document.created_at, date_from, date_to)
    return stmt.order_by(Document.created_at.desc(), Document.id.desc())


def ledger_query(
    product_id: int | None = None,
    doc_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Select[tuple[LedgerEntry]]:
    stmt = (
        select(LedgerEntry)
        .join(Document, Document.id == LedgerEntry.document_id)
        .options(
            joinedload(LedgerEntry.document).options(
                noload(Document.entries),
                noload(Document.snapshot),
                selectinload(Document.reversed_by).raiseload("*"),
            )
        )
    )
    if product_id:
        stmt = stmt.where(LedgerEntry.product_id == product_id)
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    stmt = _date_range(stmt, LedgerEntry.created_at, date_from, date_to)
    # id is the real write order (it follows the qty_after chain)
    return stmt.order_by(LedgerEntry.id.desc())