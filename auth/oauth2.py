"""
Tokenlar va ruxsat tekshiruvi.

Autentifikatsiya (kim?) — `get_current_user`: JWT imzosi, muddati, foydalanuvchi
faolligi va `token_version`. Rol tokendan emas, har so'rovda bazadan olinadi —
shunda bloklash yoki rol almashtirish darhol kuchga kiradi.

Avtorizatsiya (nima qila oladi?) — `require_roles(...)`.
"""

from collections.abc import Callable
from datetime import timedelta

import jwt
from fastapi import Depends, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from config import settings
from database.config import get_pg_db
from errors import generate_error
from models import User, UserRole
from translations import Msg
from utils.logger import user_id_ctx
from utils.timeutils import utcnow

# auto_error=False: token yo'qligini o'zimiz bir xil formatda qaytaramiz
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

_TOKEN_TYPE = "access"


def create_access_token(user: User) -> tuple[str, int]:
    expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    now = utcnow()
    payload = {
        "sub": str(user.id),
        "role": user.role,  # faqat klient uchun ma'lumot; serverda bazadan olinadi
        "ver": user.token_version,
        "typ": _TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, expires_in


def _unauthorized(msg: Msg):
    return generate_error(msg, status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate": "Bearer"})


def _load_user(token: str | None, db: Session) -> User:
    if not token:
        raise _unauthorized(Msg.NOT_AUTHENTICATED)
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat", "ver", "typ"]},
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized(Msg.TOKEN_EXPIRED) from None
    except jwt.PyJWTError:
        raise _unauthorized(Msg.TOKEN_INVALID) from None

    if payload.get("typ") != _TOKEN_TYPE:
        raise _unauthorized(Msg.TOKEN_INVALID)
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        raise _unauthorized(Msg.TOKEN_INVALID) from None

    user = db.get(User, user_id)
    if user is None or user.token_version != payload.get("ver"):
        # Parol almashgan, rol o'zgargan yoki bloklangan — eski token yaroqsiz
        raise _unauthorized(Msg.TOKEN_INVALID)
    if not user.is_active:
        raise generate_error(Msg.USER_INACTIVE, status.HTTP_403_FORBIDDEN)

    user_id_ctx.set(str(user.id))
    return user


def get_current_user_allow_password_change(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_pg_db)
) -> User:
    """Faqat /auth/me va /auth/change-password uchun: parol almashtirish majburiy bo'lsa ham kiradi."""
    return _load_user(token, db)


def get_current_user(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_pg_db)) -> User:
    user = _load_user(token, db)
    if user.must_change_password:
        raise generate_error(Msg.PASSWORD_CHANGE_REQUIRED, status.HTTP_403_FORBIDDEN)
    return user


def require_roles(*roles: UserRole) -> Callable[..., User]:
    allowed = {r.value for r in roles}

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise generate_error(Msg.FORBIDDEN, status.HTTP_403_FORBIDDEN)
        return user

    dependency.__name__ = f"require_{'_or_'.join(sorted(allowed))}"
    return dependency


# Tez-tez ishlatiladigan kombinatsiyalar
get_current_admin = require_roles(UserRole.ADMIN)
get_admin_or_warehouse = require_roles(UserRole.ADMIN, UserRole.WAREHOUSE)
get_any_role = require_roles(UserRole.ADMIN, UserRole.WAREHOUSE, UserRole.OPERATOR)
