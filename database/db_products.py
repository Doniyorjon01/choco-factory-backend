import re

from fastapi import status
from sqlalchemy import Select, func, or_, select, text
from sqlalchemy.orm import Session

from errors import generate_error
from models import CODE_PREFIX, Product, ProductKind, ProductUnit, RecipeLine, RecipeStatus, RecipeVersion, StockBalance
from schemas.products import ProductCreate, ProductUpdate
from translations import Msg
from utils.timeutils import utcnow

_CODE_RE = re.compile(r"^(XA|TM)-(\d{3,})$")


def get_product(db: Session, pk: int, *, for_update: bool = False) -> Product:
    stmt = select(Product).where(Product.id == pk)
    if for_update:
        stmt = stmt.with_for_update(of=Product).execution_options(populate_existing=True)
    product = db.scalars(stmt).first()
    if product is None:
        raise generate_error(Msg.PRODUCT_NOT_FOUND, status.HTTP_404_NOT_FOUND)
    return product


def products_query(
    kind: str | None = None, archived: bool | None = False, q: str | None = None
) -> Select[tuple[Product]]:
    stmt = select(Product)
    if kind:
        stmt = stmt.where(Product.kind == kind)
    if archived is not None:
        stmt = stmt.where(Product.is_archived.is_(archived))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Product.code.ilike(like), Product.name_uz.ilike(like), Product.name_ru.ilike(like)))
    # Avval xomashyo, keyin tayyor mahsulot; ichida kod bo'yicha
    return stmt.order_by(Product.kind.desc(), Product.code)


def _next_code(db: Session, kind: ProductKind) -> str:
    prefix = CODE_PREFIX[kind]
    # Ikki admin bir vaqtda mahsulot qo'shsa, bir xil kod olmasin
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"product_code:{prefix}"})
    codes = db.scalars(select(Product.code).where(Product.code.like(f"{prefix}-%"))).all()
    last = max((int(m.group(2)) for c in codes if (m := _CODE_RE.match(c))), default=0)
    return f"{prefix}-{last + 1:03d}"


def _ensure_names_free(db: Session, name_uz: str, name_ru: str, exclude_id: int | None = None) -> None:
    stmt = select(Product.id).where(
        or_(func.lower(Product.name_uz) == name_uz.lower(), func.lower(Product.name_ru) == name_ru.lower())
    )
    if exclude_id is not None:
        stmt = stmt.where(Product.id != exclude_id)
    if db.scalar(stmt.limit(1)):
        raise generate_error(Msg.PRODUCT_NAME_TAKEN, status.HTTP_409_CONFLICT)


def create_product(db: Session, data: ProductCreate) -> Product:
    kind = ProductKind(data.kind)
    # Tayyor mahsulot doim dona; xomashyo uchun sukut — gramm
    unit = ProductUnit.PCS if kind == ProductKind.FINISHED else ProductUnit(data.unit or ProductUnit.G)

    if data.target_qty < data.min_qty:
        raise generate_error(Msg.TARGET_BELOW_MIN, status.HTTP_422_UNPROCESSABLE_CONTENT)
    _ensure_names_free(db, data.name_uz, data.name_ru)

    prefix = CODE_PREFIX[kind]
    if data.code:
        m = _CODE_RE.match(data.code)
        if not m or m.group(1) != prefix:
            raise generate_error(
                Msg.PRODUCT_CODE_PREFIX, status.HTTP_422_UNPROCESSABLE_CONTENT, params={"prefix": prefix}
            )
        if db.scalar(select(Product.id).where(Product.code == data.code)):
            raise generate_error(Msg.PRODUCT_CODE_TAKEN, status.HTTP_409_CONFLICT, params={"code": data.code})
        code = data.code
    else:
        code = _next_code(db, kind)

    product = Product(
        code=code,
        name_uz=data.name_uz,
        name_ru=data.name_ru,
        kind=kind,
        unit=unit,
        min_qty=data.min_qty,
        target_qty=data.target_qty,
    )
    db.add(product)
    db.flush()
    # Har bir mahsulotning qoldiq qatori boshidanoq bor — hujjatlar uni
    # FOR UPDATE bilan qulflay olishi uchun
    db.add(StockBalance(product_id=product.id, qty=0))
    db.commit()
    return get_product(db, product.id)


def update_product(db: Session, pk: int, data: ProductUpdate) -> Product:
    product = get_product(db, pk, for_update=True)
    changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}

    min_qty = changes.get("min_qty", product.min_qty)
    target_qty = changes.get("target_qty", product.target_qty)
    if target_qty < min_qty:
        raise generate_error(Msg.TARGET_BELOW_MIN, status.HTTP_422_UNPROCESSABLE_CONTENT)

    if "name_uz" in changes or "name_ru" in changes:
        _ensure_names_free(
            db, changes.get("name_uz", product.name_uz), changes.get("name_ru", product.name_ru), exclude_id=pk
        )

    for key, value in changes.items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return product


def active_recipes_using(db: Session, raw_product_id: int) -> list[Product]:
    """Shu xomashyo ishlatiladigan faol retseptlarning tayyor mahsulotlari."""
    return list(
        db.scalars(
            select(Product)
            .join(RecipeVersion, RecipeVersion.product_id == Product.id)
            .join(RecipeLine, RecipeLine.recipe_version_id == RecipeVersion.id)
            .where(RecipeLine.raw_product_id == raw_product_id, RecipeVersion.status == RecipeStatus.ACTIVE)
            .order_by(Product.code)
        ).unique()
    )


def archive_product(db: Session, pk: int) -> Product:
    product = get_product(db, pk, for_update=True)
    if product.is_archived:
        return product

    # Qoldiq qatorini ham qulflaymiz — shu orada hujjat yozilib, qoldiq paydo bo'lmasin
    qty = db.scalar(select(StockBalance.qty).where(StockBalance.product_id == pk).with_for_update())
    if qty:
        unit = "g" if product.unit == ProductUnit.G else "dona"
        raise generate_error(Msg.PRODUCT_HAS_STOCK, status.HTTP_409_CONFLICT, params={"qty": f"{qty} {unit}"})

    if product.kind == ProductKind.RAW:
        users = active_recipes_using(db, pk)
        if users:
            raise generate_error(
                Msg.PRODUCT_USED_IN_ACTIVE_RECIPE,
                status.HTTP_409_CONFLICT,
                params={"products": ", ".join(f"{p.code} {p.name_uz}" for p in users)},
                data={
                    "products": [
                        {"id": p.id, "code": p.code, "name_uz": p.name_uz, "name_ru": p.name_ru} for p in users
                    ]
                },
            )

    product.is_archived = True
    product.archived_at = utcnow()
    db.commit()
    db.refresh(product)
    return product


def unarchive_product(db: Session, pk: int) -> Product:
    product = get_product(db, pk, for_update=True)
    if product.is_archived:
        product.is_archived = False
        product.archived_at = None
        db.commit()
        db.refresh(product)
    return product
