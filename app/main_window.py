"""Single-window batter OCR review application."""

from __future__ import annotations

import sys
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QStackedWidget,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CardWidget,
    ComboBox,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    Theme,
    isDarkTheme,
    setTheme,
)

from app.app_info import APP_NAME, APP_VERSION, ORG_NAME
from app.app_settings import (
    get_settings, image_last_directory, reset_user_preferences, set_image_last_directory,
    set_theme, theme,
)
from app.logging_setup import configure_logging
from app.resources import resource_path
from app.models import InternalGame, PlayerRecord, RecognitionInfo
from app.settings import (
    load_last_namelist_path,
    load_next_game_id_serial,
    load_user_name,
    save_last_namelist_path,
    save_next_game_id_serial,
    save_user_name,
)
from data.gamejson_exporter import GameJsonExporter
from data.namelist import NameList, NameListError
from data.validators import ValidationError
from ocr.engines.paddle_engine import PaddleOcrEngine
from ocr.engine import OcrEngineUnavailableError
from parser.batter_parser import PlayerRowImage, merge_batter_screens
from parser.pitcher_parser import merge_pitcher_screens
from ui.review_table import BatterReviewTable, PitcherReviewTable


DARK_STYLE = """
QMainWindow, QWidget#appRoot {
    background-color: #141a21;
    color: #f1f5f9;
    font-size: 13px;
}
QFrame#previewPanel, QLabel#previewLabel {
    border: 1px solid #334155;
    border-radius: 4px;
}
QLabel { color: #f1f5f9; }
QDialog, QMessageBox {
    background-color: #141a21;
    color: #f1f5f9;
}
QDialog QLabel, QMessageBox QLabel { color: #f1f5f9; }
QDialogButtonBox QPushButton, QMessageBox QPushButton {
    background-color: #202a35;
    color: #f1f5f9;
    border: 1px solid #64748b;
    border-radius: 4px;
    padding: 5px 12px;
}
QDialogButtonBox QPushButton:hover, QMessageBox QPushButton:hover { background-color: #334155; }
QMenuBar, QMenu {
    background-color: #141a21;
    color: #f1f5f9;
}
QMenuBar::item:selected, QMenu::item:selected { background-color: #2563eb; color: #ffffff; }
QTableWidget QLineEdit, QTableWidget QComboBox {
    background-color: #202a35;
    color: #ffffff;
    border: 1px solid #64748b;
    border-radius: 3px;
    padding: 4px;
}
QTableWidget QComboBox QAbstractItemView {
    background-color: #202a35;
    color: #ffffff;
    selection-background-color: #2563eb;
}
QTableWidget {
    background-color: #1b2430;
    alternate-background-color: #202a35;
    color: #ffffff;
    gridline-color: #475569;
    border: 1px solid #475569;
}
QTableWidget::item { color: #ffffff; }
QTableWidget::item:selected { background-color: #1d4ed8; color: #ffffff; }
QHeaderView::section {
    background-color: #0f172a;
    color: #ffffff;
    border: 1px solid #475569;
    padding: 5px;
}
QToolTip { background-color: #0f172a; color: #ffffff; border: 1px solid #64748b; }
"""

LIGHT_STYLE = """
QMainWindow, QWidget#appRoot {
    background-color: #f8fafc;
    color: #1f2937;
    font-size: 13px;
}
QFrame#previewPanel, QLabel#previewLabel {
    border: 1px solid #cbd5e1;
    border-radius: 4px;
}
QLabel { color: #1f2937; }
QDialog, QMessageBox {
    background-color: #f8fafc;
    color: #1f2937;
}
QDialog QLabel, QMessageBox QLabel { color: #1f2937; }
QDialogButtonBox QPushButton, QMessageBox QPushButton {
    background-color: #ffffff;
    color: #1f2937;
    border: 1px solid #94a3b8;
    border-radius: 4px;
    padding: 5px 12px;
}
QDialogButtonBox QPushButton:hover, QMessageBox QPushButton:hover { background-color: #e2e8f0; }
QMenuBar, QMenu {
    background-color: #f8fafc;
    color: #1f2937;
}
QMenuBar::item:selected, QMenu::item:selected { background-color: #bfdbfe; color: #111827; }
QTableWidget QLineEdit, QTableWidget QComboBox {
    background-color: #ffffff;
    color: #111827;
    border: 1px solid #94a3b8;
    border-radius: 3px;
    padding: 4px;
}
QTableWidget QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #111827;
    selection-background-color: #bfdbfe;
    selection-color: #111827;
}
QTableWidget {
    background-color: #ffffff;
    alternate-background-color: #f8fafc;
    color: #111827;
    gridline-color: #cbd5e1;
    border: 1px solid #cbd5e1;
}
QTableWidget::item { color: #111827; }
QTableWidget::item:selected { background-color: #bfdbfe; color: #111827; }
QHeaderView::section {
    background-color: #e2e8f0;
    color: #1e293b;
    border: 1px solid #cbd5e1;
    padding: 5px;
}
QToolTip { background-color: #ffffff; color: #111827; border: 1px solid #94a3b8; }
"""


