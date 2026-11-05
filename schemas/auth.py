from typing import Literal

from pydantic import Field

from .common import ORMModel, Password, StrictInput


class MeOut(ORMModel):
    id: int
    full_name: str
    login: str
    role: Literal["admin", "warehouse", "operator"]
    lang: Literal["uz", "ru"]
    must_change_password: bool


class AuthResponse(ORMModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Token amal qilish muddati, soniyada")
    user: MeOut


class ChangePasswordIn(StrictInput):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: Password


class MeUpdate(StrictInput):
    lang: Literal["uz", "ru"]
