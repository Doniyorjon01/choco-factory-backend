"""
So'rov konteksti: request_id va access log.

Toza ASGI middleware (BaseHTTPMiddleware emas) — u javob oqimini
buzmaydi va contextvar'lar endpoint ichida ham ko'rinadi.
"""

import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from utils.logger import request_id_ctx, user_id_ctx

logger = logging.getLogger("access")

_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _VALID_ID.match(incoming) else uuid.uuid4().hex[:16]
        rid_token = request_id_ctx.set(request_id)
        uid_token = user_id_ctx.set("-")

        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = scope.get("path", "")
            if not path.startswith("/health"):
                logger.info(
                    "%s %s %s",
                    scope.get("method"),
                    path,
                    status_code,
                    extra={
                        "status": status_code,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                        "method": scope.get("method"),
                        "path": path,
                    },
                )
            request_id_ctx.reset(rid_token)
            user_id_ctx.reset(uid_token)
