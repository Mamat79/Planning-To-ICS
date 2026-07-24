#!/usr/bin/env python
"""Native Qt desktop interface for Planning to ICS V2."""

from __future__ import annotations

import json
import sys
import traceback
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from PySide6.QtCore import (
    QDateTime,
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QPalette,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QStyle,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from planning_services import (
    export_combined_results,
    export_multiple_results,
    export_result,
    extract_one,
    extract_results_for_pdfs,
    list_planning_pdfs,
    mission_titles,
    open_path,
    pdf_label,
    people_for_pdf,
    people_sharing_missions,
    week_year_for_pdf,
)
from planning_settings import (
    import_settings,
    load_settings,
    reset_settings,
    save_settings,
)
from planning_to_ics import (
    DEFAULT_TIMEZONE,
    DayExtraction,
    ExtractionResult,
    WorkEvent,
    diagnose_events,
    extract_all_plannings,
    format_summary,
    name_match_score,
)

APP_VERSION = "V2.0"
APP_NAME = "Planning to ICS"
GITHUB_URL = "https://github.com/Mamat79/Planning-To-ICS"

LIGHT_STYLESHEET = """
QMainWindow, QDialog { background: #f5f7f8; color: #172229; }
QWidget { color: #172229; font-family: "Segoe UI"; font-size: 10pt; }
QFrame#sidePanel { background: #eef2f3; border-right: 1px solid #d4dcdf; }
QFrame#instruction { background: #eaf7f2; border: 1px solid #b7dfcf; border-radius: 5px; }
QFrame#dropZone { background: transparent; border: 1px dashed #7d9aa4; border-radius: 5px; }
QLabel#title { font-size: 17pt; font-weight: 700; color: #10242b; }
QLabel#version { color: #50656e; font-size: 9pt; }
QLabel#signature { color: #536970; font-style: italic; }
QLabel#agents { color: #70838a; font-size: 8pt; font-style: italic; }
QLabel#signatureFader { color: #8a999e; font-family: "Consolas"; font-size: 7pt; }
QLabel#sectionTitle { font-size: 13pt; font-weight: 700; }
QLineEdit, QComboBox, QPlainTextEdit, QListWidget, QTableWidget, QDateTimeEdit {
  background: white; border: 1px solid #bdcbd0; border-radius: 4px; padding: 5px;
  selection-background-color: #14786b;
}
QComboBox QAbstractItemView, QListView {
  background: white; color: #172229; border: 1px solid #9fb1b7;
  selection-background-color: #14786b; selection-color: white; outline: 0;
}
QToolTip { background: #ffffff; color: #172229; border: 1px solid #9fb1b7; }
QPushButton { min-height: 30px; padding: 3px 12px; border: 1px solid #1b756c; border-radius: 4px; background: white; color: #155f58; font-weight: 600; }
QPushButton:hover { background: #edf8f5; }
QPushButton#primary { background: #14786b; color: white; border-color: #14786b; }
QPushButton#primary:hover { background: #0f665b; }
QPushButton:disabled { color: #8b989d; border-color: #ccd3d6; background: #edf0f1; }
QHeaderView::section { background: #e9eef0; color: #26373d; padding: 7px; border: 0; border-bottom: 1px solid #ccd6d9; font-weight: 600; }
QTabBar::tab { padding: 8px 14px; }
QMenuBar, QMenu { background: #f5f7f8; color: #172229; }
QMenuBar::item:selected, QMenu::item:selected { background: #dcebe7; color: #10242b; }
QStatusBar { background: #edf1f2; color: #172229; }
"""

DARK_STYLESHEET = """
QMainWindow, QDialog { background: #1e2225; color: #e7ecee; }
QWidget { color: #e7ecee; font-family: "Segoe UI"; font-size: 10pt; }
QFrame#sidePanel { background: #252b2f; border-right: 1px solid #3a4449; }
QFrame#instruction { background: #18352f; border: 1px solid #28695d; border-radius: 5px; }
QFrame#dropZone { background: transparent; border: 1px dashed #76939d; border-radius: 5px; }
QLabel#title { font-size: 17pt; font-weight: 700; color: #f2f7f8; }
QLabel#version { color: #a9bbc2; font-size: 9pt; }
QLabel#signature { color: #b6c5ca; font-style: italic; }
QLabel#agents { color: #8ea1a8; font-size: 8pt; font-style: italic; }
QLabel#signatureFader { color: #71848b; font-family: "Consolas"; font-size: 7pt; }
QLabel#sectionTitle { font-size: 13pt; font-weight: 700; }
QLineEdit, QComboBox, QPlainTextEdit, QListWidget, QTableWidget, QDateTimeEdit {
  background: #15191c; color: #e7ecee; border: 1px solid #4c5a60; border-radius: 4px; padding: 5px;
  selection-background-color: #278b7c;
}
QComboBox QAbstractItemView, QListView {
  background: #15191c; color: #e7ecee; border: 1px solid #58676d;
  selection-background-color: #278b7c; selection-color: white; outline: 0;
}
QToolTip { background: #252b2f; color: #e7ecee; border: 1px solid #58676d; }
QPushButton { min-height: 30px; padding: 3px 12px; border: 1px solid #4c958a; border-radius: 4px; background: #252b2f; color: #bde4dc; font-weight: 600; }
QPushButton:hover { background: #30413f; }
QPushButton#primary { background: #238071; color: white; border-color: #238071; }
QPushButton#primary:hover { background: #2b9483; }
QPushButton:disabled { color: #69777c; border-color: #3b4448; background: #24292c; }
QHeaderView::section { background: #2b3236; color: #dfe7e9; padding: 7px; border: 0; border-bottom: 1px solid #49545a; font-weight: 600; }
QTabBar::tab { padding: 8px 14px; }
QMenuBar, QMenu, QStatusBar { background: #252b2f; color: #e7ecee; }
QMenuBar::item:selected, QMenu::item:selected { background: #344147; color: white; }
"""


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def application_palette(dark: bool) -> QPalette:
    palette = QPalette()
    colors = (
        {
            "window": "#1e2225",
            "base": "#15191c",
            "alternate": "#252b2f",
            "text": "#e7ecee",
            "button": "#252b2f",
            "button_text": "#e7ecee",
            "highlight": "#278b7c",
            "highlighted_text": "#ffffff",
            "placeholder": "#87979d",
            "tooltip": "#252b2f",
        }
        if dark
        else {
            "window": "#f5f7f8",
            "base": "#ffffff",
            "alternate": "#eef2f3",
            "text": "#172229",
            "button": "#ffffff",
            "button_text": "#155f58",
            "highlight": "#14786b",
            "highlighted_text": "#ffffff",
            "placeholder": "#6c7c82",
            "tooltip": "#ffffff",
        }
    )
    palette.setColor(QPalette.ColorRole.Window, QColor(colors["window"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors["base"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["alternate"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors["button"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors["button_text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors["highlight"]))
    palette.setColor(
        QPalette.ColorRole.HighlightedText, QColor(colors["highlighted_text"])
    )
    palette.setColor(
        QPalette.ColorRole.PlaceholderText, QColor(colors["placeholder"])
    )
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors["tooltip"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(colors["text"]))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor("#8b989d" if not dark else "#69777c"),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor("#8b989d" if not dark else "#69777c"),
    )
    return palette


class WorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, function: Callable[[], Any]) -> None:
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            value = self.function()
        except Exception as exc:
            details = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            try:
                self.signals.failed.emit(details)
            except RuntimeError:
                pass
        else:
            try:
                self.signals.succeeded.emit(value)
            except RuntimeError:
                pass
        finally:
            try:
                self.signals.finished.emit()
            except RuntimeError:
                pass


class PdfSelectionDialog(QDialog):
    def __init__(
        self, pdfs: list[Path], selected: list[Path], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sélectionner plusieurs semaines")
        self.resize(720, 560)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Cochez les plannings à regrouper dans un seul fichier ICS. "
            "Une seule semaine par PDF sera retenue."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher un PDF...")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        selected_keys = {str(path.resolve()).casefold() for path in selected if path.exists()}
        for pdf in pdfs:
            item = QListWidgetItem(pdf_label(pdf))
            item.setData(Qt.ItemDataRole.UserRole, str(pdf))
            item.setToolTip(str(pdf))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = str(pdf.resolve()).casefold() in selected_keys
            item.setCheckState(
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget, 1)

        tools = QHBoxLayout()
        select_all = QPushButton("Tout sélectionner")
        select_all.clicked.connect(lambda: self._set_all(True))
        clear_all = QPushButton("Tout désélectionner")
        clear_all.clicked.connect(lambda: self._set_all(False))
        add_files = QPushButton("Ajouter d'autres PDF...")
        add_files.clicked.connect(self._add_files)
        tools.addWidget(select_all)
        tools.addWidget(clear_all)
        tools.addStretch()
        tools.addWidget(add_files)
        layout.addLayout(tools)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Continuer")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _filter(self, text: str) -> None:
        needle = text.casefold().strip()
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            item.setHidden(needle not in item.text().casefold())

    def _set_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if not item.isHidden():
                item.setCheckState(state)

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Ajouter des plannings PDF", "", "Fichiers PDF (*.pdf)"
        )
        existing = {
            str(self.list_widget.item(index).data(Qt.ItemDataRole.UserRole)).casefold()
            for index in range(self.list_widget.count())
        }
        for path_text in paths:
            path = Path(path_text)
            if str(path).casefold() in existing:
                continue
            item = QListWidgetItem(pdf_label(path))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.list_widget.addItem(item)
            existing.add(str(path).casefold())

    def selected_pdfs(self) -> list[Path]:
        return [
            Path(str(item.data(Qt.ItemDataRole.UserRole)))
            for index in range(self.list_widget.count())
            if (item := self.list_widget.item(index)).checkState()
            == Qt.CheckState.Checked
        ]


class TechnicianSelectionDialog(QDialog):
    def __init__(
        self,
        results: list[ExtractionResult],
        principal: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.results = results
        self.principal = principal
        self.action = ""
        self.common_people = people_sharing_missions(results, principal)
        self.setWindowTitle("Ajouter des techniciens")
        self.resize(1000, 650)
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Le technicien principal est déjà coché. Vous pouvez ajouter d'autres "
            "techniciens ou sélectionner ceux qui partagent au moins une mission."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher un technicien...")
        self.search.textChanged.connect(self._filter)
        toolbar.addWidget(self.search, 1)
        all_button = QPushButton("Tout sélectionner")
        all_button.clicked.connect(lambda: self._set_all(True))
        none_button = QPushButton("Tout désélectionner")
        none_button.clicked.connect(lambda: self._set_all(False))
        common_button = QPushButton("Même(s) mission(s)")
        common_button.setToolTip(
            "Cocher les techniciens qui travaillent sur au moins une mission du technicien principal"
        )
        common_button.clicked.connect(self._select_common)
        toolbar.addWidget(all_button)
        toolbar.addWidget(none_button)
        toolbar.addWidget(common_button)
        layout.addLayout(toolbar)

        self.table = QTableWidget(len(results), 5)
        self.table.setHorizontalHeaderLabels(
            ["Inclure", "Technicien", "Événements", "Missions", "Mission commune"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.checkboxes: list[QCheckBox] = []
        for row, result in enumerate(results):
            check = QCheckBox()
            check.setChecked(name_match_score(result.person_name, principal) >= 0.95)
            holder = QWidget()
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(0, 0, 0, 0)
            holder_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            holder_layout.addWidget(check)
            self.checkboxes.append(check)
            self.table.setCellWidget(row, 0, holder)
            self.table.setItem(row, 1, QTableWidgetItem(result.person_name))
            self.table.setItem(row, 2, QTableWidgetItem(str(len(result.events))))
            titles = mission_titles(result)
            missions = " ; ".join(titles[:5]) or "Aucune mission exportable"
            if len(titles) > 5:
                missions += " ; ..."
            self.table.setItem(row, 3, QTableWidgetItem(missions))
            common = result.person_name in self.common_people
            label = "Principal" if name_match_score(result.person_name, principal) >= 0.95 else (
                "Oui" if common else "Non"
            )
            self.table.setItem(row, 4, QTableWidgetItem(label))
            self.table.setRowHeight(row, 48)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("Annuler")
        cancel.clicked.connect(self.reject)
        preview = QPushButton("Prévisualiser et modifier")
        preview.clicked.connect(lambda: self._finish("preview"))
        direct = QPushButton("Exporter directement")
        direct.setObjectName("primary")
        direct.clicked.connect(lambda: self._finish("direct"))
        actions.addWidget(cancel)
        actions.addWidget(preview)
        actions.addWidget(direct)
        layout.addLayout(actions)

    def _filter(self, text: str) -> None:
        needle = text.casefold().strip()
        for row, result in enumerate(self.results):
            self.table.setRowHidden(row, needle not in result.person_name.casefold())

    def _set_all(self, checked: bool) -> None:
        for row, checkbox in enumerate(self.checkboxes):
            if not self.table.isRowHidden(row):
                checkbox.setChecked(checked)

    def _select_common(self) -> None:
        for result, checkbox in zip(self.results, self.checkboxes):
            checkbox.setChecked(
                result.person_name in self.common_people
                or name_match_score(result.person_name, self.principal) >= 0.95
            )

    def _finish(self, action: str) -> None:
        if not self.selected_results():
            QMessageBox.warning(self, APP_NAME, "Sélectionnez au moins un technicien.")
            return
        self.action = action
        self.accept()

    def selected_results(self) -> list[ExtractionResult]:
        return [
            result
            for result, checkbox in zip(self.results, self.checkboxes)
            if checkbox.isChecked()
        ]


@dataclass
class EventRow:
    original: WorkEvent
    include: QCheckBox
    start: QDateTimeEdit
    end: QDateTimeEdit
    summary: QLineEdit
    description: QPlainTextEdit


class EventEditorDialog(QDialog):
    def __init__(
        self,
        results: list[ExtractionResult],
        title: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.results = results
        self.rows: list[list[EventRow]] = []
        self.setWindowTitle(title)
        self.resize(1380, 800)
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Vérifiez les événements avant l'export. Les cases, dates, heures, "
            "titres et descriptions restent modifiables."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.tabs = QTabWidget()
        for result in results:
            self.tabs.addTab(self._result_tab(result), self._tab_label(result))
        layout.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Exporter ICS")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _tab_label(self, result: ExtractionResult) -> str:
        if len(self.results) == 1:
            return f"{result.person_name} · S{result.week:02d} {result.year}"
        same_person = len({item.person_name for item in self.results}) == 1
        return (
            f"S{result.week:02d} {result.year}"
            if same_person
            else result.person_name
        )

    def _result_tab(self, result: ExtractionResult) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        diagnostics = diagnose_events(result.events)
        ignored = sum(1 for day in result.days if not day.included)
        summary = QLabel(
            f"Période : S{result.week:02d} {result.year}   ·   "
            f"{diagnostics.event_count} événement(s)   ·   "
            f"{ignored} jour(s) ignoré(s)   ·   "
            f"{diagnostics.overnight_count} vacation(s) de nuit   ·   "
            f"{diagnostics.duplicate_count} doublon(s)   ·   "
            f"{diagnostics.overlap_count} chevauchement(s)"
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        table = QTableWidget(len(result.events), 5)
        table.setHorizontalHeaderLabels(
            ["Inclure", "Début", "Fin", "Résumé", "Description"]
        )
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        result_rows: list[EventRow] = []
        for row, event in enumerate(result.events):
            include = QCheckBox()
            include.setChecked(True)
            include_holder = QWidget()
            include_layout = QHBoxLayout(include_holder)
            include_layout.setContentsMargins(0, 0, 0, 0)
            include_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            include_layout.addWidget(include)
            table.setCellWidget(row, 0, include_holder)

            start = QDateTimeEdit(QDateTime(event.start))
            start.setDisplayFormat("dd/MM/yyyy  HH:mm")
            start.setCalendarPopup(True)
            end = QDateTimeEdit(QDateTime(event.end))
            end.setDisplayFormat("dd/MM/yyyy  HH:mm")
            end.setCalendarPopup(True)
            summary_edit = QLineEdit(event.summary)
            description = QPlainTextEdit(event.description)
            description.setTabChangesFocus(True)
            table.setCellWidget(row, 1, start)
            table.setCellWidget(row, 2, end)
            table.setCellWidget(row, 3, summary_edit)
            table.setCellWidget(row, 4, description)
            table.setRowHeight(row, 84)
            result_rows.append(
                EventRow(event, include, start, end, summary_edit, description)
            )
        self.rows.append(result_rows)
        layout.addWidget(table, 1)
        return container

    @staticmethod
    def _aware_datetime(editor: QDateTimeEdit) -> datetime:
        value = editor.dateTime()
        naive = datetime.combine(value.date().toPython(), value.time().toPython())
        return naive.replace(tzinfo=ZoneInfo(DEFAULT_TIMEZONE))

    def edited_results(self) -> list[ExtractionResult]:
        edited: list[ExtractionResult] = []
        for original_result, rows in zip(self.results, self.rows):
            events: list[WorkEvent] = []
            for row in rows:
                if not row.include.isChecked():
                    continue
                start = self._aware_datetime(row.start)
                end = self._aware_datetime(row.end)
                if end <= start:
                    raise ValueError(
                        f"La fin doit être postérieure au début pour « {row.summary.text()} »."
                    )
                summary = row.summary.text().strip()
                if not summary:
                    raise ValueError("Le résumé d'un événement ne peut pas être vide.")
                events.append(
                    WorkEvent(
                        day_label=row.original.day_label,
                        summary=summary,
                        description=row.description.toPlainText().strip(),
                        start=start,
                        end=end,
                        source_text=row.original.source_text,
                    )
                )
            day_date = (
                min((event.start.date() for event in events), default=original_result.days[0].date)
                if original_result.days
                else datetime.now().date()
            )
            warnings = list(original_result.warnings)
            warnings.append("ICS vérifié ou modifié depuis la prévisualisation V2.")
            edited.append(
                ExtractionResult(
                    pdf=original_result.pdf,
                    person_name=original_result.person_name,
                    matched_score=original_result.matched_score,
                    week=original_result.week,
                    year=original_result.year,
                    days=[
                        DayExtraction(
                            label="Modifié",
                            date=day_date,
                            raw_text="Événements modifiés depuis la prévisualisation.",
                            included=events,
                        )
                    ],
                    warnings=warnings,
                )
            )
        return edited


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = load_settings()
        self.thread_pool = QThreadPool.globalInstance()
        self.active_workers: set[Worker] = set()
        self.pdfs: list[Path] = []
        self.selected_multi_pdfs: list[Path] = []
        self.busy_count = 0
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1380, 860)
        self.setMinimumSize(1050, 700)
        self.setAcceptDrops(True)
        icon = resource_path("assets/planning-to-ics.ico")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

        self._build_menu()
        self._build_ui()
        self.apply_dark_mode(self.settings.get("dark_mode") == "true")
        self.refresh_pdfs()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&Fichier")
        import_action = QAction("Importer mes réglages...", self)
        import_action.triggered.connect(self.import_settings_file)
        export_action = QAction("Exporter mes réglages...", self)
        export_action.triggered.connect(self.export_settings_file)
        reset_action = QAction("Réinitialiser les réglages", self)
        reset_action.triggered.connect(self.reset_all_settings)
        quit_action = QAction("Quitter", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(import_action)
        file_menu.addAction(export_action)
        file_menu.addSeparator()
        file_menu.addAction(reset_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        view_menu = self.menuBar().addMenu("&Affichage")
        self.dark_action = QAction("Mode sombre", self)
        self.dark_action.setCheckable(True)
        self.dark_action.triggered.connect(self.apply_dark_mode)
        view_menu.addAction(self.dark_action)

        help_menu = self.menuBar().addMenu("&Aide")
        notice_action = QAction("Ouvrir la notice", self)
        notice_action.triggered.connect(self.open_notice)
        github_action = QAction("Ouvrir le dépôt GitHub", self)
        github_action.triggered.connect(lambda: webbrowser.open(GITHUB_URL))
        about_action = QAction(f"À propos de {APP_NAME}", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(notice_action)
        help_menu.addSeparator()
        help_menu.addAction(github_action)
        help_menu.addAction(about_action)

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        header.setContentsMargins(22, 14, 22, 12)
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        version = QLabel(APP_VERSION)
        version.setObjectName("version")
        header.addWidget(title)
        header.addWidget(version)
        header.addStretch()
        signature_box = QVBoxLayout()
        signature_box.setSpacing(0)
        signature = QLabel("by Mamat")
        signature.setObjectName("signature")
        agents = QLabel("et ses agents")
        agents.setObjectName("agents")
        signature_fader = QLabel("-------[]--")
        signature_fader.setObjectName("signatureFader")
        signature_box.addWidget(signature, alignment=Qt.AlignmentFlag.AlignRight)
        signature_box.addWidget(agents, alignment=Qt.AlignmentFlag.AlignRight)
        signature_box.addWidget(
            signature_fader, alignment=Qt.AlignmentFlag.AlignRight
        )
        header.addLayout(signature_box)
        root.addLayout(header)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_side_panel())
        splitter.addWidget(self._build_result_panel())
        splitter.setSizes([420, 960])
        root.addWidget(splitter, 1)
        self.setCentralWidget(central)

        status = QStatusBar()
        self.status_label = QLabel("Prêt")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedWidth(150)
        self.progress.hide()
        status.addWidget(self.status_label, 1)
        status.addPermanentWidget(self.progress)
        self.setStatusBar(status)

    def _build_side_panel(self) -> QWidget:
        side = QFrame()
        side.setObjectName("sidePanel")
        side.setMinimumWidth(390)
        side.setMaximumWidth(500)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(10)

        self.planning_dir = QLineEdit(self.settings["planning_dir"])
        form.addRow("Dossier des plannings", self._path_row(self.planning_dir, self.choose_planning_dir))

        self.pdf_combo = QComboBox()
        self.pdf_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.pdf_combo.setMinimumContentsLength(25)
        self.pdf_combo.currentIndexChanged.connect(self.on_pdf_changed)
        browse_pdf = QPushButton("Parcourir")
        browse_pdf.clicked.connect(self.choose_pdf)
        pdf_row = QWidget()
        pdf_layout = QHBoxLayout(pdf_row)
        pdf_layout.setContentsMargins(0, 0, 0, 0)
        pdf_layout.addWidget(self.pdf_combo, 1)
        pdf_layout.addWidget(browse_pdf)
        form.addRow("PDF de planning", pdf_row)

        self.drop_zone = QFrame()
        self.drop_zone.setObjectName("dropZone")
        drop_layout = QVBoxLayout(self.drop_zone)
        drop_layout.setContentsMargins(8, 10, 8, 10)
        drop_label = QLabel("Glissez-déposez un PDF ici")
        drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(drop_label)
        form.addRow("", self.drop_zone)

        self.person_combo = QComboBox()
        self.person_combo.setEditable(True)
        self.person_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.person_combo.lineEdit().setPlaceholderText("Choisir un technicien...")
        form.addRow("Technicien", self.person_combo)

        self.output_dir = QLineEdit(self.settings["output_dir"])
        form.addRow("Exporter vers", self._path_row(self.output_dir, self.choose_output_dir))
        layout.addLayout(form)

        self.generate_button = QPushButton("Générer ICS")
        self.generate_button.setObjectName("primary")
        self.generate_button.clicked.connect(self.generate_single)
        self.preview_button = QPushButton("Prévisualiser et modifier")
        self.preview_button.clicked.connect(self.preview_single)
        primary_row = QHBoxLayout()
        primary_row.addWidget(self.generate_button)
        primary_row.addWidget(self.preview_button)
        layout.addLayout(primary_row)

        self.multi_people_button = QPushButton("Ajouter des techniciens")
        self.multi_people_button.clicked.connect(self.choose_technicians)
        self.multi_week_button = QPushButton("Plusieurs semaines")
        self.multi_week_button.clicked.connect(self.choose_multiple_weeks)
        alternate_row = QHBoxLayout()
        alternate_row.addWidget(self.multi_people_button)
        alternate_row.addWidget(self.multi_week_button)
        layout.addLayout(alternate_row)

        instruction = QFrame()
        instruction.setObjectName("instruction")
        instruction_layout = QVBoxLayout(instruction)
        instruction_layout.setContentsMargins(11, 9, 11, 9)
        instruction_text = QLabel(
            "Après génération, importez le fichier ICS dans votre agenda. "
            "Dans le nouvel Outlook : Calendrier > Ajouter un calendrier > "
            "Charger à partir d'un fichier."
        )
        instruction_text.setWordWrap(True)
        instruction_layout.addWidget(instruction_text)
        layout.addWidget(instruction)
        layout.addStretch()
        return side

    def _path_row(self, edit: QLineEdit, callback: Callable[[], None]) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton("Parcourir")
        button.clicked.connect(callback)
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return widget

    def _build_result_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 18, 24, 18)
        heading = QLabel("Analyse du planning")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        self.analysis = QPlainTextEdit()
        self.analysis.setReadOnly(True)
        self.analysis.setPlaceholderText(
            "Choisissez un PDF. Les techniciens détectés et le résumé du planning "
            "apparaîtront ici."
        )
        layout.addWidget(self.analysis, 1)
        self.last_export = QLabel("")
        self.last_export.setWordWrap(True)
        self.last_export.hide()
        layout.addWidget(self.last_export)
        return panel

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.busy_count += 1 if busy else -1
        self.busy_count = max(0, self.busy_count)
        active = self.busy_count > 0
        self.progress.setVisible(active)
        self.generate_button.setEnabled(not active)
        self.preview_button.setEnabled(not active)
        self.multi_people_button.setEnabled(not active)
        self.multi_week_button.setEnabled(not active)
        if message:
            self.status_label.setText(message)
        elif not active:
            self.status_label.setText("Prêt")

    def run_task(
        self,
        message: str,
        function: Callable[[], Any],
        success: Callable[[Any], None],
    ) -> None:
        worker = Worker(function)
        self.active_workers.add(worker)
        self._set_busy(True, message)
        worker.signals.succeeded.connect(success)
        worker.signals.failed.connect(self.show_error)

        def finished() -> None:
            self.active_workers.discard(worker)
            self._set_busy(False)

        worker.signals.finished.connect(finished)
        self.thread_pool.start(worker)

    def choose_planning_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Dossier des plannings", self.planning_dir.text()
        )
        if selected:
            self.planning_dir.setText(selected)
            self._save_paths()
            self.refresh_pdfs()

    def choose_output_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Dossier d'export", self.output_dir.text()
        )
        if selected:
            self.output_dir.setText(selected)
            self._save_paths()

    def choose_pdf(self) -> None:
        start = self.planning_dir.text() or str(Path.home())
        selected, _ = QFileDialog.getOpenFileName(
            self, "Choisir un planning PDF", start, "Fichiers PDF (*.pdf)"
        )
        if selected:
            self.set_selected_pdf(Path(selected))

    def refresh_pdfs(self) -> None:
        current = self.selected_pdf()
        self.pdfs = list_planning_pdfs(self.planning_dir.text())
        self.pdf_combo.blockSignals(True)
        self.pdf_combo.clear()
        self.pdf_combo.addItem("Choisir un PDF...", None)
        for pdf in self.pdfs:
            self.pdf_combo.addItem(pdf_label(pdf), str(pdf))
        self.pdf_combo.blockSignals(False)
        if current and current.exists():
            self.set_selected_pdf(current)
        elif self.pdf_combo.count() > 1:
            self.pdf_combo.setCurrentIndex(1)
        else:
            self.person_combo.clear()
            self.analysis.setPlainText("Aucun PDF trouvé dans ce dossier.")

    def set_selected_pdf(self, pdf: Path) -> None:
        if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
            self.show_error("Le fichier sélectionné n'est pas un PDF valide.")
            return
        index = self.pdf_combo.findData(str(pdf))
        if index < 0:
            self.pdf_combo.insertItem(1, pdf_label(pdf), str(pdf))
            index = 1
        self.pdf_combo.setCurrentIndex(index)

    def selected_pdf(self) -> Path | None:
        value = self.pdf_combo.currentData()
        return Path(str(value)) if value else None

    def selected_person(self) -> str:
        return self.person_combo.currentText().strip()

    def on_pdf_changed(self) -> None:
        pdf = self.selected_pdf()
        self.person_combo.clear()
        if not pdf:
            return

        def loaded(value: object) -> None:
            selected_pdf, year, week, people = value  # type: ignore[misc]
            if self.selected_pdf() != selected_pdf:
                return
            self.person_combo.addItems(list(people))
            self.analysis.setPlainText(
                f"{selected_pdf.name}\nSemaine {week} - {year}\n\n"
                f"{len(people)} technicien(s) détecté(s).\n"
                "Choisissez un technicien puis prévisualisez ou générez l'ICS."
            )
            self.status_label.setText(f"{len(people)} technicien(s) détecté(s)")

        self.run_task(
            "Analyse du PDF...",
            lambda: (pdf, *week_year_for_pdf(pdf), people_for_pdf(pdf)),
            loaded,
        )

    def _validate_selection(self) -> tuple[Path, str, Path] | None:
        pdf = self.selected_pdf()
        person = self.selected_person()
        output = Path(self.output_dir.text()).expanduser()
        if not pdf:
            self.show_error("Choisissez d'abord un PDF de planning.")
            return None
        if not person:
            self.show_error("Choisissez un technicien.")
            return None
        if not self.output_dir.text().strip():
            self.show_error("Choisissez un dossier d'export.")
            return None
        self._save_paths()
        return pdf, person, output

    def generate_single(self) -> None:
        selection = self._validate_selection()
        if not selection:
            return
        pdf, person, output = selection

        def exported(result: object) -> None:
            extraction, path = result  # type: ignore[misc]
            self.show_result(extraction)
            self.show_export_success([path])

        self.run_task(
            "Extraction et génération de l'ICS...",
            lambda: (lambda result: (result, export_result(result, output)))(
                extract_one(pdf, person)
            ),
            exported,
        )

    def preview_single(self) -> None:
        selection = self._validate_selection()
        if not selection:
            return
        pdf, person, output = selection

        def ready(result: object) -> None:
            extraction = result  # type: ignore[assignment]
            self.show_result(extraction)
            editor = EventEditorDialog(
                [extraction], "Prévisualiser et modifier", self
            )
            if editor.exec() != QDialog.DialogCode.Accepted:
                return
            try:
                edited = editor.edited_results()[0]
                path = export_result(edited, output)
            except Exception as exc:
                self.show_error(str(exc))
                return
            self.show_result(edited)
            self.show_export_success([path])

        self.run_task(
            "Extraction du planning...",
            lambda: extract_one(pdf, person),
            ready,
        )

    def choose_multiple_weeks(self) -> None:
        person = self.selected_person()
        if not person:
            self.show_error("Choisissez d'abord le technicien principal.")
            return
        available = list(self.pdfs)
        current = self.selected_pdf()
        if current and current not in available:
            available.insert(0, current)
        dialog = PdfSelectionDialog(
            available,
            self.selected_multi_pdfs or ([current] if current else []),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected = dialog.selected_pdfs()
        if len(selected) < 2:
            self.show_error("Sélectionnez au moins deux PDF pour plusieurs semaines.")
            return
        self.selected_multi_pdfs = selected
        output = Path(self.output_dir.text()).expanduser()
        self._save_paths()

        def ready(value: object) -> None:
            results, errors = value  # type: ignore[misc]
            if not results:
                self.show_error("\n".join(errors) or "Aucun planning exploitable.")
                return
            if errors:
                QMessageBox.warning(self, APP_NAME, "\n".join(errors))
            editor = EventEditorDialog(
                results, "Prévisualiser plusieurs semaines", self
            )
            if editor.exec() != QDialog.DialogCode.Accepted:
                return
            try:
                edited = editor.edited_results()
                path = export_combined_results(edited, output)
            except Exception as exc:
                self.show_error(str(exc))
                return
            self.analysis.setPlainText(
                "\n\n".join(format_summary(result) for result in edited)
            )
            self.show_export_success([path])

        self.run_task(
            f"Extraction de {len(selected)} semaine(s)...",
            lambda: extract_results_for_pdfs(selected, person),
            ready,
        )

    def choose_technicians(self) -> None:
        selection = self._validate_selection()
        if not selection:
            return
        pdf, principal, output = selection
        year, week = week_year_for_pdf(pdf)

        def ready(value: object) -> None:
            results = value  # type: ignore[assignment]
            dialog = TechnicianSelectionDialog(results, principal, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            selected = dialog.selected_results()
            if dialog.action == "preview":
                editor = EventEditorDialog(
                    selected, "Prévisualiser plusieurs techniciens", self
                )
                if editor.exec() != QDialog.DialogCode.Accepted:
                    return
                try:
                    selected = editor.edited_results()
                except Exception as exc:
                    self.show_error(str(exc))
                    return
            try:
                paths, zip_path = export_multiple_results(
                    selected, output, week, year
                )
            except Exception as exc:
                self.show_error(str(exc))
                return
            self.analysis.setPlainText(
                "\n\n".join(format_summary(result) for result in selected)
            )
            self.show_export_success(paths, zip_path)

        self.run_task(
            "Analyse de tous les techniciens...",
            lambda: extract_all_plannings(pdf, week, year),
            ready,
        )

    def show_result(self, result: ExtractionResult) -> None:
        diagnostics = diagnose_events(result.events)
        ignored = sum(1 for day in result.days if not day.included)
        heading = (
            f"Diagnostic : {diagnostics.event_count} événement(s), "
            f"{ignored} jour(s) ignoré(s), "
            f"{diagnostics.overnight_count} de nuit, "
            f"{diagnostics.duplicate_count} doublon(s), "
            f"{diagnostics.overlap_count} chevauchement(s).\n\n"
        )
        self.analysis.setPlainText(heading + format_summary(result))

    def show_export_success(
        self, paths: list[Path], zip_path: Path | None = None
    ) -> None:
        shown = zip_path or paths[0]
        self.last_export.setText(
            "Export terminé : " + ", ".join(path.name for path in paths)
            + (f"\nArchive : {zip_path.name}" if zip_path else "")
        )
        self.last_export.show()
        box = QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setIcon(QMessageBox.Icon.Information)
        box.setText("Export terminé.")
        box.setInformativeText(str(shown))
        open_button = box.addButton(
            "Ouvrir l'ICS" if len(paths) == 1 and not zip_path else "Ouvrir le dossier",
            QMessageBox.ButtonRole.AcceptRole,
        )
        folder_button = box.addButton(
            "Afficher dans le dossier", QMessageBox.ButtonRole.ActionRole
        )
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        try:
            if box.clickedButton() is open_button:
                open_path(paths[0] if len(paths) == 1 and not zip_path else shown.parent)
            elif box.clickedButton() is folder_button:
                open_path(shown.parent)
        except Exception as exc:
            self.show_error(str(exc))

    def show_error(self, message: str) -> None:
        self.status_label.setText("Erreur")
        QMessageBox.critical(self, APP_NAME, message)

    def apply_dark_mode(self, enabled: bool) -> None:
        self.dark_action.blockSignals(True)
        self.dark_action.setChecked(enabled)
        self.dark_action.blockSignals(False)
        app = QApplication.instance()
        app.setPalette(application_palette(enabled))
        app.setStyleSheet(DARK_STYLESHEET if enabled else LIGHT_STYLESHEET)
        save_settings({"dark_mode": "true" if enabled else "false"})

    def _save_paths(self) -> None:
        self.settings = save_settings(
            {
                "planning_dir": self.planning_dir.text().strip(),
                "output_dir": self.output_dir.text().strip(),
                "dark_mode": "true" if self.dark_action.isChecked() else "false",
            }
        )

    def export_settings_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter les réglages",
            "Planning_to_ICS_reglages.json",
            "Fichier JSON (*.json)",
        )
        if path:
            Path(path).write_text(
                json.dumps(load_settings(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def import_settings_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Importer les réglages", "", "Fichier JSON (*.json)"
        )
        if not path:
            return
        try:
            settings = import_settings(
                json.loads(Path(path).read_text(encoding="utf-8"))
            )
        except Exception as exc:
            self.show_error(str(exc))
            return
        self.planning_dir.setText(settings["planning_dir"])
        self.output_dir.setText(settings["output_dir"])
        self.apply_dark_mode(settings.get("dark_mode") == "true")
        self.refresh_pdfs()

    def reset_all_settings(self) -> None:
        answer = QMessageBox.question(
            self, APP_NAME, "Réinitialiser les dossiers et l'affichage ?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        settings = reset_settings()
        self.planning_dir.setText(settings["planning_dir"])
        self.output_dir.setText(settings["output_dir"])
        self.apply_dark_mode(False)
        self.refresh_pdfs()

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            f"À propos de {APP_NAME}",
            f"<b>{APP_NAME} {APP_VERSION}</b><br><br>"
            "Application de bureau native pour convertir les plannings PDF en ICS."
            "<br><br><i>by Mamat<br><small>et ses agents</small></i>",
        )

    def open_notice(self) -> None:
        filename = f"Planning_to_ICS_{APP_VERSION}_Notice.pdf"
        candidates = [
            resource_path(filename),
            Path(__file__).resolve().parent / "output" / "pdf" / filename,
        ]
        notice = next((path for path in candidates if path.is_file()), None)
        if notice is None:
            self.show_error(
                "La notice locale est introuvable. Réinstallez l'application "
                "ou ouvrez la page GitHub du projet."
            )
            return
        try:
            open_path(notice)
        except Exception as exc:
            self.show_error(str(exc))

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if any(Path(url.toLocalFile()).suffix.lower() == ".pdf" for url in urls):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_file() and path.suffix.lower() == ".pdf":
                self.set_selected_pdf(path)
                event.acceptProposedAction()
                return

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_paths()
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("Mamat et ses agents")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
