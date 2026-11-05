"""
Xatolar: yagona javob formati va global handlerlar.

Har qanday xato javobi bir xil ko'rinishda:

    {"detail": {"code": "INSUFFICIENT_STOCK", "message": "...", "data": {...}}}

- `code` — o'zgarmas, frontend mantiqni shunga quradi;
- `message` — Accept-Language bo'yicha tarjima qilingan matn;
- `data` — ixtiyoriy tafsilotlar (masalan, max_possible, yetmagan qatorlar).

Kodda xato shunday ko'tariladi:

    raise generate_error(Msg.PRODUCT_NOT_FOUND, status.HTTP_404_NOT_FOUND)

Til handlerda so'rovdan aniqlanadi, shuning uchun database/ va services/
funksiyalariga `lang` uzatish shart emas.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg import errors as pg_errors
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from translations import Msg, translate
from utils.i18n import pick_lang

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(
        self,
        msg: Msg,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(msg.value)
        self.msg = msg
        self.status_code = status_code
        self.params = params or {}
        self.data = data
        self.headers = headers


def generate_error(
    msg: Msg,
    status_code: int = status.HTTP_400_BAD_REQUEST,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> AppError:
    return AppError(msg, status_code, params, data, headers)


def _body(request: Request, msg: Msg, params: dict | None = None, data: Any = None) -> dict:
    detail: dict[str, Any] = {"code": msg.value, "message": translate(msg, pick_lang(request), params)}
    if data is not None:
        detail["data"] = data
    return {"detail": detail}


# Poyga holatlarida (ikki so'rov bir vaqtda) bazaning o'zi ushlagan cheklovlar.
# Odatdagi holatda bular kodda oldindan tekshiriladi.
_CONSTRAINT_ERRORS: dict[str, tuple[Msg, int]] = {
    "uq_users_login": (Msg.LOGIN_TAKEN, status.HTTP_409_CONFLICT),
    "uq_products_name_uz_lower": (Msg.PRODUCT_NAME_TAKEN, status.HTTP_409_CONFLICT),
    "uq_products_name_ru_lower": (Msg.PRODUCT_NAME_TAKEN, status.HTTP_409_CONFLICT),
    "ck_stock_balance_qty_nonnegative": (Msg.INSUFFICIENT_STOCK, status.HTTP_409_CONFLICT),
}


def _constraint_name(exc: DBAPIError) -> str | None:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(request, exc.msg, exc.params, exc.data),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        fields = [
            {
                "loc": ".".join(str(p) for p in err.get("loc", ())),
                "type": err.get("type"),
                "msg": err.get("msg"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_body(request, Msg.VALIDATION_ERROR, data={"fields": fields}),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException):
        mapping = {
            401: Msg.NOT_AUTHENTICATED,
            403: Msg.FORBIDDEN,
            404: Msg.NOT_FOUND,
            405: Msg.METHOD_NOT_ALLOWED,
        }
        msg = mapping.get(exc.status_code, Msg.UNKNOWN_ERROR)
        return JSONResponse(status_code=exc.status_code, content=_body(request, msg), headers=exc.headers)

    @app.exception_handler(IntegrityError)
    async def integrity_handler(request: Request, exc: IntegrityError):
        name = _constraint_name(exc)
        mapped = _CONSTRAINT_ERRORS.get(name or "")
        if mapped:
            logger.warning("Constraint caught a race", extra={"constraint": name})
            return JSONResponse(status_code=mapped[1], content=_body(request, mapped[0]))
        # Xaritada yo'q cheklov — bu kodda tekshiruv yetishmayotganini bildiradi
        logger.error("Unmapped integrity error", extra={"constraint": name}, exc_info=exc)
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=_body(request, Msg.CONFLICT))

    @app.exception_handler(OperationalError)
    async def operational_handler(request: Request, exc: OperationalError):
        if isinstance(exc.orig, pg_errors.LockNotAvailable):
            logger.warning("Lock timeout")
            return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=_body(request, Msg.LOCK_TIMEOUT))
        if isinstance(exc.orig, (pg_errors.DeadlockDetected, pg_errors.SerializationFailure)):
            # Tranzaksiya to'liq bekor qilingan — klient xavfsiz qayta urinishi mumkin
            logger.warning("Transaction aborted by concurrency", extra={"pg_error": type(exc.orig).__name__})
            return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=_body(request, Msg.CONFLICT))
        logger.error("Database operational error", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=_body(request, Msg.SERVICE_UNAVAILABLE)
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=_body(request, Msg.UNKNOWN_ERROR)
        )
