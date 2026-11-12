"""Языки перевода (код ISO 639-1 → название)."""

LANGUAGES = {
    "ru": "Русский",
    "en": "Английский",
    "uk": "Украинский",
    "de": "Немецкий",
    "fr": "Французский",
    "es": "Испанский",
    "it": "Итальянский",
    "pt": "Португальский",
    "pl": "Польский",
    "tr": "Турецкий",
    "zh": "Китайский",
    "ja": "Японский",
    "ko": "Корейский",
    "ar": "Арабский",
    "nl": "Нидерландский",
    "cs": "Чешский",
    "kk": "Казахский",
}

# Английские названия для промптов модели
ENGLISH_NAMES = {
    "ru": "Russian", "en": "English", "uk": "Ukrainian", "de": "German", "fr": "French",
    "es": "Spanish", "it": "Italian", "pt": "Portuguese", "pl": "Polish", "tr": "Turkish",
    "zh": "Chinese (Simplified)", "ja": "Japanese", "ko": "Korean", "ar": "Arabic",
    "nl": "Dutch", "cs": "Czech", "kk": "Kazakh",
}


def language_name(code: str) -> str:
    return LANGUAGES.get((code or "").lower(), code or "?")
