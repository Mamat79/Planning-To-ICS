"""Application services shared by native and legacy user interfaces."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import zipfile
from functools import lru_cache
from pathlib import Path

from planning_to_ics import (
    ExtractionResult,
    Request,
    combined_output_ics_path,
    extract_all_plannings,
    extract_planning,
    list_people_for_week,
    name_match_score,
    normalize_text,
    output_ics_path,
    week_year_from_path,
    week_year_from_pdf,
    write_combined_ics_file,
    write_ics_file,
    write_log,
)


def week_year_for_pdf(pdf_path: Path) -> tuple[int, int]:
    parsed = week_year_from_pdf(pdf_path) or week_year_from_path(pdf_path)
    if parsed:
        return parsed
    raise ValueError(
        "PDF lisible, mais la semaine et l'année du planning sont introuvables. "
        "Vérifiez qu'il s'agit bien d'un Planning des Techniciens."
    )


@lru_cache(maxsize=64)
def _cached_people(
    pdf_path_text: str, modified_ns: int, size: int
) -> tuple[str, ...]:
    del modified_ns, size
    pdf = Path(pdf_path_text)
    year, week = week_year_for_pdf(pdf)
    return tuple(
        list_people_for_week(pdf.parent, week=week, year=year, explicit_pdf=pdf)
    )


def people_for_pdf(pdf: Path) -> tuple[str, ...]:
    if not pdf.is_file():
        raise FileNotFoundError(f"PDF introuvable : {pdf}")
    stat = pdf.stat()
    return _cached_people(str(pdf), stat.st_mtime_ns, stat.st_size)


def list_planning_pdfs(planning_dir: str | Path) -> list[Path]:
    root = Path(planning_dir).expanduser()
    if not root.exists():
        return []
    if root.is_file():
        return [root] if root.suffix.lower() == ".pdf" else []
    pdfs = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() == ".pdf"
    ]
    return sorted(
        pdfs,
        key=lambda path: (path.stat().st_mtime_ns, path.name.casefold()),
        reverse=True,
    )


def pdf_label(path: Path) -> str:
    parsed = week_year_from_path(path)
    suffix = f"  ·  S{parsed[1]:02d} {parsed[0]}" if parsed else ""
    return f"{path.name}{suffix}"


def extract_one(pdf: Path, person: str) -> ExtractionResult:
    year, week = week_year_for_pdf(pdf)
    return extract_planning(
        Request(person=person, week=week, year=year),
        source_dir=pdf.parent,
        explicit_pdf=pdf,
        assume_yes=True,
    )


def extract_results_for_pdfs(
    pdfs: list[Path], person: str
) -> tuple[list[ExtractionResult], list[str]]:
    results: list[ExtractionResult] = []
    errors: list[str] = []
    seen_periods: set[tuple[int, int]] = set()
    for pdf in pdfs:
        try:
            year, week = week_year_for_pdf(pdf)
            period = (year, week)
            if period in seen_periods:
                errors.append(
                    f"{pdf.name} : la semaine S{week:02d} {year} est déjà sélectionnée."
                )
                continue
            results.append(extract_one(pdf, person))
            seen_periods.add(period)
        except Exception as exc:
            errors.append(f"{pdf.name} : {exc}")
    results.sort(key=lambda result: (result.year, result.week))
    return results, errors


def export_result(result: ExtractionResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_ics_path(output_dir, result)
    write_ics_file(path, result)
    write_log(output_dir, result, path)
    return path


def export_combined_results(
    results: list[ExtractionResult], output_dir: Path
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = combined_output_ics_path(output_dir, results)
    write_combined_ics_file(path, results)
    for result in results:
        write_log(output_dir, result, path)
    return path


def export_multiple_results(
    results: list[ExtractionResult], output_dir: Path, week: int, year: int
) -> tuple[list[Path], Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    reserved: set[Path] = set()
    for result in results:
        path = output_ics_path(output_dir, result)
        if path in reserved:
            counter = 2
            while True:
                candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
                if candidate not in reserved:
                    path = candidate
                    break
                counter += 1
        reserved.add(path)
        write_ics_file(path, result)
        write_log(output_dir, result, path)
        paths.append(path)

    zip_path = output_dir / f"Planning_ICS_S{week:02d}_{year}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, arcname=path.name)
    return paths, zip_path


MISSION_SUFFIX_RE = re.compile(r"\s+\((?:\d+/\d+|-\d+h(?:\d{2})?)\)$")


def mission_title(summary: str) -> str:
    title = summary.strip()
    while True:
        cleaned = MISSION_SUFFIX_RE.sub("", title).strip()
        if cleaned == title:
            return title
        title = cleaned


def mission_titles(result: ExtractionResult) -> list[str]:
    titles: dict[str, str] = {}
    for event in result.events:
        title = mission_title(event.summary)
        key = normalize_text(title)
        if key and key not in titles:
            titles[key] = title
    return list(titles.values())


def people_sharing_missions(
    results: list[ExtractionResult], principal_name: str
) -> set[str]:
    principal = next(
        (
            result
            for result in results
            if name_match_score(result.person_name, principal_name) >= 0.95
        ),
        None,
    )
    if principal is None:
        return set()
    principal_keys = {
        normalize_text(mission_title(event.summary)) for event in principal.events
    }
    return {
        result.person_name
        for result in results
        if {
            normalize_text(mission_title(event.summary)) for event in result.events
        }
        & principal_keys
    }


def open_path(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
