from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings

_PERSIAN_WORD_NUMS = {
    "یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5,
    "شش": 6, "هفت": 7, "هشت": 8, "نه": 9, "ده": 10,
    "یازده": 11, "دوازده": 12, "سیزده": 13, "چهارده": 14, "پانزده": 15,
    "شانزده": 16, "هفده": 17, "هجده": 18, "نوزده": 19, "بیست": 20,
}

_PERSIAN_DIGITS_TO_LATIN = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def _to_int(text: str) -> int | None:
    text = text.strip().translate(_PERSIAN_DIGITS_TO_LATIN)
    if text.isdigit():
        return int(text)
    return _PERSIAN_WORD_NUMS.get(text)


def _add_months(today: date, months: int) -> date:
    month = today.month + months
    year = today.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(today.day, last_day))


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
    raw = " ".join(str(value).strip().lower().replace("‌", " ").split())
    today = local_today()

    # Past / present
    if raw in {"today", "امروز"}:
        return today
    if raw in {"tomorrow", "فردا"}:
        return today + timedelta(days=1)
    if raw in {"پس‌فردا", "پس فردا", "day after tomorrow"}:
        return today + timedelta(days=2)
    if raw in {"yesterday", "دیروز"}:
        return today - timedelta(days=1)
    if raw in {"پریروز", "دو روز پیش", "2 روز پیش"}:
        return today - timedelta(days=2)
    if raw in {"سه روز پیش", "3 روز پیش"}:
        return today - timedelta(days=3)
    if raw in {"هفته پیش", "هفته گذشته", "هفته قبل"}:
        return today - timedelta(days=7)

    # End of month
    if raw in {"آخر این ماه", "آخر ماه", "پایان ماه", "end of month"}:
        last_day = calendar.monthrange(today.year, today.month)[1]
        return date(today.year, today.month, last_day)
    if raw in {"آخر ماه بعد", "آخر ماه آینده", "پایان ماه بعد"}:
        nm = _add_months(today, 1)
        last_day = calendar.monthrange(nm.year, nm.month)[1]
        return date(nm.year, nm.month, last_day)

    # Exact fixed futures
    if raw in {"یک سال بعد", "یک سال دیگر", "یک سال دیگه", "سال بعد", "سال آینده"}:
        return _add_months(today, 12)
    if raw in {"یک ماه بعد", "یک ماه دیگر", "یک ماه دیگه", "ماه بعد", "ماه بعدی", "ماه آینده"}:
        return _add_months(today, 1)
    if raw in {"یک هفته دیگه", "یک هفته دیگر", "هفته دیگه", "هفته آینده"}:
        return today + timedelta(weeks=1)
    if raw in {"دو هفته دیگه", "دو هفته دیگر"}:
        return today + timedelta(weeks=2)

    # "N روز دیگه / دیگر / بعد"
    m = re.search(r"(\S+)\s+روز\s+(?:دیگه|دیگر|بعد)", raw)
    if m:
        n = _to_int(m.group(1))
        if n is not None:
            return today + timedelta(days=n)

    # "N هفته دیگه / دیگر / بعد / آینده"
    m = re.search(r"(\S+)\s+هفته\s+(?:دیگه|دیگر|بعد|آینده)", raw)
    if m:
        n = _to_int(m.group(1))
        if n is not None:
            return today + timedelta(weeks=n)

    # "N ماه دیگه / دیگر / بعد / آینده" — must come before year check
    m = re.search(r"(\S+)\s+ماه\s+(?:دیگه|دیگر|بعد|آینده)", raw)
    if m:
        n = _to_int(m.group(1))
        if n is not None:
            return _add_months(today, n)

    # "N سال دیگه / دیگر / بعد / آینده"
    m = re.search(r"(\S+)\s+سال\s+(?:دیگه|دیگر|بعد|آینده)", raw)
    if m:
        n = _to_int(m.group(1))
        if n is not None:
            return _add_months(today, n * 12)

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
    text = message.replace("‌", " ")
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
