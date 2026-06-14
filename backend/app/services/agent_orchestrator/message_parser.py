from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.agent_orchestrator.date_utils import detect_date_range, parse_relative_date

_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_WORD_NUMBERS = {
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
    "ده": 10,
}


@dataclass
class TransactionSignal:
    amount: int
    tx_type: str
    description: str
    date: str


def normalize_text(message: str) -> str:
    return re.sub(r"\s+", " ", message.translate(_DIGIT_MAP).replace("\u200c", " ")).strip()


def extract_amount(message: str) -> int | None:
    text = normalize_text(message)
    number_match = re.search(r"(\d[\d,]*)\s*(میلیون|ملیون|ملیون|هزار|تومن|تومان)?", text)
    if number_match:
        value = int(number_match.group(1).replace(",", ""))
        unit = number_match.group(2) or ""
        if "میلیون" in unit or "ملیون" in unit:
            return value * 1_000_000
        if "هزار" in unit:
            return value * 1_000
        return value

    for word, value in _WORD_NUMBERS.items():
        if re.search(rf"\b{word}\s*(میلیون|ملیون)\b", text):
            return value * 1_000_000
        if re.search(rf"\b{word}\s*هزار\b", text):
            return value * 1_000
    return None


def detect_transaction_signal(message: str) -> TransactionSignal | None:
    text = normalize_text(message)
    amount = extract_amount(text)
    if not amount or amount < 1000:
        return None

    income_words = ("درآمد", "در آمد", "حقوق", "واریز", "پروژه", "گرفتم", "دریافت")
    expense_words = ("دادم", "خریدم", "پرداخت", "هزینه", "خرج", "پول")
    tx_type = None
    if any(word in text for word in income_words) and not any(word in text for word in ("خرج", "هزینه", "دادم")):
        tx_type = "income"
    elif any(word in text for word in expense_words):
        tx_type = "expense"
    if not tx_type:
        return None

    _, start, _ = detect_date_range(text)
    if "دیروز" in text:
        tx_date = parse_relative_date("دیروز")
    elif "امروز" in text:
        tx_date = parse_relative_date("امروز")
    else:
        tx_date = start

    description = text
    if tx_type == "income":
        if "پروژه" in text:
            description = "درآمد پروژه"
        elif "حقوق" in text:
            description = "حقوق"
        else:
            description = "درآمد"
    return TransactionSignal(amount=amount, tx_type=tx_type, description=description, date=tx_date.isoformat())
