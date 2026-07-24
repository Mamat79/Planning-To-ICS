from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtGui import QPalette

import planning_native
import planning_settings
from planning_native import EventEditorDialog, MainWindow, TechnicianSelectionDialog
from planning_services import (
    extract_one,
    list_planning_pdfs,
    people_for_pdf,
    week_year_for_pdf,
)
from planning_to_ics import extract_all_plannings


@pytest.fixture(scope="session")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_native_entry_has_no_web_server_or_webview() -> None:
    source = Path(planning_native.__file__).read_text(encoding="utf-8")
    assert "ThreadingHTTPServer" not in source
    assert "BaseHTTPRequestHandler" not in source
    assert "webview" not in source.casefold()


def test_native_window_is_v2_and_starts_without_pdf(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        planning_native,
        "load_settings",
        lambda: {
            "planning_dir": str(tmp_path),
            "output_dir": str(tmp_path),
            "dark_mode": "false",
        },
    )
    monkeypatch.setattr(planning_native, "save_settings", lambda updates: updates)
    window = MainWindow()
    assert window.windowTitle() == "Planning to ICS V2.0"
    assert window.findChild(planning_native.QLabel, "signatureFader").text() == "-------[]--"
    help_actions = [
        action.text()
        for menu_action in window.menuBar().actions()
        if (menu := menu_action.menu()) is not None
        for action in menu.actions()
    ]
    assert "Ouvrir la notice" in help_actions
    assert window.pdf_combo.count() == 1
    assert "Aucun PDF" in window.analysis.toPlainText()
    window.close()


def test_native_light_and_dark_palettes_cover_popup_controls(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        planning_native,
        "load_settings",
        lambda: {
            "planning_dir": str(tmp_path),
            "output_dir": str(tmp_path),
            "dark_mode": "false",
        },
    )
    monkeypatch.setattr(planning_native, "save_settings", lambda updates: updates)
    window = MainWindow()

    window.apply_dark_mode(False)
    assert qt_app.palette().color(QPalette.ColorRole.Base).name() == "#ffffff"
    assert qt_app.palette().color(QPalette.ColorRole.Text).name() == "#172229"
    assert "QComboBox QAbstractItemView" in qt_app.styleSheet()

    window.apply_dark_mode(True)
    assert qt_app.palette().color(QPalette.ColorRole.Base).name() == "#15191c"
    assert qt_app.palette().color(QPalette.ColorRole.Text).name() == "#e7ecee"
    window.close()


def test_native_services_find_pdf_and_people(planning_pdf: Path) -> None:
    assert list_planning_pdfs(planning_pdf.parent) == [planning_pdf]
    assert week_year_for_pdf(planning_pdf) == (2026, 30)
    assert people_for_pdf(planning_pdf) == ("DUPONT ALICE", "MARTIN BOB")


def test_native_editor_keeps_and_modifies_events(
    qt_app: QApplication, planning_pdf: Path
) -> None:
    result = extract_one(planning_pdf, "DUPONT ALICE")
    dialog = EventEditorDialog([result], "Test")
    assert dialog.rows
    dialog.rows[0][0].summary.setText("Hôtel Étoilé modifié")
    edited = dialog.edited_results()[0]
    assert len(edited.events) == len(result.events)
    assert edited.events[0].summary == "Hôtel Étoilé modifié"
    assert edited.events[0].start == result.events[0].start
    dialog.reject()


def test_native_editor_can_exclude_event(
    qt_app: QApplication, planning_pdf: Path
) -> None:
    result = extract_one(planning_pdf, "DUPONT ALICE")
    dialog = EventEditorDialog([result], "Test")
    dialog.rows[0][0].include.setChecked(False)
    assert dialog.edited_results()[0].events == []
    dialog.reject()


def test_technician_dialog_selects_principal_and_shared_missions(
    qt_app: QApplication, planning_pdf: Path
) -> None:
    year, week = week_year_for_pdf(planning_pdf)
    results = extract_all_plannings(planning_pdf, week, year)
    dialog = TechnicianSelectionDialog(results, "DUPONT ALICE")
    selected = dialog.selected_results()
    assert [result.person_name for result in selected] == ["DUPONT ALICE"]
    dialog._select_common()
    assert "DUPONT ALICE" in {
        result.person_name for result in dialog.selected_results()
    }
    dialog.reject()


def test_native_settings_preserve_v1_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "settings.json"
    monkeypatch.setattr(planning_settings, "settings_path", lambda: path)
    planning_settings.save_settings(
        {
            "planning_dir": "D:/Plannings",
            "output_dir": "D:/Exports",
            "dark_mode": "true",
        }
    )
    assert planning_settings.load_settings() == {
        "planning_dir": "D:/Plannings",
        "output_dir": "D:/Exports",
        "dark_mode": "true",
    }
