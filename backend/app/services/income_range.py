from __future__ import annotations

import re
from typing import Any


_CODE_MAX_TOMAN = {
    "lt10": 10_000_000,
    "10to20": 20_000_000,
    "20to40": 40_000_000,
    "40to80": 80_000_000,
    "gt80": 80_000_000,
}

_PERSIAN_DIGITS = str.maketrans(
    {
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
    }
)


def income_range_max_toman(
    income_range: str | None = None,
    *,
    income_range_min: int | None = None,
    income_range_max: int | None = None,
    payload: dict[str, Any] | None = None,
) -> int | None:
    """Return the maximum monthly budget amount implied by an income range.

    The app stores known ranges as codes, but this also supports legacy/string
    payloads and structured min/max data. The returned value is always toman.
    """
    if payload:
        structured_max = _coerce_int(
            payload.get("income_range_max")
            or payload.get("monthly_income_max")
            or payload.get("max")
        )
        structured_min = _coerce_int(
            payload.get("income_range_min")
            or payload.get("monthly_income_min")
            or payload.get("min")
        )
        if structured_max is not None:
            return _normalize_amount(structured_max)
        income_range_max = structured_max
        income_range_min = structured_min
        income_range = income_range or payload.get("income_range") or payload.get("label")

    if income_range_max is not None:
        return _normalize_amount(income_range_max)

    if income_range in _CODE_MAX_TOMAN:
        return _CODE_MAX_TOMAN[income_range]

    if income_range_min is not None and income_range_max is None and income_range is None:
        return _normalize_amount(income_range_min)

    if not income_range:
        return None

    return _parse_income_range_text(str(income_range))


def _parse_income_range_text(text: str) -> int | None:
    normalized = text.translate(_PERSIAN_DIGITS).replace(",", "").replace("٬", "")
    numbers = [int(match) for match in re.findall(r"\d+", normalized)]
    if not numbers:
        return None

    max_value = max(numbers)
    has_million_unit = any(unit in normalized.lower() for unit in ("million", "میلیون", "ملیون"))
    if has_million_unit or max_value < 1_000:
        return max_value * 1_000_000
    return max_value


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(str(value).translate(_PERSIAN_DIGITS).replace(",", "").replace("٬", ""))
    except (TypeError, ValueError):
        return None


def _normalize_amount(value: int) -> int:
    return value * 1_000_000 if value < 1_000 else value
