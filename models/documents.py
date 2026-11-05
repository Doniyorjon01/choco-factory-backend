import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .products import Product
from .recipes import RecipeVersion
from .users import User


class DocumentType(StrEnum):
    RECEIPT = "receipt"  # KRM — kirim
    PRODUCTION = "production"  # PRD — ishlab chiqarish
    ADJUSTMENT = "adjustment"  # TZT — tuzatish (inventarizatsiya)
    SCRAP = "scrap"  # BRK — brak
    REVERSAL = "reversal"  # STR — storno


DOC_PREFIX: dict[DocumentType, str] = {
    DocumentType.RECEIPT: "KRM",
    DocumentType.PRODUCTION: "PRD",
    DocumentType.ADJUSTMENT: "TZT",
    DocumentType.SCRAP: "BRK",
    DocumentType.REVERSAL: "STR",
}


class Document(Base):
    """
    Ombordagi har bir o'zgarishning sababi. Hujjat va uning jurnal qatorlari
    hech qachon o'zgartirilmaydi va o'chirilmaydi (bazadagi trigger) —
    xato faqat storno (teskari hujjat) bilan tuzatiladi.

    `quantity` ma'nosi turga bog'liq: PRD — chiqarilgan dona, TZT — haqiqiy
    sanalgan miqdor, BRK — brak miqdori. KRM va STR da bo'sh.
    """

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    doc_type: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    # Klient yuboradigan idempotentlik kaliti va so'rov tanasining xeshi:
    # bir xil kalit + boshqa ma'lumot = IDEMPOTENCY_CONFLICT
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, unique=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    product_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("products.id"))
    quantity: Mapped[int | None] = mapped_column(BigInteger)
    recipe_version_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("recipe_versions.id"))

    reason: Mapped[str | None] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(String(1000))
    reverses_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("documents.id"), unique=True)

    supplier_name: Mapped[str | None] = mapped_column(String(200))
    supplier_doc_no: Mapped[str | None] = mapped_column(String(64))
    supplier_doc_date: Mapped[date | None] = mapped_column(Date)

    created_by: Mapped[User] = relationship(lazy="joined")
    product: Mapped[Product | None] = relationship(lazy="joined")
    entries: Mapped[list["LedgerEntry"]] = relationship(
        back_populates="document", order_by="LedgerEntry.id", lazy="selectin"
    )
    # Only id/version are read from these, so they load lazily ("raise" in list queries).
    recipe_version: Mapped[RecipeVersion | None] = relationship(viewonly=True, lazy="select")
    snapshot: Mapped[list["ProductionRecipeSnapshot"]] = relationship(
        viewonly=True, order_by="ProductionRecipeSnapshot.raw_product_id", lazy="selectin"
    )
    # Reversal links in both directions: STR -> original and original -> STR.
    reverses: Mapped["Document | None"] = relationship(
        remote_side="Document.id",
        foreign_keys="Document.reverses_id",
        back_populates="reversed_by",
        viewonly=True,
        lazy="select",
    )
    reversed_by: Mapped["Document | None"] = relationship(
        foreign_keys="Document.reverses_id",
        back_populates="reverses",
        uselist=False,
        viewonly=True,
        lazy="select",
    )

    __table_args__ = (
        CheckConstraint(
            "doc_type IN ('receipt', 'production', 'adjustment', 'scrap', 'reversal')", name="doc_type_valid"
        ),
        CheckConstraint("(doc_type = 'reversal') = (reverses_id IS NOT NULL)", name="reversal_has_target"),
        CheckConstraint(
            "doc_type <> 'production' OR (product_id IS NOT NULL AND quantity > 0 AND recipe_version_id IS NOT NULL)",
            name="production_fields",
        ),
        CheckConstraint(
            "doc_type NOT IN ('adjustment', 'scrap') OR (product_id IS NOT NULL AND quantity IS NOT NULL)",
            name="single_product_fields",
        ),
        CheckConstraint("quantity IS NULL OR quantity >= 0", name="quantity_nonnegative"),
        CheckConstraint(
            "doc_type NOT IN ('adjustment', 'scrap', 'reversal') OR reason IS NOT NULL", name="reason_required"
        ),
        CheckConstraint(
            "doc_type = 'receipt' OR (supplier_name IS NULL AND supplier_doc_no IS NULL AND supplier_doc_date IS NULL)",
            name="supplier_only_on_receipt",
        ),
        Index("ix_documents_type_created", "doc_type", "created_at"),
        Index("ix_documents_created_at", "created_at"),
        Index("ix_documents_created_by_created", "created_by_id", "created_at"),
        Index("ix_documents_product_id", "product_id"),
    )


class ProductionRecipeSnapshot(Base):
    """Ishlab chiqarish paytidagi retsept tarkibi — hujjat bilan birga muhrlanadi."""

    __tablename__ = "production_recipe_snapshot"

    document_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("documents.id"), primary_key=True)
    raw_product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), primary_key=True)
    qty_per_unit: Mapped[int] = mapped_column(BigInteger, nullable=False)

    raw_product: Mapped[Product] = relationship(lazy="joined")

    __table_args__ = (CheckConstraint("qty_per_unit > 0", name="qty_per_unit_positive"),)


class LedgerEntry(Base):
    """
    Harakatlar jurnali — yagona haqiqat manbai. Faqat INSERT.
    `qty_after` — shu harakatdan keyingi qoldiq (qator qulflangan holda yoziladi,
    shuning uchun mahsulot bo'yicha zanjir doim izchil).
    """

    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    document_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("documents.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False)
    qty_delta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    qty_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document: Mapped[Document] = relationship(back_populates="entries")
    product: Mapped[Product] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("document_id", "product_id", name="uq_ledger_entries_document_product"),
        CheckConstraint("qty_delta <> 0", name="qty_delta_nonzero"),
        CheckConstraint("qty_after >= 0", name="qty_after_nonnegative"),
        Index("ix_ledger_entries_product_created", "product_id", "created_at"),
    )


class DocCounter(Base):
    """
    Hujjat raqamlari hisoblagichi (uzluksiz: PRD-0142 dan keyin albatta PRD-0143).
    Qator hujjat tranzaksiyasi ichida qulflanadi; rollback bo'lsa raqam ham qaytadi.
    """

    __tablename__ = "doc_counters"

    doc_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (CheckConstraint("last_number >= 0", name="last_number_nonnegative"),)