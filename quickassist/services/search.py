"""Обычный веб-поиск: построение URL выбранной поисковой системы."""
from __future__ import annotations

from urllib.parse import quote_plus, urlparse

SEARCH_ENGINES: dict[str, tuple[str, str]] = {
    "google": ("Google", "https://www.google.com/search?q={query}"),
    "yandex": ("Яндекс", "https://yandex.ru/search/?text={query}"),
    "bing": ("Bing", "https://www.bing.com/search?q={query}"),
    "duckduckgo": ("DuckDuckGo", "https://duckduckgo.com/?q={query}"),
    "custom": ("Свой шаблон", ""),
}

MAX_QUERY_CHARS = 1500


def validate_custom_template(template: str) -> str | None:
    """Возвращает текст ошибки или None, если шаблон корректен."""
    template = (template or "").strip()
    if "{query}" not in template:
        return "Шаблон должен содержать {query}."
    parsed = urlparse(template.replace("{query}", "x"))
    if parsed.scheme != "https" or not parsed.netloc:
        return "Шаблон должен начинаться с https://"
    return None


def build_search_url(query: str, engine: str, custom_template: str = "") -> str:
    query = " ".join((query or "").split())[:MAX_QUERY_CHARS]
    if not query:
        raise ValueError("empty query")
    if engine == "custom":
        if validate_custom_template(custom_template):
            engine = "google"
        else:
            return custom_template.strip().replace("{query}", quote_plus(query))
    template = SEARCH_ENGINES.get(engine, SEARCH_ENGINES["google"])[1]
    return template.replace("{query}", quote_plus(query))
