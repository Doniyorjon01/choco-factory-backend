"""
Production (PRD): use raw materials by the recipe, add finished products.

    1 Dark chocolate = 50 g cocoa + 20 g sugar
    produce 40  ->  cocoa -2000 g, sugar -800 g, Dark chocolate +40

Everything happens in one transaction: either all rows change, or none.
Two operators pressing "Produce" at the same time cannot push stock below
zero: stock rows are locked, so the second request waits and then checks
the NEW stock.
"""

from datetime import datetime

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from errors import generate_error
from models import (
    Document,
    DocumentType,
    Product,
    ProductionRecipeSnapshot,
    ProductKind,
    RecipeStatus,
    RecipeVersion,
    User,
)
from schemas.documents import ProductionCreate
from services.documents import find_replay, load_products, lock_stock, post_document, product_ref, request_hash
from translations import Msg


def _active_version_locked(db: Session, product_id: int) -> RecipeVersion | None:
    # FOR SHARE: the admin cannot switch the active version until we commit.
    return (
        db.scalars(
            select(RecipeVersion)
            .where(RecipeVersion.product_id == product_id, RecipeVersion.status == RecipeStatus.ACTIVE)
            .with_for_update(of=RecipeVersion, read=True)
            .execution_options(populate_existing=True)
        )
        .unique()
        .first()
    )


def create_production(
    db: Session, data: ProductionCreate, user: User, *, created_at: datetime | None = None
) -> tuple[Document, bool]:
    """Returns (document, replayed). replayed=True means the same request was already done."""
    req_hash = request_hash(DocumentType.PRODUCTION, user, data)
    existing = find_replay(db, data.request_id, req_hash)
    if existing:
        return existing, True

    product = db.get(Product, data.product_id)
    if product is None:
        raise generate_error(Msg.PRODUCT_NOT_FOUND, status.HTTP_404_NOT_FOUND)
    if product.kind != ProductKind.FINISHED:
        raise generate_error(Msg.PRODUCT_NOT_FINISHED, status.HTTP_422_UNPROCESSABLE_CONTENT)

    active = _active_version_locked(db, product.id)
    if active is None:
        raise generate_error(Msg.NO_ACTIVE_RECIPE, status.HTTP_409_CONFLICT)

    # The operator saw another version (the admin activated a new one meanwhile).
    # Nothing is written; we send the new recipe so the screen can recalculate.
    if active.id != data.recipe_version_id:
        seen = db.get(RecipeVersion, data.recipe_version_id)
        seen_number = seen.version if seen is not None and seen.product_id == product.id else "?"
        raise generate_error(
            Msg.RECIPE_VERSION_CHANGED,
            status.HTTP_409_CONFLICT,
            params={"old": seen_number, "new": active.version},
            data={
                "recipe_version_id": active.id,
                "version": active.version,
                "lines": [
                    {"raw_product": product_ref(line.raw_product), "qty_per_unit": line.qty_per_unit}
                    for line in active.lines
                ],
            },
        )

    need = {line.raw_product_id: line.qty_per_unit * data.qty for line in active.lines}
    moves = {raw_id: -qty for raw_id, qty in need.items()}
    moves[product.id] = data.qty

    stock = lock_stock(db, moves.keys())
    products = load_products(db, moves.keys())

    # Check with the real, locked stock. If anything is short, report ALL short
    # lines with exact grams and the maximum that can be produced right now.
    shortages = [
        {
            "product": product_ref(products[raw_id]),
            "need": qty,
            "have": stock[raw_id],
            "missing": qty - stock[raw_id],
        }
        for raw_id, qty in sorted(need.items())
        if qty > stock[raw_id]
    ]
    if shortages:
        per_unit = {line.raw_product_id: line.qty_per_unit for line in active.lines}
        limits = {raw_id: stock[raw_id] // per_unit[raw_id] for raw_id in per_unit}
        limiting_id = min(limits, key=lambda raw_id: (limits[raw_id], raw_id))
        raise generate_error(
            Msg.INSUFFICIENT_STOCK,
            status.HTTP_409_CONFLICT,
            data={
                "requested": data.qty,
                "max_possible": limits[limiting_id],
                "limiting": product_ref(products[limiting_id]),
                "shortages": shortages,
            },
        )

    document = post_document(
        db,
        doc_type=DocumentType.PRODUCTION,
        user=user,
        request_id=data.request_id,
        req_hash=req_hash,
        moves=moves,
        stock=stock,
        created_at=created_at,
        product_id=product.id,
        quantity=data.qty,
        recipe_version_id=active.id,
        note=data.note or None,
    )
    # Freeze the recipe inside the document. Later recipe changes do not touch it.
    db.add_all(
        ProductionRecipeSnapshot(
            document_id=document.id, raw_product_id=line.raw_product_id, qty_per_unit=line.qty_per_unit
        )
        for line in active.lines
    )
    db.commit()
    return document, False