"""Extensible base table and batter-review implementation."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QIntValidator
from PySide6.QtWidgets import QComboBox, QHeaderView, QLineEdit, QMenu, QTableWidget, QTableWidgetItem

from app.models import (
    BATTER_STAT_FIELDS,
    PITCHER_MANUAL_BINARY_FIELDS,
    PITCHER_MANUAL_INTEGER_FIELDS,
    PITCHER_OCR_FIELDS,
    RecognizedBatter,
    RecognizedPitcher,
)


BATTER_COLUMNS: tuple[tuple[str, str | None], ...] = (
    ("状態", None),
    ("確認理由", None),
    ("選手名", "matched_name"),
    ("OCR名", "ocr_name"),
    ("試合", "games"),
    ("打数", "at_bats"),
    ("得点", "runs"),
    ("安打", "hits"),
    ("二塁打", "doubles"),
    ("三塁打", "triples"),
    ("本塁打", "home_runs"),
    ("打点", "rbi"),
    ("三振", "strikeouts"),
    ("四死球", "walks_hbp"),
    ("犠打", "sacrifices"),
    ("盗塁", "steals"),
    ("併殺", "double_plays"),
    ("失策", "errors"),
    ("犠飛", "sac_flies"),
    ("備考", "remarks"),
)

# The table has many numeric columns.  These proportions keep every column in
# view at the default window size while preserving useful room for names/notes.
_COMPACT_COLUMN_WIDTHS = (58, 160, 125, 90, 42, *([44] * 14), 170)

_STATUS_COLOURS = {
    True: {
        "OK": (QColor("#1f6b45"), QColor("#ffffff")),
        "要確認": (QColor("#725300"), QColor("#ffffff")),
        "エラー": (QColor("#7b2635"), QColor("#ffffff")),
        "除外": (QColor("#4b5563"), QColor("#ffffff")),
    },
    False: {
        "OK": (QColor("#dcfce7"), QColor("#166534")),
        "要確認": (QColor("#fef3c7"), QColor("#92400e")),
        "エラー": (QColor("#fee2e2"), QColor("#b91c1c")),
        "除外": (QColor("#e5e7eb"), QColor("#374151")),
    },
}
_NEW_PLAYER_VALUE = "__jpbl_add_new_player__"


class ReviewTableBase(QTableWidget):
    """Shared foundation for future pitcher and batter review tables."""

    row_selected = Signal(int)

    def __init__(self, headers: list[str], parent=None) -> None:
        super().__init__(0, len(headers), parent)
        self._is_dark_theme = True
        self.setHorizontalHeaderLabels(headers)
        self.setAlternatingRowColors(True)
        # Cell selection makes the current column visible when navigating with
        # the left/right keys; the current-row signal still drives previews.
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setMinimumSectionSize(1)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.currentCellChanged.connect(self._on_current_cell_changed)
        self.cellDoubleClicked.connect(self._confirm_review_on_double_click)

    def set_theme(self, is_dark: bool) -> None:
        """Repaint status cells after the application theme changes."""
        self._is_dark_theme = is_dark
        for row in range(self.rowCount()):
            self._refresh_status(row)

    def _paint_status_item(self, item: QTableWidgetItem, status: str) -> None:
        background, foreground = _STATUS_COLOURS[self._is_dark_theme][status]
        item.setBackground(background)
        item.setForeground(foreground)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._fit_columns()

    def _fit_columns(self) -> None:
        """Scale columns to the viewport and avoid a horizontal scroll bar."""
        widths = getattr(self, "_compact_column_widths", ())
        if not widths or self.columnCount() != len(widths):
            return
        available = max(1, self.viewport().width())
        scale = available / sum(widths)
        assigned = 0
        for column, preferred in enumerate(widths[:-1]):
            width = max(1, round(preferred * scale))
            self.setColumnWidth(column, width)
            assigned += width
        self.setColumnWidth(len(widths) - 1, max(1, available - assigned))

    def _on_current_cell_changed(self, current_row: int, _current_column: int, _previous_row: int, _previous_column: int) -> None:
        if current_row >= 0:
            self.row_selected.emit(current_row)

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """Keep row selection while allowing keyboard movement across columns."""
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right) and self.currentRow() >= 0:
            direction = -1 if event.key() == Qt.Key.Key_Left else 1
            target_column = max(0, min(self.columnCount() - 1, self.currentColumn() + direction))
            if target_column != self.currentColumn():
                self.setCurrentCell(self.currentRow(), target_column)
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """Offer export exclusion only from a row's status cell."""
        index = self.indexAt(event.pos())
        if index.column() != 0 or not 0 <= index.row() < len(self.records):
            event.ignore()
            return
        row = index.row()
        record = self.records[row]
        menu = QMenu(self)
        action = menu.addAction("除外を取り消す" if record.excluded_from_export else "GameJSONから除外する")
        if menu.exec(event.globalPos()) is action:
            record.excluded_from_export = not record.excluded_from_export
            self._refresh_status(row)
            self.records_changed.emit()

    def _confirm_review_on_double_click(self, row: int, column: int) -> None:
        """A double-click on a review state records the user's confirmation."""
        if column != 0 or not 0 <= row < len(self.records):
            return
        record = self.records[row]
        if record.status != "要確認":
            return
        record.requires_review = False
        self._refresh_status(row)
        self.records_changed.emit()

    def _name_widget(self, row: int, record, candidates: tuple[str, ...]):  # type: ignore[no-untyped-def]
        """Return either the roster selector or a manual-name editor."""
        if getattr(record, "manually_added_name", False):
            return self._manual_name_editor(row, record)
        selector = QComboBox(self)
        selector.addItem("＋ 新しく追加…", _NEW_PLAYER_VALUE)
        selector.addItem("-- 選択 --", None)
        for candidate in candidates:
            selector.addItem(candidate, candidate)
        selector.setCurrentIndex(1)
        if record.matched_name in candidates:
            selector.setCurrentText(record.matched_name)
        selector.currentIndexChanged.connect(lambda _index, r=row: self._set_name(r))
        return selector

    def _manual_name_editor(self, row: int, record):  # type: ignore[no-untyped-def]
        editor = QLineEdit(self)
        editor.setText(record.matched_name or "")
        editor.setPlaceholderText("追加する選手名を入力")
        editor.textEdited.connect(lambda text, r=row: self._set_manual_name(r, text))
        editor.setToolTip("NameListには保存されません。この試合のGameJSONにだけ追加されます。")
        return editor

    def _set_name(self, row: int) -> None:
        selector = self.cellWidget(row, 2)
        if not isinstance(selector, QComboBox):
            return
        record = self.records[row]
        value = selector.currentData()
        if value == _NEW_PLAYER_VALUE:
            record.matched_name = None
            record.manually_added_name = True
            record.manually_corrected_name = True
            record.requires_review = True
            editor = self._manual_name_editor(row, record)
            self.setCellWidget(row, 2, editor)
            editor.setFocus()
        else:
            record.matched_name = value
            record.manually_added_name = False
            record.manually_corrected_name = True
            record.match_source = "manual"
            record.requires_review = record.matched_name is None
        self._refresh_status(row)
        self.records_changed.emit()

    def _set_manual_name(self, row: int, text: str) -> None:
        record = self.records[row]
        record.matched_name = text.strip() or None
        record.manually_added_name = True
        record.manually_corrected_name = True
        record.match_source = "manual"
        record.requires_review = record.matched_name is None
        self._refresh_status(row)
        self.records_changed.emit()

    def _refresh_name_widget(self, row: int) -> None:
        record = self.records[row]
        widget = self.cellWidget(row, 2)
        if isinstance(widget, QComboBox):
            if record.status == "OK":
                widget.setStyleSheet("")
            elif record.status == "除外":
                widget.setStyleSheet("QComboBox { background: #4b5563; color: #ffffff; }")
            else:
                widget.setStyleSheet("QComboBox { background: #725300; color: #ffffff; }")
        elif isinstance(widget, QLineEdit):
            if record.matched_name:
                # Keep the text inherited from the active theme.  White text was
                # unreadable on the light-theme editor background.
                widget.setStyleSheet("QLineEdit { border: 1px solid #f59e0b; }")
            else:
                widget.setStyleSheet("QLineEdit { background: #7b2635; color: #ffffff; }")


