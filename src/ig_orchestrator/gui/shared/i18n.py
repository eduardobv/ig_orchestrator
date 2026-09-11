from __future__ import annotations

import json
from pathlib import Path


LOCALES_DIR = Path(__file__).with_name("locales")
SUPPORTED_LANGUAGES = ("es", "en")
DEFAULT_LANGUAGE = "es"

_current = DEFAULT_LANGUAGE
_catalog: dict[str, str] = {}


def available_languages() -> tuple[str, ...]:
    return SUPPORTED_LANGUAGES


def current_language() -> str:
    return _current


def load_language(language: str) -> str:
    """Load a locale catalog. Unknown codes fall back to Spanish."""

    global _current, _catalog
    code = language.strip().lower() if language else DEFAULT_LANGUAGE
    if code not in SUPPORTED_LANGUAGES:
        code = DEFAULT_LANGUAGE
    path = LOCALES_DIR / f"{code}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Locale file is not an object: {path}")
    _catalog = {str(key): str(value) for key, value in payload.items()}
    _current = code
    return code


def t(key: str, **values: object) -> str:
    template = _catalog.get(key, key)
    if values:
        return template.format(**values)
    return template


def locale_keys(language: str) -> set[str]:
    path = LOCALES_DIR / f"{language}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(key) for key in payload}


load_language(DEFAULT_LANGUAGE)


__all__ = [
    "DEFAULT_LANGUAGE",
    "SUPPORTED_LANGUAGES",
    "available_languages",
    "current_language",
    "load_language",
    "locale_keys",
    "t",
]
