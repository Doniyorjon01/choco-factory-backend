from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth.oauth2 import get_any_role
from database.config import get_pg_db
from models import User
from schemas.stock import CapacityOut, StockItemOut
from services import stock as stock_service

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("", response_model=list[StockItemOut])
def get_stock(
    kind: Literal["raw", "finished"] | None = None,
    level: Literal["ok", "low", "out"] | None = None,
    q: str | None = None,
    db: Session = Depends(get_pg_db),
    user: User = Depends(get_any_role),
):
    """Faol mahsulotlar qoldig'i. Sahifalash yo'q: faol mahsulotlar soni o'nlab,
    ekran esa hammasini bitta ro'yxatda ko'rsatadi."""
    return stock_service.stock_list(db, kind, level, q)


@router.get("/capacity", response_model=list[CapacityOut])
def get_capacity(product_id: int | None = None, db: Session = Depends(get_pg_db), user: User = Depends(get_any_role)):
    """Har bir tayyor mahsulotdan hozirgi qoldiq bilan maksimal nechta chiqadi."""
    return stock_service.capacity(db, product_id)
