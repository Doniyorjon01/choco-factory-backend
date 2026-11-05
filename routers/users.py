from typing import Literal

from fastapi import APIRouter, Depends, status
from fastapi_pagination.ext.sqlalchemy import paginate
from sqlalchemy.orm import Session

from auth.oauth2 import get_current_admin
from database import db_users
from database.config import get_pg_db
from models import User
from schemas.users import PasswordReset, UserCreate, UserOut, UserUpdate
from utils.pagination import CustomPage

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=CustomPage[UserOut])
def get_users(
    q: str | None = None,
    role: Literal["admin", "warehouse", "operator"] | None = None,
    is_active: bool | None = None,
    db: Session = Depends(get_pg_db),
    admin: User = Depends(get_current_admin),
):
    return paginate(db, db_users.users_query(q, role, is_active))


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, db: Session = Depends(get_pg_db), admin: User = Depends(get_current_admin)):
    return db_users.create_user(db, data, created_by=admin)


@router.get("/{pk}", response_model=UserOut)
def get_user(pk: int, db: Session = Depends(get_pg_db), admin: User = Depends(get_current_admin)):
    return db_users.get_user(db, pk)


@router.patch("/{pk}", response_model=UserOut)
def update_user(pk: int, data: UserUpdate, db: Session = Depends(get_pg_db), admin: User = Depends(get_current_admin)):
    """Ism, rol, til, bloklash (is_active=false). Foydalanuvchi o'chirilmaydi — jurnalda nomi qoladi."""
    return db_users.update_user(db, pk, data, actor=admin)


@router.post("/{pk}/reset-password", response_model=UserOut)
def reset_password(
    pk: int, data: PasswordReset, db: Session = Depends(get_pg_db), admin: User = Depends(get_current_admin)
):
    """Vaqtinchalik parol: qulf ochiladi, keyingi kirishda almashtirish majburiy."""
    return db_users.reset_password(db, pk, data.password)
