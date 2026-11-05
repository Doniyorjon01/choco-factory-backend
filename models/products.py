from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class ProductKind(StrEnum):
    RAW = "raw"  # xomashyo
    FINISHED = "finished"  # tayyor mahsulot


class ProductUnit(StrEnum):
    G = "g"
    PCS = "pcs"


CODE_PREFIX = {ProductKind.RAW: "XA", ProductKind.FINISHED: "TM"}


class Product(TimestampMixin, Base):
    """
    Xomashyo ham, tayyor mahsulot ham shu jadvalda, `kind` bilan ajratiladi.

    Miqdorlar BIGINT: gramm bilan int (2,1 mlrd) atigi 2,1 tonnaga yetadi,
    real omborda bu chegara tez tugaydi.
    `kind`, `unit` va `code` yaratilgandan keyin o'zgarmaydi — tarixdagi
    jurnal qatorlarining ma'nosi shularga bog'liq.
    """

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name_uz: Mapped[str] = mapped_column(String(150), nullable=False)
    name_ru: Mapped[str] = mapped_column(String(150), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    unit: Mapped[str] = mapped_column(String(4), nullable=False)
    min_qty: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    target_qty: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    stock: Mapped["StockBalance"] = relationship(back_populates="product", uselist=False, lazy="joined")

    __table_args__ = (
        # recipe_* jadvallaridagi kompozit FK uchun: "bu id xomashyo" degan
        # shartni bazaning o'zi kafolatlaydi
        UniqueConstraint("id", "kind", name="uq_products_id_kind"),
        CheckConstraint("kind IN ('raw', 'finished')", name="kind_valid"),
        CheckConstraint("unit IN ('g', 'pcs')", name="unit_valid"),
        CheckConstraint("kind = 'raw' OR unit = 'pcs'", name="finished_in_pcs"),
        CheckConstraint(
            "(kind = 'raw' AND code ~ '^XA-[0-9]{3,}$') OR (kind = 'finished' AND code ~ '^TM-[0-9]{3,}$')",
            name="code_format",
        ),
        CheckConstraint("min_qty >= 0", name="min_qty_nonnegative"),
        CheckConstraint("target_qty >= min_qty", name="target_gte_min"),
        CheckConstraint("is_archived = (archived_at IS NOT NULL)", name="archived_at_consistent"),
        CheckConstraint("length(trim(name_uz)) > 0 AND length(trim(name_ru)) > 0", name="names_not_blank"),
        Index("uq_products_name_uz_lower", func.lower(name_uz), unique=True),
        Index("uq_products_name_ru_lower", func.lower(name_ru), unique=True),
        Index("ix_products_kind_archived", "kind", "is_archived"),
    )


class StockBalance(Base):
    """
    Joriy qoldiq — tez o'qish uchun. Haqiqat manbai ledger_entries:
    har bir mahsulot uchun SUM(qty_delta) = stock_balance.qty.
    Faqat hujjat tranzaksiyasi ichida, jurnal bilan birga o'zgaradi.
    """

    __tablename__ = "stock_balance"

    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), primary_key=True)
    qty: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    product: Mapped[Product] = relationship(back_populates="stock")

    __table_args__ = (
        # Oxirgi himoya chizig'i: kodda xato bo'lsa ham qoldiq manfiy bo'lmaydi
        CheckConstraint("qty >= 0", name="qty_nonnegative"),
    )
