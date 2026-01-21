"""
i18n internationalization module
Supports English and Chinese switching, default is English
"""

import streamlit as st
import json
from pathlib import Path

# Default language
DEFAULT_LANGUAGE = "en"

# Cache for loaded translations
_translations_cache = {}


def _load_translations(lang: str) -> dict:
    """
    Load translations from JSON file

    Args:
        lang: Language code (e.g., 'en', 'zh')

    Returns:
        Translation dictionary
    """
    if lang in _translations_cache:
        return _translations_cache[lang]

    try:
        # Get the path to the locales directory
        locales_dir = Path(__file__).parent / "locales"
        locale_file = locales_dir / f"{lang}.json"

        with open(locale_file, "r", encoding="utf-8") as f:
            translations = json.load(f)
            _translations_cache[lang] = translations
            return translations
    except FileNotFoundError:
        # Fallback to English if translation file not found
        if lang != DEFAULT_LANGUAGE:
            return _load_translations(DEFAULT_LANGUAGE)
        return {}
    except json.JSONDecodeError:
        return {}


def init_i18n():
    """Initialize i18n, set default language to English"""
    if "language" not in st.session_state:
        st.session_state.language = DEFAULT_LANGUAGE


def get_current_language() -> str:
    """Get current language"""
    return st.session_state.get("language", DEFAULT_LANGUAGE)


def set_language(lang: str):
    """
    Set language

    Args:
        lang: Language code (e.g., 'en', 'zh')
    """
    st.session_state.language = lang


def t(key: str, **kwargs) -> str:
    """
    Get translated text

    Args:
        key: Translation key
        **kwargs: Format parameters

    Returns:
        Translated text
    """
    lang = get_current_language()
    translations = _load_translations(lang)
    text = translations.get(key, key)

    # Format parameters
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text

    return text


def get_language_options() -> list:
    """
    Get available language options

    Returns:
        List of (lang_code, lang_name) tuples
    """
    return [
        ("en", t("english")),
        ("zh", t("chinese")),
    ]


def get_available_languages() -> list:
    """
    Get all available language codes from locales directory

    Returns:
        List of language codes
    """
    locales_dir = Path(__file__).parent / "locales"
    if not locales_dir.exists():
        return [DEFAULT_LANGUAGE]

    languages = []
    for file in locales_dir.glob("*.json"):
        languages.append(file.stem)

    return languages if languages else [DEFAULT_LANGUAGE]
