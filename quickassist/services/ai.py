"""Адаптеры языковых моделей.

* AnthropicProvider — официальный SDK `anthropic`; поддерживает изображения и
  серверный инструмент веб-поиска (ответ с реальными источниками).
* OpenAICompatProvider — любой сервис с OpenAI-совместимым /chat/completions
  (OpenAI, OpenRouter, локальные LM Studio/Ollama). Веб-поиска нет.

Ответ модели без веб-поиска всегда помечается в интерфейсе как «ответ модели»,
а не как результат интернет-поиска.
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field

import httpx2

from quickassist.services.errors import NotConfiguredError, ServiceError
from quickassist.services.http import make_client, request_json

log = logging.getLogger(__name__)

AI_TIMEOUT = 120.0
MAX_OUTPUT_TOKENS = 16_000


@dataclass
class Source:
    title: str
    url: str


@dataclass
class AIAnswer:
    text: str
    sources: list[Source] = field(default_factory=list)
    used_web_search: bool = False
    provider: str = ""


@dataclass
class ImageInput:
    data: bytes
    media_type: str = "image/png"


class AIProvider:
    name = "ИИ"
    supports_vision = False
    supports_web_search = False

    def ask(self, prompt: str, system: str | None = None, image: ImageInput | None = None,
            effort: str = "medium") -> AIAnswer:
        raise NotImplementedError

    def search_answer(self, query: str) -> AIAnswer:
        raise ServiceError("Этот провайдер ИИ не умеет искать в интернете.")


# ---------------------------------------------------------------- Anthropic

# Новый веб-поиск с динамической фильтрацией; если модель его не принимает —
# повторяем запрос с базовой версией инструмента и без параметра effort.
_WEB_SEARCH_TOOL = "web_search_20260209"
_BASIC_WEB_SEARCH_TOOL = "web_search_20250305"

SEARCH_SYSTEM = (
    "You are a research assistant inside a desktop quick-search panel. Search the web, then answer "
    "concisely in the language of the user's query. Base the answer on the search results and say "
    "plainly when the results do not answer the question."
)


class AnthropicProvider(AIProvider):
    supports_vision = True
    supports_web_search = True

    def __init__(self, api_key: str, model: str, web_search: bool = True, client=None):
        if not api_key:
            raise NotConfiguredError("Anthropic API не настроен: добавьте ключ в Настройки → ИИ.")
        import anthropic  # импорт здесь, чтобы базовые функции работали без SDK

        self._anthropic = anthropic
        if not model.strip():
            raise NotConfiguredError("Укажите имя модели Anthropic в Настройки → ИИ.")
        self.model = model.strip()
        self._legacy = False  # True — модель не понимает effort и новый веб-поиск
        self.name = f"Anthropic · {self.model}"
        self.supports_web_search = web_search
        self._client = client or anthropic.Anthropic(
            api_key=api_key,
            timeout=anthropic.Timeout(AI_TIMEOUT, connect=10.0),
            max_retries=1,
        )

    def _base_params(self, effort: str) -> dict:
        params: dict = {"model": self.model, "max_tokens": MAX_OUTPUT_TOKENS}
        if not self._legacy:
            params["output_config"] = {"effort": effort}
        return params

    def _web_search_tool(self) -> dict:
        tool_type = _BASIC_WEB_SEARCH_TOOL if self._legacy else _WEB_SEARCH_TOOL
        return {"type": tool_type, "name": "web_search", "max_uses": 5}

    def _to_legacy(self, params: dict) -> dict:
        """Параметры для моделей без effort и нового веб-поиска."""
        self._legacy = True
        params = {k: v for k, v in params.items() if k != "output_config"}
        if "tools" in params:
            params["tools"] = [self._web_search_tool()]
        return params

    def _call(self, params: dict, messages: list) -> object:
        a = self._anthropic
        try:
            try:
                return self._client.messages.create(messages=messages, **params)
            except a.BadRequestError:
                if self._legacy:
                    raise
                log.info("Модель отклонила запрос; повтор в режиме совместимости")
                params = self._to_legacy(params)
                return self._client.messages.create(messages=messages, **params)
        except a.AuthenticationError:
            raise ServiceError("Anthropic: ключ API отклонён. Проверьте ключ в настройках.") from None
        except a.PermissionDeniedError:
            raise ServiceError("Anthropic: у ключа нет доступа к этой модели или функции.") from None
        except a.NotFoundError:
            raise ServiceError(f"Anthropic: модель «{self.model}» не найдена. Проверьте имя модели.") from None
        except a.RateLimitError:
            raise ServiceError("Anthropic: превышен лимит запросов, повторите позже.") from None
        except a.BadRequestError as exc:
            msg = str(getattr(exc, "message", "")).lower()
            if "web_search" in msg or "web search" in msg:
                raise ServiceError(
                    "Anthropic: веб-поиск недоступен для этой организации/модели. "
                    "Включите его в консоли Anthropic или отключите в настройках."
                ) from None
            raise ServiceError("Anthropic: запрос отклонён (HTTP 400). Проверьте модель и параметры.") from None
        except a.APITimeoutError:
            raise ServiceError("Anthropic: превышено время ожидания ответа.") from None
        except a.APIStatusError as exc:
            raise ServiceError(f"Anthropic: ошибка сервиса (HTTP {exc.status_code}). Повторите позже.") from None
        except a.APIConnectionError:
            raise ServiceError("Anthropic: нет соединения с сервером. Проверьте интернет.") from None

    def _run(self, params: dict, messages: list) -> AIAnswer:
        response = self._call(params, messages)
        # Долгий ход с серверными инструментами может прийти с pause_turn — продолжаем.
        for _ in range(3):
            if getattr(response, "stop_reason", None) != "pause_turn":
                break
            messages = messages + [{
                "role": "assistant",
                "content": [b.model_dump(exclude_none=True) for b in response.content],
            }]
            response = self._call(params, messages)

        if getattr(response, "stop_reason", None) == "refusal":
            raise ServiceError("Модель отказалась отвечать на этот запрос.")

        texts: list[str] = []
        sources: list[Source] = []
        seen: set[str] = set()

        def add_source(url: str | None, title: str | None) -> None:
            if url and url.startswith(("https://", "http://")) and url not in seen:
                seen.add(url)
                sources.append(Source(title=(title or url).strip(), url=url))

        used_search = False
        for block in response.content:
            btype = getattr(block, "type", "")
            if btype == "text":
                texts.append(block.text)
                for c in getattr(block, "citations", None) or []:
                    add_source(getattr(c, "url", None), getattr(c, "title", None))
            elif btype == "web_search_tool_result":
                used_search = True
                content = getattr(block, "content", None)
                if isinstance(content, list):  # при ошибке поиска content — объект, а не список
                    for r in content:
                        add_source(getattr(r, "url", None), getattr(r, "title", None))
        text = "".join(texts).strip()
        if getattr(response, "stop_reason", None) == "max_tokens":
            text += "\n\n[Ответ обрезан по лимиту длины]"
        if not text:
            raise ServiceError("Модель вернула пустой ответ.")
        return AIAnswer(text=text, sources=sources, used_web_search=used_search, provider=self.name)

    def ask(self, prompt, system=None, image=None, effort="medium") -> AIAnswer:
        params = self._base_params(effort)
        if system:
            params["system"] = system
        content: list[dict] = []
        if image is not None:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image.media_type,
                    "data": base64.standard_b64encode(image.data).decode("ascii"),
                },
            })
        content.append({"type": "text", "text": prompt})
        return self._run(params, [{"role": "user", "content": content}])

    def search_answer(self, query: str) -> AIAnswer:
        if not self.supports_web_search:
            raise NotConfiguredError("Веб-поиск Anthropic отключён в настройках.")
        params = self._base_params("medium")
        params["tools"] = [self._web_search_tool()]
        params["system"] = SEARCH_SYSTEM
        answer = self._run(params, [{"role": "user", "content": query}])
        if not answer.used_web_search:
            # Модель ответила, не выполнив поиск: честно сообщаем об этом в UI.
            answer.sources = []
        return answer


# ---------------------------------------------------------- OpenAI-compatible

class OpenAICompatProvider(AIProvider):
    supports_vision = True  # зависит от модели; при ошибке пользователь увидит сообщение сервиса

    def __init__(self, base_url: str, api_key: str, model: str, transport: httpx2.BaseTransport | None = None):
        base_url = (base_url or "").strip().rstrip("/")
        if not base_url:
            raise NotConfiguredError("Укажите адрес OpenAI-совместимого API в Настройки → ИИ.")
        local = base_url.startswith(("http://127.0.0.1", "http://localhost"))
        if not base_url.startswith("https://") and not local:
            raise NotConfiguredError("Адрес API должен начинаться с https:// (http допускается только для localhost).")
        if not api_key and not local:
            raise NotConfiguredError("OpenAI-совместимый API не настроен: добавьте ключ в Настройки → ИИ.")
        if not model.strip():
            raise NotConfiguredError("Укажите имя модели в Настройки → ИИ.")
        self._url = base_url + "/chat/completions"
        self._key = api_key
        self.model = model.strip()
        self.name = f"{self.model}"
        self._transport = transport

    def ask(self, prompt, system=None, image=None, effort="medium") -> AIAnswer:
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        if image is not None:
            data_url = f"data:{image.media_type};base64," + base64.b64encode(image.data).decode("ascii")
            messages.append({"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]})
        else:
            messages.append({"role": "user", "content": prompt})
        headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
        with make_client(AI_TIMEOUT, self._transport) as client:
            data = request_json(client, "POST", self._url, "API ИИ", headers=headers,
                                json={"model": self.model, "messages": messages})
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ServiceError("API ИИ вернул ответ в неожиданном формате.") from None
        if not text.strip():
            raise ServiceError("Модель вернула пустой ответ.")
        return AIAnswer(text=text.strip(), provider=self.name)
