"""Окно настроек."""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from quickassist.config import DEFAULT_HOTKEY, FALLBACK_HOTKEY, Settings
from quickassist.context import AppContext
from quickassist.languages import LANGUAGES
from quickassist.platform import autostart
from quickassist.platform.hotkey import HotkeyParseError, parse_hotkey
from quickassist.services.ocr import WindowsOCR
from quickassist.services.reverse_image import REVERSE_IMAGE_SERVICES
from quickassist.services.search import SEARCH_ENGINES, validate_custom_template

HOTKEY_PRESETS = [DEFAULT_HOTKEY, FALLBACK_HOTKEY, "Ctrl+Shift+Space", "Alt+Q", "Ctrl+Alt+Q", "Win+Shift+Q", "F9"]


def _muted(text: str) -> QLabel:
    lbl = QLabel(text, objectName="Muted")
    lbl.setWordWrap(True)
    lbl.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
    lbl.setOpenExternalLinks(True)
    return lbl


class SecretField(QWidget):
    """Поле ключа: показывает только факт наличия; новое значение вводится явно."""

    def __init__(self, has_value: bool):
        super().__init__()
        l = QHBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setPlaceholderText("сохранён — введите новый, чтобы заменить" if has_value else "не задан")
        self.clear_box = QCheckBox("Удалить")
        self.clear_box.setVisible(has_value)
        l.addWidget(self.edit, 1)
        l.addWidget(self.clear_box)

    def new_value(self) -> str | None:
        """None — не менять; '' — удалить; иначе новое значение."""
        if self.clear_box.isChecked():
            return ""
        v = self.edit.text().strip()
        return v or None


