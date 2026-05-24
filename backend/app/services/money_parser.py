import re
from typing import Optional

FA_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

NUMBER_WORDS = {
    "صفر": 0,
    "یک": 1,
    "یه": 1,
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
    "یازده": 11,
    "دوازده": 12,
    "سیزده": 13,
    "چهارده": 14,
    "پانزده": 15,
    "شانزده": 16,
    "هفده": 17,
    "هجده": 18,
    "نوزده": 19,
    "بیست": 20,
    "سی": 30,
    "چهل": 40,
    "پنجاه": 50,
    "شصت": 60,
    "هفتاد": 70,
    "هشتاد": 80,
    "نود": 90,
    "صد": 100,
    "دویست": 200,
    "سیصد": 300,
    "چهارصد": 400,
    "پانصد": 500,
    "ششصد": 600,
    "هفتصد": 700,
    "هشتصد": 800,
    "نهصد": 900,
}

SCALE_WORDS = {"هزار": 1_000, "میلیون": 1_000_000, "ملیون": 1_000_000, "میلیارد": 1_000_000_000}


def normalize_digits(value: str) -> str:
    return value.translate(FA_TO_EN).replace("٫", ".").replace("٬", ",")


def format_toman(amount: int) -> str:
    return f"{amount:,} تومان"


def parse_money(text: str) -> Optional[int]:
    normalized = normalize_digits(text).lower().replace("تومن", "تومان")

    suffix_match = re.search(r"(\d+(?:[.,]\d+)?)\s*([mk])\b", normalized)
    if suffix_match:
        number = float(suffix_match.group(1).replace(",", ""))
        multiplier = 1_000 if suffix_match.group(2) == "k" else 1_000_000
        return int(number * multiplier)

    unit_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(هزار|میلیون|ملیون|میلیارد)", normalized)
    if unit_match:
        number = float(unit_match.group(1).replace(",", ""))
        return int(number * SCALE_WORDS[unit_match.group(2)])

    plain_match = re.search(r"\d[\d,]*", normalized)
    if plain_match:
        return int(plain_match.group(0).replace(",", ""))

    tokens = re.split(r"[\s‌\-]+", normalized)
    total = 0
    current = 0
    found = False
    for token in tokens:
        token = token.strip("،.?!")
        if token == "و":
            continue
        if token in NUMBER_WORDS:
            current += NUMBER_WORDS[token]
            found = True
        elif token in SCALE_WORDS:
            current = max(current, 1) * SCALE_WORDS[token]
            total += current
            current = 0
            found = True
    if found:
        return total + current
    return None
