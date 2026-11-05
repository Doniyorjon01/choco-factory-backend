from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi_pagination.ext.sqlalchemy import paginate
from sqlalchemy.orm import Session

from auth.oauth2 import get_admin_or_warehouse
from database import db_documents
from database.config import get_pg_db
from models import User
from schemas.documents import LedgerLineOut
from utils.pagination import CustomPage

router = APIRouter(prefix="/ledger", tags=["ledger"])


@router.get("", response_model=CustomPage[LedgerLineOut])
def get_ledger(
    product_id: int | None = None,
    doc_type: Literal["receipt", "production", "adjustment", "scrap", "reversal"] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_pg_db),
    user: User = Depends(get_admin_or_warehouse),
):
    """Movement lines ("Lines" view of the journal), newest first.
    With product_id this is the product card: every move with stock after it."""
    return paginate(db, db_documents.ledger_query(product_id, doc_type, date_from, date_to))