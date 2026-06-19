from typing import Literal

SUPPORTED_LOCALES = ["fa", "ar", "en", "de", "zh"]
DEFAULT_LOCALE = "fa"

LOCALE_META: dict[str, dict] = {
    "fa": {
        "name": "Persian",
        "native_name": "فارسی",
        "emoji": "🇮🇷",
        "direction": "rtl",
        "default_currency": "IRT",
        "default": True,
    },
    "ar": {
        "name": "Arabic",
        "native_name": "العربية",
        "emoji": "🇸🇦",
        "direction": "rtl",
        "default_currency": "IRT",
        "default": False,
    },
    "en": {
        "name": "English",
        "native_name": "English",
        "emoji": "🇬🇧",
        "direction": "ltr",
        "default_currency": "USD",
        "default": False,
    },
    "de": {
        "name": "German",
        "native_name": "Deutsch",
        "emoji": "🇩🇪",
        "direction": "ltr",
        "default_currency": "EUR",
        "default": False,
    },
    "zh": {
        "name": "Chinese",
        "native_name": "中文",
        "emoji": "🇨🇳",
        "direction": "ltr",
        "default_currency": "CNY",
        "default": False,
    },
}

SUPPORTED_CURRENCIES = ["IRT", "USD", "EUR", "CNY", "AED", "SAR"]

LocaleCode = Literal["fa", "ar", "en", "de", "zh"]


def get_direction(locale: str) -> str:
    return LOCALE_META.get(locale, LOCALE_META["fa"])["direction"]


def is_valid_locale(locale: str) -> bool:
    return locale in SUPPORTED_LOCALES


def is_valid_currency(currency: str) -> bool:
    return currency in SUPPORTED_CURRENCIES
