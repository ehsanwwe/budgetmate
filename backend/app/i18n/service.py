from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any, Optional

from app.i18n.config import DEFAULT_LOCALE, SUPPORTED_LOCALES

logger = logging.getLogger(__name__)

_DICT_DIR = os.path.join(os.path.dirname(__file__), "dictionaries")


@lru_cache(maxsize=None)
def _load_file_dict(locale: str) -> dict:
    path = os.path.join(_DICT_DIR, f"{locale}.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("i18n dictionary not found: %s", path)
        return {}
    except json.JSONDecodeError as exc:
        logger.error("i18n dictionary parse error %s: %s", path, exc)
        return {}


def _get_nested(d: dict, key: str) -> str | None:
    parts = key.split(".")
    node: Any = d
    for part in parts:
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    if isinstance(node, str):
        return node
    return None


def _interpolate(template: str, params: dict | None) -> str:
    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, ValueError):
        return template


class I18nService:
    def __init__(self) -> None:
        self._db_overrides: dict[str, dict[str, str]] = {}

    def load_db_overrides(self, db_entries: list[dict]) -> None:
        """Load active translation overrides from database. Call at startup or on cache invalidation."""
        overrides: dict[str, dict[str, str]] = {}
        for entry in db_entries:
            if not entry.get("is_active"):
                continue
            locale = entry["locale"]
            full_key = f"{entry['namespace']}.{entry['key']}"
            overrides.setdefault(locale, {})[full_key] = entry["value"]
        self._db_overrides = overrides

    def t(self, key: str, locale: str = DEFAULT_LOCALE, params: dict | None = None) -> str:
        if locale not in SUPPORTED_LOCALES:
            locale = DEFAULT_LOCALE

        # DB override wins
        locale_overrides = self._db_overrides.get(locale, {})
        if key in locale_overrides:
            return _interpolate(locale_overrides[key], params)

        # File dictionary
        value = _get_nested(_load_file_dict(locale), key)
        if value is not None:
            return _interpolate(value, params)

        # Fallback to fa
        if locale != DEFAULT_LOCALE:
            value = _get_nested(_load_file_dict(DEFAULT_LOCALE), key)
            if value is not None:
                if os.environ.get("APP_ENV") == "development":
                    logger.debug("i18n fallback to fa for key=%s locale=%s", key, locale)
                return _interpolate(value, params)

        # Last resort: return key itself (never crash production)
        logger.warning("i18n missing key=%s locale=%s", key, locale)
        return key


_service = I18nService()


def get_i18n_service() -> I18nService:
    return _service


def t(key: str, locale: str = DEFAULT_LOCALE, params: dict | None = None) -> str:
    return _service.t(key, locale, params)
