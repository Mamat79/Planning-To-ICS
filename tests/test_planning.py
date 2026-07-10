from __future__ import annotations

import json
import os
import urllib.parse
from datetime import datetime
from pathlib import Path

from reportlab.pdfgen import canvas

import planning_ui
from planning_to_ics import Request, build_ics, extract_planning, write_ics_file
from tests.conftest import build_planning_pdf


def test_period_comes_from_pdf_content_not_file_timestamp(planning_pdf: Path) -> None:
    future = datetime(2031, 1, 10).timestamp()
    os.utime(planning_pdf, (future, future))

    assert planning_ui.week_year_for_pdf(planning_pdf) == (2026, 30)


def test_people_and_events_are_extracted_from_a_real_pdf_table(planning_pdf: Path) -> None:
    people = planning_ui.cached_people_for_pdf(str(planning_pdf))
    assert people == ("DUPONT ALICE", "MARTIN BOB")

    result = extract_planning(
        Request(person="Alice Dupont", week=30, year=2026),
        source_dir=planning_pdf.parent,
        explicit_pdf=planning_pdf,
        assume_yes=True,
    )
    assert len(result.events) == 2
    assert [event.summary for event in result.events] == ["Hôtel Étoilé (1/2)", "Hôtel Étoilé (2/2)"]
    assert result.events[0].start.strftime("%Y-%m-%d %H:%M") == "2026-07-20 09:00"
    assert result.events[-1].end.strftime("%Y-%m-%d %H:%M") == "2026-07-20 18:00"


def test_people_cache_refreshes_when_same_pdf_path_is_replaced(planning_pdf: Path, tmp_path: Path) -> None:
    assert "MARTIN BOB" in planning_ui.cached_people_for_pdf(str(planning_pdf))
    replacement = tmp_path / "replacement.pdf"
    build_planning_pdf(replacement, second_person="BERNARD\nCLARA")
    os.replace(replacement, planning_pdf)

    assert planning_ui.cached_people_for_pdf(str(planning_pdf)) == ("BERNARD CLARA", "DUPONT ALICE")


def test_ics_is_outlook_compatible_and_keeps_accents(planning_pdf: Path, tmp_path: Path) -> None:
    result = extract_planning(
        Request(person="Alice Dupont", week=30, year=2026),
        source_dir=planning_pdf.parent,
        explicit_pdf=planning_pdf,
        assume_yes=True,
    )
    output = tmp_path / "planning.ics"
    write_ics_file(output, result)
    raw = output.read_bytes()
    text = raw.decode("utf-8-sig")

    assert raw.startswith(b"\xef\xbb\xbf")
    assert "SUMMARY:Hôtel Étoilé" in text
    assert "\r\n" in text
    assert all(len(line.encode("utf-8")) <= 75 for line in build_ics(result).splitlines())


def test_pdf_diagnostic_reports_supported_and_unsupported_files(
    planning_pdf: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(planning_ui, "settings_path", lambda: tmp_path / "settings.json")
    supported_query = urllib.parse.urlencode({"pdf": str(planning_pdf)})
    supported = json.loads(planning_ui.render_people_api(supported_query))
    assert supported["status"] == "compatible"
    assert supported["week"] == 30
    assert supported["year"] == 2026

    other_pdf = tmp_path / "document-logistique-semaine-29.pdf"
    drawing = canvas.Canvas(str(other_pdf))
    drawing.drawString(50, 800, "LOGISTIQUE SEMAINE 29")
    drawing.drawString(50, 780, "Lundi: transport de materiel")
    drawing.save()
    unsupported_query = urllib.parse.urlencode({"pdf": str(other_pdf)})
    unsupported = json.loads(planning_ui.render_people_api(unsupported_query))
    assert unsupported["status"] == "unsupported"
    assert "Planning des Techniciens" in unsupported["message"]


def test_pdf_list_includes_nested_and_uppercase_extensions(tmp_path: Path) -> None:
    nested = tmp_path / "Sous-dossier"
    nested.mkdir()
    (tmp_path / "a.pdf").write_bytes(b"pdf")
    (nested / "b.PDF").write_bytes(b"pdf")
    (nested / "notes.txt").write_text("non", encoding="utf-8")

    listed = {Path(path).name for path in planning_ui.list_planning_pdfs(str(tmp_path))}
    assert listed == {"a.pdf", "b.PDF"}


def test_open_export_uses_windows_default_application(tmp_path: Path, monkeypatch) -> None:
    ics_path = tmp_path / "planning.ics"
    ics_path.write_text("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", encoding="utf-8")
    opened: list[str] = []
    monkeypatch.setattr(planning_ui.os, "startfile", lambda value: opened.append(value))

    planning_ui.open_export_target(ics_path, show_folder=False)
    planning_ui.open_export_target(ics_path, show_folder=True)
    assert opened == [str(ics_path), str(tmp_path)]
