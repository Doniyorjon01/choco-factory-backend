from datetime import timedelta

from fastapi import status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from config import settings
from database.hash import Hash
from errors import generate_error
from models import User, UserRole
from schemas.users import UserCreate, UserUpdate
from translations import Msg
from utils.timeutils import utcnow


def get_user(db: Session, pk: int, *, for_update: bool = False) -> User:
    stmt = select(User).where(User.id == pk)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    user = db.scalars(stmt).first()
    if user is None:
        raise generate_error(Msg.USER_NOT_FOUND, status.HTTP_404_NOT_FOUND)
    return user


def users_query(q: str | None = None, role: str | None = None, is_active: bool | None = None) -> Select[tuple[User]]:
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active.is_(is_active))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.full_name.ilike(like), User.login.ilike(like)))
    return stmt.order_by(User.is_active.desc(), User.full_name, User.id)


# --------------------------------------------------------------------- #
# Kirish
# --------------------------------------------------------------------- #


def authenticate(db: Session, login: str, password: str) -> User:
    """
    Login + parol. Ketma-ket LOGIN_MAX_ATTEMPTS marta xato — hisob
    LOGIN_LOCK_MINUTES daqiqaga qulflanadi. Hisoblagich bazada, shuning
    uchun bir nechta worker bo'lsa ham to'g'ri ishlaydi.
    """
    login = login.strip().lower()
    user = db.scalars(select(User).where(User.login == login).with_for_update()).first()
    if user is None:
        Hash.dummy_verify(password)
        raise generate_error(Msg.INVALID_CREDENTIALS, status.HTTP_401_UNAUTHORIZED)

    now = utcnow()
    if user.locked_until and user.locked_until > now:
        minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        raise generate_error(
            Msg.ACCOUNT_LOCKED,
            status.HTTP_429_TOO_MANY_REQUESTS,
            params={"minutes": minutes},
            data={"retry_after_seconds": int((user.locked_until - now).total_seconds())},
            headers={"Retry-After": str(int((user.locked_until - now).total_seconds()) + 1)},
        )

    if not Hash.verify(user.password_hash, password):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.LOGIN_MAX_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
            user.failed_login_count = 0
        db.commit()
        raise generate_error(Msg.INVALID_CREDENTIALS, status.HTTP_401_UNAUTHORIZED)

    # Parol to'g'ri bo'lgandan keyingina "bloklangan" deb aytamiz
    if not user.is_active:
        db.rollback()
        raise generate_error(Msg.USER_INACTIVE, status.HTTP_403_FORBIDDEN)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    db.commit()
    return user


def change_password(db: Session, user: User, current_password: str, new_password: str) -> User:
    if not Hash.verify(user.password_hash, current_password):
        raise generate_error(Msg.WRONG_CURRENT_PASSWORD, status.HTTP_400_BAD_REQUEST)
    if current_password == new_password:
        raise generate_error(Msg.PASSWORD_SAME_AS_OLD, status.HTTP_400_BAD_REQUEST)
    user.password_hash = Hash.bcrypt(new_password)
    user.must_change_password = False
    user.token_version += 1  # boshqa qurilmalardagi eski sessiyalar yopiladi
    db.commit()
    db.refresh(user)
    return user


def update_lang(db: Session, user: User, lang: str) -> User:
    user.lang = lang
    db.commit()
    db.refresh(user)
    return user


# --------------------------------------------------------------------- #
# Administrator amallari
# --------------------------------------------------------------------- #


def create_user(db: Session, data: UserCreate, created_by: User) -> User:
    exists = db.scalar(select(User.id).where(User.login == data.login))
    if exists:
        raise generate_error(Msg.LOGIN_TAKEN, status.HTTP_409_CONFLICT)
    user = User(
        full_name=data.full_name,
        login=data.login,
        role=data.role,
        lang=data.lang,
        password_hash=Hash.bcrypt(data.password),
        must_change_password=data.must_change_password,
        created_by_id=created_by.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _lock_active_admins(db: Session) -> list[int]:
    """
    Barcha faol adminlar id tartibida qulflanadi. Rol yoki faollik o'zgaradigan
    har bir so'rov aynan shu bilan BOSHLANADI — qulflar hamma joyda bir xil
    tartibda olinadi, shuning uchun ikki admin bir vaqtda bir-birini bloklasa,
    deadlock emas, navbat bo'ladi va kamida bittasi qoladi.
    """
    return list(
        db.scalars(
            select(User.id)
            .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
            .order_by(User.id)
            .with_for_update()
        ).all()
    )


def update_user(db: Session, pk: int, data: UserUpdate, actor: User) -> User:
    changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}

    admin_ids = _lock_active_admins(db) if ("role" in changes or "is_active" in changes) else []
    user = get_user(db, pk, for_update=True)

    role_changes = "role" in changes and changes["role"] != user.role
    deactivates = changes.get("is_active") is False and user.is_active

    if user.id == actor.id and (role_changes or deactivates):
        raise generate_error(Msg.CANNOT_MODIFY_SELF, status.HTTP_409_CONFLICT)

    loses_admin = user.role == UserRole.ADMIN and user.is_active and (role_changes or deactivates)
    if loses_admin and not any(i != user.id for i in admin_ids):
        raise generate_error(Msg.LAST_ADMIN, status.HTTP_409_CONFLICT)

    for key, value in changes.items():
        setattr(user, key, value)

    if role_changes or deactivates:
        user.token_version += 1  # amaldagi sessiyalar darhol yopiladi
    db.commit()
    db.refresh(user)
    return user


def reset_password(db: Session, pk: int, new_password: str) -> User:
    """Administrator vaqtinchalik parol beradi: keyingi kirishda almashtirish majburiy."""
    user = get_user(db, pk, for_update=True)
    user.password_hash = Hash.bcrypt(new_password)
    user.must_change_password = True
    user.token_version += 1
    user.failed_login_count = 0
    user.locked_until = None
    db.commit()
    db.refresh(user)
    return user


def count_users(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User)) or 0
