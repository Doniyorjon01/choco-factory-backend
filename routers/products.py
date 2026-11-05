from typing import Literal

from fastapi import APIRouter, Depends, status
from fastapi_pagination.ext.sqlalchemy import paginate
from sqlalchemy.orm import Session

from auth.oauth2 import get_admin_or_warehouse, get_current_admin
from database import db_products
from database.config import get_pg_db
from models import User
from schemas.products import ProductCreate, ProductOut, ProductUpdate
from utils.pagination import CustomPage

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=CustomPage[ProductOut])
def get_products(
    kind: Literal["raw", "finished"] | None = None,
    state: Literal["active", "archived", "all"] = "active",
    q: str | None = None,
    db: Session = Depends(get_pg_db),
    user: User = Depends(get_admin_or_warehouse),
):
    """`state`: active — faollar (sukut), archived — arxiv, all — hammasi."""
    archived = {"active": False, "archived": True, "all": None}[state]
    return paginate(db, db_products.products_query(kind, archived, q))


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(data: ProductCreate, db: Session = Depends(get_pg_db), admin: User = Depends(get_current_admin)):
    return db_products.create_product(db, data)


@router.get("/{pk}", response_model=ProductOut)
def get_product(pk: int, db: Session = Depends(get_pg_db), user: User = Depends(get_admin_or_warehouse)):
    return db_products.get_product(db, pk)


@router.patch("/{pk}", response_model=ProductOut)
def update_product(
    pk: int, data: ProductUpdate, db: Session = Depends(get_pg_db), admin: User = Depends(get_current_admin)
):
    return db_products.update_product(db, pk, data)


@router.post("/{pk}/archive", response_model=ProductOut)
def archive_product(pk: int, db: Session = Depends(get_pg_db), admin: User = Depends(get_current_admin)):
    """O'chirish yo'q — faqat arxiv. Qoldig'i bor yoki faol retseptda ishlatilayotgan mahsulot arxivlanmaydi."""
    return db_products.archive_product(db, pk)


@router.post("/{pk}/unarchive", response_model=ProductOut)
def unarchive_product(pk: int, db: Session = Depends(get_pg_db), admin: User = Depends(get_current_admin)):
    return db_products.unarchive_product(db, pk)