class BatterReviewTable(ReviewTableBase):
    """Editable table that keeps OCR values distinct from user edits."""

    records_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__([title for title, _ in BATTER_COLUMNS], parent)
        self._compact_column_widths = _COMPACT_COLUMN_WIDTHS
        self.records: list[RecognizedBatter] = []
        self._candidate_names: tuple[str, ...] = ()

    def set_records(self, records: list[RecognizedBatter], candidate_names: tuple[str, ...]) -> None:
        self.records = records
        self._candidate_names = candidate_names
        self.setRowCount(len(records))
        for row, record in enumerate(records):
            self._populate_row(row, record)
        self._fit_columns()
        if records:
            self.selectRow(0)

    def _populate_row(self, row: int, record: RecognizedBatter) -> None:
        status = QTableWidgetItem(record.status)
        self._paint_status_item(status, record.status)
        status.setToolTip(self._status_tooltip(record))
        status.setFlags(status.flags() & ~status.flags().ItemIsEditable)
        self.setItem(row, 0, status)

        reason_item = QTableWidgetItem(record.review_reason_text)
        reason_item.setFlags(reason_item.flags() & ~reason_item.flags().ItemIsEditable)
        reason_item.setToolTip(self._status_tooltip(record))
        self.setItem(row, 1, reason_item)

        self.setCellWidget(row, 2, self._name_widget(row, record, self._candidate_names))

        ocr_item = QTableWidgetItem(record.ocr_name)
        ocr_item.setFlags(ocr_item.flags() & ~ocr_item.flags().ItemIsEditable)
        ocr_item.setToolTip(self._name_tooltip(record))
        self.setItem(row, 3, ocr_item)

        games_item = QTableWidgetItem("1")
        games_item.setFlags(games_item.flags() & ~games_item.flags().ItemIsEditable)
        games_item.setToolTip("GameJSON v1の固定値: 試合 = 1")
        self.setItem(row, 4, games_item)

        for column, (_title, field_name) in enumerate(BATTER_COLUMNS[5:-1], start=5):
            assert field_name in BATTER_STAT_FIELDS
            editor = QLineEdit(self)
            editor.setValidator(QIntValidator(0, 9999, editor))
            value = getattr(record, field_name)
            editor.setText("" if value is None else str(value))
            editor.setAlignment(Qt.AlignmentFlag.AlignRight)
            editor.textEdited.connect(lambda text, r=row, f=field_name: self._set_stat(r, f, text))
            self.setCellWidget(row, column, editor)
            self._paint_stat_editor(editor, value)

        remarks_editor = QLineEdit(self)
        remarks_editor.setText(record.remarks)
        remarks_editor.setPlaceholderText("任意の備考")
        remarks_editor.textEdited.connect(lambda text, r=row: self._set_remarks(r, text))
        self.setCellWidget(row, len(BATTER_COLUMNS) - 1, remarks_editor)

    def _set_remarks(self, row: int, text: str) -> None:
        self.records[row].remarks = text
        self.records_changed.emit()

    def _set_stat(self, row: int, field_name: str, text: str) -> None:
        editor = self.cellWidget(row, self._column_for(field_name))
        if not isinstance(editor, QLineEdit):
            return
        value = int(text) if text and text.isdigit() else None
        self.records[row].set_stat(field_name, value)
        self._paint_stat_editor(editor, value)
        self._refresh_status(row)
        self.records_changed.emit()

    def _column_for(self, field_name: str) -> int:
        return next(index for index, (_title, name) in enumerate(BATTER_COLUMNS) if name == field_name)

    def _refresh_status(self, row: int) -> None:
        record = self.records[row]
        item = self.item(row, 0)
        if item is None:
            return
        item.setText(record.status)
        self._paint_status_item(item, record.status)
        item.setToolTip(self._status_tooltip(record))
        reason_item = self.item(row, 1)
        if reason_item is not None:
            reason_item.setText(record.review_reason_text)
            reason_item.setToolTip(self._status_tooltip(record))
        self._refresh_name_widget(row)

    @staticmethod
    def _paint_stat_editor(editor: QLineEdit, value: int | None) -> None:
        editor.setStyleSheet("QLineEdit { background: #7b2635; color: #ffffff; }" if value is None else "")
        editor.setToolTip("OCRで認識できませんでした。0以上の整数を入力してください。" if value is None else "")

    @staticmethod
    def _name_tooltip(record: RecognizedBatter) -> str:
        second = "" if record.second_name is None else f"\n2位: {record.second_name} ({record.second_score:.1f})"
        return f"1位: {record.matched_name or 'なし'} ({record.match_score:.1f}){second}"

    @staticmethod
    def _status_tooltip(record: RecognizedBatter) -> str:
        return record.review_reason_text


