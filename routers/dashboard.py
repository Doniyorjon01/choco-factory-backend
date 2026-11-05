from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth.oauth2 import get_admin_or_warehouse
from database.config import get_pg_db
from models import User
from schemas.dashboard import DashboardOut
from services.dashboard import build_dashboard

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def get_dashboard(db: Session = Depends(get_pg_db), user: User = Depends(get_admin_or_warehouse)):
    """Home page: today's output, low stock, capacity, 7-day production chart, last documents."""
    return build_dashboard(db)