# Display order only.  NameList keeps its original team keys and all OCR /
# GameJSON lookups continue to use those exact names.
TEAM_DISPLAY_GROUPS: tuple[tuple[str, ...], ...] = (
    ("湘南", "東都", "群馬", "熊本", "神戸", "名古屋", "瀬戸内", "神急"),
    ("北海道", "栃木", "岡山", "福島", "舞鶴", "青森", "桜館", "宇部"),
    ("テスト",),
)

TEAM_GAME_ID_CODES = {
    "湘南": "BT", "東都": "RG", "群馬": "GM", "熊本": "SM",
    "神戸": "SP", "名古屋": "NS", "瀬戸内": "SC", "神急": "SS",
    "北海道": "HO", "栃木": "RV", "岡山": "WH", "福島": "WS",
    "舞鶴": "NG", "青森": "SB", "桜館": "SO", "宇部": "UM",
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._settings = get_settings()
        self._logger = logging.getLogger("jpbl_powerpro_importer")
        self._apply_theme(theme(self._settings))
        self.setWindowTitle(f"{APP_NAME} - 野手成績")
        icon_path = resource_path("assets/icon.ico")
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1500, 900)
        self.setAcceptDrops(True)
        self._name_list: NameList | None = None
        self._images: list[Any] = []
        self._image_paths: list[Path] = []
        self._source_rows: list[PlayerRowImage] = []

        self._build_ui()
        self._restore_window_state()
        self._restore_last_namelist()

    def _build_ui(self) -> None:
        self._build_menu()
        root = QWidget(self)
        root.setObjectName("appRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        # Card 1: NameList.  Keep the complete path in the tooltip only.
        name_card = CardWidget(root)
        name_layout = QHBoxLayout(name_card)
        name_layout.setContentsMargins(10, 8, 10, 8)
        name_layout.setSpacing(8)
        name_title = self._section_label("NameList")
        name_title.setMinimumWidth(72)
        name_layout.addWidget(name_title)
        self.name_list_label = QLabel("未選択")
        self.name_list_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        name_layout.addWidget(self.name_list_label, 1)
        self.name_list_status = QLabel("未読込")
        self.name_list_status.setObjectName("statusTag")
        self._set_name_list_status_style(loaded=False)
        name_layout.addWidget(self.name_list_status)

        select_name_list = PushButton("変更")
        select_name_list.clicked.connect(self.select_name_list)
        name_layout.addWidget(select_name_list)
        root_layout.addWidget(name_card)

        # Keep user-specific settings independent from the shared NameList.
        user_card = CardWidget(root)
        user_layout = QHBoxLayout(user_card)
        user_layout.setContentsMargins(10, 8, 10, 8)
        user_layout.setSpacing(8)
        user_title = self._section_label("ユーザー設定")
        user_title.setMinimumWidth(72)
        user_layout.addWidget(user_title)
        user_layout.addWidget(QLabel("ユーザー名"))
        self.user_name_edit = LineEdit()
        self.user_name_edit.setMaxLength(3)
        self.user_name_edit.setPlaceholderText("3文字")
        self.user_name_edit.setText(load_user_name())
        self.user_name_edit.setFixedWidth(70)
        self.user_name_edit.editingFinished.connect(self.save_user_name_setting)
        user_layout.addWidget(self.user_name_edit)
        user_hint = QLabel("空欄時: UKN / 入力後に自動保存")
        user_hint.setObjectName("userHint")
        self.user_hint = user_hint
        self._set_user_hint_style()
        user_layout.addWidget(user_hint)
        user_layout.addStretch(1)
        root_layout.addWidget(user_card)

        # Card 2: compact match metadata.
        match_card = CardWidget(root)
        match_layout = QGridLayout(match_card)
        match_layout.setContentsMargins(10, 8, 10, 8)
        match_layout.setHorizontalSpacing(8)
        match_layout.setVerticalSpacing(4)
        match_title = self._section_label("試合情報")
        match_title.setMinimumWidth(72)
        match_layout.addWidget(match_title, 0, 0, 1, 1)

        self.team_combo = ComboBox()
        self.team_combo.setEnabled(False)
        self.team_combo.currentTextChanged.connect(self._team_changed)
        self.team_combo.setMinimumWidth(150)
        match_layout.addWidget(QLabel("球団"), 0, 1)
        match_layout.addWidget(self.team_combo, 0, 2)

        self.screen_kind_combo = ComboBox()
        self.screen_kind_combo.setObjectName("screenKindCombo")
        # QFluentWidgets treats its second positional addItem argument as an
        # icon, not user data.  Keyword arguments are essential here: without
        # them currentData() is None and image selection incorrectly falls
        # through to the one-image limit.
        self.screen_kind_combo.addItem("野手記録", userData="batter")
        self.screen_kind_combo.addItem("投手記録", userData="pitcher")
        self.screen_kind_combo.currentIndexChanged.connect(self._screen_kind_changed)
        self.screen_kind_combo.setMinimumWidth(150)
        self._apply_screen_kind_style()
        match_layout.addWidget(QLabel("成績種別"), 0, 3)
        match_layout.addWidget(self.screen_kind_combo, 0, 4)

        now = datetime.now()
        self.game_id_edit = LineEdit()
        self.game_id_edit.setText(f"{now:%Y%m%d}-001")
        match_layout.addWidget(QLabel("Game ID"), 1, 1)
        match_layout.addWidget(self.game_id_edit, 1, 2)
        self.game_date_edit = LineEdit()
        self.game_date_edit.setText(f"{now.month}/{now.day}")
        self.game_date_edit.setMaximumWidth(110)
        self.game_date_edit.editingFinished.connect(self._refresh_generated_game_id)
        match_layout.addWidget(QLabel("試合日"), 1, 3)
        match_layout.addWidget(self.game_date_edit, 1, 4)
        match_layout.setColumnStretch(2, 3)
        match_layout.setColumnStretch(4, 1)
        root_layout.addWidget(match_card)

        # Card 3: source image and actions.  The table/preview below remains
        # intentionally untouched.
        image_card = CardWidget(root)
        image_layout = QGridLayout(image_card)
        image_layout.setContentsMargins(10, 8, 10, 8)
        image_layout.setHorizontalSpacing(8)
        image_layout.setVerticalSpacing(6)
        image_title = self._section_label("成績画像")
        image_title.setMinimumWidth(72)
        image_layout.addWidget(image_title, 0, 0)
        self.image_label = QLabel("未選択（最大2枚。スクロール時は上側→下側の順）")
        self.image_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        image_layout.addWidget(self.image_label, 0, 1)
        select_image = PushButton("画像を選択")
        select_image.clicked.connect(self.select_image)
        image_layout.addWidget(select_image, 0, 2)

        action_line = QHBoxLayout()
        action_line.setSpacing(8)
        self.analyze_button = PushButton("画像を解析")
        self.analyze_button.setObjectName("analyzeButton")
        self.analyze_button.setStyleSheet("""
            QPushButton#analyzeButton {
                background-color: #2563eb;
                color: #ffffff;
                border: 1px solid #60a5fa;
                border-radius: 4px;
                font-weight: 600;
                padding: 5px 12px;
            }
            QPushButton#analyzeButton:hover { background-color: #1d4ed8; }
            QPushButton#analyzeButton:pressed { background-color: #1e40af; }
            QPushButton#analyzeButton:disabled {
                background-color: #334155;
                color: #94a3b8;
                border-color: #475569;
            }
        """)
        self.analyze_button.setEnabled(False)
        self.analyze_button.clicked.connect(self.analyze_image)
        action_line.addWidget(self.analyze_button)

        self.reset_image_button = PushButton("画像をリセット")
        self.reset_image_button.setEnabled(False)
        self.reset_image_button.clicked.connect(self.reset_image_selection)
        action_line.addWidget(self.reset_image_button)
        action_line.addStretch(1)

        self.export_button = PrimaryPushButton("GameJSONを書き出す")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_gamejson)
        action_line.addWidget(self.export_button)
        image_layout.addLayout(action_line, 1, 1, 1, 2)
        image_layout.setColumnStretch(1, 1)
        root_layout.addWidget(image_card)

        self.batter_review_table = BatterReviewTable(root)
        self.pitcher_review_table = PitcherReviewTable(root)
        self.batter_review_table.set_theme(self._is_dark_theme)
        self.pitcher_review_table.set_theme(self._is_dark_theme)
        self.review_table = self.batter_review_table
        for table in (self.batter_review_table, self.pitcher_review_table):
            table.row_selected.connect(self.show_row_preview)
            table.records_changed.connect(self._update_summary)
        self.review_stack = QStackedWidget(root)
        self.review_stack.addWidget(self.batter_review_table)
        self.review_stack.addWidget(self.pitcher_review_table)

        preview_panel = QFrame(root)
        preview_panel.setObjectName("previewPanel")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.addWidget(QLabel("表見出し＋選択した選手行（1920×1080へ正規化後）"))
        self.preview_label = QLabel("解析後に行を選択してください")
        self.preview_label.setObjectName("previewLabel")
        self.preview_label.setMinimumSize(360, 160)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setFrameShape(QFrame.Shape.StyledPanel)
        preview_layout.addWidget(self.preview_label, 1)

        splitter = QSplitter(Qt.Orientation.Vertical, root)
        splitter.addWidget(self.review_stack)
        splitter.addWidget(preview_panel)
        splitter.setSizes([560, 240])
        root_layout.addWidget(splitter, 1)

        self.summary_label = QLabel("NameListと野手成績画像を選択してください。")
        root_layout.addWidget(self.summary_label)
        self.setCentralWidget(root)
        self._refresh_generated_game_id()

    def _build_menu(self) -> None:
        settings_action = QAction("設定", self)
        settings_action.triggered.connect(self.show_settings_dialog)
        self.menuBar().addMenu("設定").addAction(settings_action)
        about_action = QAction("このアプリについて", self)
        about_action.triggered.connect(self.show_about_dialog)
        self.menuBar().addMenu("ヘルプ").addAction(about_action)

    def _apply_theme(self, value: str) -> None:
        value = value if value in ("dark", "light", "system") else "dark"
        setTheme({"dark": Theme.DARK, "light": Theme.LIGHT, "system": Theme.AUTO}[value])
        self._is_dark_theme = isDarkTheme()
        self.setStyleSheet(DARK_STYLE if self._is_dark_theme else LIGHT_STYLE)
        if hasattr(self, "name_list_status"):
            self._set_name_list_status_style(loaded=self._name_list is not None)
        if hasattr(self, "user_hint"):
            self._set_user_hint_style()
        for table_name in ("batter_review_table", "pitcher_review_table"):
            if hasattr(self, table_name):
                getattr(self, table_name).set_theme(self._is_dark_theme)

    def _set_name_list_status_style(self, *, loaded: bool) -> None:
        color = "#86efac" if loaded and self._is_dark_theme else "#166534" if loaded else "#94a3b8" if self._is_dark_theme else "#64748b"
        self.name_list_status.setStyleSheet(f"QLabel#statusTag {{ color: {color}; }}")

    def _set_user_hint_style(self) -> None:
        color = "#94a3b8" if self._is_dark_theme else "#64748b"
        self.user_hint.setStyleSheet(f"QLabel#userHint {{ color: {color}; }}")

    def _apply_dialog_theme(self, dialog: QDialog) -> None:
        """Apply the app palette to top-level Qt dialogs as well."""
        dialog.setStyleSheet(DARK_STYLE if self._is_dark_theme else LIGHT_STYLE)

    def show_settings_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("設定")
        self._apply_dialog_theme(dialog)
        layout = QFormLayout(dialog)
        theme_combo = ComboBox(dialog)
        choices = (("ダーク", "dark"), ("ライト", "light"), ("システム設定に従う", "system"))
        for label, value in choices:
            theme_combo.addItem(label, userData=value)
        theme_combo.setCurrentIndex(next(index for index, (_label, value) in enumerate(choices) if value == theme(self._settings)))
        layout.addRow("テーマ", theme_combo)
        layout.addRow("NameList", QLabel(self.name_list_label.text(), dialog))
        reset_button = PushButton("設定を初期化", dialog)
        reset_button.clicked.connect(lambda: self._confirm_reset_preferences(dialog))
        layout.addRow("", reset_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            value = theme_combo.currentData()
            set_theme(value if isinstance(value, str) else "dark", self._settings)
            self._apply_theme(theme(self._settings))

    def _confirm_reset_preferences(self, dialog: QDialog) -> None:
        message = QMessageBox(QMessageBox.Icon.Question, "設定を初期化", "ウィンドウ状態、NameList、画像フォルダ、テーマを初期化しますか？", parent=self)
        message.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        self._apply_dialog_theme(message)
        answer = message.exec()
        if answer == QMessageBox.StandardButton.Yes:
            reset_user_preferences(self._settings)
            self._apply_theme("dark")
            dialog.accept()

    def show_about_dialog(self) -> None:
        dialog = QMessageBox(QMessageBox.Icon.Information, f"{APP_NAME} について", f"{APP_NAME}\nVersion {APP_VERSION}\n\nJPBL成績入力支援ツール\n\nPython / PySide6\n\n©2026 JPBL Systems Department", parent=self)
        self._apply_dialog_theme(dialog)
        dialog.exec()

    def _restore_window_state(self) -> None:
        geometry = self._settings.value("window/geometry")
        if geometry is not None and self.restoreGeometry(geometry):
            screen = self.screen() or QApplication.primaryScreen()
            if screen is not None and not self.frameGeometry().intersects(screen.availableGeometry()):
                self.resize(1500, 900)
                self.move(screen.availableGeometry().center() - self.rect().center())
        state = self._settings.value("window/state")
        if state is not None:
            self.restoreState(state)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-size: 13px; font-weight: 600;")
        return label

    def select_name_list(self) -> None:
        initial_path = str(self._name_list_path()) if self._name_list_path() else ""
        path, _ = QFileDialog.getOpenFileName(self, "NameListを選択", initial_path, "JSON (*.json)")
        if path:
            self.load_name_list(Path(path))

    def load_name_list(self, path: Path, *, save_as_last: bool = True) -> None:
        try:
            name_list = NameList.from_file(path)
        except NameListError as error:
            self._logger.warning("NameList読込失敗: %s", path, exc_info=True)
            self._show_error("NameListを読み込めません", str(error))
            return
        self._name_list = name_list
        self.name_list_label.setText(path.name)
        self.name_list_label.setToolTip(str(path))
        self.name_list_status.setText("読込済")
        self._set_name_list_status_style(loaded=True)
        self.team_combo.clear()
        team_groups = self._team_display_groups(name_list.team_names())
        for group_index, team_group in enumerate(team_groups):
            for team_name in team_group:
                self.team_combo.addItem(team_name, userData=team_name)
            if team_group and any(team_groups[group_index + 1:]):
                self.team_combo.addItem("────────", userData=None)
                self.team_combo.setItemEnabled(self.team_combo.count() - 1, False)
        self.team_combo.setEnabled(True)
        if save_as_last:
            save_last_namelist_path(path)
            self._logger.info("NameList読込: %s", path)
            self._show_success("NameListを読み込みました", path.name)
        self._update_analyze_enabled()
        self._refresh_generated_game_id()

    def _restore_last_namelist(self) -> None:
        path = load_last_namelist_path()
        if path is not None and path.is_file():
            self.load_name_list(path, save_as_last=False)

    def _name_list_path(self) -> Path | None:
        value = load_last_namelist_path()
        return value if value is not None and value.is_file() else None

    @staticmethod
    def _team_display_groups(team_names: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
        """Order known JPBL teams in UI groups without changing NameList data."""
        available = set(team_names)
        ordered_groups: list[tuple[str, ...]] = []
        used: set[str] = set()
        for group in TEAM_DISPLAY_GROUPS:
            selected = tuple(team for team in group if team in available)
            ordered_groups.append(selected)
            used.update(selected)
        # Keep future teams visible.  Place them before the dedicated test team
        # group so the requested test-team placement stays last.
        remaining = tuple(sorted(available - used))
        if remaining:
            ordered_groups[1] = (*ordered_groups[1], *remaining)
        return tuple(ordered_groups)

    def save_user_name_setting(self) -> None:
        user_name = self.user_name_edit.text().strip()
        if user_name and len(user_name) != 3:
            self._show_error("ユーザー名は3文字で設定してください", "Game IDの先頭3文字に使用します。")
            return
        save_user_name(user_name)
        self._refresh_generated_game_id()

    @staticmethod
    def _game_id_date(date_text: str) -> str:
        """Convert the editable match date into the Game ID's YYYYMMDD part."""
        value = date_text.strip()
        for format_string in ("%Y%m%d", "%Y/%m/%d", "%Y-%m-%d", "%m/%d", "%m-%d"):
            try:
                parsed = datetime.strptime(value, format_string)
            except ValueError:
                continue
            if format_string in ("%m/%d", "%m-%d"):
                parsed = parsed.replace(year=datetime.now().year)
            return parsed.strftime("%Y%m%d")
        return datetime.now().strftime("%Y%m%d")

    def _refresh_generated_game_id(self) -> None:
        """Build USER-TEAM-YYYYMMDD-NNN while retaining a manually set serial."""
        existing_id = getattr(self, "game_id_edit", None)
        if existing_id is None:
            return
        user_name = self.user_name_edit.text().strip() if hasattr(self, "user_name_edit") else ""
        user_part = user_name if len(user_name) == 3 else "UKN"
        team_code = TEAM_GAME_ID_CODES.get(self.team_combo.currentText(), "??")
        date_part = self._game_id_date(self.game_date_edit.text()) if hasattr(self, "game_date_edit") else datetime.now().strftime("%Y%m%d")
        prefix = f"{user_part}-{team_code}-{date_part}"
        serial_match = re.fullmatch(rf"{re.escape(prefix)}-(\d+)", existing_id.text().strip())
        serial = serial_match.group(1).zfill(3) if serial_match else f"{load_next_game_id_serial(prefix):03d}"
        existing_id.setText(f"{prefix}-{serial}")

    def _advance_game_id_serial(self) -> None:
        """Advance only after a GameJSON file was written successfully."""
        match = re.fullmatch(r"(.+)-(\d+)", self.game_id_edit.text().strip())
        if match is None:
            return
        prefix, current_serial_text = match.groups()
        next_serial = max(int(current_serial_text) + 1, load_next_game_id_serial(prefix))
        save_next_game_id_serial(prefix, next_serial)
        self.game_id_edit.setText(f"{prefix}-{next_serial:03d}")

    def _screen_kind(self) -> str:
        """Return a valid mode even if an old widget state has no user data."""
        kind = self.screen_kind_combo.currentData()
        if kind in ("batter", "pitcher"):
            return kind
        return "pitcher" if self.screen_kind_combo.currentIndex() == 1 else "batter"

    def _apply_screen_kind_style(self) -> None:
        """Make the selected score type unambiguous in the compact header."""
        is_pitcher = self._screen_kind() == "pitcher"
        background = "#b4232c" if is_pitcher else "#1d4ed8"
        border = "#f87171" if is_pitcher else "#60a5fa"
        hover = "#d13a43" if is_pitcher else "#2563eb"
        self.screen_kind_combo.setStyleSheet(f"""
            QPushButton#screenKindCombo {{
                background-color: {background};
                color: #ffffff;
                border: 1px solid {border};
                border-radius: 4px;
                font-weight: 600;
                padding: 5px 24px 5px 9px;
            }}
            QPushButton#screenKindCombo:hover {{ background-color: {hover}; }}
            QPushButton#screenKindCombo:pressed {{ background-color: {background}; }}
        """)

    def select_image(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, f"{self.screen_kind_combo.currentText()}画像を選択（上側→下側、最大2枚）", image_last_directory(self._settings), "画像 (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if paths:
            set_image_last_directory(Path(paths[0]).parent, self._settings)
            self.load_images([Path(path) for path in paths])

    def load_image(self, path: Path) -> None:
        """Compatibility wrapper for one-image selection/drop."""
        self.load_images([path])

    def load_images(self, paths: list[Path]) -> None:
        if not 1 <= len(paths) <= 2:
            self._show_error("画像は1～2枚まで", "成績画像は1枚、またはスクロール前後の2枚を上側→下側の順で選択してください。")
            return
        try:
            import cv2
            import numpy as np
        except ImportError:
            self._show_error("依存関係がありません", "OpenCVをインストールしてください。\npython -m pip install -r requirements.txt")
            return
        images: list[Any] = []
        for path in paths:
            image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                self._show_error("画像を読み込めません", str(path))
                return
            images.append(image)
        self._images = images
        self._image_paths = paths
        self.image_label.setText(" / ".join(path.name for path in paths))
        self.image_label.setToolTip("\n".join(str(path) for path in paths))
        self._update_analyze_enabled()

    def append_images(self, paths: list[Path]) -> None:
        """Add dropped images after the current selection, up to two files."""
        combined = list(self._image_paths)
        existing = {path.resolve() for path in combined}
        for path in paths:
            resolved = path.resolve()
            if resolved not in existing:
                combined.append(path)
                existing.add(resolved)
        if len(combined) > 2:
            self._show_error("画像は1～2枚まで", "すでに選択中の画像を含めて最大2枚です。画像をリセットしてから選び直してください。")
            return
        if combined:
            self.load_images(combined)

    def reset_image_selection(self) -> None:
        """Clear source-image inputs without discarding reviewed table data."""
        self._images = []
        self._image_paths = []
        self._source_rows = []
        self.image_label.setText("未選択（最大2枚。スクロール時は上側→下側の順）")
        self.image_label.setToolTip("")
        self.preview_label.setText("画像がリセットされました。新しい画像を選択して解析してください。")
        self._update_analyze_enabled()

    def _update_analyze_enabled(self) -> None:
        self.analyze_button.setEnabled(self._name_list is not None and bool(self._images) and bool(self.team_combo.currentText()))
        self.reset_image_button.setEnabled(bool(self._images))

    def _update_export_enabled(self) -> None:
        has_records = bool(self.batter_review_table.records or self.pitcher_review_table.records)
        self.export_button.setEnabled(self._name_list is not None and has_records)

    def _team_changed(self, _team: str) -> None:
        # Results are scoped to one team's batter candidates; never leave old
        # results on screen after a team switch.
        if self.batter_review_table.records or self.pitcher_review_table.records:
            self.batter_review_table.set_records([], ())
            self.pitcher_review_table.set_records([], ())
            self._source_rows = []
            self.preview_label.setText("球団が変更されました。画像を再解析してください。")
            self.summary_label.setText("球団が変更されました。")
        self._update_analyze_enabled()
        self._update_export_enabled()
        self._refresh_generated_game_id()

    def _screen_kind_changed(self, _index: int) -> None:
        is_pitcher = self._screen_kind() == "pitcher"
        self._apply_screen_kind_style()
        self.review_stack.setCurrentIndex(1 if is_pitcher else 0)
        self.review_table = self.pitcher_review_table if is_pitcher else self.batter_review_table
        self._images = []
        self._image_paths = []
        self.image_label.setText("未選択（最大2枚。スクロール時は上側→下側の順）")
        self.image_label.setToolTip("")
        self._source_rows = []
        self.preview_label.setText("成績種別が変更されました。対応する画像を選択して解析してください。")
        self.summary_label.setText("成績種別が変更されました。")
        self._update_analyze_enabled()
        self._update_export_enabled()

    def analyze_image(self) -> None:
        if self._name_list is None or not self._images:
            return
        if not self._confirm_image_analysis():
            return
        self._logger.info("画像解析開始: count=%d mode=%s", len(self._images), self._screen_kind())
        try:
            engine = PaddleOcrEngine()
            team = self.team_combo.currentText()
            if self._screen_kind() == "pitcher":
                records, rows = merge_pitcher_screens(
                    self._images, self._name_list.get_pitchers(team), engine,
                    aliases=self._name_list.aliases(team, "pitchers"),
                )
                candidates = self._name_list.get_pitchers(team)
            else:
                records, rows = merge_batter_screens(
                    self._images, self._name_list.get_batters(team), engine,
                    aliases=self._name_list.aliases(team, "batters"),
                )
                candidates = self._name_list.get_batters(team)
        except (OcrEngineUnavailableError, RuntimeError, ValueError) as error:
            self._logger.exception("画像解析失敗")
            self._show_error("画像を解析できません", str(error))
            return
        if not records:
            self.review_table.set_records([], candidates)
            self._source_rows = []
            config = "pitcher_screen_regions.json" if self._screen_kind() == "pitcher" else "batter_screen_regions.json"
            self.preview_label.setText(f"選手行を検出できませんでした。\nconfig/{config}を実機画像に合わせて校正してください。")
            self.summary_label.setText("検出行: 0")
            self._logger.info("画像解析完了: records=0")
            return
        self._source_rows = rows
        self.review_table.set_records(records, candidates)
        self._update_summary()
        self._show_success("画像解析が完了しました", f"{len(records)}行を確認テーブルへ追加しました")
        self._logger.info("画像解析完了: records=%d", len(records))

    def _confirm_image_analysis(self) -> bool:
        """Confirm the current inputs before creating the OCR engine."""
        image_names = "\n".join(path.name for path in self._image_paths)
        dialog = QMessageBox(QMessageBox.Icon.Question, "解析前の確認", "この設定で画像を解析しますか？", parent=self)
        self._apply_dialog_theme(dialog)
        dialog.setInformativeText(
            f"球団: {self.team_combo.currentText()}\n"
            f"成績種別: {self.screen_kind_combo.currentText()}\n"
            f"画像: {image_names}"
        )
        analyze_button = dialog.addButton("解析する", QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton("戻る", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        return dialog.clickedButton() is analyze_button

    def _update_summary(self) -> None:
        records = self.review_table.records
        states = {state: sum(record.status == state for record in records) for state in ("OK", "要確認", "エラー", "除外")}
        filter_note = "（赤色の投手行は除外）" if self._screen_kind() == "batter" else ""
        self.summary_label.setText(
            f"検出行: {len(records)}{filter_note} / OK: {states['OK']} / 要確認: {states['要確認']} / エラー: {states['エラー']} / 除外: {states['除外']}"
        )
        self._update_export_enabled()

    @staticmethod
    def _recognition_info(record: Any) -> RecognitionInfo:
        return RecognitionInfo(
            ocr_text=record.ocr_name,
            matched_name=record.matched_name,
            confidence=record.match_score,
            manually_corrected=record.manually_corrected_name,
            manually_added_name=record.manually_added_name,
            second_candidate=record.second_name,
            second_candidate_score=record.second_score,
            match_source=record.match_source,
        )

    def build_internal_game(self) -> InternalGame:
        """Convert both review tables into one validated GameJSON-ready game."""
        if self._name_list is None:
            raise ValueError("NameListを選択してください")
        team = self.team_combo.currentText()
        if not team:
            raise ValueError("球団を選択してください")
        players: list[PlayerRecord] = []
        for record in self.batter_review_table.records:
            if record.excluded_from_export:
                continue
            players.append(PlayerRecord(
                team=team, position="野手", recognition=self._recognition_info(record),
                stats=record.to_batter_stats(), remarks=record.remarks,
            ))
        for record in self.pitcher_review_table.records:
            if record.excluded_from_export:
                continue
            players.append(PlayerRecord(
                team=team, position="投手", recognition=self._recognition_info(record),
                stats=record.to_pitcher_stats(), remarks=record.remarks,
            ))
        if not players:
            raise ValueError("野手または投手の成績を解析・確認してください")
        return InternalGame(
            game_id=self.game_id_edit.text().strip(),
            game_date=self.game_date_edit.text().strip(),
            away_team=team,
            home_team=team,
            players=players,
        )

    def export_gamejson(self) -> None:
        if self._name_list is None:
            return
        try:
            game = self.build_internal_game()
            exporter = GameJsonExporter()
            # Validate before presenting the save dialog, so an invalid file
            # path is never selected for data that cannot be written.
            exporter.export(game, self._name_list)
        except (ValidationError, ValueError, RuntimeError) as error:
            self._logger.exception("GameJSON出力失敗")
            self._show_error("GameJSONを書き出せません", str(error))
            return
        safe_game_id = re.sub(r'[\\/:*?"<>|]+', "_", game.game_id) or "game"
        path, _ = QFileDialog.getSaveFileName(
            self, "GameJSONを書き出す", f"JPBL_Game_{safe_game_id}.json", "JSON (*.json)"
        )
        if not path:
            return
        output_path = Path(path)
        if output_path.suffix.lower() != ".json":
            output_path = output_path.with_suffix(".json")
        try:
            exporter.export_to_file(game, self._name_list, output_path)
        except (OSError, ValidationError, ValueError, RuntimeError) as error:
            self._logger.exception("GameJSON出力失敗")
            self._show_error("GameJSONを書き出せません", str(error))
            return
        self._advance_game_id_serial()
        self._logger.info("GameJSON出力: %s", output_path)
        self._show_success("GameJSONを書き出しました", str(output_path))

    def show_row_preview(self, table_row: int) -> None:
        if not 0 <= table_row < len(self.review_table.records):
            return
        source_index = self.review_table.records[table_row].source_row_index
        row = next((value for value in self._source_rows if value.row_index == source_index), None)
        if row is None:
            return
        self._show_bgr_image(row.preview_image)

    def _show_bgr_image(self, image: Any) -> None:
        try:
            import cv2
        except ImportError:
            return
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        qimage = QImage(rgb.data, width, height, width * channels, QImage.Format.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(qimage)
        self.preview_label.setPixmap(pixmap.scaled(
            self.preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))

    def dragEnterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        urls = event.mimeData().urls()
        if urls:
            self.append_images([Path(url.toLocalFile()) for url in urls])
            event.acceptProposedAction()

    def _show_error(self, title: str, detail: str) -> None:
        InfoBar.error(
            title, detail, duration=8000, position=InfoBarPosition.TOP_RIGHT, parent=self,
        )

    def _show_success(self, title: str, detail: str) -> None:
        InfoBar.success(
            title, detail, duration=3500, position=InfoBarPosition.TOP_RIGHT, parent=self,
        )

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("window/state", self.saveState())
        self._settings.sync()
        self._logger.info("アプリケーション終了")
        event.accept()


def run() -> None:
    application = QApplication(sys.argv)
    application.setApplicationName(APP_NAME)
    application.setApplicationDisplayName(APP_NAME)
    application.setOrganizationName(ORG_NAME)
    application.setApplicationVersion(APP_VERSION)
    icon_path = resource_path("assets/icon.ico")
    if icon_path.is_file():
        application.setWindowIcon(QIcon(str(icon_path)))
    logger = configure_logging()
    logger.info("アプリケーション起動 version=%s", APP_VERSION)
    window = MainWindow()
    window.show()
    raise SystemExit(application.exec())
