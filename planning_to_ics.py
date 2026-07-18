#!/usr/bin/env python
"""Generate Outlook-compatible ICS files from Radio France weekly planning PDFs."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import re
import sys
import unicodedata
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

try:
    import pdfplumber
except ImportError as exc:  # pragma: no cover - exercised by users without deps
    raise SystemExit(
        "pdfplumber est requis. Installe-le avec: python -m pip install pdfplumber pypdf"
    ) from exc


SOURCE_DIR = Path.home() / "Documents" / "Planning To ICS" / "Plannings"
OUTPUT_DIR = Path.home() / "Documents" / "Planning To ICS" / "Exports"
DEFAULT_PERSON = ""
DEFAULT_TIMEZONE = "Europe/Paris"
ICS_FILE_ENCODING = "utf-8"
ICS_FILE_BOM = b""

MONTHS_FR = {
    "janvier": 1,
    "janv": 1,
    "jan": 1,
    "fevrier": 2,
    "fevr": 2,
    "fev": 2,
    "mars": 3,
    "avril": 4,
    "avr": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "juil": 7,
    "aout": 8,
    "septembre": 9,
    "sept": 9,
    "sep": 9,
    "octobre": 10,
    "oct": 10,
    "novembre": 11,
    "nov": 11,
    "decembre": 12,
    "dec": 12,
}

DAY_LABELS = [
    ("lun", "Lun"),
    ("mar", "Mar"),
    ("mer", "Mer"),
    ("jeu", "Jeu"),
    ("ven", "Ven"),
    ("sam", "Sam"),
    ("dim", "Dim"),
]

NON_WORK_PATTERNS = [
    "sv",
    "rh",
    "conge",
    "conges",
    "recup",
    "sante",
    "absence",
    "mobilite",
    "liberte demandee",
    "liberte",
]

COMMON_REQUEST_WORDS = {
    "planning",
    "ics",
    "calendrier",
    "semaine",
    "sem",
    "s",
    "pour",
    "fais",
    "moi",
    "genere",
    "generez",
    "faire",
    "sortir",
    "cree",
    "creer",
}

TIME_RE = r"(?P<{name}>\d{{1,2}}[hH:.]\d{{2}})"
DETAILED_TIME_RE = re.compile(
    rf"{TIME_RE.format(name='start')}\s*(?:Pause\s*:\s*TTE\s*:|Pause\s*:|TTE\s*:)?\s*"
    rf"{TIME_RE.format(name='end')}\s+"
    r"(?P<pause>\d{1,2}:\d{2})\s+(?P<worked>\d{1,2}:\d{2})",
    re.IGNORECASE | re.DOTALL,
)
STACKED_TIME_RE = re.compile(
    rf"{TIME_RE.format(name='start')}\s+"
    r"(?P<pause>\d{1,2}:\d{2})\s+(?P<worked>\d{1,2}:\d{2})\s+"
    rf"{TIME_RE.format(name='end')}",
    re.IGNORECASE | re.DOTALL,
)
SIMPLE_TIME_RE = re.compile(r"\b\d{1,2}[hH]\d{2}\b")
VACATION_RANGE_RE = re.compile(
    rf"Vacation\s*:\s*{TIME_RE.format(name='start')}\s*[-–]\s*{TIME_RE.format(name='end')}",
    re.IGNORECASE,
)
EXPLICIT_PAUSE_RE = re.compile(
    rf"Pause\s+{TIME_RE.format(name='pause_start')}\s*[-–]\s*{TIME_RE.format(name='pause_end')}",
    re.IGNORECASE,
)
DAY_HEADER_RE = re.compile(
    r"\b(lun|mar|mer|jeu|ven|sam|dim)\w*\.?\s+(\d{1,2})\s+([A-Za-zÀ-ÿ.]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Request:
    person: str
    week: int
    year: int


@dataclass(frozen=True)
class PdfCandidate:
    path: Path
    score: int


@dataclass(frozen=True)
class WeekInfo:
    year: int
    week: int
    monday: date
    pdf_count: int


@dataclass(frozen=True)
class PersonBlock:
    name: str
    page_number: int
    table_index: int
    rows: list[list[str | None]]
    header: list[str | None]


@dataclass(frozen=True)
class DayColumn:
    key: str
    label: str
    date: date
    start_col: int
    end_col: int


@dataclass(frozen=True)
class WorkEvent:
    day_label: str
    summary: str
    description: str
    start: datetime
    end: datetime
    source_text: str


@dataclass(frozen=True)
class DayExtraction:
    label: str
    date: date
    raw_text: str
    included: list[WorkEvent]
    ignored_reason: str | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtractionResult:
    pdf: Path
    person_name: str
    matched_score: float
    week: int
    year: int
    days: list[DayExtraction]
    warnings: list[str]

    @property
    def events(self) -> list[WorkEvent]:
        return [event for day in self.days for event in day.included]


@dataclass(frozen=True)
class EventDiagnostics:
    event_count: int
    overnight_count: int
    duplicate_count: int
    overlap_count: int
    collision_count: int
    duplicate_details: tuple[str, ...] = ()
    overlap_details: tuple[str, ...] = ()
    collision_details: tuple[str, ...] = ()


def _diagnostic_event_label(event: WorkEvent) -> str:
    return f"{event.day_label} {event.start:%d/%m %H:%M}-{event.end:%H:%M} {event.summary}"


def diagnose_events(events: Iterable[WorkEvent]) -> EventDiagnostics:
    """Summarize duplicate, overlapping, overnight and ambiguous events."""
    items = sorted(events, key=lambda event: (event.start, event.end, normalize_text(event.summary)))
    duplicate_groups: dict[tuple[object, ...], list[WorkEvent]] = {}
    slot_groups: dict[tuple[datetime, datetime], list[WorkEvent]] = {}
    for event in items:
        duplicate_key = (
            event.start,
            event.end,
            normalize_text(event.summary),
            normalize_text(event.description),
        )
        duplicate_groups.setdefault(duplicate_key, []).append(event)
        slot_groups.setdefault((event.start, event.end), []).append(event)

    duplicate_details: list[str] = []
    for group in duplicate_groups.values():
        if len(group) > 1:
            duplicate_details.append(f"{len(group)}x {_diagnostic_event_label(group[0])}")

    collision_details: list[str] = []
    for group in slot_groups.values():
        summaries = {normalize_text(event.summary) for event in group}
        if len(group) > 1 and len(summaries) > 1:
            collision_details.append(
                f"Même créneau : {' / '.join(event.summary for event in group[:3])}"
            )

    overlap_details: list[str] = []
    for index, left in enumerate(items):
        for right in items[index + 1 :]:
            if right.start >= left.end:
                break
            if left.start < right.end and right.start < left.end:
                overlap_details.append(
                    f"Chevauchement : {_diagnostic_event_label(left)} / {_diagnostic_event_label(right)}"
                )

    return EventDiagnostics(
        event_count=len(items),
        overnight_count=sum(event.end.date() != event.start.date() for event in items),
        duplicate_count=sum(max(len(group) - 1, 0) for group in duplicate_groups.values()),
        overlap_count=len(overlap_details),
        collision_count=len(collision_details),
        duplicate_details=tuple(duplicate_details),
        overlap_details=tuple(overlap_details),
        collision_details=tuple(collision_details),
    )


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def normalize_text(value: str) -> str:
    value = strip_accents(value).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def compact_text(value: str) -> str:
    return normalize_text(value).replace(" ", "")


def name_tokens(value: str) -> list[str]:
    return [tok for tok in normalize_text(value).split() if tok and tok not in {"mr", "mme"}]


def name_match_score(query: str, candidate: str) -> float:
    q_tokens = name_tokens(query)
    c_tokens = name_tokens(candidate)
    if not q_tokens or not c_tokens:
        return 0.0

    q_compact = "".join(q_tokens)
    c_compact = "".join(c_tokens)
    if q_compact == c_compact:
        return 1.0
    if sorted(q_tokens) == sorted(c_tokens):
        return 0.98
    if all(tok in c_tokens for tok in q_tokens):
        return 0.95

    q_variants = {
        q_compact,
        "".join(reversed(q_tokens)),
        "".join(sorted(q_tokens)),
    }
    c_variants = {
        c_compact,
        "".join(reversed(c_tokens)),
        "".join(sorted(c_tokens)),
    }
    direct = max(
        difflib.SequenceMatcher(None, q_variant, c_variant).ratio()
        for q_variant in q_variants
        for c_variant in c_variants
    )

    shared = len(set(q_tokens) & set(c_tokens))
    token_bonus = shared / max(len(set(q_tokens)), 1) * 0.18
    return min(0.94, direct + token_bonus)


def parse_request(text: str, default_person: str = DEFAULT_PERSON) -> Request:
    text = text.strip()
    year_match = re.search(r"\b(20\d{2})\b", text)
    year = int(year_match.group(1)) if year_match else datetime.now().year

    week_match = re.search(r"\b(?:semaine|sem|s)\s*0?(\d{1,2})\b", normalize_text(text))
    if not week_match:
        raise ValueError("Aucune semaine détectée. Exemple attendu: 'Leroy Matthieu semaine 27'.")
    week = int(week_match.group(1))
    if not 1 <= week <= 53:
        raise ValueError(f"Semaine invalide: {week}")

    cleaned = normalize_text(text)
    cleaned = re.sub(r"\b(?:semaine|sem|s)\s*0?\d{1,2}\b", " ", cleaned)
    cleaned = re.sub(r"\b20\d{2}\b", " ", cleaned)
    remaining = [tok for tok in cleaned.split() if tok not in COMMON_REQUEST_WORDS and not tok.isdigit()]
    person = " ".join(remaining).strip() or default_person

    return Request(person=person, week=week, year=year)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Génère un fichier ICS Outlook depuis un PDF de planning Radio France."
    )
    parser.add_argument(
        "request",
        nargs="*",
        help='Phrase libre, par exemple: "Leroy Matthieu semaine 27".',
    )
    parser.add_argument("--person", help="Technicien à traiter. Obligatoire en mode CLI.")
    parser.add_argument("--week", type=int, help="Numéro de semaine ISO.")
    parser.add_argument("--year", type=int, help="Année ISO. Par défaut: année courante.")
    parser.add_argument("--source", type=Path, default=SOURCE_DIR, help="Dossier source des PDF.")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR, help="Dossier de sortie des ICS.")
    parser.add_argument("--pdf", type=Path, help="PDF précis à utiliser.")
    parser.add_argument("--dry-run", action="store_true", help="Affiche le résumé sans écrire l'ICS.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Accepte le meilleur match lorsque le nom est seulement approximatif.",
    )
    return parser.parse_args(argv)


def request_from_args(args: argparse.Namespace) -> Request:
    if args.week:
        person = args.person or " ".join(args.request).strip() or DEFAULT_PERSON
        return Request(person=person, week=args.week, year=args.year or datetime.now().year)

    text = " ".join(args.request).strip()
    if not text or not re.search(r"\b(?:semaine|sem|s)\s*0?\d{1,2}\b", normalize_text(text)):
        latest = latest_available_week(args.source, year=args.year)
        if latest is None:
            raise ValueError("Aucune semaine détectée et aucun PDF disponible pour choisir la semaine récente.")
        person = args.person or text or DEFAULT_PERSON
        return Request(person=person, week=latest.week, year=latest.year)

    request = parse_request(text, DEFAULT_PERSON)
    if args.person:
        request = Request(person=args.person, week=request.week, year=request.year)
    if args.year:
        request = Request(person=request.person, week=request.week, year=args.year)
    return request


def week_pattern(week: int) -> re.Pattern[str]:
    return re.compile(rf"(?<!\d)(?:semaine|sem|s)[\s._-]*0?{week}(?!\d)", re.IGNORECASE)


def score_pdf_path(path: Path, request: Request) -> int:
    normalized_path = normalize_text(str(path))
    name = normalize_text(path.name)
    score = 0

    if week_pattern(request.week).search(normalized_path):
        score += 100
    if str(request.year) in normalized_path:
        score += 40
    if "son dits" in name or "son ext" in name or "son_ext" in path.name.lower():
        score += 35
    if "planning hebdo individuel" in name:
        score += 20
    if "studios personnels" in name or "studios_personnels" in path.name.lower():
        score += 15
    if "logistique" in name:
        score -= 5
    if "occupation" in name and "personnel" not in name:
        score -= 8
    return score


def week_year_from_path(path: Path) -> tuple[int, int] | None:
    normalized_path = normalize_text(str(path))
    week_match = re.search(r"(?<!\d)(?:semaine|sem|s)[\s._-]*0?(\d{1,2})(?!\d)", normalized_path)
    if not week_match:
        return None
    week = int(week_match.group(1))
    if not 1 <= week <= 53:
        return None

    years = [int(match) for match in re.findall(r"(?<!\d)(20\d{2})(?!\d)", str(path))]
    if not years:
        return None
    year = years[-1]
    try:
        date.fromisocalendar(year, week, 1)
    except ValueError:
        return None
    return year, week


def read_pdf_header_text(pdf: Path, max_pages: int = 2) -> str:
    """Read enough of a PDF to identify its planning period."""
    try:
        with pdfplumber.open(pdf) as document:
            texts = []
            for page in document.pages[:max_pages]:
                texts.append(page.extract_text(x_tolerance=2, y_tolerance=2) or "")
    except Exception as exc:
        raise ValueError(
            "Le fichier PDF ne peut pas être lu. Il est peut-être endommagé ou protégé."
        ) from exc

    text = "\n".join(texts).strip()
    if not text:
        raise ValueError(
            "Ce PDF ne contient pas de texte exploitable. Il s'agit peut-être d'un document scanné."
        )
    return text


def week_year_from_pdf(pdf: Path) -> tuple[int, int] | None:
    """Detect the ISO planning week from the PDF content, never from file timestamps."""
    text = read_pdf_header_text(pdf)
    normalized = normalize_text(text)
    week_matches = list(
        re.finditer(r"(?<!\d)(?:semaine|sem|s)[\s._-]*0?(\d{1,2})(?!\d)", normalized)
    )
    year_matches = list(re.finditer(r"(?<!\d)(20\d{2})(?!\d)", normalized))

    for week_match in week_matches:
        week = int(week_match.group(1))
        if not 1 <= week <= 53:
            continue
        nearby_years = sorted(
            year_matches,
            key=lambda match: abs(match.start() - week_match.start()),
        )
        for year_match in nearby_years:
            year = int(year_match.group(1))
            try:
                date.fromisocalendar(year, week, 1)
            except ValueError:
                continue
            return year, week

    if not year_matches:
        return None

    # Some exports omit "Semaine NN" but retain the seven dated day headers.
    header_dates = DAY_HEADER_RE.findall(strip_accents(text))
    monday_headers = [match for match in header_dates if normalize_text(match[0]).startswith("lun")]
    if not monday_headers:
        return None

    monday_day = int(monday_headers[0][1])
    monday_month = MONTHS_FR.get(normalize_text(monday_headers[0][2].rstrip(".")))
    if not monday_month:
        return None

    for year_match in year_matches:
        iso_year = int(year_match.group(1))
        for week in range(1, 54):
            try:
                monday = date.fromisocalendar(iso_year, week, 1)
            except ValueError:
                continue
            if monday.day == monday_day and monday.month == monday_month:
                return iso_year, week
    return None


def available_weeks(source_dir: Path, year: int | None = None) -> list[WeekInfo]:
    if not source_dir.exists():
        return []

    counts: dict[tuple[int, int], int] = {}
    for path in source_dir.rglob("*.pdf"):
        parsed = week_year_from_path(path)
        if not parsed:
            continue
        parsed_year, parsed_week = parsed
        if year and parsed_year != year:
            continue
        counts[(parsed_year, parsed_week)] = counts.get((parsed_year, parsed_week), 0) + 1

    weeks: list[WeekInfo] = []
    for (parsed_year, parsed_week), count in counts.items():
        weeks.append(
            WeekInfo(
                year=parsed_year,
                week=parsed_week,
                monday=date.fromisocalendar(parsed_year, parsed_week, 1),
                pdf_count=count,
            )
        )
    weeks.sort(key=lambda item: item.monday, reverse=True)
    return weeks


def latest_available_week(source_dir: Path, year: int | None = None) -> WeekInfo | None:
    weeks = available_weeks(source_dir, year=year)
    return weeks[0] if weeks else None


def find_pdf_candidates(source_dir: Path, request: Request, explicit_pdf: Path | None = None) -> list[PdfCandidate]:
    if explicit_pdf:
        if not explicit_pdf.exists():
            raise FileNotFoundError(f"PDF introuvable: {explicit_pdf}")
        return [PdfCandidate(explicit_pdf, 10_000)]

    if not source_dir.exists():
        raise FileNotFoundError(f"Dossier source introuvable: {source_dir}")

    all_pdfs = list(source_dir.rglob("*.pdf"))
    year_pdfs = [path for path in all_pdfs if str(request.year) in normalize_text(str(path))]
    search_space = year_pdfs or all_pdfs

    candidates: list[PdfCandidate] = []
    for path in search_space:
        score = score_pdf_path(path, request)
        if score >= 80:
            candidates.append(PdfCandidate(path, score))

    candidates.sort(key=lambda item: (item.score, item.path.stat().st_mtime), reverse=True)
    return candidates


def clean_cell(value: str | None) -> str:
    if not value:
        return ""
    value = value.replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def has_day_header(row: list[str | None]) -> bool:
    hits = 0
    for value in row:
        if value and DAY_HEADER_RE.search(strip_accents(value)):
            hits += 1
    return hits >= 3


def find_header_row(data: list[list[str | None]]) -> int | None:
    for index, row in enumerate(data[:5]):
        if has_day_header(row):
            return index
    return None


def table_day_columns(header: list[str | None], request: Request) -> list[DayColumn]:
    positions: list[tuple[int, str, str, int, int | None]] = []
    tte_col = len(header)
    for index, value in enumerate(header):
        if not value:
            continue
        normalized = strip_accents(value)
        if re.search(r"\b(?:TTE|Total)\b", value, re.IGNORECASE):
            tte_col = index
            continue
        match = DAY_HEADER_RE.search(normalized)
        if not match:
            continue
        key = match.group(1).lower()[:3]
        day_num = int(match.group(2))
        month_key = normalize_text(match.group(3).rstrip("."))
        month = MONTHS_FR.get(month_key)
        positions.append((index, key, value.splitlines()[0], day_num, month))

    if len(positions) < 7:
        raise ValueError("Impossible d'identifier les 7 colonnes jour dans l'en-tête.")

    iso_monday = date.fromisocalendar(request.year, request.week, 1)
    columns: list[DayColumn] = []
    for offset, (start_col, key, header_label, _day_num, month) in enumerate(positions[:7]):
        next_col = positions[offset + 1][0] if offset + 1 < len(positions[:7]) else tte_col
        if next_col <= start_col:
            next_col = start_col + 1
        day_date = iso_monday + timedelta(days=offset)
        label = DAY_LABELS[offset][1]
        if month:
            label = header_label.replace("\n", " ")
        columns.append(DayColumn(key=key, label=label, date=day_date, start_col=start_col, end_col=next_col))
    return columns


def is_probable_name_cell(value: str) -> bool:
    text = clean_cell(value)
    if not text:
        return False
    compact = normalize_text(text)
    if not compact or any(word in compact for word in {"semaine", "juillet", "juin", "lundi"}):
        return False
    if re.search(r"\d", text):
        return False
    lines = [line for line in text.splitlines() if line.strip()]
    return 1 <= len(lines) <= 3 and any(ch.isalpha() for ch in text)


def iter_person_blocks(data: list[list[str | None]], header_index: int) -> Iterable[tuple[str, list[list[str | None]]]]:
    body = data[header_index + 1 :]
    starts: list[int] = []
    for index, row in enumerate(body):
        first = clean_cell(row[0] if row else None)
        if is_probable_name_cell(first):
            starts.append(index)

    for offset, start in enumerate(starts):
        end = starts[offset + 1] if offset + 1 < len(starts) else len(body)
        block_rows = body[start:end]
        name = clean_cell(block_rows[0][0] if block_rows and block_rows[0] else "")
        yield name, block_rows


def find_person_blocks(pdf: Path, request: Request) -> list[tuple[PersonBlock, float]]:
    matches: list[tuple[PersonBlock, float]] = []
    query_tokens = [token for token in name_tokens(request.person) if len(token) > 2]
    with pdfplumber.open(pdf) as document:
        for page_index, page in enumerate(document.pages):
            try:
                page_text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            except Exception:
                page_text = ""
            normalized_page = normalize_text(page_text)
            if query_tokens and not any(token in normalized_page for token in query_tokens):
                continue
            try:
                tables = page.find_tables()
            except Exception:
                continue
            for table_index, table in enumerate(tables):
                try:
                    data = table.extract(x_tolerance=2, y_tolerance=2)
                except Exception:
                    continue
                if not data:
                    continue
                header_index = find_header_row(data)
                if header_index is None:
                    continue
                header = data[header_index]
                try:
                    table_day_columns(header, request)
                except ValueError:
                    continue
                for name, rows in iter_person_blocks(data, header_index):
                    score = name_match_score(request.person, name)
                    if score >= 0.72:
                        matches.append(
                            (
                                PersonBlock(
                                    name=name,
                                    page_number=page_index + 1,
                                    table_index=table_index,
                                    rows=rows,
                                    header=header,
                                ),
                                score,
                            )
                        )
    matches.sort(key=lambda item: item[1], reverse=True)
    return matches


def extract_people_from_pdf(pdf: Path, request: Request) -> list[str]:
    names: dict[str, str] = {}
    with pdfplumber.open(pdf) as document:
        for page in document.pages:
            try:
                tables = page.find_tables()
            except Exception:
                continue
            for table in tables:
                try:
                    data = table.extract(x_tolerance=2, y_tolerance=2)
                except Exception:
                    continue
                if not data:
                    continue
                header_index = find_header_row(data)
                if header_index is None:
                    continue
                try:
                    table_day_columns(data[header_index], request)
                except ValueError:
                    continue
                for name, _rows in iter_person_blocks(data, header_index):
                    clean_name = name.replace("\n", " ").strip()
                    key = normalize_text(clean_name)
                    if clean_name and key not in names:
                        names[key] = clean_name
    return sorted(names.values(), key=normalize_text)


def list_people_for_week(source_dir: Path, week: int, year: int, explicit_pdf: Path | None = None) -> list[str]:
    request = Request(person=DEFAULT_PERSON, week=week, year=year)
    candidates = find_pdf_candidates(source_dir, request, explicit_pdf)
    if not candidates:
        return []

    best_people: list[str] = []
    for candidate in candidates[:6]:
        people = extract_people_from_pdf(candidate.path, request)
        if len(people) > len(best_people):
            best_people = people
        if len(best_people) >= 10 and candidate.score >= candidates[0].score - 5:
            break
    return best_people


def day_raw_text(block: PersonBlock, column: DayColumn) -> str:
    pieces: list[str] = []
    seen: set[str] = set()
    for row in block.rows:
        for col in range(column.start_col, min(column.end_col, len(row))):
            value = clean_cell(row[col])
            if not value:
                continue
            key = normalize_text(value)
            if key in seen:
                continue
            seen.add(key)
            pieces.append(value)
    return "\n".join(pieces).strip()


def parse_pdf_date_headers(pdf: Path, request: Request) -> list[str]:
    warnings: list[str] = []
    expected = [date.fromisocalendar(request.year, request.week, 1) + timedelta(days=i) for i in range(7)]
    with pdfplumber.open(pdf) as document:
        if not document.pages:
            return warnings
        text = document.pages[0].extract_text(x_tolerance=2, y_tolerance=2) or ""
    header_dates = DAY_HEADER_RE.findall(strip_accents(text))
    if len(header_dates) >= 7:
        for index, match in enumerate(header_dates[:7]):
            day_num = int(match[1])
            month = MONTHS_FR.get(normalize_text(match[2].rstrip(".")))
            if month and (expected[index].day != day_num or expected[index].month != month):
                warnings.append(
                    "L'en-tête PDF semble différer de la date ISO attendue "
                    f"pour {DAY_LABELS[index][1]}: PDF={day_num:02d}/{month:02d}, "
                    f"ISO={expected[index].strftime('%d/%m/%Y')}."
                )
    return warnings


def parse_time(value: str) -> time:
    value = value.strip().lower().replace("h", ":").replace(".", ":")
    hour_s, minute_s = value.split(":", 1)
    return time(hour=int(hour_s), minute=int(minute_s))


def parse_duration(value: str) -> int:
    hour_s, minute_s = value.strip().split(":", 1)
    return int(hour_s) * 60 + int(minute_s)


def minutes_between(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() // 60)


def combine_date_time(day: date, start: time, end: time, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start_dt = datetime.combine(day, start, tzinfo=tz)
    end_dt = datetime.combine(day, end, tzinfo=tz)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return start_dt, end_dt


def strip_vacation_headers(raw_text: str) -> str:
    text = raw_text.replace("\r", "\n")
    text = VACATION_RANGE_RE.sub("", text)
    lines = []
    skip_next_range = False
    for line in text.splitlines():
        stripped = line.strip()
        normalized = normalize_text(stripped)
        if not stripped:
            continue
        if normalized == "vacation":
            skip_next_range = True
            continue
        if skip_next_range and re.fullmatch(r"\d{1,2}[hH:.]\d{2}\s*[-–]\s*\d{1,2}[hH:.]\d{2}", stripped):
            skip_next_range = False
            continue
        skip_next_range = False
        lines.append(stripped)
    return "\n".join(lines).strip()


def is_non_working_only(raw_text: str) -> bool:
    normalized = normalize_text(raw_text)
    if not normalized:
        return True
    has_work_time = bool(DETAILED_TIME_RE.search(raw_text))
    has_vacation = bool(VACATION_RANGE_RE.search(raw_text))
    if has_work_time or has_vacation:
        return False
    reduced = normalized
    for pattern in NON_WORK_PATTERNS:
        reduced = re.sub(rf"\b{re.escape(pattern)}\b", " ", reduced)
    reduced = re.sub(r"\bsur place\b|\bplace\b|\*\*", " ", reduced)
    reduced = re.sub(r"\s+", " ", reduced).strip()
    return not reduced


def clean_summary(chunk: str) -> str:
    lines = []
    for line in chunk.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        normalized = normalize_text(stripped)
        if normalized in {"pause", "tte", "vacation"}:
            continue
        if re.fullmatch(r"(pause\s*:|tte\s*:)?", normalized):
            continue
        if re.fullmatch(r"\d{1,2}[hH:.]\d{2}(\s+Pause\s*:\s*TTE\s*:)?", stripped, re.IGNORECASE):
            continue
        if re.fullmatch(r"\d{1,2}:\d{2}", stripped):
            continue
        lines.append(stripped)

    summary = " / ".join(lines[:3])
    summary = re.sub(r"\s+", " ", summary).strip(" /")
    if not summary:
        return "Planning Radio France"
    if len(summary) > 110:
        summary = summary[:107].rstrip() + "..."
    return summary


def person_name_variants(person_name: str) -> list[str]:
    compact = re.sub(r"\s+", " ", person_name.replace("\n", " ")).strip()
    if not compact:
        return []
    variants = [compact]
    parts = compact.split()
    if len(parts) >= 2:
        reversed_name = " ".join([parts[-1], *parts[:-1]])
        if reversed_name not in variants:
            variants.append(reversed_name)
    return variants


def strip_person_from_summary(summary: str, person_name: str) -> str:
    cleaned = summary.strip()
    for variant in person_name_variants(person_name):
        pattern = rf"^\s*{re.escape(variant)}(?:\s*[-–—:|/]+\s*|\s+)"
        match = re.match(pattern, cleaned, flags=re.IGNORECASE)
        if not match:
            continue
        title = cleaned[match.end() :].strip(" -–—:|/")
        if title:
            return title
    return cleaned


def strip_person_from_events(days: list[DayExtraction], person_name: str) -> list[DayExtraction]:
    updated_days: list[DayExtraction] = []
    for day in days:
        included = [
            replace(event, summary=strip_person_from_summary(event.summary, person_name))
            for event in day.included
        ]
        updated_days.append(replace(day, included=included))
    return updated_days


SEGMENT_SUFFIX_RE = re.compile(r"\s+\(\d+/\d+\)$")
PAUSE_SUFFIX_RE = re.compile(r"\s+\(-(?P<hours>\d+)h(?P<minutes>\d{2})?\)$")


def _base_event_summary(summary: str) -> str:
    summary = SEGMENT_SUFFIX_RE.sub("", summary).strip()
    return PAUSE_SUFFIX_RE.sub("", summary).strip()


def _summary_pause_minutes(summary: str) -> int:
    match = PAUSE_SUFFIX_RE.search(summary)
    if not match:
        return 0
    return int(match.group("hours")) * 60 + int(match.group("minutes") or 0)


def _merge_key(event: WorkEvent) -> tuple[str, str, str]:
    """Return the business identity used for same-day vacation merging."""
    summary = _base_event_summary(event.summary)
    return normalize_text(summary), normalize_text(event.source_text), normalize_text(event.day_label)


def _pause_suffix(minutes: int) -> str:
    hours, remainder = divmod(minutes, 60)
    return f"(-{hours}h{remainder:02d})" if remainder else f"(-{hours}h)"


def merge_identical_events(events: list[WorkEvent]) -> list[WorkEvent]:
    """Merge identical vacations from one planning column, including overnight ends."""
    if not events:
        return []

    merged: list[WorkEvent] = []
    for event in sorted(events, key=lambda item: (item.start, item.end, item.summary)):
        if not merged:
            merged.append(event)
            continue

        previous = merged[-1]
        same_planning_day = previous.day_label == event.day_label and previous.start.date() == event.start.date()
        can_merge = (
            same_planning_day
            and event.start >= previous.end
            and _merge_key(previous) == _merge_key(event)
        )
        if not can_merge:
            merged.append(event)
            continue

        pause_start = previous.end
        pause_end = event.start
        total_pause = _summary_pause_minutes(previous.summary) + max(
            int((pause_end - pause_start).total_seconds() // 60), 0
        )
        summary = _base_event_summary(previous.summary)
        if total_pause:
            summary = f"{summary} {_pause_suffix(total_pause)}"
        merged[-1] = replace(
            previous,
            summary=summary,
            end=event.end,
            source_text=previous.source_text,
        )

    return merged


def explicit_pause_window(raw_text: str, start_dt: datetime, end_dt: datetime) -> tuple[datetime, datetime] | None:
    match = EXPLICIT_PAUSE_RE.search(raw_text)
    if not match:
        return None
    tz = start_dt.tzinfo
    pause_start = datetime.combine(start_dt.date(), parse_time(match.group("pause_start")), tzinfo=tz)
    pause_end = datetime.combine(start_dt.date(), parse_time(match.group("pause_end")), tzinfo=tz)
    if pause_end <= pause_start:
        pause_end += timedelta(days=1)
    if start_dt < pause_start < pause_end < end_dt:
        return pause_start, pause_end
    return None


def logical_pause_window(start_dt: datetime, end_dt: datetime, pause_minutes: int) -> tuple[datetime, datetime]:
    explicit_midday = datetime.combine(start_dt.date(), time(13, 0), tzinfo=start_dt.tzinfo)
    noon = datetime.combine(start_dt.date(), time(12, 0), tzinfo=start_dt.tzinfo)

    if start_dt <= explicit_midday and end_dt >= explicit_midday + timedelta(minutes=pause_minutes):
        if end_dt.hour <= 15 and start_dt.hour <= 9:
            pause_start = noon
        else:
            pause_start = explicit_midday
    else:
        worked_minutes = max(minutes_between(start_dt, end_dt) - pause_minutes, 0)
        target = start_dt + timedelta(minutes=worked_minutes / 2)
        rounded = round((target.hour * 60 + target.minute) / 30) * 30
        pause_start = datetime.combine(
            target.date(), time(hour=(rounded // 60) % 24, minute=rounded % 60), tzinfo=start_dt.tzinfo
        )
        if pause_start <= start_dt:
            pause_start = start_dt + timedelta(minutes=max(60, worked_minutes // 2))
        if pause_start + timedelta(minutes=pause_minutes) >= end_dt:
            pause_start = end_dt - timedelta(minutes=pause_minutes + max(30, worked_minutes // 3))

    pause_end = pause_start + timedelta(minutes=pause_minutes)
    if pause_start <= start_dt or pause_end >= end_dt:
        fallback = start_dt + (end_dt - start_dt - timedelta(minutes=pause_minutes)) / 2
        pause_start = fallback
        pause_end = pause_start + timedelta(minutes=pause_minutes)
    return pause_start, pause_end


def split_for_pause(
    start_dt: datetime, end_dt: datetime, pause_minutes: int, raw_text: str
) -> list[tuple[datetime, datetime]]:
    if pause_minutes <= 0:
        return [(start_dt, end_dt)]

    window = explicit_pause_window(raw_text, start_dt, end_dt)
    if window is None:
        window = logical_pause_window(start_dt, end_dt, pause_minutes)

    pause_start, pause_end = window
    segments = [(start_dt, pause_start), (pause_end, end_dt)]
    return [(start, end) for start, end in segments if end > start]


def parse_events_for_day(
    raw_text: str, day_label: str, day_date: date, tz: ZoneInfo
) -> tuple[list[WorkEvent], list[str], str | None]:
    if is_non_working_only(raw_text):
        reason = normalize_text(raw_text) or "vide"
        return [], [], reason

    text = strip_vacation_headers(raw_text)
    matches = list(DETAILED_TIME_RE.finditer(text))
    warnings: list[str] = []
    events: list[WorkEvent] = []

    if not matches:
        stacked_matches = list(STACKED_TIME_RE.finditer(text))
        if stacked_matches:
            previous_end = 0
            for match in stacked_matches:
                chunk = text[previous_end : match.start()]
                previous_end = match.end()
                summary = clean_summary(chunk)
                start_dt, end_dt = combine_date_time(
                    day_date, parse_time(match.group("start")), parse_time(match.group("end")), tz
                )
                pause_minutes = parse_duration(match.group("pause"))
                worked_minutes = parse_duration(match.group("worked"))
                segments = split_for_pause(start_dt, end_dt, pause_minutes, raw_text)
                total_minutes = sum(minutes_between(start, end) for start, end in segments)
                if worked_minutes and total_minutes != worked_minutes:
                    warnings.append(
                        f"{day_label}: durée calculée {total_minutes // 60:02d}:{total_minutes % 60:02d} "
                        f"différente de TTE {worked_minutes // 60:02d}:{worked_minutes % 60:02d} pour '{summary}'."
                    )
                for segment_index, (segment_start, segment_end) in enumerate(segments):
                    segment_summary = summary
                    if len(segments) > 1:
                        segment_summary = f"{summary} ({segment_index + 1}/{len(segments)})"
                    events.append(
                        WorkEvent(
                            day_label=day_label,
                            summary=segment_summary,
                            description=raw_text,
                            start=segment_start,
                            end=segment_end,
                            source_text=raw_text,
                        )
                    )
            return events, warnings, None

        simple_times = SIMPLE_TIME_RE.findall(text)
        if len(simple_times) >= 2:
            start_dt, end_dt = combine_date_time(day_date, parse_time(simple_times[0]), parse_time(simple_times[-1]), tz)
            duration_minutes = minutes_between(start_dt, end_dt)
            inferred_pause = 60 if duration_minutes >= 7 * 60 else 0
            segments = split_for_pause(start_dt, end_dt, inferred_pause, raw_text)
            summary = clean_summary(text)
            if inferred_pause:
                warnings.append(
                    f"{day_label}: pause non lisible dans l'extraction, pause de 01:00 inférée pour '{summary}'."
                )
            else:
                warnings.append(
                    f"{day_label}: pause non lisible dans l'extraction, créneau conservé sans découpe pour '{summary}'."
                )
            for segment_index, (segment_start, segment_end) in enumerate(segments):
                segment_summary = summary
                if len(segments) > 1:
                    segment_summary = f"{summary} ({segment_index + 1}/{len(segments)})"
                events.append(
                    WorkEvent(
                        day_label=day_label,
                        summary=segment_summary,
                        description=raw_text,
                        start=segment_start,
                        end=segment_end,
                        source_text=raw_text,
                    )
                )
            return events, warnings, None

        vacation = VACATION_RANGE_RE.search(raw_text)
        if vacation and not is_non_working_only(raw_text):
            start_dt, end_dt = combine_date_time(
                day_date, parse_time(vacation.group("start")), parse_time(vacation.group("end")), tz
            )
            summary = clean_summary(strip_vacation_headers(raw_text))
            events.append(
                WorkEvent(
                    day_label=day_label,
                    summary=summary,
                    description=raw_text,
                    start=start_dt,
                    end=end_dt,
                    source_text=raw_text,
                )
            )
            warnings.append(f"{day_label}: horaires Vacation utilisés faute de détail Pause/TTE.")
            return events, warnings, None
        warnings.append(f"{day_label}: aucun horaire exploitable trouvé, journée ignorée.")
        return [], warnings, "horaire introuvable"

    previous_end = 0
    for index, match in enumerate(matches):
        chunk = text[previous_end : match.start()]
        previous_end = match.end()
        summary = clean_summary(chunk)
        start_dt, end_dt = combine_date_time(
            day_date, parse_time(match.group("start")), parse_time(match.group("end")), tz
        )
        pause_minutes = parse_duration(match.group("pause"))
        worked_minutes = parse_duration(match.group("worked"))
        segments = split_for_pause(start_dt, end_dt, pause_minutes, raw_text)
        total_minutes = sum(minutes_between(start, end) for start, end in segments)
        if worked_minutes and total_minutes != worked_minutes:
            warnings.append(
                f"{day_label}: durée calculée {total_minutes // 60:02d}:{total_minutes % 60:02d} "
                f"différente de TTE {worked_minutes // 60:02d}:{worked_minutes % 60:02d} pour '{summary}'."
            )
        for segment_index, (segment_start, segment_end) in enumerate(segments):
            segment_summary = summary
            if len(segments) > 1:
                segment_summary = f"{summary} ({segment_index + 1}/{len(segments)})"
            events.append(
                WorkEvent(
                    day_label=day_label,
                    summary=segment_summary,
                    description=raw_text,
                    start=segment_start,
                    end=segment_end,
                    source_text=raw_text,
                )
            )

    return events, warnings, None


def choose_best_match(
    matches_by_pdf: list[tuple[PdfCandidate, PersonBlock, float]], request: Request, assume_yes: bool
) -> tuple[PdfCandidate, PersonBlock, float]:
    if not matches_by_pdf:
        raise LookupError(f"Aucune ligne/personne trouvée pour '{request.person}' en semaine {request.week}.")

    matches_by_pdf.sort(key=lambda item: (item[2], item[0].score, item[0].path.stat().st_mtime), reverse=True)
    best = matches_by_pdf[0]
    same_score = [item for item in matches_by_pdf if abs(item[2] - best[2]) < 0.01]
    if len(same_score) > 1 and not assume_yes:
        choices = "\n".join(
            f"- {item[1].name} dans {item[0].path} (score nom {item[2]:.2f})" for item in same_score[:8]
        )
        raise RuntimeError(
            "Extraction ambiguë: plusieurs lignes correspondent presque autant.\n"
            f"{choices}\nRelance avec --pdf ou --yes après vérification."
        )
    if best[2] < 0.9 and not assume_yes:
        raise RuntimeError(
            f"Correspondance approximative détectée: '{request.person}' -> '{best[1].name}' "
            f"(score {best[2]:.2f}). Relance avec --yes si c'est correct."
        )
    return best


def extract_planning(
    request: Request,
    source_dir: Path,
    explicit_pdf: Path | None = None,
    assume_yes: bool = False,
    timezone: str = DEFAULT_TIMEZONE,
) -> ExtractionResult:
    candidates = find_pdf_candidates(source_dir, request, explicit_pdf)
    if not candidates:
        raise FileNotFoundError(
            f"Aucun PDF trouvé pour la semaine {request.week} dans {source_dir}."
        )

    matches_by_pdf: list[tuple[PdfCandidate, PersonBlock, float]] = []
    top_pdf_score = candidates[0].score
    for candidate in candidates[:20]:
        candidate_matches = []
        for block, score in find_person_blocks(candidate.path, request):
            match = (candidate, block, score)
            matches_by_pdf.append(match)
            candidate_matches.append(match)
        if candidate_matches and max(item[2] for item in candidate_matches) >= 0.98:
            break
        if (
            candidate_matches
            and candidate.score >= top_pdf_score - 5
            and max(item[2] for item in candidate_matches) >= 0.92
        ):
            break

    candidate, block, score = choose_best_match(matches_by_pdf, request, assume_yes)
    tz = ZoneInfo(timezone)
    warnings = parse_pdf_date_headers(candidate.path, request)
    columns = table_day_columns(block.header, request)
    days: list[DayExtraction] = []
    for offset, column in enumerate(columns):
        label = DAY_LABELS[offset][1]
        raw = day_raw_text(block, column)
        included, day_warnings, ignored_reason = parse_events_for_day(raw, label, column.date, tz)
        days.append(
            DayExtraction(
                label=label,
                date=column.date,
                raw_text=raw,
                included=included,
                ignored_reason=ignored_reason if not included else None,
                warnings=tuple(day_warnings),
            )
        )
        warnings.extend(day_warnings)

    person_name = block.name.replace("\n", " ")

    return ExtractionResult(
        pdf=candidate.path,
        person_name=person_name,
        matched_score=score,
        week=request.week,
        year=request.year,
        days=[
            replace(day, included=merge_identical_events(day.included))
            for day in strip_person_from_events(days, person_name)
        ],
        warnings=warnings,
    )


def format_hhmm(value: datetime) -> str:
    return value.strftime("%H:%M")


def format_summary(result: ExtractionResult) -> str:
    lines = [
        f"{result.person_name} - Semaine {result.week} - {result.year}",
        f"PDF: {result.pdf}",
    ]
    for day in result.days:
        date_label = day.date.strftime("%d/%m")
        if day.included:
            bits = []
            for event in day.included:
                end_label = format_hhmm(event.end)
                if event.end.date() != event.start.date():
                    end_label += f" (+{(event.end.date() - event.start.date()).days}j)"
                bits.append(f"{format_hhmm(event.start)}-{end_label} {event.summary}")
            lines.append(f"{day.label} {date_label} : " + " ; ".join(bits))
        else:
            reason = day.ignored_reason or "non inclus"
            lines.append(f"{day.label} {date_label} : {reason}, non inclus")
    if result.warnings:
        lines.append("")
        lines.append("Alertes :")
        lines.extend(f"- {warning}" for warning in result.warnings)
    return "\n".join(lines)


def canonical_person_for_filename(person: str) -> tuple[str, str]:
    tokens = [tok for tok in re.split(r"\s+", person.replace("\n", " ").strip()) if tok]
    if not tokens:
        return "Personne", "Inconnue"
    if len(tokens) == 1:
        return tokens[0].title(), "Planning"
    first = tokens[-1].title()
    last = "_".join(tok.title() for tok in tokens[:-1])
    return first, last


def ics_escape(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    return (
        value.replace("\\", "\\\\")
        .replace(";", r"\;")
        .replace(",", r"\,")
        .replace("\r\n", r"\n")
        .replace("\n", r"\n")
    )


def fold_ics_line(line: str) -> str:
    encoded = line.encode(ICS_FILE_ENCODING)
    if len(encoded) <= 75:
        return line
    parts: list[str] = []
    current = ""
    current_len = 0
    for ch in line:
        ch_len = len(ch.encode(ICS_FILE_ENCODING))
        if current and current_len + ch_len > 75:
            parts.append(current)
            current = " " + ch
            current_len = 1 + ch_len
        else:
            current += ch
            current_len += ch_len
    parts.append(current)
    return "\r\n".join(parts)


def utc_stamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def build_uid(result: ExtractionResult, event: WorkEvent) -> str:
    """Build an ICS identifier that survives PDF moves and repeated exports."""
    key = "|".join(
        [
            normalize_text(result.person_name),
            str(result.year),
            f"{result.week:02d}",
            event.start.isoformat(),
            event.end.isoformat(),
            normalize_text(event.summary),
        ]
    )
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]
    return f"{digest}@planning-to-ics.local"


def build_ics(result: ExtractionResult) -> str:
    now = datetime.now(UTC)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Planning Radio France Local Agent//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:Planning {ics_escape(result.person_name)} S{result.week:02d} {result.year}",
        f"X-WR-TIMEZONE:{DEFAULT_TIMEZONE}",
    ]
    for event in result.events:
        description = (
            f"Source PDF: {result.pdf}\n"
            f"Personne: {result.person_name}\n"
            f"Semaine: {result.week} {result.year}\n\n"
            f"Cellule extraite:\n{event.description}"
        )
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{build_uid(result, event)}",
                f"DTSTAMP:{now.strftime('%Y%m%dT%H%M%SZ')}",
                f"DTSTART:{utc_stamp(event.start)}",
                f"DTEND:{utc_stamp(event.end)}",
                f"SUMMARY:{ics_escape(event.summary)}",
                f"DESCRIPTION:{ics_escape(description)}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold_ics_line(line) for line in lines) + "\r\n"


def output_ics_path(output_dir: Path, result: ExtractionResult) -> Path:
    first, last = canonical_person_for_filename(result.person_name)
    return output_dir / f"Planning_{first}_{last}_S{result.week:02d}_{result.year}.ics"


def write_ics_file(path: Path, result: ExtractionResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ICS_FILE_BOM + build_ics(result).encode(ICS_FILE_ENCODING, errors="strict"))


def write_log(output_dir: Path, result: ExtractionResult, ics_path: Path | None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "Planning_agent_log.txt"
    lines = [
        "=" * 72,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        f"PDF utilisé: {result.pdf}",
        f"Personne traitée: {result.person_name}",
        f"Semaine traitée: S{result.week:02d} {result.year}",
        f"Nombre d'événements générés: {len(result.events)}",
        f"ICS: {ics_path if ics_path else 'dry-run'}",
    ]
    if result.warnings:
        lines.append("Alertes:")
        lines.extend(f"- {warning}" for warning in result.warnings)
    lines.append("")
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        request = request_from_args(args)
        result = extract_planning(
            request,
            source_dir=args.source,
            explicit_pdf=args.pdf,
            assume_yes=args.yes,
        )
        print(format_summary(result))
        if args.dry_run:
            return 0
        args.output.mkdir(parents=True, exist_ok=True)
        ics_path = output_ics_path(args.output, result)
        write_ics_file(ics_path, result)
        write_log(args.output, result, ics_path)
        print()
        print(f"ICS généré: {ics_path}")
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
