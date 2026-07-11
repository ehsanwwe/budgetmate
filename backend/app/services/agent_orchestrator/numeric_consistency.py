"""Deterministic sanity check for numerical allocation responses.

This is intentionally conservative. It only flags a response as inconsistent
when it detects a strong pattern: the message contains BOTH a declared
"available" amount and a set of allocations whose total exceeds it.

It does NOT decide the financial strategy. It only refuses arithmetic that is
demonstrably wrong. When it cannot confidently interpret the message, it
passes through — the LLM remains in charge of judgment.

No keyword-based intent routing lives here: this is a *validator*, not a
router. Its output is a boolean signal to the composer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# Persian / Arabic-Indic digit map
_PERSIAN_DIGIT_MAP = str.maketrans({
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
})

# Words that indicate an "available/remaining" claim (Persian + English).
# These are *cue* words used to locate a number in the LLM's own writing;
# they are not intent classifiers. Adding to this list only reduces false
# negatives, never changes behavior for routing.
_AVAILABLE_CUES = (
    "باقی مانده",
    "باقی‌مانده",
    "باقی مونده",
    "باقی می‌ماند",
    "می‌ماند",
    "میماند",
    "آزاد",
    "قابل استفاده",
    "موجودی",
    "در دسترس",
    "remaining",
    "available",
    "left",
    "balance",
    "free",
)
_ALLOCATION_CUES = (
    "کنار بذار",
    "کنار بگذار",
    "پس انداز",
    "پس‌انداز",
    "پس‌اندازکن",
    "اختصاص",
    "خرج کن",
    "بریز",
    "بده",
    "save",
    "allocate",
    "spend",
    "put",
    "keep",
)

_NUM_UNIT_RE = re.compile(
    # optional grouping commas, optional decimal, followed by an optional
    # magnitude word (میلیون / میلیارد / thousand / million / billion / k / m / b),
    # then a "toman/تومان/rial" cue. We only accept numbers that have a
    # currency/magnitude context so plain "5" or dates like "2026" are ignored.
    r"(?P<num>\d{1,3}(?:[,٬، ]?\d{3})*(?:[.,]\d+)?)"
    r"\s*(?P<mag>میلیون|میلیارد|هزار|k|m|b|million|billion|thousand)?"
    r"\s*(?P<unit>تومان|تومن|toman|rial|ریال)?",
    re.IGNORECASE,
)


@dataclass
class ExtractedAmount:
    value: int
    span: tuple[int, int]
    context_before: str
    context_after: str


def _normalize_digits(s: str) -> str:
    return s.translate(_PERSIAN_DIGIT_MAP)


def _parse_amount(num_text: str, magnitude: str | None) -> int | None:
    n = _normalize_digits(num_text).replace(",", "").replace("٬", "").replace("،", "").replace(" ", "")
    try:
        base = float(n)
    except ValueError:
        return None
    mag = (magnitude or "").lower()
    multiplier = 1
    if mag in ("میلیون", "million", "m"):
        multiplier = 1_000_000
    elif mag in ("میلیارد", "billion", "b"):
        multiplier = 1_000_000_000
    elif mag in ("هزار", "thousand", "k"):
        multiplier = 1_000
    return int(round(base * multiplier))


def _extract_all_amounts(text: str) -> list[ExtractedAmount]:
    normalized = _normalize_digits(text)
    out: list[ExtractedAmount] = []
    for m in _NUM_UNIT_RE.finditer(normalized):
        num_text = m.group("num") or ""
        mag = m.group("mag")
        unit = m.group("unit")
        # Require SOME currency/magnitude signal so plain digits like "1405"
        # (Jalali year) are not treated as amounts.
        if not mag and not unit:
            continue
        # Small numbers with only currency (e.g. "5 تومان") are almost
        # always shorthand for "5 million toman" in Persian finance chat.
        # We do NOT rewrite these; if the LLM meant "5 toman" that is
        # already an implausibly tiny allocation and the consistency check
        # simply won't apply.
        value = _parse_amount(num_text, mag)
        if value is None or value <= 0:
            continue
        span = m.span()
        # Keep the context window tight and stop at the nearest sentence
        # boundary so cues bound to a neighboring amount do not leak in.
        raw_before = normalized[max(0, span[0] - 30) : span[0]]
        raw_after = normalized[span[1] : span[1] + 30]
        context_before = _last_segment(raw_before)
        context_after = _first_segment(raw_after)
        out.append(
            ExtractedAmount(
                value=value,
                span=span,
                context_before=context_before,
                context_after=context_after,
            )
        )
    return out


_SEGMENT_BOUNDARY_RE = re.compile(r"[.!?؟\n،,]")


def _last_segment(text: str) -> str:
    parts = _SEGMENT_BOUNDARY_RE.split(text)
    return parts[-1] if parts else text


def _first_segment(text: str) -> str:
    parts = _SEGMENT_BOUNDARY_RE.split(text)
    return parts[0] if parts else text


def _classify(amount: ExtractedAmount) -> str:
    # Persian follows "N-toman is-remaining" order, so look at both sides.
    # A cue in the trailing context is authoritative (the sentence structure
    # is "X تومان باقی مانده"). A cue in the leading context also counts
    # ("save X تومان" / "پس‌انداز کن X تومان").
    before = amount.context_before.lower()
    after = amount.context_after.lower()
    for cue in _AVAILABLE_CUES:
        if cue in before or cue in after:
            return "available"
    for cue in _ALLOCATION_CUES:
        if cue in before or cue in after:
            return "allocation"
    return "other"


@dataclass
class ConsistencyResult:
    ok: bool
    declared_available: int | None = None
    total_allocated: int | None = None
    reason: str | None = None


def check_response_consistency(message: str) -> ConsistencyResult:
    """Return a ConsistencyResult flagging demonstrably inconsistent allocations.

    Conservative: returns ``ok=True`` whenever the response does not present a
    clearly-scoped allocation. Only flags when both an available amount and
    an over-allocation are clearly present in the same message.
    """
    if not message or not message.strip():
        return ConsistencyResult(ok=True)
    amounts = _extract_all_amounts(message)
    if len(amounts) < 2:
        return ConsistencyResult(ok=True)

    available_values: list[int] = []
    allocation_values: list[int] = []
    for amt in amounts:
        kind = _classify(amt)
        if kind == "available":
            available_values.append(amt.value)
        elif kind == "allocation":
            allocation_values.append(amt.value)

    if not available_values or not allocation_values:
        return ConsistencyResult(ok=True)
    declared = min(available_values)  # be forgiving — use the smallest claim
    total = sum(allocation_values)
    # Tolerate small rounding errors (1%)
    if total > declared * 1.01:
        return ConsistencyResult(
            ok=False,
            declared_available=declared,
            total_allocated=total,
            reason=(
                f"allocations sum to {total:,} which exceeds the declared "
                f"available {declared:,}"
            ),
        )
    return ConsistencyResult(
        ok=True,
        declared_available=declared,
        total_allocated=total,
    )
