from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=1800,
    connect_args={
        # Sessiya UTC da ishlaydi; uzoq so'rov va cheksiz qulf kutish yo'q
        "options": (
            "-c timezone=UTC"
            f" -c statement_timeout={settings.DB_STATEMENT_TIMEOUT_MS}"
            f" -c lock_timeout={settings.DB_LOCK_TIMEOUT_MS}"
        ),
        "application_name": "chocolate-api",
    },
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_pg_db() -> Iterator[Session]:
    """
    So'rov uchun sessiya. Commit — database/ va services/ funksiyalari ichida,
    aniq joyda. Xato bo'lsa, close() ochiq tranzaksiyani rollback qiladi.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
