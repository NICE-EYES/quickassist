import pytest

from quickassist.platform.hotkey import HotkeyParseError, parse_hotkey
from quickassist.services.search import build_search_url, validate_custom_template
from quickassist.services.translate import browser_translate_url


def test_search_urls():
    assert build_search_url("привет мир", "google") == "https://www.google.com/search?q=%D0%BF%D1%80%D0%B8%D0%B2%D0%B5%D1%82+%D0%BC%D0%B8%D1%80"
    assert build_search_url("a&b", "yandex") == "https://yandex.ru/search/?text=a%26b"
    assert build_search_url("x", "custom", "https://s.example/?q={query}") == "https://s.example/?q=x"
    assert build_search_url("x", "custom", "javascript:{query}").startswith("https://www.google.com/")
    with pytest.raises(ValueError):
        build_search_url("   ", "google")


def test_custom_template_validation():
    assert validate_custom_template("https://a.b/?q={query}") is None
    assert validate_custom_template("http://a.b/?q={query}")
    assert validate_custom_template("https://a.b/")


def test_browser_translate_url():
    url = browser_translate_url("Hello world", "ru")
    assert url == "https://translate.google.com/?sl=auto&tl=ru&text=Hello%20world&op=translate"


@pytest.mark.parametrize("text,canonical,vk", [
    ("Alt+Space", "Alt+Space", 0x20),
    ("ctrl + alt + q", "Ctrl+Alt+Q", ord("Q")),
    ("Win+Shift+F12", "Shift+Win+F12", 0x7B),
    ("F9", "F9", 0x78),
    ("Ctrl+`", "Ctrl+`", 0xC0),
])
def test_hotkey_parse_ok(text, canonical, vk):
    _, code, name = parse_hotkey(text)
    assert name == canonical and code == vk


@pytest.mark.parametrize("text", ["", "Q", "Shift+A", "Ctrl+", "Ctrl+Alt", "Hyper+Q", "Ctrl+Ü"])
def test_hotkey_parse_errors(text):
    with pytest.raises(HotkeyParseError):
        parse_hotkey(text)