class SettingsDialog(QDialog):
    # (новые настройки, новые секреты) — применяет приложение; при ошибке диалог остаётся открытым
    applyRequested = Signal(object, object)

    def __init__(self, ctx: AppContext, bridge_status: str, parent=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint)
        self.ctx = ctx
        self.setWindowTitle("Настройки — Быстрый помощник")
        self.setMinimumWidth(620)
        s = ctx.settings
        sec = ctx.secrets

        tabs = QTabWidget()
        tabs.addTab(self._general_tab(s), "Общие")
        tabs.addTab(self._translate_tab(s, sec), "Перевод")
        tabs.addTab(self._search_tab(s), "Поиск")
        tabs.addTab(self._ai_tab(s, sec), "ИИ")
        tabs.addTab(self._image_tab(s), "Изображения")
        tabs.addTab(self._bridge_tab(s, bridge_status), "Браузер")

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        if not sec.persistent:
            warn = QLabel("⚠ Системное хранилище ключей недоступно: ключи будут храниться только до выхода из программы.")
            warn.setWordWrap(True)
            layout.addWidget(warn)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    # ---------------------------------------------------------------- вкладки
    def _general_tab(self, s: Settings) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.hotkey = QComboBox()
        self.hotkey.setEditable(True)
        self.hotkey.addItems(HOTKEY_PRESETS)
        self.hotkey.setCurrentText(s.hotkey)
        f.addRow("Горячая клавиша:", self.hotkey)
        f.addRow("", _muted("Формат: Ctrl+Alt+Space, Alt+Q, Win+Shift+Q, F9. Alt+Space может конфликтовать "
                            "с PowerToys Run или системным меню окна — тогда выберите другое сочетание."))
        self.theme = QComboBox()
        for key, title in (("system", "Как в системе"), ("light", "Светлая"), ("dark", "Тёмная")):
            self.theme.addItem(title, key)
        self.theme.setCurrentIndex(self.theme.findData(s.theme))
        f.addRow("Тема:", self.theme)
        self.capture = QCheckBox("Подставлять выделенный текст при вызове")
        self.capture.setChecked(s.capture_selection)
        f.addRow("", self.capture)
        f.addRow("", _muted("Программа на мгновение копирует выделение (Ctrl+C) и сразу восстанавливает прежнее "
                            "содержимое буфера. Журнал буфера Windows (Win+V) может увидеть временную копию. "
                            "В окнах терминалов захват не выполняется."))
        self.autostart = QCheckBox("Запускать при входе в Windows")
        self.autostart.setChecked(autostart.is_enabled() if autostart.supported() else False)
        self.autostart.setEnabled(autostart.supported())
        f.addRow("", self.autostart)
        self.timeout = QSpinBox()
        self.timeout.setRange(5, 120)
        self.timeout.setSuffix(" с")
        self.timeout.setValue(s.network_timeout)
        f.addRow("Тайм-аут сети:", self.timeout)
        return w

    def _translate_tab(self, s: Settings, sec) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.target_lang = QComboBox()
        for code, name in LANGUAGES.items():
            self.target_lang.addItem(name, code)
        self.target_lang.setCurrentIndex(max(0, self.target_lang.findData(s.target_lang)))
        f.addRow("Язык перевода:", self.target_lang)
        self.tr_provider = QComboBox()
        for key, title in (("browser", "Браузер — Google Переводчик (без ключа)"), ("deepl", "DeepL API"),
                           ("libretranslate", "LibreTranslate"), ("ai", "Через подключённый ИИ")):
            self.tr_provider.addItem(title, key)
        self.tr_provider.setCurrentIndex(self.tr_provider.findData(s.translate_provider))
        f.addRow("Сервис:", self.tr_provider)
        self.deepl_key = SecretField(sec.has("deepl_api_key"))
        f.addRow("Ключ DeepL:", self.deepl_key)
        f.addRow("", _muted("Бесплатный ключ DeepL API Free (500 000 символов/мес.): "
                            "<a href='https://www.deepl.com/pro-api'>deepl.com/pro-api</a>. Ключи Free оканчиваются на «:fx»."))
        self.libre_url = QLineEdit(s.libretranslate_url)
        self.libre_url.setPlaceholderText("https://translate.example.com или http://localhost:5000")
        f.addRow("Адрес LibreTranslate:", self.libre_url)
        self.libre_key = SecretField(sec.has("libretranslate_api_key"))
        f.addRow("Ключ LibreTranslate:", self.libre_key)
        return w

    def _search_tab(self, s: Settings) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.engine = QComboBox()
        for key, (title, _) in SEARCH_ENGINES.items():
            self.engine.addItem(title, key)
        self.engine.setCurrentIndex(self.engine.findData(s.search_engine))
        f.addRow("Поисковая система:", self.engine)
        self.custom_url = QLineEdit(s.custom_search_url)
        self.custom_url.setPlaceholderText("https://example.com/search?q={query}")
        f.addRow("Свой шаблон:", self.custom_url)
        f.addRow("", _muted("«Ответ ИИ с источниками» в режиме «Поиск» использует веб-поиск Anthropic (вкладка «ИИ»)."))
        return w

    def _ai_tab(self, s: Settings, sec) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.ai_provider = QComboBox()
        for key, title in (("none", "Не подключать"), ("anthropic", "Anthropic"),
                           ("openai_compat", "OpenAI-совместимый API")):
            self.ai_provider.addItem(title, key)
        self.ai_provider.setCurrentIndex(self.ai_provider.findData(s.ai_provider))
        f.addRow("Провайдер:", self.ai_provider)
        f.addRow(QLabel("<b>Anthropic</b>"))
        self.anthropic_key = SecretField(sec.has("anthropic_api_key"))
        f.addRow("Ключ API:", self.anthropic_key)
        self.anthropic_model = QLineEdit(s.anthropic_model)
        self.anthropic_model.setPlaceholderText("имя модели из консоли Anthropic")
        f.addRow("Модель:", self.anthropic_model)
        self.web_search = QCheckBox("Разрешить веб-поиск (ответ с источниками)")
        self.web_search.setChecked(s.anthropic_web_search)
        f.addRow("", self.web_search)
        f.addRow("", _muted("Ключ: <a href='https://console.anthropic.com/'>console.anthropic.com</a>. "
                            "Веб-поиск оплачивается отдельно и должен быть разрешён в консоли организации."))
        f.addRow(QLabel("<b>OpenAI-совместимый</b>"))
        self.openai_url = QLineEdit(s.openai_base_url)
        f.addRow("Адрес API:", self.openai_url)
        self.openai_key = SecretField(sec.has("openai_api_key"))
        f.addRow("Ключ API:", self.openai_key)
        self.openai_model = QLineEdit(s.openai_model)
        f.addRow("Модель:", self.openai_model)
        f.addRow("", _muted("Подходит для OpenAI, OpenRouter, LM Studio (http://localhost:1234/v1), "
                            "Ollama (http://localhost:11434/v1). Для localhost ключ не обязателен."))
        return w

    def _image_tab(self, s: Settings) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.ocr = QComboBox()
        self.ocr.addItem("Windows OCR — локально, офлайн", "windows")
        self.ocr.addItem("Через ИИ (изображение отправляется провайдеру)", "ai")
        self.ocr.setCurrentIndex(self.ocr.findData(s.ocr_provider))
        f.addRow("OCR:", self.ocr)
        reason = WindowsOCR.availability()
        f.addRow("", _muted("Windows OCR: " + ("доступен." if reason is None else reason)))
        self.ocr_lang = QLineEdit(s.ocr_lang)
        self.ocr_lang.setPlaceholderText("пусто — языки профиля Windows; например ru, en-US")
        f.addRow("Язык OCR:", self.ocr_lang)
        self.reverse = QComboBox()
        for key, svc in REVERSE_IMAGE_SERVICES.items():
            self.reverse.addItem(svc.title, key)
        self.reverse.setCurrentIndex(max(0, self.reverse.findData(s.reverse_image_service)))
        f.addRow("Поиск похожих по умолчанию:", self.reverse)
        return w

    def _bridge_tab(self, s: Settings, status: str) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.bridge_enabled = QCheckBox("Принимать данные от расширения браузера")
        self.bridge_enabled.setChecked(s.bridge_enabled)
        f.addRow("", self.bridge_enabled)
        self.bridge_status = QLabel(status)
        f.addRow("Состояние:", self.bridge_status)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(s.bridge_port)
        f.addRow("Порт (только 127.0.0.1):", self.port)
        token_row = QWidget()
        tl = QHBoxLayout(token_row)
        tl.setContentsMargins(0, 0, 0, 0)
        self.token_view = QLineEdit(self.ctx.secrets.bridge_token())
        self.token_view.setReadOnly(True)
        self.token_view.setEchoMode(QLineEdit.Password)
        show = QPushButton("Показать")
        show.setCheckable(True)
        show.toggled.connect(lambda on: self.token_view.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        copy = QPushButton("Копировать")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.token_view.text()))
        regen = QPushButton("Новый")
        regen.setToolTip("Создать новый токен; старый перестанет работать")
        regen.clicked.connect(self._regenerate_token)
        for b in (self.token_view, show, copy, regen):
            tl.addWidget(b)
        f.addRow("Токен сопряжения:", token_row)
        self.ext_id = QLineEdit(s.bridge_allowed_extension_id)
        self.ext_id.setPlaceholderText("необязательно: ID из chrome://extensions")
        f.addRow("Разрешённый ID расширения:", self.ext_id)
        f.addRow("", _muted("Скопируйте порт и токен в настройки расширения «QuickAssist Bridge». "
                            "Если указать ID расширения, запросы от других расширений будут отклоняться."))
        return w

    def _regenerate_token(self) -> None:
        self.token_view.setText(self.ctx.secrets.regenerate_bridge_token())

    # ---------------------------------------------------------------- сохранение
    def _on_save(self) -> None:
        try:
            _, _, hotkey = parse_hotkey(self.hotkey.currentText())
        except HotkeyParseError as exc:
            QMessageBox.warning(self, "Горячая клавиша", str(exc))
            return
        if self.engine.currentData() == "custom":
            err = validate_custom_template(self.custom_url.text())
            if err:
                QMessageBox.warning(self, "Свой шаблон поиска", err)
                return
        new = replace(
            self.ctx.settings,
            hotkey=hotkey,
            theme=self.theme.currentData(),
            capture_selection=self.capture.isChecked(),
            autostart=self.autostart.isChecked(),
            network_timeout=self.timeout.value(),
            target_lang=self.target_lang.currentData(),
            translate_provider=self.tr_provider.currentData(),
            libretranslate_url=self.libre_url.text().strip(),
            search_engine=self.engine.currentData(),
            custom_search_url=self.custom_url.text().strip(),
            ai_provider=self.ai_provider.currentData(),
            anthropic_model=self.anthropic_model.text().strip(),
            anthropic_web_search=self.web_search.isChecked(),
            openai_base_url=self.openai_url.text().strip(),
            openai_model=self.openai_model.text().strip(),
            ocr_provider=self.ocr.currentData(),
            ocr_lang=self.ocr_lang.text().strip(),
            reverse_image_service=self.reverse.currentData(),
            bridge_enabled=self.bridge_enabled.isChecked(),
            bridge_port=self.port.value(),
            bridge_allowed_extension_id=self.ext_id.text().strip().lower(),
        )
        secrets = {}
        for name, field in (("deepl_api_key", self.deepl_key), ("libretranslate_api_key", self.libre_key),
                            ("anthropic_api_key", self.anthropic_key), ("openai_api_key", self.openai_key)):
            v = field.new_value()
            if v is not None:
                secrets[name] = v
        self.applyRequested.emit(new, secrets)

    def show_error(self, text: str) -> None:
        QMessageBox.warning(self, "Настройки", text)

    def set_bridge_status(self, text: str) -> None:
        self.bridge_status.setText(text)
