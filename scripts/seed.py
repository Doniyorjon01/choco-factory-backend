"""
Demo data for development (guide, section 10).

    docker compose run --rm api python -m scripts.seed

Creates:
- 3 users: admin, omborchi, operator (password: --password, default Kakao2026);
- 5 raw materials and 3 finished products (with min / target stock);
- recipe versions: Dark v1-v2 archived, v3 active, v4 draft;
  Milk v1 archived, v2 active; Bitter 85% v1 draft;
- document history 28.10-04.11.2026 (guide, section 10.3): opening stock,
  PRD-0132 ... PRD-0142, BRK-0004, TZT-0009 + STR-0011, KRM-0087.
  Documents go through the same services as the API, so the ledger and
  stock_balance always match. After the seed: cocoa 12 400 g, sugar 3 180 g,
  Dark chocolate 248 pcs, and the next numbers are PRD-0143, KRM-0088 ...

Safe to run again: existing rows are skipped; documents are written only
into an empty journal.
"""

import argparse
import sys
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from config import settings
from database.config import SessionLocal
from database.hash import Hash
from models import (
    DocCounter,
    Document,
    Product,
    RecipeLine,
    RecipeStatus,
    RecipeVersion,
    StockBalance,
    User,
    UserRole,
)
from schemas.documents import AdjustmentCreate, ProductionCreate, ReceiptCreate, ReversalCreate, ScrapCreate
from services import adjustment, production, receipt, reversal, scrap

USERS = [
    ("admin", "Administrator", UserRole.ADMIN),
    ("omborchi", "Dilnoza Rahimova", UserRole.WAREHOUSE),
    ("operator", "Bekzod Toshmatov", UserRole.OPERATOR),
]

# code, name_uz, name_ru, kind, unit, min_qty, target_qty
PRODUCTS = [
    ("XA-001", "Kakao kukuni", "Какао-порошок", "raw", "g", 5_000, 25_000),
    ("XA-002", "Shakar", "Сахар", "raw", "g", 4_000, 10_000),
    ("XA-003", "Kakao yogʻi", "Какао-масло", "raw", "g", 2_000, 10_000),
    ("XA-004", "Sut kukuni", "Сухое молоко", "raw", "g", 3_000, 12_000),
    ("XA-005", "Vanilin", "Ванилин", "raw", "g", 50, 300),
    ("TM-001", "Qora shokolad", "Тёмный шоколад", "finished", "pcs", 100, 400),
    ("TM-002", "Sutli shokolad", "Молочный шоколад", "finished", "pcs", 80, 250),
    ("TM-003", "Achchiq shokolad 85%", "Горький шоколад 85%", "finished", "pcs", 50, 200),
]

# product_code: [(version, status, activated_at, note, {raw_code: qty_per_unit})]
RECIPES = {
    "TM-001": [
        (1, "archived", "2026-03-02", "Birinchi retsept", {"XA-001": 55, "XA-002": 22}),
        (2, "archived", "2026-06-15", "Shakar kamaytirildi", {"XA-001": 52, "XA-002": 20}),
        (3, "active", "2026-10-12", "Kakao 50 g ga tushirildi", {"XA-001": 50, "XA-002": 20}),
        (4, "draft", None, "Kakao yogʻi qoʻshilmoqda", {"XA-001": 50, "XA-002": 18, "XA-003": 5}),
    ],
    "TM-002": [
        (1, "archived", "2026-03-02", None, {"XA-001": 32, "XA-002": 25, "XA-004": 20, "XA-003": 13, "XA-005": 1}),
        (2, "active", "2026-08-20", None, {"XA-001": 30, "XA-002": 25, "XA-004": 20, "XA-003": 15, "XA-005": 1}),
    ],
    "TM-003": [
        (1, "draft", None, "Sinov partiyasi uchun", {"XA-001": 55, "XA-003": 30, "XA-002": 15}),
    ],
}


def _at(day: str) -> datetime:
    # Mahalliy 09:00 (UTC 04:00)
    return datetime.fromisoformat(day).replace(hour=4, tzinfo=UTC)


