"""
Retsept versiyalari.

Qulflash tartibi (deadlock bo'lmasligi uchun hamma joyda bir xil):
    1) tayyor mahsulot qatori (products) — FOR UPDATE
    2) retsept versiyasi — FOR UPDATE
    3) xomashyo qatorlari (products) — FOR SHARE, id bo'yicha o'sish tartibida
"""

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from errors import generate_error
from models import Product, ProductKind, RecipeLine, RecipeStatus, RecipeVersion, User
from schemas.recipes import RecipeDraftCreate, RecipeDraftUpdate, RecipeLineIn
from translations import Msg
from utils.timeutils import utcnow


def get_version(db: Session, pk: int, *, for_update: bool = False) -> RecipeVersion:
    stmt = select(RecipeVersion).where(RecipeVersion.id == pk)
    if for_update:
        stmt = stmt.with_for_update(of=RecipeVersion).execution_options(populate_existing=True)
    version = db.scalars(stmt).unique().first()
    if version is None:
        raise generate_error(Msg.RECIPE_VERSION_NOT_FOUND, status.HTTP_404_NOT_FOUND)
    return version


def get_active_version(db: Session, product_id: int) -> RecipeVersion | None:
    return (
        db.scalars(
            select(RecipeVersion).where(
                RecipeVersion.product_id == product_id, RecipeVersion.status == RecipeStatus.ACTIVE
            )
        )
        .unique()
        .first()
    )


def _lock_finished_product(db: Session, product_id: int) -> Product:
    product = db.scalars(
        select(Product)
        .where(Product.id == product_id)
        .with_for_update(of=Product)
        .execution_options(populate_existing=True)
    ).first()
    if product is None:
        raise generate_error(Msg.PRODUCT_NOT_FOUND, status.HTTP_404_NOT_FOUND)
    if product.kind != ProductKind.FINISHED:
        raise generate_error(Msg.PRODUCT_NOT_FINISHED, status.HTTP_422_UNPROCESSABLE_CONTENT)
    if product.is_archived:
        raise generate_error(
            Msg.PRODUCT_ARCHIVED, status.HTTP_409_CONFLICT, params={"name": f"{product.code} {product.name_uz}"}
        )
    return product


def _validate_lines(db: Session, lines: list[RecipeLineIn]) -> None:
    """Takrorlanmaydi, hammasi mavjud, faol xomashyo. Xomashyo qatorlari FOR SHARE —
    shu orada kimdir ularni arxivlay olmaydi."""
    ids = [line.raw_product_id for line in lines]
    if len(ids) != len(set(ids)):
        raise generate_error(Msg.RECIPE_DUPLICATE_LINE, status.HTTP_422_UNPROCESSABLE_CONTENT)
    if not ids:
        return
    raws = {
        p.id: p
        for p in db.scalars(
            select(Product).where(Product.id.in_(ids)).order_by(Product.id).with_for_update(of=Product, read=True)
        )
    }
    for raw_id in ids:
        raw = raws.get(raw_id)
        if raw is None:
            raise generate_error(Msg.PRODUCT_NOT_FOUND, status.HTTP_404_NOT_FOUND, data={"product_id": raw_id})
        if raw.kind != ProductKind.RAW:
            raise generate_error(
                Msg.PRODUCT_NOT_RAW, status.HTTP_422_UNPROCESSABLE_CONTENT, data={"product_id": raw_id}
            )
        if raw.is_archived:
            raise generate_error(
                Msg.PRODUCT_ARCHIVED,
                status.HTTP_409_CONFLICT,
                params={"name": f"{raw.code} {raw.name_uz}"},
                data={"product_id": raw_id},
            )


def list_recipes(db: Session, include_archived: bool = False) -> list[dict]:
    stmt = select(Product).where(Product.kind == ProductKind.FINISHED)
    if not include_archived:
        stmt = stmt.where(Product.is_archived.is_(False))
    products = list(db.scalars(stmt.order_by(Product.code)))
    if not products:
        return []

    versions = db.scalars(
        select(RecipeVersion).where(
            RecipeVersion.product_id.in_([p.id for p in products]),
            RecipeVersion.status.in_([RecipeStatus.ACTIVE, RecipeStatus.DRAFT]),
        )
    ).unique()
    active: dict[int, RecipeVersion] = {}
    draft: dict[int, RecipeVersion] = {}
    for v in versions:
        (active if v.status == RecipeStatus.ACTIVE else draft)[v.product_id] = v

    return [
        {
            "product": p,
            "active": active.get(p.id),
            "draft_version": draft[p.id].version if p.id in draft else None,
            "draft_id": draft[p.id].id if p.id in draft else None,
        }
        for p in products
    ]


