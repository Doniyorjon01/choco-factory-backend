import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class StrictInput(BaseModel):
    """Kiruvchi so'rovlar: noma'lum maydon kelsa — 422 (mass assignment yo'q)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


_LOGIN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


def _normalize_login(value: str) -> str:
    value = value.strip().lower()
    if not _LOGIN_RE.match(value):
        raise ValueError("login: 3–64 belgi, lotin harflari, raqam, '.', '_' yoki '-'")
    return value


def _check_password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("password must be at least 8 characters")
    if len(value.encode("utf-8")) > 72:
        raise ValueError("password must be at most 72 bytes")
    if not re.search(r"[^\W\d_]", value) or not re.search(r"\d", value):
        raise ValueError("password must contain letters and digits")
    return value


Login = Annotated[str, AfterValidator(_normalize_login)]
Password = Annotated[str, AfterValidator(_check_password)]
FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=150)]
ProductName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
