from datetime import datetime
from typing import Literal

from pydantic import AliasPath, Field, field_validator

from .common import ORMModel, ProductName, StrictInput

Kind = Literal["raw", "finished"]
Unit = Literal["g", "pcs"]

# 1 000 000 kg — real ombor uchun yetarli yuqori chegara (xato kiritishdan himoya)
MAX_QTY = 1_000_000_000


class ProductOut(ORMModel):
    id: int
    code: str
    name_uz: str
    name_ru: str
    kind: Kind
    unit: Unit
    min_qty: int
    target_qty: int
    is_archived: bool
    archived_at: datetime | None
    stock_qty: int = Field(validation_alias=AliasPath("stock", "qty"))
    created_at: datetime
    updated_at: datetime


class ProductShort(ORMModel):
    """Boshqa javoblar ichida ishlatiladi (retsept qatori, jurnal)."""

    id: int
    code: str
    name_uz: str
    name_ru: str
    kind: Kind
    unit: Unit
    is_archived: bool


class ProductCreate(StrictInput):
    # Berilmasa, keyingi bo'sh kod avtomatik olinadi: XA-006, TM-004
    code: str | None = Field(default=None, max_length=20)
    name_uz: ProductName
    name_ru: ProductName
    kind: Kind
    # Tayyor mahsulot doim dona; xomashyo uchun sukut — gramm
    unit: Unit | None = None
    min_qty: int = Field(default=0, ge=0, le=MAX_QTY)
    target_qty: int = Field(default=0, ge=0, le=MAX_QTY)

    @field_validator("code")
    @classmethod
    def _upper_code(cls, v: str | None) -> str | None:
        return v.strip().upper() if v else None


class ProductUpdate(StrictInput):
    """`kind`, `unit` va `code` o'zgarmaydi — jurnal tarixining ma'nosi shularga bog'liq."""

    name_uz: ProductName | None = None
    name_ru: ProductName | None = None
    min_qty: int | None = Field(default=None, ge=0, le=MAX_QTY)
    target_qty: int | None = Field(default=None, ge=0, le=MAX_QTY)
