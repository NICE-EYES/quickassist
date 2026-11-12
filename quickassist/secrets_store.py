"""Хранение секретов в системном хранилище (Windows: Диспетчер учётных данных).

Если keyring недоступен, секреты живут только в памяти до выхода из программы,
а интерфейс показывает предупреждение. Значения секретов никогда не логируются.
"""
from __future__ import annotations

import logging
import secrets as _secrets

from quickassist import APP_NAME

log = logging.getLogger(__name__)

SECRET_NAMES = (
    "deepl_api_key",
    "libretranslate_api_key",
    "anthropic_api_key",
    "openai_api_key",
    "bridge_token",
)


class SecretStore:
    def __init__(self, service: str = APP_NAME, backend=None):
        self.service = service
        self._memory: dict[str, str] = {}
        self._keyring = backend
        self.persistent = False
        if self._keyring is None:
            try:
                import keyring  # noqa: WPS433
                from keyring.backends import fail

                if isinstance(keyring.get_keyring(), fail.Keyring):
                    raise RuntimeError("no keyring backend")
                self._keyring = keyring
            except Exception as exc:  # pragma: no cover - зависит от ОС
                log.warning("system keyring unavailable (%s); secrets kept in memory only", type(exc).__name__)
                self._keyring = None
        self.persistent = self._keyring is not None

    def get(self, name: str) -> str:
        if name in self._memory:
            return self._memory[name]
        value = ""
        if self._keyring is not None:
            try:
                value = self._keyring.get_password(self.service, name) or ""
            except Exception as exc:  # pragma: no cover
                log.warning("keyring read failed for %s (%s)", name, type(exc).__name__)
        self._memory[name] = value
        return value

    def set(self, name: str, value: str) -> None:
        value = (value or "").strip()
        self._memory[name] = value
        if self._keyring is None:
            return
        try:
            if value:
                self._keyring.set_password(self.service, name, value)
            else:
                try:
                    self._keyring.delete_password(self.service, name)
                except Exception:
                    pass
        except Exception as exc:  # pragma: no cover
            log.warning("keyring write failed for %s (%s)", name, type(exc).__name__)

    def has(self, name: str) -> bool:
        return bool(self.get(name))

    def bridge_token(self) -> str:
        token = self.get("bridge_token")
        if not token:
            token = self.regenerate_bridge_token()
        return token

    def regenerate_bridge_token(self) -> str:
        token = _secrets.token_urlsafe(32)
        self.set("bridge_token", token)
        log.info("bridge token generated")
        return token
