import json
from types import SimpleNamespace

import httpx2
import pytest

from quickassist.secrets_store import SecretStore
from quickassist.services.ai import AnthropicProvider, OpenAICompatProvider
from quickassist.services.errors import NotConfiguredError, ServiceError
from quickassist.services.translate import AITranslator, DeepLTranslator, LibreTranslator


def mock(handler):
    return httpx2.MockTransport(handler)


def test_deepl_free_endpoint_and_parse():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["auth"] = req.headers["Authorization"]
        seen["body"] = json.loads(req.content)
        return httpx2.Response(200, json={"translations": [{"detected_source_language": "EN", "text": "Привет"}]})

    r = DeepLTranslator("k:fx", 5, mock(handler)).translate("Hello", "ru")
    assert r.text == "Привет" and r.detected_lang == "en"
    assert seen["url"] == "https://api-free.deepl.com/v2/translate"
    assert seen["auth"] == "DeepL-Auth-Key k:fx"
    assert seen["body"] == {"text": ["Hello"], "target_lang": "RU"}


def test_deepl_errors():
    t = DeepLTranslator("k", 5, mock(lambda r: httpx2.Response(403)))
    with pytest.raises(ServiceError, match="ключ"):
        t.translate("x", "ru")
    with pytest.raises(NotConfiguredError):
        DeepLTranslator("", 5)

    def boom(req):
        raise httpx2.ConnectTimeout("t")
    with pytest.raises(ServiceError, match="время"):
        DeepLTranslator("k", 5, mock(boom)).translate("x", "ru")


def test_libretranslate():
    def handler(req):
        body = json.loads(req.content)
        assert body["source"] == "auto" and body["target"] == "ru" and body["api_key"] == "kk"
        return httpx2.Response(200, json={"translatedText": "мир", "detectedLanguage": {"language": "en", "confidence": 90}})
    r = LibreTranslator("https://lt.example/", "kk", 5, mock(handler)).translate("world", "ru")
    assert r.text == "мир" and r.detected_lang == "en"
    with pytest.raises(NotConfiguredError):
        LibreTranslator("http://remote.example", "", 5)


def test_openai_compat_and_ai_translator():
    def handler(req):
        body = json.loads(req.content)
        assert str(req.url) == "http://localhost:1234/v1/chat/completions"
        assert body["messages"][0]["role"] == "system"
        return httpx2.Response(200, json={"choices": [{"message": {"content": " Привет "}}]})
    p = OpenAICompatProvider("http://localhost:1234/v1", "", "local-model", mock(handler))
    assert AITranslator(p).translate("Hi", "ru").text == "Привет"
    with pytest.raises(NotConfiguredError):
        OpenAICompatProvider("http://remote.example/v1", "k", "m")


class FakeAnthropicClient:
    def __init__(self, response):
        self.calls = []
        self.response = response
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        return self.response


def blk(**kw):
    return SimpleNamespace(**kw)


def test_anthropic_web_answer_collects_real_sources():
    resp = SimpleNamespace(stop_reason="end_turn", content=[
        blk(type="server_tool_use"),
        blk(type="web_search_tool_result", content=[blk(url="https://a.example", title="A"), blk(url="https://b.example", title="B")]),
        blk(type="text", text="Ответ", citations=[blk(url="https://a.example", title="A")]),
    ])
    client = FakeAnthropicClient(resp)
    p = AnthropicProvider("key", "test-model", True, client=client)
    a = p.search_answer("что нового")
    assert a.used_web_search and [s.url for s in a.sources] == ["https://a.example", "https://b.example"]
    call = client.calls[0]
    assert call["tools"][0]["type"] == "web_search_20260209"
    assert call["output_config"] == {"effort": "medium"}


def test_anthropic_answer_without_search_has_no_sources_and_refusal():
    resp = SimpleNamespace(stop_reason="end_turn", content=[blk(type="text", text="Просто ответ", citations=None)])
    p = AnthropicProvider("key", "test-model", True, client=FakeAnthropicClient(resp))
    a = p.search_answer("q")
    assert not a.used_web_search and a.sources == []
    refused = SimpleNamespace(stop_reason="refusal", content=[])
    with pytest.raises(ServiceError, match="отказалась"):
        AnthropicProvider("key", "test-model", client=FakeAnthropicClient(refused)).ask("q")


def test_anthropic_legacy_model_retry(monkeypatch):
    import anthropic

    class Rejected(Exception):
        pass

    monkeypatch.setattr(anthropic, "BadRequestError", Rejected)
    ok = SimpleNamespace(stop_reason="end_turn", content=[blk(type="text", text="ok", citations=None)])
    client = FakeAnthropicClient(ok)
    first = [True]

    def create(**kw):
        client.calls.append(kw)
        if first[0]:
            first[0] = False
            raise Rejected()
        return ok

    client.messages = SimpleNamespace(create=create)
    p = AnthropicProvider("key", "older-model", True, client=client)
    p.search_answer("q")
    assert "output_config" in client.calls[0]
    assert client.calls[0]["tools"][0]["type"] == "web_search_20260209"
    assert "output_config" not in client.calls[1]
    assert client.calls[1]["tools"][0]["type"] == "web_search_20250305"


def test_anthropic_requires_model():
    with pytest.raises(NotConfiguredError):
        AnthropicProvider("key", "  ", client=FakeAnthropicClient(None))


class DictKeyring:
    def __init__(self):
        self.d = {}

    def get_password(self, s, n):
        return self.d.get((s, n))

    def set_password(self, s, n, v):
        self.d[(s, n)] = v

    def delete_password(self, s, n):
        self.d.pop((s, n), None)


def test_secret_store():
    kr = DictKeyring()
    st = SecretStore("T", backend=kr)
    st.set("deepl_api_key", " abc ")
    assert SecretStore("T", backend=kr).get("deepl_api_key") == "abc"
    st.set("deepl_api_key", "")
    assert not SecretStore("T", backend=kr).has("deepl_api_key")
    tok = st.bridge_token()
    assert len(tok) > 30 and st.bridge_token() == tok
