"""Обратный поиск изображений (поиск похожих / источника).

Публичных бесплатных API для загрузки изображения у Google Lens, Яндекс Картинок и
Bing нет, поэтому программа НЕ отправляет изображение сама: она копирует его в буфер
обмена (с согласия пользователя) и открывает страницу сервиса, где пользователь
вставляет изображение вручную. Это честный, работающий сценарий без выдуманных endpoint.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReverseImageService:
    key: str
    title: str
    url: str
    steps: str


REVERSE_IMAGE_SERVICES: dict[str, ReverseImageService] = {
    "google": ReverseImageService(
        "google", "Google Объектив", "https://images.google.com/",
        "Нажмите значок камеры («Поиск по картинке») и вставьте изображение: Ctrl+V.",
    ),
    "yandex": ReverseImageService(
        "yandex", "Яндекс Картинки", "https://yandex.ru/images/",
        "Нажмите значок камеры рядом со строкой поиска и вставьте изображение: Ctrl+V.",
    ),
    "bing": ReverseImageService(
        "bing", "Bing Визуальный поиск", "https://www.bing.com/visualsearch",
        "Нажмите в область загрузки и вставьте изображение: Ctrl+V.",
    ),
    "tineye": ReverseImageService(
        "tineye", "TinEye", "https://tineye.com/",
        "Вставьте изображение на странице (Ctrl+V) или нажмите «Upload» и выберите сохранённый файл.",
    ),
}
