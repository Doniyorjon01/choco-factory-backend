from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Identity, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class UserRole(StrEnum):
    ADMIN = "admin"
    WAREHOUSE = "warehouse"  # omborchi
    OPERATOR = "operator"  # ishlab chiqarish operatori


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    # Doim kichik harfda saqlanadi — "Admin" va "admin" bitta login
    login: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # Oshirilsa, foydalanuvchining barcha eski tokenlari darhol yaroqsiz bo'ladi
    # (bloklash, rol o'zgarishi, parol almashtirish yoki tiklash).
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lang: Mapped[str] = mapped_column(String(2), nullable=False, default="uz", server_default=text("'uz'"))
    created_by_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))

    __table_args__ = (
        CheckConstraint("login = lower(login)", name="login_lowercase"),
        CheckConstraint("role IN ('admin', 'warehouse', 'operator')", name="role_valid"),
        CheckConstraint("lang IN ('uz', 'ru')", name="lang_valid"),
        CheckConstraint("failed_login_count >= 0", name="failed_login_count_nonnegative"),
    )
