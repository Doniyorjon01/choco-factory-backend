"""
Vaqt bilan ishlash.

Bazada hamma vaqt `timestamptz` (UTC). Biznes kunlari ("bugun", "7 kun",
yetkazib beruvchi sanasi) esa korxona vaqt zonasida (Asia/Tashkent) hisoblanadi.
"""

from datetime import UTC, date, datetime, time, timedelta

from config import settings


def utcnow() -> datetime:
    return datetime.now(UTC)


def local_today() -> date:
    return datetime.now(settings.tz).date()


def local_day_start_utc(day: date) -> datetime:
    """Mahalliy kun boshlanishi (00:00 Toshkent) UTC da."""
    return datetime.combine(day, time.min, tzinfo=settings.tz).astimezone(UTC)


def local_days_range_utc(days: int) -> tuple[datetime, datetime]:
    """Bugunni ham qoʻshib oxirgi `days` kunning [boshi, hozir) oraligʻi, UTC da."""
    start_day = local_today() - timedelta(days=days - 1)
    return local_day_start_utc(start_day), utcnow()
