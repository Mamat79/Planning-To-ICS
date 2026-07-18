from __future__ import annotations

import json
import os
import urllib.parse
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from reportlab.pdfgen import canvas

import planning_ui
from planning_to_ics import (
    ExtractionResult,
    Request,
    WorkEvent,
    build_ics,
    build_uid,
    diagnose_events,
    extract_planning,
    merge_identical_events,
    DayExtraction,
    write_ics_file,
)
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
    assert len(result.events) == 1
    assert [event.summary for event in result.events] == ["Hôtel Étoilé (-1h)"]
    assert result.events[0].start.strftime("%Y-%m-%d %H:%M") == "2026-07-20 09:00"
    assert result.events[-1].end.strftime("%Y-%m-%d %H:%M") == "2026-07-20 18:00"
    assert "(-1h)" in result.events[0].summary


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

    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.startswith(b"BEGIN:VCALENDAR")
    assert "SUMMARY:Hôtel Étoilé" in text
    assert "\r\n" in text
    assert all(len(line.encode("utf-8")) <= 75 for line in build_ics(result).splitlines())


def test_uid_is_stable_when_pdf_is_moved() -> None:
    event = make_event(20, 9, 0, 17, 0)
    first = ExtractionResult(Path("C:/one/planning.pdf"), "DUPONT ALICE", 1.0, 30, 2026, [], [])
    moved = ExtractionResult(Path("D:/another/planning.pdf"), "DUPONT ALICE", 1.0, 30, 2026, [], [])

    assert build_uid(first, event) == build_uid(moved, event)


def test_uid_changes_for_title_schedule_or_person() -> None:
    event = make_event(20, 9, 0, 17, 0)
    base = ExtractionResult(Path("planning.pdf"), "DUPONT ALICE", 1.0, 30, 2026, [], [])
    title_changed = make_event(20, 9, 0, 17, 0, summary="Autre mission")
    time_changed = make_event(20, 10, 0, 17, 0)
    other_person = ExtractionResult(Path("planning.pdf"), "MARTIN BOB", 1.0, 30, 2026, [], [])

    assert build_uid(base, event) != build_uid(base, title_changed)
    assert build_uid(base, event) != build_uid(base, time_changed)
    assert build_uid(base, event) != build_uid(other_person, event)


def make_event(
    day: int,
    start_hour: int,
    start_minute: int,
    end_hour: int,
    end_minute: int,
    summary: str = "Mission Hôtel Étoilé",
    description: str = "Mission Hôtel Étoilé, équipe d'été, l'équipe d'astreinte",
) -> WorkEvent:
    tz = ZoneInfo("Europe/Paris")
    start = datetime(2026, 7, day, start_hour, start_minute, tzinfo=tz)
    end = datetime(2026, 7, day, end_hour, end_minute, tzinfo=tz)
    return WorkEvent("Lun", summary, description, start, end, description)


def test_merge_two_identical_same_day_calculates_one_hour_pause() -> None:
    merged = merge_identical_events([make_event(20, 9, 0, 12, 0), make_event(20, 13, 0, 17, 0)])

    assert len(merged) == 1
    assert merged[0].start.hour == 9 and merged[0].end.hour == 17
    assert merged[0].summary == "Mission Hôtel Étoilé (-1h)"
    assert "(-1h)" in merged[0].summary


def test_merge_three_identical_same_day_keeps_all_pauses() -> None:
    merged = merge_identical_events(
        [make_event(20, 8, 0, 10, 0), make_event(20, 11, 0, 12, 0), make_event(20, 14, 0, 18, 0)]
    )

    assert len(merged) == 1
    assert merged[0].summary == "Mission Hôtel Étoilé (-3h)"
    assert "(-3h)" in merged[0].summary


def test_merge_calculates_non_integer_pause() -> None:
    merged = merge_identical_events([make_event(20, 9, 0, 12, 0), make_event(20, 13, 30, 17, 0)])

    assert len(merged) == 1
    assert merged[0].summary == "Mission Hôtel Étoilé (-1h30)"
    assert "(-1h30)" in merged[0].summary


def test_merge_keeps_separate_planning_dates() -> None:
    merged = merge_identical_events([make_event(20, 9, 0, 17, 0), make_event(21, 9, 0, 17, 0)])

    assert len(merged) == 2


def test_merge_allows_vacation_to_end_after_midnight() -> None:
    tz = ZoneInfo("Europe/Paris")
    business_text = "Mission Hôtel Étoilé, équipe d'été, l'équipe d'astreinte"
    overnight = WorkEvent(
        "Lun",
        "Mission Hôtel Étoilé",
        business_text,
        datetime(2026, 7, 20, 21, 0, tzinfo=tz),
        datetime(2026, 7, 21, 1, 0, tzinfo=tz),
        business_text,
    )
    merged = merge_identical_events([make_event(20, 8, 0, 12, 0), make_event(20, 14, 0, 19, 0), overnight])

    assert len(merged) == 1
    assert merged[0].end == overnight.end
    assert merged[0].summary == "Mission Hôtel Étoilé (-4h)"


def test_merge_requires_same_business_information() -> None:
    different_title = make_event(20, 13, 0, 17, 0, summary="Mission différente")
    different_details = make_event(20, 13, 0, 17, 0, description="Lieu différent")

    assert len(merge_identical_events([make_event(20, 9, 0, 12, 0), different_title])) == 2
    assert len(merge_identical_events([make_event(20, 9, 0, 12, 0), different_details])) == 2


