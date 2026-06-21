"""Persian/Farsi text utilities for user-facing output."""
from __future__ import annotations

_LATIN_TO_PERSIAN = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def to_persian_digits(text: str) -> str:
    """Replace ASCII digits with Persian digits in a user-facing string.

    Safe to call on any string — does not touch JSON keys, SQL, or non-digit chars.
    """
    return text.translate(_LATIN_TO_PERSIAN)