def seed_users(db: Session, password: str) -> dict[str, User]:
    result = {}
    for login, full_name, role in USERS:
        user = db.scalars(select(User).where(User.login == login)).first()
        if user is None:
            user = User(
                login=login,
                full_name=full_name,
                role=role,
                password_hash=Hash.bcrypt(password),
                must_change_password=False,
            )
            db.add(user)
            print(f"  + foydalanuvchi {login} ({role})")
        result[login] = user
    db.flush()
    return result


def seed_products(db: Session) -> dict[str, Product]:
    result = {}
    for code, name_uz, name_ru, kind, unit, min_qty, target_qty in PRODUCTS:
        product = db.scalars(select(Product).where(Product.code == code)).first()
        if product is None:
            product = Product(
                code=code,
                name_uz=name_uz,
                name_ru=name_ru,
                kind=kind,
                unit=unit,
                min_qty=min_qty,
                target_qty=target_qty,
            )
            db.add(product)
            db.flush()
            db.add(StockBalance(product_id=product.id, qty=0))
            print(f"  + mahsulot {code} {name_uz}")
        result[code] = product
    db.flush()
    return result


def seed_recipes(db: Session, products: dict[str, Product], admin: User) -> None:
    for code, versions in RECIPES.items():
        product = products[code]
        if db.scalar(select(RecipeVersion.id).where(RecipeVersion.product_id == product.id).limit(1)):
            continue
        current_active: RecipeVersion | None = None
        for number, final_status, activated, note, lines in versions:
            # Tarkib faqat qoralamaga yoziladi (trigger), keyin holat o'zgaradi
            version = RecipeVersion(
                product_id=product.id,
                version=number,
                status=RecipeStatus.DRAFT,
                note=note,
                created_by_id=admin.id,
                lines=[RecipeLine(raw_product_id=products[raw].id, qty_per_unit=qty) for raw, qty in lines.items()],
            )
            db.add(version)
            db.flush()
            if final_status == "draft":
                continue
            if current_active is not None:
                current_active.status = RecipeStatus.ARCHIVED
                db.flush()
            version.status = RecipeStatus.ACTIVE
            version.activated_at = _at(activated)
            version.activated_by_id = admin.id
            db.flush()
            current_active = version
        print(f"  + retseptlar {code}: {len(versions)} versiya")


# --------------------------------------------------------------------- #
# Document history (guide, section 10.3)
# --------------------------------------------------------------------- #

# Counters are set so that the seeded documents get the numbers from the guide.
COUNTERS = {"receipt": 85, "production": 131, "adjustment": 6, "scrap": 3, "reversal": 10}

# Opening stock on 28.10 (worked out backwards from the guide's numbers).
OPENING_RAW = {"XA-001": 16_400, "XA-002": 9_560, "XA-003": 7_650, "XA-004": 9_400, "XA-005": 200}
OPENING_FINISHED = {"TM-001": 10, "TM-002": 60}

# (local time, finished product code, pcs) — 7-day chart: Dark 30,34,24,0,36,80,40 / Milk 12,10,8,0,14,16,0
PRODUCTIONS = [
    ("2026-10-29 10:00", "TM-001", 30),
    ("2026-10-29 14:00", "TM-002", 12),
    ("2026-10-30 10:00", "TM-001", 34),
    ("2026-10-30 14:00", "TM-002", 10),
    ("2026-10-31 10:00", "TM-001", 24),
    ("2026-10-31 14:00", "TM-002", 8),
    ("2026-11-02 11:00", "TM-002", 14),
    ("2026-11-02 16:45", "TM-001", 36),  # PRD-0139
    ("2026-11-03 10:20", "TM-002", 16),  # PRD-0140
    ("2026-11-03 15:02", "TM-001", 80),  # PRD-0141
]


def _local(value: str) -> datetime:
    """'2026-11-04 14:32' in Tashkent time -> aware datetime."""
    return datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=settings.tz)


def _rid() -> uuid.UUID:
    return uuid.uuid4()


def _stock(db: Session, product: Product) -> int:
    return db.scalar(select(StockBalance.qty).where(StockBalance.product_id == product.id)) or 0


