from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from auth.oauth2 import get_current_admin
from database import db_recipes
from database.config import get_pg_db
from models import User
from schemas.recipes import RecipeDraftCreate, RecipeDraftUpdate, RecipeSummaryOut, RecipeVersionOut

router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.get("", response_model=list[RecipeSummaryOut])
def get_recipes(
    include_archived: bool = False, db: Session = Depends(get_pg_db), admin: User = Depends(get_current_admin)
):
    """Har bir tayyor mahsulot: faol versiya (tarkibi bilan) va qoralama raqami.
    Sahifalash yo'q — tayyor mahsulotlar soni kichik va chegaralangan."""
    return db_recipes.list_recipes(db, include_archived)


@router.get("/products/{product_id}/versions", response_model=list[RecipeVersionOut])
def get_versions(product_id: int, db: Session = Depends(get_pg_db), admin: User = Depends(get_current_admin)):
    """Mahsulotning barcha versiyalari, yangisi birinchi."""
    return db_recipes.versions_for_product(db, product_id)


@router.post("/products/{product_id}/versions", response_model=RecipeVersionOut, status_code=status.HTTP_201_CREATED)
def create_draft(
    product_id: int,
    data: RecipeDraftCreate,
    db: Session = Depends(get_pg_db),
    admin: User = Depends(get_current_admin),
):
    """Yangi qoralama. `lines` berilmasa — faol versiya tarkibi nusxalanadi."""
    return db_recipes.create_draft(db, product_id, data, admin)


@router.get("/versions/{version_id}", response_model=RecipeVersionOut)
def get_version(version_id: int, db: Session = Depends(get_pg_db), admin: User = Depends(get_current_admin)):
    return db_recipes.get_version(db, version_id)


@router.patch("/versions/{version_id}", response_model=RecipeVersionOut)
def update_draft(
    version_id: int,
    data: RecipeDraftUpdate,
    db: Session = Depends(get_pg_db),
    admin: User = Depends(get_current_admin),
):
    """Faqat qoralama. `lines` berilsa — tarkib to'liq almashtiriladi."""
    return db_recipes.update_draft(db, version_id, data)


@router.delete("/versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_draft(version_id: int, db: Session = Depends(get_pg_db), admin: User = Depends(get_current_admin)):
    """Faqat qoralama o'chiriladi — uning tarixi yo'q."""
    db_recipes.delete_draft(db, version_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/versions/{version_id}/activate", response_model=RecipeVersionOut)
def activate(version_id: int, db: Session = Depends(get_pg_db), admin: User = Depends(get_current_admin)):
    return db_recipes.activate(db, version_id, admin)
