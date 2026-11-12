"""Общие объекты приложения, которые передаются в окна."""
from __future__ import annotations

from dataclasses import dataclass, field

from quickassist.config import Settings, SettingsStore
from quickassist.secrets_store import SecretStore
from quickassist.services.hub import ServiceHub
from quickassist.tasks import TaskRunner


@dataclass
class AppContext:
    settings: Settings
    store: SettingsStore
    secrets: SecretStore
    hub: ServiceHub
    tasks: TaskRunner
    # Согласия на отправку изображений внешним сервисам — только до перезапуска.
    image_consents: set = field(default_factory=set)

    def save_settings(self, settings: Settings) -> None:
        self.settings = settings.normalized()
        self.hub.settings = self.settings
        self.store.save(self.settings)
