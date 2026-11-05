from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from .common import ORMModel, StrictInput
from .products import ProductShort

RecipeNote = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class UserShort(ORMModel):
    id: int
    full_name: str


class RecipeLineIn(StrictInput):
    raw_product_id: int = Field(gt=0)
    # 1 dona tayyor mahsulot uchun, xomashyoning o'z birligida (butun gramm yoki dona)
    qty_per_unit: int = Field(gt=0, le=10_000_000)


class RecipeDraftCreate(StrictInput):
    # None — faol versiya tarkibi nusxalanadi (bo'lmasa, bo'sh qoralama)
    lines: list[RecipeLineIn] | None = Field(default=None, max_length=50)
    note: RecipeNote | None = None


class RecipeDraftUpdate(StrictInput):
    lines: list[RecipeLineIn] | None = Field(default=None, max_length=50)
    note: RecipeNote | None = None


class RecipeLineOut(ORMModel):
    id: int
    raw_product: ProductShort
    qty_per_unit: int


class RecipeVersionOut(ORMModel):
    id: int
    product_id: int
    version: int
    status: Literal["draft", "active", "archived"]
    note: str | None
    created_at: datetime
    created_by: UserShort
    activated_at: datetime | None
    activated_by: UserShort | None
    lines: list[RecipeLineOut]


class RecipeSummaryOut(ORMModel):
    """Retseptlar ro'yxati: har bir tayyor mahsulot, faol versiyasi va qoralamasi."""

    product: ProductShort
    active: RecipeVersionOut | None
    draft_version: int | None
    draft_id: int | None
