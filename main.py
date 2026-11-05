import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_pagination import add_pagination
from sqlalchemy import text

from auth import authentication
from config import settings
from database.config import engine
from errors import register_exception_handlers
from middleware import RequestContextMiddleware
from routers import dashboard, documents, ledger, products, recipes, stock, users
from utils.logger import setup_logging

setup_logging(settings.LOG_LEVEL, settings.LOG_JSON)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s (%s)", settings.APP_NAME, settings.APP_ENV)
    yield
    engine.dispose()
    logger.info("Stopped")


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan,
    # Prodda API sxemasi ochiq turmasin
    docs_url=None if settings.is_prod else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_prod else "/openapi.json",
)

# Tartib muhim: oxirgi qo'shilgan middleware eng tashqarida ishlaydi
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Accept-Language", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
app.add_middleware(RequestContextMiddleware)

register_exception_handlers(app)

app.include_router(authentication.router)
app.include_router(users.router)
app.include_router(products.router)
app.include_router(recipes.router)
app.include_router(stock.router)
app.include_router(documents.router)
app.include_router(ledger.router)
app.include_router(dashboard.router)

add_pagination(app)


@app.get("/health", tags=["health"], include_in_schema=False)
def health():
    """Liveness: jarayon tirikmi."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"], include_in_schema=False)
def ready():
    """Readiness: baza javob beryaptimi va migratsiyalar qo'llanganmi."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            version = conn.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception:
        logger.exception("Readiness check failed")
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok", "db_revision": version}