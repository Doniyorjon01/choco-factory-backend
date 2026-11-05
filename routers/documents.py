from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Response, status
from fastapi_pagination.ext.sqlalchemy import paginate
from sqlalchemy.orm import Session

from auth.oauth2 import get_admin_or_warehouse, get_any_role, get_current_admin, require_roles
from database import db_documents
from database.config import get_pg_db
from models import Document, User, UserRole
from schemas.documents import (
    AdjustmentCreate,
    DocumentOut,
    DocumentsMetaOut,
    ProductionCreate,
    ReceiptCreate,
    ReversalCreate,
    ScrapCreate,
)
from services import adjustment, production, receipt, reversal, scrap
from utils.pagination import CustomPage

router = APIRouter(prefix="/documents", tags=["documents"])

get_admin_or_operator = require_roles(UserRole.ADMIN, UserRole.OPERATOR)

DocTypeFilter = Literal["receipt", "production", "adjustment", "scrap", "reversal"]


def _respond(db: Session, response: Response, result: tuple[Document, bool]) -> Document:
    """201 for a new document; 200 + header when the same request_id was already processed."""
    document, replayed = result
    if replayed:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
    return db_documents.get_document(db, document.id)


# --------------------------------------------------------------------- #
# Read
# --------------------------------------------------------------------- #

_REASONS = {
    "adjustment": [
        ("inventory", "Inventarizatsiya natijasi", "Результат инвентаризации"),
        ("spill", "Toʻkilgan / isrof", "Просыпано / потери"),
        ("scale_error", "Oʻlchov xatosi", "Ошибка взвешивания"),
        ("other", "Boshqa", "Другое"),
    ],
    "scrap_raw": [
        ("wet", "Namlangan", "Намокло"),
        ("bag_damaged", "Qop yoki qadoq buzilgan", "Повреждён мешок или упаковка"),
        ("dirty", "Ifloslangan", "Загрязнено"),
        ("other", "Boshqa", "Другое"),
    ],
    "scrap_finished": [
        ("shape", "Shakli buzilgan", "Нарушена форма"),
        ("pack_damaged", "Qadoq shikastlangan", "Повреждена упаковка"),
        ("quality", "Sifat talabiga mos emas", "Не соответствует качеству"),
        ("other", "Boshqa", "Другое"),
    ],
}


@router.get("/meta", response_model=DocumentsMetaOut)
def get_meta(user: User = Depends(get_any_role)):
    """Reason codes with uz/ru labels, so the frontend does not hardcode them."""

    def pack(key: str) -> list[dict]:
        return [{"code": c, "uz": uz, "ru": ru} for c, uz, ru in _REASONS[key]]

    return {
        "adjustment_reasons": pack("adjustment"),
        "scrap_reasons_raw": pack("scrap_raw"),
        "scrap_reasons_finished": pack("scrap_finished"),
        "note_required_for": ["other"],
    }


@router.get("", response_model=CustomPage[DocumentOut])
def get_documents(
    doc_type: DocTypeFilter | None = None,
    product_id: int | None = None,
    created_by_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = None,
    db: Session = Depends(get_pg_db),
    user: User = Depends(get_any_role),
):
    """Document journal, newest first. Dates are Tashkent business days (inclusive).
    An operator always gets only own documents ("My documents")."""
    stmt = db_documents.documents_query(user, doc_type, product_id, created_by_id, date_from, date_to, q)
    return paginate(db, stmt)


@router.get("/{pk}", response_model=DocumentOut)
def get_document(pk: int, db: Session = Depends(get_pg_db), user: User = Depends(get_any_role)):
    return db_documents.get_document(db, pk, user)


# --------------------------------------------------------------------- #
# Write. Each request carries request_id (UUID) — safe to retry.
# --------------------------------------------------------------------- #


@router.post("/receipts", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def create_receipt(
    data: ReceiptCreate,
    response: Response,
    db: Session = Depends(get_pg_db),
    user: User = Depends(get_admin_or_warehouse),
):
    return _respond(db, response, receipt.create_receipt(db, data, user))


@router.post("/productions", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def create_production(
    data: ProductionCreate,
    response: Response,
    db: Session = Depends(get_pg_db),
    user: User = Depends(get_admin_or_operator),
):
    """
    409 INSUFFICIENT_STOCK  -> data: requested, max_possible, limiting, shortages[]
    409 RECIPE_VERSION_CHANGED -> data: recipe_version_id, version, lines[]
    """
    return _respond(db, response, production.create_production(db, data, user))


@router.post("/adjustments", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def create_adjustment(
    data: AdjustmentCreate,
    response: Response,
    db: Session = Depends(get_pg_db),
    user: User = Depends(get_admin_or_warehouse),
):
    """409 STOCK_CHANGED -> data: expected_qty, current_qty, new_diff, last_document.
    To confirm the new difference, send again with expected_qty = current_qty and a NEW request_id."""
    return _respond(db, response, adjustment.create_adjustment(db, data, user))


@router.post("/scraps", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def create_scrap(
    data: ScrapCreate,
    response: Response,
    db: Session = Depends(get_pg_db),
    user: User = Depends(get_any_role),
):
    """Operator: finished products only (checked on the server)."""
    return _respond(db, response, scrap.create_scrap(db, data, user))


@router.post("/{pk}/reverse", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def reverse_document(
    pk: int,
    data: ReversalCreate,
    response: Response,
    db: Session = Depends(get_pg_db),
    admin: User = Depends(get_current_admin),
):
    """409 NEGATIVE_BALANCE -> data.lines[]: product, current, delta, would_be."""
    return _respond(db, response, reversal.reverse_document(db, pk, data, admin))