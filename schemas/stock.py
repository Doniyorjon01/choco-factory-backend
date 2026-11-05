from typing import Literal

from .common import ORMModel
from .products import ProductShort

Level = Literal["ok", "low", "out"]


class StockItemOut(ORMModel):
    product_id: int
    code: str
    name_uz: str
    name_ru: str
    kind: Literal["raw", "finished"]
    unit: Literal["g", "pcs"]
    qty: int
    min_qty: int
    target_qty: int
    # out — 0; low — minimal qoldiqdan kam; ok — yetarli
    level: Level
    # Xomashyo: oxirgi 7 kunda ishlab chiqarishga sarflangan (aniq birlikda)
    consumed_7d: int | None
    # Xomashyo: qoldiq / o'rtacha kunlik sarf (pastga yaxlitlangan); sarf bo'lmasa — null
    days_left: int | None


class CapacityLineOut(ORMModel):
    raw_product: ProductShort
    qty_per_unit: int
    stock_qty: int
    # Faqat shu xomashyo bo'yicha nechta chiqadi
    max_by_this: int


class CapacityOut(ORMModel):
    """Har bir tayyor mahsulot ALOHIDA hisoblangan — umumiy xomashyodan.
    Ikkalasini birga maksimal miqdorda chiqarib bo'lmaydi."""

    product: ProductShort
    recipe_version_id: int
    recipe_version: int
    max_possible: int
    limiting: ProductShort | None
    lines: list[CapacityLineOut]