def versions_for_product(db: Session, product_id: int) -> list[RecipeVersion]:
    if db.get(Product, product_id) is None:
        raise generate_error(Msg.PRODUCT_NOT_FOUND, status.HTTP_404_NOT_FOUND)
    return list(
        db.scalars(
            select(RecipeVersion).where(RecipeVersion.product_id == product_id).order_by(RecipeVersion.version.desc())
        ).unique()
    )


def create_draft(db: Session, product_id: int, data: RecipeDraftCreate, user: User) -> RecipeVersion:
    _lock_finished_product(db, product_id)

    existing = db.scalars(
        select(RecipeVersion).where(RecipeVersion.product_id == product_id, RecipeVersion.status == RecipeStatus.DRAFT)
    ).first()
    if existing:
        raise generate_error(
            Msg.RECIPE_DRAFT_EXISTS,
            status.HTTP_409_CONFLICT,
            params={"version": existing.version},
            data={"draft_id": existing.id},
        )

    if data.lines is not None:
        lines = data.lines
    else:
        current = get_active_version(db, product_id)
        lines = (
            [RecipeLineIn(raw_product_id=line.raw_product_id, qty_per_unit=line.qty_per_unit) for line in current.lines]
            if current
            else []
        )
    _validate_lines(db, lines)

    last = db.scalar(select(func.max(RecipeVersion.version)).where(RecipeVersion.product_id == product_id)) or 0
    version = RecipeVersion(
        product_id=product_id,
        version=last + 1,
        status=RecipeStatus.DRAFT,
        note=data.note or None,
        created_by_id=user.id,
        lines=[RecipeLine(raw_product_id=line.raw_product_id, qty_per_unit=line.qty_per_unit) for line in lines],
    )
    db.add(version)
    db.commit()
    return get_version(db, version.id)


def update_draft(db: Session, pk: int, data: RecipeDraftUpdate) -> RecipeVersion:
    version = get_version(db, pk, for_update=True)
    if version.status != RecipeStatus.DRAFT:
        raise generate_error(Msg.RECIPE_NOT_DRAFT, status.HTTP_409_CONFLICT)

    changes = data.model_dump(exclude_unset=True)
    if "lines" in changes and data.lines is not None:
        _validate_lines(db, data.lines)
        version.lines.clear()
        db.flush()  # eski qatorlar unique cheklovga urilmasligi uchun avval o'chadi
        version.lines.extend(
            RecipeLine(raw_product_id=line.raw_product_id, qty_per_unit=line.qty_per_unit) for line in data.lines
        )
    if "note" in changes:
        version.note = data.note or None
    db.commit()
    db.expire_all()
    return get_version(db, pk)


def delete_draft(db: Session, pk: int) -> None:
    version = get_version(db, pk, for_update=True)
    if version.status != RecipeStatus.DRAFT:
        raise generate_error(Msg.RECIPE_NOT_DRAFT, status.HTTP_409_CONFLICT)
    db.delete(version)
    db.commit()


def activate(db: Session, pk: int, user: User) -> RecipeVersion:
    """
    Qoralama faollashadi, avvalgi faol versiya arxivga o'tadi — bitta tranzaksiyada.
    Shu paytdan yangi ishlab chiqarishlar yangi versiya bo'yicha hisoblanadi;
    eski versiyani ko'rib turgan operator 409 RECIPE_VERSION_CHANGED oladi (2-qism).
    """
    peek = get_version(db, pk)
    _lock_finished_product(db, peek.product_id)
    version = get_version(db, pk, for_update=True)
    if version.status != RecipeStatus.DRAFT:
        raise generate_error(Msg.RECIPE_NOT_DRAFT, status.HTTP_409_CONFLICT)
    if not version.lines:
        raise generate_error(Msg.RECIPE_EMPTY, status.HTTP_422_UNPROCESSABLE_CONTENT)
    _validate_lines(
        db, [RecipeLineIn(raw_product_id=line.raw_product_id, qty_per_unit=line.qty_per_unit) for line in version.lines]
    )

    current = db.scalars(
        select(RecipeVersion)
        .where(RecipeVersion.product_id == version.product_id, RecipeVersion.status == RecipeStatus.ACTIVE)
        .with_for_update(of=RecipeVersion)
    ).first()
    if current is not None:
        current.status = RecipeStatus.ARCHIVED
        db.flush()  # "bitta faol" indeksi: avval eskisi arxivga o'tadi

    version.status = RecipeStatus.ACTIVE
    version.activated_at = utcnow()
    version.activated_by_id = user.id
    db.commit()
    db.expire_all()
    return get_version(db, pk)
