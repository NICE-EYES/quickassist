import json

from quickassist.config import Settings, SettingsStore


def test_roundtrip(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    s = Settings(target_lang="en", translate_provider="deepl", bridge_port=50000)
    store.save(s)
    loaded = store.load()
    assert loaded.target_lang == "en" and loaded.translate_provider == "deepl" and loaded.bridge_port == 50000


def test_bad_values_are_normalized(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"theme": "neon", "bridge_port": 80, "autostart": "yes", "unknown": 1, "network_timeout": 999}))
    s = SettingsStore(p).load()
    assert s.theme == "system" and s.bridge_port == 48731 and s.autostart is False and s.network_timeout == 120


def test_corrupt_file_gives_defaults(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{not json")
    assert SettingsStore(p).load() == Settings()


def test_no_secrets_in_settings_file(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    store.save(Settings())
    text = (tmp_path / "s.json").read_text()
    assert "api_key" not in text and "token" not in text
