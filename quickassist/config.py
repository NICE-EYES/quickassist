"""Настройки приложения: JSON-файл без секретов.

Секреты (API-ключи, токен моста) хранятся отдельно — см. secrets_store.py.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from quickassist import APP_NAME

log = logging.getLogger(__name__)

DEFAULT_HOTKEY = "Alt+Space"
FALLBACK_HOTKEY = "Ctrl+Alt+Space"
DEFAULT_BRIDGE_PORT = 48731

TRANSLATE_PROVIDERS = ("browser", "deepl", "libretranslate", "ai")
AI_PROVIDERS = ("none", "anthropic", "openai_compat")
OCR_PROVIDERS = ("windows", "ai")
THEMES = ("system", "light", "dark")
MODES = ("translate", "search", "image", "ask")


@dataclass
class Settings:
    # Общие
    hotkey: str = DEFAULT_HOTKEY
    theme: str = "system"
    autostart: bool = False
    capture_selection: bool = True       # копировать выделение при вызове (с восстановлением буфера)
    last_mode: str = "translate"
    network_timeout: int = 30            # секунды для перевода/OCR; ИИ получает больше

    # Перевод
    target_lang: str = "ru"
    translate_provider: str = "browser"  # browser | deepl | libretranslate | ai
    libretranslate_url: str = ""

    # Поиск
    search_engine: str = "google"
    custom_search_url: str = ""          # https://example.com/search?q={query}

    # ИИ
    ai_provider: str = "none"            # none | anthropic | openai_compat
    anthropic_model: str = ""            # имя модели вводит пользователь
    anthropic_web_search: bool = True
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    # Изображения
    ocr_provider: str = "windows"        # windows | ai
    ocr_lang: str = ""                   # "" = языки профиля Windows
    reverse_image_service: str = "google"

    # Браузер
    bridge_enabled: bool = True
    bridge_port: int = DEFAULT_BRIDGE_PORT
    bridge_allowed_extension_id: str = ""

    def normalized(self) -> "Settings":
        """Возвращает копию с исправленными недопустимыми значениями."""
        s = Settings(**asdict(self))
        d = Settings()
        if s.theme not in THEMES:
            s.theme = d.theme
        if s.translate_provider not in TRANSLATE_PROVIDERS:
            s.translate_provider = d.translate_provider
        if s.ai_provider not in AI_PROVIDERS:
            s.ai_provider = d.ai_provider
        if s.ocr_provider not in OCR_PROVIDERS:
            s.ocr_provider = d.ocr_provider
        if s.last_mode not in MODES:
            s.last_mode = d.last_mode
        if not (1024 <= int(s.bridge_port) <= 65535):
            s.bridge_port = d.bridge_port
        s.network_timeout = max(5, min(int(s.network_timeout), 120))
        s.bridge_allowed_extension_id = s.bridge_allowed_extension_id.strip().lower()
        if not s.hotkey.strip():
            s.hotkey = d.hotkey
        return s


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / APP_NAME


def log_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / APP_NAME / "logs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / APP_NAME
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / APP_NAME / "logs"


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (config_dir() / "settings.json")

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("settings root is not an object")
        except (OSError, ValueError) as exc:
            log.warning("settings file unreadable, defaults used (%s)", type(exc).__name__)
            return Settings()
        defaults = Settings()
        values = {}
        for f in fields(Settings):
            if f.name not in raw:
                continue
            default_value = getattr(defaults, f.name)
            value = raw[f.name]
            # Простая проверка типа: значение должно совпадать с типом значения по умолчанию.
            if isinstance(default_value, bool):
                if isinstance(value, bool):
                    values[f.name] = value
            elif isinstance(default_value, int):
                if isinstance(value, int) and not isinstance(value, bool):
                    values[f.name] = value
            elif isinstance(value, type(default_value)):
                values[f.name] = value
        return Settings(**values).normalized()

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(asdict(settings.normalized()), ensure_ascii=False, indent=2)
        # Атомарная запись: временный файл + замена.
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".settings-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(data)
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
