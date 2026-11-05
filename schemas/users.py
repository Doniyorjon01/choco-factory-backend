from datetime import datetime
from typing import Literal

from .common import FullName, Login, ORMModel, Password, StrictInput

Role = Literal["admin", "warehouse", "operator"]


class UserOut(ORMModel):
    id: int
    full_name: str
    login: str
    role: Role
    lang: Literal["uz", "ru"]
    is_active: bool
    must_change_password: bool
    locked_until: datetime | None
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserCreate(StrictInput):
    full_name: FullName
    login: Login
    role: Role
    # Vaqtinchalik parol — administrator foydalanuvchiga og'zaki beradi
    password: Password
    must_change_password: bool = True
    lang: Literal["uz", "ru"] = "uz"


class UserUpdate(StrictInput):
    full_name: FullName | None = None
    role: Role | None = None
    is_active: bool | None = None
    lang: Literal["uz", "ru"] | None = None


class PasswordReset(StrictInput):
    password: Password
