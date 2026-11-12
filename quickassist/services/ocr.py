"""Адаптеры OCR (распознавания текста). Это НЕ обратный поиск и НЕ анализ моделью.

* WindowsOCR — встроенный офлайн-движок Windows.Media.Ocr (Windows 10/11).
  Нужны пакеты из requirements-ocr-windows.txt и установленный языковой пакет
  с компонентом распознавания текста. Изображение не покидает компьютер.
* AIVisionOCR — распознавание через модель с поддержкой изображений
  (изображение отправляется провайдеру ИИ, требуется согласие пользователя).
"""
from __future__ import annotations

import asyncio
import sys

from quickassist.services.ai import AIProvider, ImageInput
from quickassist.services.errors import NotConfiguredError, ServiceError


class WindowsOCR:
    name = "Windows OCR (локально)"
    sends_externally = False

    def __init__(self, lang: str = ""):
        self.lang = lang.strip()

    @staticmethod
    def availability() -> str | None:
        """None — доступно, иначе текст причины."""
        if sys.platform != "win32":
            return "Windows OCR доступен только в Windows."
        try:
            import winrt.windows.media.ocr  # noqa: F401
            import winrt.windows.graphics.imaging  # noqa: F401
            import winrt.windows.storage.streams  # noqa: F401
        except Exception:
            return "Не установлены пакеты Windows OCR: pip install -r requirements-ocr-windows.txt"
        return None

    def recognize(self, bgra: bytes, width: int, height: int) -> str:
        reason = self.availability()
        if reason:
            raise NotConfiguredError(reason)
        try:
            import ctypes

            ctypes.windll.combase.RoInitialize(1)  # MTA для рабочего потока; повторный вызов безопасен
        except Exception:
            pass
        return asyncio.run(self._recognize(bgra, width, height))

    async def _recognize(self, bgra: bytes, width: int, height: int) -> str:
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter

        engine = None
        if self.lang:
            language = Language(self.lang)
            if OcrEngine.is_language_supported(language):
                engine = OcrEngine.try_create_from_language(language)
        if engine is None:
            engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            raise NotConfiguredError(
                "В Windows нет языка с распознаванием текста. Добавьте язык: Параметры → Время и язык → "
                "Язык и регион → Добавить язык (с компонентом «Оптическое распознавание символов»)."
            )
        writer = DataWriter()
        writer.write_bytes(bgra)
        buffer = writer.detach_buffer()
        bitmap = SoftwareBitmap.create_copy_from_buffer(
            buffer, BitmapPixelFormat.BGRA8, width, height, BitmapAlphaMode.PREMULTIPLIED
        )
        result = await engine.recognize_async(bitmap)
        return "\n".join(line.text for line in result.lines).strip()


class AIVisionOCR:
    sends_externally = True

    def __init__(self, provider: AIProvider | None):
        if provider is None:
            raise NotConfiguredError("OCR через ИИ не настроен: выберите провайдера ИИ в Настройки → ИИ.")
        if not provider.supports_vision:
            raise NotConfiguredError("Выбранный провайдер ИИ не поддерживает изображения.")
        self._provider = provider
        self.name = f"ИИ ({provider.name})"

    def recognize_png(self, png: bytes) -> str:
        answer = self._provider.ask(
            "Extract all text from this image exactly as written, preserving line breaks. "
            "Output only the extracted text. If there is no text, output nothing.",
            image=ImageInput(png, "image/png"),
            effort="low",
        )
        text = answer.text.strip()
        if not text:
            raise ServiceError("Текст на изображении не найден.")
        return text