def seed_documents(db: Session, users: dict[str, User], p: dict[str, Product]) -> None:
    if db.scalar(select(func.count()).select_from(Document)):
        print("  = hujjatlar bor — tarix yozilmadi")
        return

    # The history uses Dark v3 and Milk v2. If someone already activated
    # another version, the numbers would not match the guide.
    active = {}
    for code, expected in (("TM-001", 3), ("TM-002", 2)):
        version = db.scalars(
            select(RecipeVersion).where(
                RecipeVersion.product_id == p[code].id, RecipeVersion.status == RecipeStatus.ACTIVE
            )
        ).first()
        if version is None or version.version != expected:
            print(f"  ! {code}: faol retsept v{expected} emas — hujjatlar tarixi yozilmadi")
            return
        active[code] = version.id

    for doc_type, value in COUNTERS.items():
        db.execute(update(DocCounter).where(DocCounter.doc_type == doc_type).values(last_number=value))
    db.commit()

    warehouse, operator, admin = users["omborchi"], users["operator"], users["admin"]

    # 28.10 — opening stock: count of finished goods, then the opening receipt
    for minute, (code, qty) in zip(("08:30", "08:35"), OPENING_FINISHED.items(), strict=True):
        adjustment.create_adjustment(
            db,
            AdjustmentCreate(
                request_id=_rid(),
                product_id=p[code].id,
                counted_qty=qty,
                expected_qty=0,
                reason="inventory",
                note="Boshlangʻich qoldiq",
            ),
            warehouse,
            created_at=_local(f"2026-10-28 {minute}"),
        )
    receipt.create_receipt(
        db,
        ReceiptCreate(
            request_id=_rid(),
            lines=[{"product_id": p[code].id, "qty": qty} for code, qty in OPENING_RAW.items()],
            supplier_name="Choco Trade MChJ",
            supplier_doc_no="NK-2280",
            supplier_doc_date="2026-10-27",
            note="Boshlangʻich qoldiq",
        ),
        warehouse,
        created_at=_local("2026-10-28 09:00"),
    )

    for when, code, qty in PRODUCTIONS:
        production.create_production(
            db,
            ProductionCreate(request_id=_rid(), product_id=p[code].id, qty=qty, recipe_version_id=active[code]),
            operator,
            created_at=_local(when),
        )

    scrap.create_scrap(
        db,
        ScrapCreate(request_id=_rid(), product_id=p["TM-001"].id, qty=6, reason="shape"),
        operator,
        created_at=_local("2026-11-03 17:20"),
    )

    # 04.11 — a wrong sugar count (TZT-0009), then its reversal (STR-0011)
    sugar_now = _stock(db, p["XA-002"])
    tzt, _ = adjustment.create_adjustment(
        db,
        AdjustmentCreate(
            request_id=_rid(),
            product_id=p["XA-002"].id,
            counted_qty=sugar_now - 400,
            expected_qty=sugar_now,
            reason="inventory",
        ),
        warehouse,
        created_at=_local("2026-11-04 09:12"),
    )
    reversal.reverse_document(
        db,
        tzt.id,
        ReversalCreate(request_id=_rid(), reason="Qayta tortildi — shakar joyida, tarozi xato koʻrsatgan"),
        admin,
        created_at=_local("2026-11-04 09:40"),
    )

    receipt.create_receipt(
        db,
        ReceiptCreate(
            request_id=_rid(),
            lines=[{"product_id": p["XA-001"].id, "qty": 10_000}],
            supplier_name="Choco Trade MChJ",
            supplier_doc_no="NK-2287",
            supplier_doc_date="2026-11-04",
        ),
        warehouse,
        created_at=_local("2026-11-04 11:05"),
    )

    production.create_production(
        db,
        ProductionCreate(request_id=_rid(), product_id=p["TM-001"].id, qty=40, recipe_version_id=active["TM-001"]),
        operator,
        created_at=_local("2026-11-04 14:32"),
    )

    count = db.scalar(select(func.count()).select_from(Document))
    print(f"  + hujjatlar tarixi: {count} ta hujjat")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed demo data (dev only)")
    parser.add_argument("--password", default="Kakao2026", help="demo foydalanuvchilar paroli")
    parser.add_argument("--force", action="store_true", help="APP_ENV=prod boʻlsa ham ishga tushirish")
    args = parser.parse_args()

    if settings.is_prod and not args.force:
        print("APP_ENV=prod: demo maʼlumotlar yozilmaydi (--force bilan majburlash mumkin).", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        print("Seed:")
        users = seed_users(db, args.password)
        products = seed_products(db)
        seed_recipes(db, products, users["admin"])
        db.commit()
        seed_documents(db, users, products)
    print("Tayyor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())