def test_event_diagnostics_detects_duplicates_overlaps_and_overnight() -> None:
    tz = ZoneInfo("Europe/Paris")
    first = WorkEvent(
        "Lun",
        "Mission",
        "Mission",
        datetime(2026, 7, 20, 21, tzinfo=tz),
        datetime(2026, 7, 21, 1, tzinfo=tz),
        "Mission",
    )
    duplicate = WorkEvent(
        "Lun",
        "Mission",
        "Mission",
        first.start,
        first.end,
        "Mission",
    )
    overlap = WorkEvent(
        "Lun",
        "Autre mission",
        "Autre mission",
        datetime(2026, 7, 20, 23, tzinfo=tz),
        datetime(2026, 7, 21, 2, tzinfo=tz),
        "Autre mission",
    )

    diagnostics = diagnose_events([first, duplicate, overlap])

    assert diagnostics.event_count == 3
    assert diagnostics.overnight_count == 3
    assert diagnostics.duplicate_count == 1
    assert diagnostics.overlap_count == 3
    assert diagnostics.collision_count == 0


def test_multiple_export_writes_safe_ics_files_and_zip(tmp_path: Path) -> None:
    event = make_event(20, 9, 0, 17, 0)
    results = [
        ExtractionResult(Path("planning.pdf"), "DUPONT ALICE", 1.0, 30, 2026, [DayExtraction("Lun", event.start.date(), "", [event])], []),
        ExtractionResult(Path("planning.pdf"), "MARTIN BOB", 1.0, 30, 2026, [DayExtraction("Lun", event.start.date(), "", [event])], []),
    ]

    paths, zip_path = planning_ui.export_multiple_results(results, tmp_path, 30, 2026)

    assert [path.name for path in paths] == [
        "Planning_Alice_Dupont_S30_2026.ics",
        "Planning_Bob_Martin_S30_2026.ics",
    ]
    assert zip_path.name == "Planning_ICS_S30_2026.zip"
    with zipfile.ZipFile(zip_path) as archive:
        assert sorted(archive.namelist()) == sorted(path.name for path in paths)


def test_ics_escapes_french_special_characters_and_is_valid() -> None:
    event = make_event(20, 9, 0, 17, 0, summary="Équipe d'été, côté théâtre; test\\ok")
    result = ExtractionResult(
        Path("planning épreuve.pdf"),
        "Leroy Matthieu",
        1.0,
        30,
        2026,
        [DayExtraction("Lun", event.start.date(), "", [event])],
        [],
    )

    ics = build_ics(result)
    assert r"SUMMARY:Équipe d'été\, côté théâtre\; test\\ok" in ics
    assert ics.startswith("BEGIN:VCALENDAR")


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


def test_settings_can_be_imported_and_reset(tmp_path: Path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(planning_ui, "settings_path", lambda: settings_file)

    planning_ui.save_settings({"planning_dir": "D:/Plannings", "output_dir": "D:/Exports"})
    assert planning_ui.load_settings() == {"planning_dir": "D:/Plannings", "output_dir": "D:/Exports"}

    planning_ui.import_settings({"planning_dir": "E:/Nouveaux plannings"})
    assert planning_ui.load_settings()["planning_dir"] == "E:/Nouveaux plannings"
    assert planning_ui.load_settings()["output_dir"] == "D:/Exports"

    assert planning_ui.reset_settings() == planning_ui.default_settings()
    assert not settings_file.exists()


def test_version_key_compares_release_numbers() -> None:
    assert planning_ui.version_key("v1.10") > planning_ui.version_key("V1.8")


def test_pdf_list_includes_nested_and_uppercase_extensions(tmp_path: Path) -> None:
    nested = tmp_path / "Sous-dossier"
    nested.mkdir()
    (tmp_path / "a.pdf").write_bytes(b"pdf")
    (nested / "b.PDF").write_bytes(b"pdf")
    (nested / "notes.txt").write_text("non", encoding="utf-8")

    listed = {Path(path).name for path in planning_ui.list_planning_pdfs(str(tmp_path))}
    assert listed == {"a.pdf", "b.PDF"}


@pytest.mark.skipif(os.name != "nt", reason="Windows default launcher only exists on Windows")
def test_open_export_uses_windows_default_application(tmp_path: Path, monkeypatch) -> None:
    ics_path = tmp_path / "planning.ics"
    ics_path.write_text("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", encoding="utf-8")
    opened: list[str] = []
    monkeypatch.setattr(planning_ui.os, "startfile", lambda value: opened.append(value))

    planning_ui.open_export_target(ics_path, show_folder=False)
    planning_ui.open_export_target(ics_path, show_folder=True)
    assert opened == [str(ics_path), str(tmp_path)]


@pytest.mark.skipif(os.name == "nt", reason="This test covers the Unix launcher")
def test_open_export_uses_unix_default_application(tmp_path: Path, monkeypatch) -> None:
    ics_path = tmp_path / "planning.ics"
    ics_path.write_text("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", encoding="utf-8")
    launched: list[list[str]] = []
    monkeypatch.setattr(planning_ui.subprocess, "Popen", lambda command: launched.append(command))

    planning_ui.open_export_target(ics_path, show_folder=False)
    planning_ui.open_export_target(ics_path, show_folder=True)

    launcher = "open" if planning_ui.sys.platform == "darwin" else "xdg-open"
    assert launched == [[launcher, str(ics_path)], [launcher, str(tmp_path)]]
