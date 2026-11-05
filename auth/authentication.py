from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from auth.oauth2 import create_access_token, get_current_user_allow_password_change
from database import db_users
from database.config import get_pg_db
from models import User
from schemas.auth import AuthResponse, ChangePasswordIn, MeOut, MeUpdate

router = APIRouter(prefix="/auth", tags=["authentication"])


def _auth_response(user: User) -> AuthResponse:
    token, expires_in = create_access_token(user)
    return AuthResponse(access_token=token, expires_in=expires_in, user=MeOut.model_validate(user))


@router.post("/login", response_model=AuthResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_pg_db)):
    """
    Kirish (application/x-www-form-urlencoded: username, password).
    Javobdagi `user.must_change_password = true` bo'lsa, klient faqat
    parol almashtirish ekranini ochadi — boshqa endpointlar 403 qaytaradi.
    """
    user = db_users.authenticate(db, form.username, form.password)
    return _auth_response(user)


@router.get("/me", response_model=MeOut)
def get_me(user: User = Depends(get_current_user_allow_password_change)):
    return user


@router.patch("/me", response_model=MeOut)
def update_me(
    data: MeUpdate,
    db: Session = Depends(get_pg_db),
    user: User = Depends(get_current_user_allow_password_change),
):
    return db_users.update_lang(db, user, data.lang)


@router.post("/change-password", response_model=AuthResponse)
def change_password(
    data: ChangePasswordIn,
    db: Session = Depends(get_pg_db),
    user: User = Depends(get_current_user_allow_password_change),
):
    """Parolni almashtiradi va yangi token qaytaradi (eski tokenlar yaroqsiz bo'ladi)."""
    user = db_users.change_password(db, user, data.current_password, data.new_password)
    return _auth_response(user)