PITCHER_COLUMNS: tuple[tuple[str, str | None], ...] = (
    ("状態", None), ("確認理由", None), ("選手名", "matched_name"), ("OCR名", "ocr_name"),
    ("登板", None), ("投球回", "innings"), ("投球回分数", "inning_fraction"), ("球数", "pitches"),
    ("打者", "batters_faced"), ("被安打", "hits_allowed"), ("奪三振", "strikeouts"),
    ("四死球", "walks_hbp"), ("失点", "runs"), ("自責点", "earned_runs"),
    ("暴投", "wild_pitches"), ("被本塁打", "home_runs_allowed"), ("QS", "qs"), ("HQS", "hqs"),
    ("先発", "starts"), ("勝利", "wins"), ("敗戦", "losses"), ("H", "holds"), ("S", "saves"),
    ("完投", "complete_games"), ("完封", "shutouts"), ("無四球", "no_walk_games"), ("敬遠数", "intentional_walks"),
    ("備考", "remarks"),
)
_PITCHER_COMPACT_COLUMN_WIDTHS = (58, 150, 110, 75, *([48] * 23), 160)


class PitcherReviewTable(ReviewTableBase):
    """Pitcher counterpart to ``BatterReviewTable`` with editable automatic flags."""

    records_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__([title for title, _ in PITCHER_COLUMNS], parent)
        self._compact_column_widths = _PITCHER_COMPACT_COLUMN_WIDTHS
        self.records: list[RecognizedPitcher] = []
        self._candidate_names: tuple[str, ...] = ()

    def set_records(self, records: list[RecognizedPitcher], candidate_names: tuple[str, ...]) -> None:
        self.records = records
        self._candidate_names = candidate_names
        self.setRowCount(len(records))
        for row, record in enumerate(records):
            self._populate_row(row, record)
        self._fit_columns()
        if records:
            self.selectRow(0)

    def _populate_row(self, row: int, record: RecognizedPitcher) -> None:
        status = QTableWidgetItem(record.status)
        self._paint_status_item(status, record.status)
        status.setToolTip(record.review_reason_text)
        status.setFlags(status.flags() & ~status.flags().ItemIsEditable)
        self.setItem(row, 0, status)
        reason = QTableWidgetItem(record.review_reason_text)
        reason.setFlags(reason.flags() & ~reason.flags().ItemIsEditable)
        reason.setToolTip(record.review_reason_text)
        self.setItem(row, 1, reason)

        self.setCellWidget(row, 2, self._name_widget(row, record, self._candidate_names))

        ocr_item = QTableWidgetItem(record.ocr_name)
        ocr_item.setFlags(ocr_item.flags() & ~ocr_item.flags().ItemIsEditable)
        second = "" if record.second_name is None else f"\n2位: {record.second_name} ({record.second_score:.1f})"
        ocr_item.setToolTip(f"1位: {record.matched_name or 'なし'} ({record.match_score:.1f}){second}")
        self.setItem(row, 3, ocr_item)

        appearances_item = QTableWidgetItem("1")
        appearances_item.setFlags(appearances_item.flags() & ~appearances_item.flags().ItemIsEditable)
        appearances_item.setToolTip("GameJSON v1の固定値: 登板 = 1")
        self.setItem(row, 4, appearances_item)

        for field_name in PITCHER_OCR_FIELDS:
            column = self._column_for(field_name)
            if field_name == "inning_fraction":
                editor = QComboBox(self)
                editor.addItem("--", None)
                for value in (0, 1, 2):
                    editor.addItem(str(value), value)
                if getattr(record, field_name) in (0, 1, 2):
                    editor.setCurrentIndex(int(getattr(record, field_name)) + 1)
                editor.currentIndexChanged.connect(lambda _index, r=row, f=field_name: self._set_fraction(r, f))
                self.setCellWidget(row, column, editor)
                self._paint_optional_editor(editor, getattr(record, field_name))
            else:
                editor = QLineEdit(self)
                editor.setValidator(QIntValidator(0, 9999, editor))
                value = getattr(record, field_name)
                editor.setText("" if value is None else str(value))
                editor.setAlignment(Qt.AlignmentFlag.AlignRight)
                editor.textEdited.connect(lambda text, r=row, f=field_name: self._set_integer(r, f, text))
                self.setCellWidget(row, column, editor)
                self._paint_optional_editor(editor, value)

        for field_name in PITCHER_MANUAL_BINARY_FIELDS:
            column = self._column_for(field_name)
            editor = QComboBox(self)
            editor.addItem("0", 0)
            editor.addItem("1", 1)
            editor.setCurrentIndex(int(getattr(record, field_name)))
            editor.currentIndexChanged.connect(lambda _index, r=row, f=field_name: self._set_binary(r, f))
            if field_name in ("wins", "losses", "holds", "saves"):
                editor.setToolTip(f"画面左の判定OCR: {record.ocr_decision or 'なし'}")
            self.setCellWidget(row, column, editor)
        for field_name in PITCHER_MANUAL_INTEGER_FIELDS:
            column = self._column_for(field_name)
            editor = QLineEdit(self)
            editor.setValidator(QIntValidator(0, 9999, editor))
            editor.setText(str(getattr(record, field_name)))
            editor.setAlignment(Qt.AlignmentFlag.AlignRight)
            editor.textEdited.connect(lambda text, r=row, f=field_name: self._set_integer(r, f, text))
            self.setCellWidget(row, column, editor)

        remarks_editor = QLineEdit(self)
        remarks_editor.setText(record.remarks)
        remarks_editor.setPlaceholderText("任意の備考")
        remarks_editor.textEdited.connect(lambda text, r=row: self._set_remarks(r, text))
        self.setCellWidget(row, len(PITCHER_COLUMNS) - 1, remarks_editor)

        self._refresh_automatic_pitcher_flags(row)
        self._refresh_status(row)

    def _set_remarks(self, row: int, text: str) -> None:
        self.records[row].remarks = text
        self.records_changed.emit()

    def _set_fraction(self, row: int, field_name: str) -> None:
        editor = self.cellWidget(row, self._column_for(field_name))
        if not isinstance(editor, QComboBox):
            return
        value = editor.currentData()
        self.records[row].set_stat(field_name, value)
        self._paint_optional_editor(editor, value)
        self._refresh_automatic_pitcher_flags(row)
        self._refresh_status(row)
        self.records_changed.emit()

    def _set_binary(self, row: int, field_name: str) -> None:
        editor = self.cellWidget(row, self._column_for(field_name))
        if isinstance(editor, QComboBox):
            self.records[row].set_stat(field_name, int(editor.currentData()))
            self._refresh_automatic_pitcher_flags(row)
            self._refresh_status(row)
            self.records_changed.emit()

    def _set_integer(self, row: int, field_name: str, text: str) -> None:
        editor = self.cellWidget(row, self._column_for(field_name))
        if not isinstance(editor, QLineEdit):
            return
        value = int(text) if text and text.isdigit() else None
        if field_name in PITCHER_MANUAL_INTEGER_FIELDS and value is None:
            value = 0
        self.records[row].set_stat(field_name, value)
        self._paint_optional_editor(editor, value)
        self._refresh_automatic_pitcher_flags(row)
        self._refresh_status(row)
        self.records_changed.emit()

    def _refresh_automatic_pitcher_flags(self, row: int) -> None:
        """Refresh unmodified automatic flags after an OCR-stat correction."""
        record = self.records[row]
        record.refresh_automatic_fields(only_pitcher=len(self.records) == 1)
        automatic_fields = ("qs", "hqs", "starts", "complete_games", "shutouts", "no_walk_games")
        for field_name in automatic_fields:
            editor = self.cellWidget(row, self._column_for(field_name))
            if not isinstance(editor, QComboBox):
                continue
            if field_name not in record.manually_corrected_stats:
                with QSignalBlocker(editor):
                    editor.setCurrentIndex(int(getattr(record, field_name)))
                editor.setToolTip("自動計算値（手動で変更できます）")
            else:
                editor.setToolTip("手動修正済み（自動計算では上書きしません）")

    def _column_for(self, field_name: str) -> int:
        return next(index for index, (_title, name) in enumerate(PITCHER_COLUMNS) if name == field_name)

    def _refresh_status(self, row: int) -> None:
        record = self.records[row]
        status = self.item(row, 0)
        if status is not None:
            status.setText(record.status)
            self._paint_status_item(status, record.status)
            status.setToolTip(record.review_reason_text)
        reason = self.item(row, 1)
        if reason is not None:
            reason.setText(record.review_reason_text)
            reason.setToolTip(record.review_reason_text)
        self._refresh_name_widget(row)

    @staticmethod
    def _paint_optional_editor(editor, value: int | None) -> None:  # type: ignore[no-untyped-def]
        editor.setStyleSheet("QLineEdit, QComboBox { background: #7b2635; color: #ffffff; }" if value is None else "")
        editor.setToolTip("OCRで認識できませんでした。値を確認してください。" if value is None else "")
