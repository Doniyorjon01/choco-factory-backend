from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .products import Product
from .users import User


class RecipeStatus(StrEnum):
    DRAFT = "draft"  # qoralama — tahrirlanadi
    ACTIVE = "active"  # faol — ishlab chiqarish shu bo'yicha, tahrirlanmaydi
    ARCHIVED = "archived"  # avval faol bo'lgan, tarix uchun saqlanadi


class RecipeVersion(Base):
    """
    Retsept versiyasi: 1 dona tayyor mahsulot uchun xomashyo normalari.

    Invariantlar (bazada):
    - mahsulotda bittadan ortiq faol va bittadan ortiq qoralama yo'q;
    - faol/arxiv versiyaning tarkibi o'zgarmaydi va versiya o'chirilmaydi (trigger);
    - mahsulot albatta tayyor mahsulot (kompozit FK).
    """

    __tablename__ = "recipe_versions"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    product_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    product_kind: Mapped[str] = mapped_column(
        String(10), nullable=False, default="finished", server_default=text("'finished'")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default=RecipeStatus.DRAFT)
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_by_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))

    product: Mapped[Product] = relationship(viewonly=True, lazy="joined")
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id], viewonly=True, lazy="joined")
    activated_by: Mapped[User | None] = relationship(foreign_keys=[activated_by_id], viewonly=True, lazy="joined")
    lines: Mapped[list["RecipeLine"]] = relationship(
        back_populates="recipe_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RecipeLine.id",
        lazy="selectin",
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["product_id", "product_kind"],
            ["products.id", "products.kind"],
            name="fk_recipe_versions_product_finished",
        ),
        UniqueConstraint("product_id", "version", name="uq_recipe_versions_product_id_version"),
        CheckConstraint("product_kind = 'finished'", name="product_is_finished"),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint("status IN ('draft', 'active', 'archived')", name="status_valid"),
        CheckConstraint(
            "(status = 'draft') = (activated_at IS NULL AND activated_by_id IS NULL)",
            name="activation_consistent",
        ),
        Index(
            "uq_recipe_versions_one_active",
            "product_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "uq_recipe_versions_one_draft",
            "product_id",
            unique=True,
            postgresql_where=text("status = 'draft'"),
        ),
    )


class RecipeLine(Base):
    __tablename__ = "recipe_lines"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    recipe_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("recipe_versions.id", ondelete="CASCADE"), nullable=False
    )
    raw_product_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    raw_kind: Mapped[str] = mapped_column(String(10), nullable=False, default="raw", server_default=text("'raw'"))
    # 1 dona tayyor mahsulot uchun, xomashyoning o'z birligida (g yoki dona)
    qty_per_unit: Mapped[int] = mapped_column(BigInteger, nullable=False)

    recipe_version: Mapped[RecipeVersion] = relationship(back_populates="lines")
    raw_product: Mapped[Product] = relationship(viewonly=True, lazy="joined")

    __table_args__ = (
        ForeignKeyConstraint(
            ["raw_product_id", "raw_kind"],
            ["products.id", "products.kind"],
            name="fk_recipe_lines_raw_product",
        ),
        UniqueConstraint("recipe_version_id", "raw_product_id", name="uq_recipe_lines_version_raw"),
        CheckConstraint("raw_kind = 'raw'", name="product_is_raw"),
        CheckConstraint("qty_per_unit > 0", name="qty_per_unit_positive"),
    )
