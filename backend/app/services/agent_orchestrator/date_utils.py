from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings


def app_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(settings.APP_TIMEZONE or "Asia/Tehran")
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Tehran")


def local_today() -> date:
    return datetime.now(app_timezone()).date()


def parse_relative_date(value: object | None) -> date:
    if isinstance(value, date):
        return value
    if not value:
        return local_today()
    raw = " ".join(str(value).strip().lower().replace("\u200c", " ").split())
    today = local_today()
    if raw in {"today", "امروز"}:
        return today
    if raw in {"yesterday", "دیروز"}:
        return today - timedelta(days=1)
    if raw in {"پریروز", "دو روز پیش", "2 روز پیش"}:
        return today - timedelta(days=2)
    if raw in {"سه روز پیش", "3 روز پیش"}:
        return today - timedelta(days=3)
    if raw in {"هفته پیش", "هفته گذشته", "هفته قبل"}:
        return today - timedelta(days=7)
    if raw in {"یک سال بعد", "یک سال دیگر", "سال بعد", "سال آینده"}:
        last_day = calendar.monthrange(today.year + 1, today.month)[1]
        return date(today.year + 1, today.month, min(today.day, last_day))
    if raw in {"یک ماه بعد", "ماه بعد", "ماه بعدی", "ماه آینده"}:
        year = today.year + (1 if today.month == 12 else 0)
        month = 1 if today.month == 12 else today.month + 1
        return date(year, month, 1)
    try:
        return date.fromisoformat(raw)
    except (ValueError, TypeError):
        return today


def local_week_range(anchor: date | None = None, previous: bool = False) -> tuple[date, date]:
    current = anchor or local_today()
    days_since_saturday = (current.weekday() + 2) % 7
    start = current - timedelta(days=days_since_saturday)
    if previous:
        start -= timedelta(days=7)
    return start, start + timedelta(days=7)


def local_month_range(anchor: date | None = None, previous: bool = False) -> tuple[date, date]:
    current = anchor or local_today()
    year = current.year
    month = current.month
    if previous:
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def detect_date_range(message: str) -> tuple[str, date, date]:
    text = message.replace("\u200c", " ")
    if "ماه گذشته" in text:
        start, end = local_month_range(previous=True)
        return "previous_month", start, end
    if "هفته گذشته" in text or "هفته قبل" in text:
        start, end = local_week_range(previous=True)
        return "previous_week", start, end
    if "این هفته" in text or "هفته جاری" in text:
        start, end = local_week_range()
        return "current_week", start, end
    if "این ماه" in text or "ماه جاری" in text:
        start, end = local_month_range()
        return "current_month", start, end
    if "دیروز" in text:
        day = local_today() - timedelta(days=1)
        return "yesterday", day, day + timedelta(days=1)
    if "امروز" in text:
        day = local_today()
        return "today", day, day + timedelta(days=1)
    start, end = local_month_range()
    return "current_month", start, end
