"""Ошибки внешних сервисов с понятными пользователю сообщениями (на русском)."""


class ServiceError(Exception):
    """Ошибка, текст которой можно показать пользователю."""

    def __init__(self, message: str):
        super().__init__(message)
        self.user_message = message


class NotConfiguredError(ServiceError):
    """Функция требует ключ/компонент, который не настроен."""


def user_message(exc: BaseException) -> str:
    if isinstance(exc, ServiceError):
        return exc.user_message
    return f"Непредвиденная ошибка ({type(exc).__name__}). Подробности не сохраняются в лог."
