from enum import Enum

from fastapi import Request


class Lang(str, Enum):
    uz = "uz"  # Oʻzbekcha
    ru = "ru"  # Русский


SUPPORTED = {lang.value for lang in Lang}
DEFAULT_LANG = Lang.uz


def pick_lang(request: Request) -> Lang:
    """Accept-Language sarlavhasidan birinchi qoʻllab-quvvatlanadigan tilni tanlaydi."""
    header = request.headers.get("Accept-Language", "")
    for token in header.split(","):
        code = token.split(";")[0].strip().lower()
        if not code:
            continue
        if code in SUPPORTED:
            return Lang(code)
        short = code.split("-")[0]  # ru-RU -> ru
        if short in SUPPORTED:
            return Lang(short)
    return DEFAULT_LANG


def get_lang(request: Request) -> Lang:
    return pick_lang(request)
