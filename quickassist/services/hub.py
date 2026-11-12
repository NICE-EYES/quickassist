"""Сборка адаптеров из текущих настроек. UI обращается к сервисам только через ServiceHub."""
from __future__ import annotations

from quickassist.config import Settings
from quickassist.secrets_store import SecretStore
from quickassist.services.ai import AIProvider, AnthropicProvider, OpenAICompatProvider
from quickassist.services.errors import NotConfiguredError
from quickassist.services.ocr import AIVisionOCR, WindowsOCR
from quickassist.services.translate import AITranslator, DeepLTranslator, LibreTranslator


class ServiceHub:
    def __init__(self, settings: Settings, secrets: SecretStore):
        self.settings = settings
        self.secrets = secrets

    # ---- ИИ
    def ai_status(self) -> str | None:
        """None — ИИ настроен, иначе описание, чего не хватает."""
        s = self.settings
        if s.ai_provider == "none":
            return "ИИ не подключён (Настройки → ИИ)."
        if s.ai_provider == "anthropic" and not self.secrets.has("anthropic_api_key"):
            return "Не задан ключ Anthropic API (Настройки → ИИ)."
        if s.ai_provider == "anthropic" and not s.anthropic_model.strip():
            return "Не указана модель Anthropic (Настройки → ИИ)."
        if s.ai_provider == "openai_compat":
            local = s.openai_base_url.startswith(("http://127.0.0.1", "http://localhost"))
            if not local and not self.secrets.has("openai_api_key"):
                return "Не задан ключ OpenAI-совместимого API (Настройки → ИИ)."
        return None

    def ai(self) -> AIProvider:
        s = self.settings
        if s.ai_provider == "anthropic":
            return AnthropicProvider(self.secrets.get("anthropic_api_key"), s.anthropic_model, s.anthropic_web_search)
        if s.ai_provider == "openai_compat":
            return OpenAICompatProvider(s.openai_base_url, self.secrets.get("openai_api_key"), s.openai_model)
        raise NotConfiguredError("ИИ не подключён: выберите провайдера в Настройки → ИИ.")

    def ai_or_none(self) -> AIProvider | None:
        try:
            return self.ai()
        except NotConfiguredError:
            return None

    def web_answer_status(self) -> str | None:
        s = self.settings
        if s.ai_provider != "anthropic":
            return "Ответ с источниками требует Anthropic API с веб-поиском (Настройки → ИИ)."
        if not s.anthropic_web_search:
            return "Веб-поиск Anthropic отключён в настройках."
        return self.ai_status()

    # ---- Перевод
    def translator_in_app_available(self) -> bool:
        return self.settings.translate_provider != "browser"

    def translator(self):
        s = self.settings
        t = s.network_timeout
        if s.translate_provider == "deepl":
            return DeepLTranslator(self.secrets.get("deepl_api_key"), t)
        if s.translate_provider == "libretranslate":
            return LibreTranslator(s.libretranslate_url, self.secrets.get("libretranslate_api_key"), t)
        if s.translate_provider == "ai":
            return AITranslator(self.ai_or_none())
        raise NotConfiguredError(
            "Перевод внутри программы не настроен. Сейчас доступен перевод в браузере (Ctrl+Enter). "
            "Подключите DeepL, LibreTranslate или ИИ в Настройки → Перевод."
        )

    # ---- OCR
    def ocr(self):
        if self.settings.ocr_provider == "ai":
            return AIVisionOCR(self.ai_or_none())
        return WindowsOCR(self.settings.ocr_lang)
