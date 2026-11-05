import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from .common import ORMModel, StrictInput
from .products import ProductShort
from .recipes import UserShort

DocType = Literal["receipt", "production", "adjustment", "scrap", "reversal"]

# Upper limit for any single quantity. It only protects from typos
# (for example 5 000 000 000 g instead of 5 000 g).
MAX_QTY = 1_000_000_000
MAX_PCS = 1_000_000

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]

# Reason codes. The frontend shows labels from GET /documents/meta.
AdjustmentReason = Literal["inventory", "spill", "scale_error", "other"]
ScrapReason = Literal["wet", "bag_damaged", "dirty", "shape", "pack_damaged", "quality", "other"]

RAW_SCRAP_REASONS = {"wet", "bag_damaged", "dirty", "other"}
FINISHED_SCRAP_REASONS = {"shape", "pack_damaged", "quality", "other"}


# --------------------------------------------------------------------- #
# Input
# --------------------------------------------------------------------- #


class WriteRequest(StrictInput):
    # The client creates this UUID once per "button press" and sends the same
    # value again on retry. The server will not create a second document.
    request_id: uuid.UUID


class ReceiptLineIn(StrictInput):
    product_id: int = Field(gt=0)
    # Always whole grams (or pieces). The frontend converts kg -> g.
    qty: int = Field(gt=0, le=MAX_QTY)


class ReceiptCreate(WriteRequest):
    lines: list[ReceiptLineIn] = Field(min_length=1, max_length=50)
    supplier_name: ShortText | None = None
    supplier_doc_no: Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)] | None = None
    # Only for the record. The ledger always uses the server time.
    supplier_doc_date: date | None = None
    note: Note | None = None


class ProductionCreate(WriteRequest):
    product_id: int = Field(gt=0)
    qty: int = Field(gt=0, le=MAX_PCS)
    # The recipe version the operator was looking at (from GET /stock/capacity).
    recipe_version_id: int = Field(gt=0)
    note: Note | None = None


class AdjustmentCreate(WriteRequest):
    product_id: int = Field(gt=0)
    counted_qty: int = Field(ge=0, le=MAX_QTY)
    # The stock value the user saw on the screen when counting.
    expected_qty: int = Field(ge=0, le=MAX_QTY)
    reason: AdjustmentReason
    note: Note | None = None


class ScrapCreate(WriteRequest):
    product_id: int = Field(gt=0)
    qty: int = Field(gt=0, le=MAX_QTY)
    reason: ScrapReason
    note: Note | None = None


class ReversalCreate(WriteRequest):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]


# --------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------- #


class DocRef(ORMModel):
    id: int
    number: str


class RecipeRef(ORMModel):
    id: int
    version: int


class LedgerEntryOut(ORMModel):
    product: ProductShort
    qty_delta: int
    qty_after: int


class SnapshotLineOut(ORMModel):
    raw_product: ProductShort
    qty_per_unit: int


class DocumentOut(ORMModel):
    id: int
    number: str
    doc_type: DocType
    created_at: datetime
    created_by: UserShort
    request_id: uuid.UUID
    product: ProductShort | None
    quantity: int | None
    recipe_version: RecipeRef | None
    reason: str | None
    note: str | None
    supplier_name: str | None
    supplier_doc_no: str | None
    supplier_doc_date: date | None
    reverses: DocRef | None
    reversed_by: DocRef | None
    entries: list[LedgerEntryOut]
    snapshot: list[SnapshotLineOut]


class LedgerLineOut(ORMModel):
    id: int
    created_at: datetime
    document: "LedgerDocRef"
    product: ProductShort
    qty_delta: int
    qty_after: int


class LedgerDocRef(ORMModel):
    id: int
    number: str
    doc_type: DocType
    created_by: UserShort
    reason: str | None
    reversed_by: DocRef | None


LedgerLineOut.model_rebuild()


class ReasonOut(ORMModel):
    code: str
    uz: str
    ru: str


class DocumentsMetaOut(ORMModel):
    adjustment_reasons: list[ReasonOut]
    scrap_reasons_raw: list[ReasonOut]
    scrap_reasons_finished: list[ReasonOut]
    # Reasons that require a note
    note_required_for: list[str]