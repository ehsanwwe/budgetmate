from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from app.services.agent_orchestrator.date_utils import local_today

_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_ONES = {
    "صفر": 0,
    "یک": 1,
    "يه": 1,
    "دو": 2,
    "سه": 3,
    "چهار": 4,
    "پنج": 5,
    "شش": 6,
    "شیش": 6,
    "هفت": 7,
    "هشت": 8,
    "نه": 9,
}
_TEENS = {
    "ده": 10,
    "یازده": 11,
    "دوازده": 12,
    "سیزده": 13,
    "چهارده": 14,
    "پانزده": 15,
    "شانزده": 16,
    "هفده": 17,
    "هجده": 18,
    "نوزده": 19,
}
_TENS = {
    "بیست": 20,
    "سی": 30,
    "چهل": 40,
    "پنجاه": 50,
    "شصت": 60,
    "هفتاد": 70,
    "هشتاد": 80,
    "نود": 90,
}
_HUNDREDS = {
    "صد": 100,
    "یکصد": 100,
    "دویست": 200,
    "سیصد": 300,
    "چهارصد": 400,
    "پانصد": 500,
    "ششصد": 600,
    "هفتصد": 700,
    "هشتصد": 800,
    "نهصد": 900,
}
_SCALES = {
    "هزار": 1_000,
    "میلیون": 1_000_000,
    "ملیون": 1_000_000,
    "میلیارد": 1_000_000_000,
}


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").translate(_DIGIT_MAP).replace("\u200c", " ").split())


def normalize_amount(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    text = normalize_text(value).replace(",", "")
    digit_match = re.search(r"\d+(?:\.\d+)?", text)
    if digit_match:
        number = float(digit_match.group(0))
        suffix = text[digit_match.end() :]
        if re.search(r"\b(میلیارد)\b", suffix):
            number *= 1_000_000_000
        elif re.search(r"\b(میلیون|ملیون)\b", suffix):
            number *= 1_000_000
        elif re.search(r"\b(هزار)\b", suffix):
            number *= 1_000
        return int(number)

    parsed = _parse_persian_number(text)
    if parsed is None:
        raise ValueError("amount must be numeric or a supported Persian number phrase")
    return parsed


def _parse_persian_number(text: str) -> int | None:
    tokens = [token for token in re.split(r"\s+و\s+|\s+", text) if token and token not in {"تومان", "تومن"}]
    if not tokens:
        return None
    total = 0
    group = 0
    seen = False
    for token in tokens:
        if token in _ONES:
            group += _ONES[token]
            seen = True
        elif token in _TEENS:
            group += _TEENS[token]
            seen = True
        elif token in _TENS:
            group += _TENS[token]
            seen = True
        elif token in _HUNDREDS:
            group += _HUNDREDS[token]
            seen = True
        elif token in _SCALES:
            scale = _SCALES[token]
            total += (group or 1) * scale
            group = 0
            seen = True
        elif token in {"پول", "بابت", "درآمد", "درامد", "هزینه", "خرج", "کرایه"}:
            continue
        else:
            continue
    if not seen:
        return None
    return total + group


def normalize_date(value: Any | None) -> date:
    if isinstance(value, date):
        return value
    text = normalize_text(value)
    today = local_today()
    if not text or text in {"today", "امروز"}:
        return today
    if text in {"yesterday", "دیروز"}:
        return today - timedelta(days=1)
    if text in {"پریروز", "دو روز پیش", "2 روز پیش"}:
        return today - timedelta(days=2)
    match = re.search(r"(\d+)\s+روز\s+پیش", text)
    if match:
        return today - timedelta(days=int(match.group(1)))
    if "سه روز پیش" in text:
        return today - timedelta(days=3)
    if "هفته پیش" in text or "هفته گذشته" in text:
        return today - timedelta(days=7)
    return date.fromisoformat(text)
