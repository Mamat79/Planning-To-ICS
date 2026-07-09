#!/usr/bin/env python
"""Small local web UI for the Radio France planning-to-ICS agent."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import socket
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from datetime import date, datetime, time
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from planning_to_ics import (
    DEFAULT_TIMEZONE,
    OUTPUT_DIR,
    SOURCE_DIR,
    DayExtraction,
    ExtractionResult,
    Request,
    WorkEvent,
    build_ics,
    extract_planning,
    format_summary,
    list_people_for_week,
    output_ics_path,
    week_year_from_path,
    write_ics_file,
    write_log,
)

APP_VERSION = "V1.03"
SETTINGS_KEYS = {"planning_dir", "output_dir"}


def settings_path() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "Planning To ICS" / "settings.json"
    return Path.home() / ".planning_to_ics" / "settings.json"


def default_settings() -> dict[str, str]:
    return {
        "planning_dir": str(SOURCE_DIR),
        "output_dir": str(OUTPUT_DIR),
    }


def load_settings() -> dict[str, str]:
    settings = default_settings()
    path = settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return settings
    if isinstance(data, dict):
        for key in SETTINGS_KEYS:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                settings[key] = value.strip()
    return settings


def save_settings(updates: dict[str, str]) -> dict[str, str]:
    settings = load_settings()
    for key, value in updates.items():
        if key in SETTINGS_KEYS and isinstance(value, str) and value.strip():
            settings[key] = value.strip()
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return settings


def find_free_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])


def explicit_pdf_from_value(value: str) -> Path | None:
    value = value.strip()
    if not value or value == "__auto__":
        return None
    return Path(value)


@lru_cache(maxsize=32)
def cached_people_for_pdf(pdf_path_text: str) -> tuple[str, ...]:
    pdf_path = explicit_pdf_from_value(pdf_path_text)
    if not pdf_path:
        return tuple()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF introuvable: {pdf_path}")
    year, week = week_year_for_pdf(pdf_path)
    return tuple(list_people_for_week(pdf_path.parent, week=week, year=year, explicit_pdf=pdf_path))


def week_year_for_pdf(pdf_path: Path) -> tuple[int, int]:
    parsed = week_year_from_path(pdf_path)
    if parsed:
        return parsed

    week_match = re.search(r"(?<!\d)(?:semaine|sem|s)[\s._-]*0?(\d{1,2})(?!\d)", str(pdf_path), re.IGNORECASE)
    if not week_match:
        raise ValueError(
            "Impossible de détecter la semaine dans le nom du PDF. "
            "Le nom doit contenir par exemple SEM30."
        )
    week = int(week_match.group(1))
    if not 1 <= week <= 53:
        raise ValueError(f"Semaine invalide dans le nom du PDF: {week}")

    year_match = re.search(r"(?<!\d)(20\d{2})(?!\d)", str(pdf_path))
    if year_match:
        year = int(year_match.group(1))
    else:
        try:
            year = datetime.fromtimestamp(pdf_path.stat().st_mtime).year
        except OSError:
            year = date.today().year
    try:
        date.fromisocalendar(year, week, 1)
    except ValueError as exc:
        raise ValueError(f"Impossible de calculer la semaine {week} pour l'année {year}.") from exc
    return year, week


def person_options(people: list[str], selected_person: str = "") -> str:
    options = ['<option value="">Choisir...</option>']
    selected_key = selected_person.strip().lower()
    for person in people:
        selected = " selected" if person.lower() == selected_key else ""
        value = html.escape(person, quote=True)
        options.append(f'<option value="{value}"{selected}>{html.escape(person)}</option>')
    return "\n".join(options)


def pdf_label(path_text: str) -> str:
    path = Path(path_text)
    parsed = week_year_from_path(path)
    if not parsed and path.exists():
        try:
            parsed = week_year_for_pdf(path)
        except Exception:
            parsed = None
    suffix = f" - S{parsed[1]:02d} {parsed[0]}" if parsed else ""
    return f"{path.name}{suffix}"


def looks_like_planning_pdf(path: Path) -> bool:
    normalized = path.name.lower()
    return bool(
        re.search(r"(?<![a-z0-9])(?:sem|semaine)\s*0?\d{1,2}(?!\d)", normalized)
        or re.search(r"(?<![a-z0-9])s\s*0?\d{1,2}(?![a-z0-9])", normalized)
    )


def list_planning_pdfs(planning_dir: str) -> list[str]:
    root = Path(planning_dir).expanduser()
    if not root.exists():
        return []
    if root.is_file():
        if root.suffix.lower() != ".pdf":
            return []
        if not looks_like_planning_pdf(root):
            return []
        try:
            week_year_for_pdf(root)
        except Exception:
            return []
        return [str(root)]
    pdfs = []
    for path in root.rglob("*.pdf"):
        if not path.is_file():
            continue
        if not looks_like_planning_pdf(path):
            continue
        try:
            week_year_for_pdf(path)
        except Exception:
            continue
        pdfs.append(path)
    pdfs.sort(key=lambda path: (path.stat().st_mtime, path.name.lower()), reverse=True)
    return [str(path) for path in pdfs[:200]]


def pdf_select_options(pdfs: list[str], selected_pdf: str = "") -> str:
    options = ['<option value="">Choisir un PDF...</option>']
    selected_norm = selected_pdf.strip().lower()
    seen = set()
    for path_text in pdfs:
        seen.add(path_text.lower())
        selected = " selected" if selected_norm and path_text.lower() == selected_norm else ""
        value = html.escape(path_text, quote=True)
        label = html.escape(pdf_label(path_text))
        options.append(f'<option value="{value}"{selected}>{label}</option>')
    if selected_pdf and selected_norm not in seen:
        value = html.escape(selected_pdf, quote=True)
        label = html.escape(pdf_label(selected_pdf))
        options.insert(1, f'<option value="{value}" selected>{label}</option>')
    if len(options) == 1:
        options.append('<option value="" disabled>Aucun PDF trouvé dans ce dossier</option>')
    return "\n".join(options)


def page_shell(
    content: str,
    *,
    people: list[str],
    pdfs: list[str] | None = None,
    selected_person: str = "",
    manual_pdf: str = "",
    planning_dir: str = "",
    output_dir: str = "",
) -> bytes:
    settings = load_settings()
    manual_pdf_value = html.escape(manual_pdf, quote=True)
    planning_dir_value = html.escape(planning_dir or settings["planning_dir"], quote=True)
    output_dir_value = html.escape(output_dir or settings["output_dir"], quote=True)
    pdfs = pdfs if pdfs is not None else list_planning_pdfs(planning_dir or settings["planning_dir"])
    body = f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Planning To ICS</title>
  <style>
    :root {{
      color-scheme: light;
      --text: #202124;
      --muted: #62676f;
      --line: #d9dde3;
      --soft: #f6f7f9;
      --accent: #146c5f;
      --accent-strong: #0f5148;
      --error: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Segoe UI, Arial, sans-serif;
      color: var(--text);
      background: #fff;
    }}
    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      min-height: 62px;
      padding: 16px 28px;
      border-bottom: 1px solid var(--line);
      background: #fbfbfc;
    }}
    h1 {{
      margin: 0;
      font-size: 20px;
      font-weight: 650;
      letter-spacing: 0;
    }}
    .version {{
      margin-left: 7px;
      color: var(--muted);
      font-size: 10px;
      font-weight: 500;
      vertical-align: super;
    }}
    .signature {{
      color: var(--muted);
      font-size: 13px;
      font-style: italic;
      white-space: nowrap;
    }}
    main {{
      display: grid;
      grid-template-columns: minmax(320px, 430px) minmax(0, 1fr);
      min-height: calc(100vh - 62px);
    }}
    form {{
      padding: 24px;
      border-right: 1px solid var(--line);
      background: var(--soft);
    }}
    label {{
      display: block;
      margin: 0 0 7px;
      font-size: 13px;
      color: var(--muted);
    }}
    select, input[type="text"], input[type="date"], input[type="time"], textarea {{
      width: 100%;
      min-height: 42px;
      margin-bottom: 16px;
      padding: 9px 11px;
      border: 1px solid #c7ccd4;
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      font: inherit;
    }}
    textarea {{
      min-height: 74px;
      resize: vertical;
    }}
    select:focus, input[type="text"]:focus, input[type="date"]:focus, input[type="time"]:focus, textarea:focus {{
      outline: 2px solid rgba(20, 108, 95, .2);
      border-color: var(--accent);
    }}
    .field-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: start;
    }}
    .field-row input[type="text"] {{
      margin-bottom: 16px;
    }}
    .field-row button {{
      min-height: 42px;
      padding: 8px 12px;
    }}
    .actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 4px;
    }}
    button {{
      min-height: 40px;
      padding: 8px 14px;
      border: 1px solid var(--accent);
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      font: inherit;
      font-weight: 600;
      cursor: pointer;
    }}
    button.secondary {{
      background: #fff;
      color: var(--accent);
    }}
    button:hover {{ border-color: var(--accent-strong); background: var(--accent-strong); }}
    button.secondary:hover {{ background: #eef7f5; color: var(--accent-strong); }}
    section {{
      padding: 24px;
      overflow: auto;
    }}
    h2 {{
      margin: 0 0 14px;
      font-size: 18px;
      font-weight: 650;
      letter-spacing: 0;
    }}
    pre {{
      margin: 0;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      line-height: 1.45;
      font-family: Consolas, Cascadia Mono, monospace;
      font-size: 13px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 0 0 16px;
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 6px;
      overflow: hidden;
    }}
    th, td {{
      padding: 9px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      text-align: left;
      font-size: 13px;
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
      background: #f8f9fb;
    }}
    td input, td textarea {{
      margin-bottom: 0;
    }}
    .event-enabled {{
      width: 44px;
      text-align: center;
    }}
    .event-date {{
      min-width: 135px;
    }}
    .event-time {{
      min-width: 105px;
    }}
    .event-summary {{
      min-width: 240px;
    }}
    .event-description {{
      min-width: 260px;
    }}
    .empty {{
      max-width: 720px;
      color: var(--muted);
      line-height: 1.5;
    }}
    .hint {{
      min-height: 18px;
      margin: -8px 0 16px;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .import-note {{
      margin: 16px 0 0;
      padding: 11px 13px;
      border: 1px solid #cbded8;
      border-radius: 6px;
      background: #f1faf7;
      color: #174f3f;
      line-height: 1.45;
      font-size: 13px;
    }}
    .ok, .error {{
      margin: 0 0 16px;
      padding: 12px 14px;
      border-radius: 6px;
      border: 1px solid var(--line);
      background: #fff;
      line-height: 1.45;
    }}
    .ok {{ border-color: #9bcfbd; color: #174f3f; }}
    .error {{ border-color: #f0b2ad; color: var(--error); }}
    code {{
      padding: 1px 4px;
      border-radius: 4px;
      background: #eef0f3;
      font-family: Consolas, Cascadia Mono, monospace;
      font-size: 12px;
    }}
    @media (max-width: 820px) {{
      header {{ padding: 16px; }}
      main {{ grid-template-columns: 1fr; }}
      form {{ border-right: 0; border-bottom: 1px solid var(--line); padding: 18px; }}
      section {{ padding: 18px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Planning To ICS <span class="version">{APP_VERSION}</span></h1>
    <div class="signature">by Mamat</div>
  </header>
  <main>
    <form method="post">
      <label for="planning_dir">Dossier des plannings</label>
      <div class="field-row">
        <input id="planning_dir" name="planning_dir" type="text" value="{planning_dir_value}">
        <button class="secondary" id="browse_planning_dir" type="button">Parcourir</button>
      </div>

      <label for="pdf_select">PDF trouvés dans ce dossier</label>
      <select id="pdf_select">
        {pdf_select_options(pdfs, manual_pdf)}
      </select>

      <label for="manual_pdf">PDF de planning</label>
      <div class="field-row">
        <input id="manual_pdf" name="manual_pdf" type="text" value="{manual_pdf_value}" required>
        <button class="secondary" id="browse_pdf" type="button">Parcourir</button>
      </div>
      <div class="hint" id="pdf_info"></div>

      <label for="person">Technicien</label>
      <select id="person" name="person" required>
        {person_options(people, selected_person)}
      </select>

      <label for="output_dir">Exporter vers</label>
      <div class="field-row">
        <input id="output_dir" name="output_dir" type="text" value="{output_dir_value}" required>
        <button class="secondary" id="browse_output" type="button">Parcourir</button>
      </div>

      <div class="actions">
        <button type="submit" name="action" value="generate">Générer ICS</button>
        <button class="secondary" type="submit" name="action" value="preview">Prévisualiser</button>
      </div>
      <p class="import-note">Après génération, importe le fichier ICS dans ton agenda Outlook, Google Agenda ou autre calendrier. L'application crée le fichier, elle ne l'ajoute pas automatiquement à l'agenda.</p>
    </form>
    <section>
      {content}
    </section>
  </main>
  <script>
    const planningDirInput = document.getElementById("planning_dir");
    const pdfSelect = document.getElementById("pdf_select");
    const manualPdfInput = document.getElementById("manual_pdf");
    const pdfInfo = document.getElementById("pdf_info");
    const personSelect = document.getElementById("person");
    const outputInput = document.getElementById("output_dir");
    const browsePlanningDirButton = document.getElementById("browse_planning_dir");
    const browsePdfButton = document.getElementById("browse_pdf");
    const browseOutputButton = document.getElementById("browse_output");

    async function rememberSettings(updates) {{
      try {{
        await fetch("/api/settings", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(updates)
        }});
      }} catch (error) {{}}
    }}

    async function loadPdfs() {{
      const selected = manualPdfInput.value.trim();
      const params = new URLSearchParams({{
        planning_dir: planningDirInput.value.trim(),
        selected
      }});
      const response = await fetch(`/api/planning-pdfs?${{params.toString()}}`);
      const data = await response.json();
      pdfSelect.innerHTML = "";
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "Choisir un PDF...";
      pdfSelect.appendChild(placeholder);
      for (const item of data.pdfs || []) {{
        const option = document.createElement("option");
        option.value = item.path;
        option.textContent = item.label;
        if (selected && item.path.toLowerCase() === selected.toLowerCase()) {{
          option.selected = true;
        }}
        pdfSelect.appendChild(option);
      }}
      if (!data.pdfs || data.pdfs.length === 0) {{
        const option = document.createElement("option");
        option.value = "";
        option.disabled = true;
        option.textContent = data.error || "Aucun PDF trouvé dans ce dossier";
        pdfSelect.appendChild(option);
      }}
    }}

    async function loadPeople() {{
      const pdf = manualPdfInput.value.trim();
      personSelect.innerHTML = '<option value="">Chargement...</option>';
      pdfInfo.textContent = "";
      if (!pdf) {{
        personSelect.innerHTML = '<option value="">Choisir...</option>';
        return;
      }}
      const params = new URLSearchParams({{ pdf }});
      const response = await fetch(`/api/people?${{params.toString()}}`);
      const data = await response.json();
      personSelect.innerHTML = '<option value="">Choisir...</option>';
      if (data.error) {{
        pdfInfo.textContent = data.error;
        return;
      }}
      if (data.planning_dir) {{
        planningDirInput.value = data.planning_dir;
      }}
      if (data.week && data.year) {{
        pdfInfo.textContent = `S${{String(data.week).padStart(2, "0")}} ${{data.year}}`;
      }}
      for (const person of data.people) {{
        const option = document.createElement("option");
        option.value = person;
        option.textContent = person;
        personSelect.appendChild(option);
      }}
    }}

    async function choose(kind) {{
      const params = new URLSearchParams({{
        kind,
        planning_dir: planningDirInput.value.trim(),
        output_dir: outputInput.value.trim(),
        pdf: manualPdfInput.value.trim()
      }});
      const response = await fetch(`/api/choose?${{params.toString()}}`);
      const data = await response.json();
      if (data.path) {{
        if (kind === "pdf") {{
          manualPdfInput.value = data.path;
          if (data.planning_dir) {{
            planningDirInput.value = data.planning_dir;
          }}
          await loadPdfs();
          await loadPeople();
        }} else if (kind === "planning_directory") {{
          planningDirInput.value = data.path;
          await loadPdfs();
        }} else {{
          outputInput.value = data.path;
        }}
      }}
    }}

    pdfSelect.addEventListener("change", async () => {{
      if (pdfSelect.value) {{
        manualPdfInput.value = pdfSelect.value;
        await loadPeople();
      }}
    }});
    manualPdfInput.addEventListener("change", loadPeople);
    planningDirInput.addEventListener("change", async () => {{
      await rememberSettings({{ planning_dir: planningDirInput.value.trim() }});
      manualPdfInput.value = "";
      personSelect.innerHTML = '<option value="">Choisir...</option>';
      pdfInfo.textContent = "";
      await loadPdfs();
    }});
    outputInput.addEventListener("change", () => rememberSettings({{ output_dir: outputInput.value.trim() }}));
    browsePlanningDirButton.addEventListener("click", () => choose("planning_directory"));
    browsePdfButton.addEventListener("click", () => choose("pdf"));
    browseOutputButton.addEventListener("click", () => choose("directory"));
  </script>
</body>
</html>"""
    return body.encode("utf-8")


def render_home() -> bytes:
    settings = load_settings()
    content = """
      <h2>Choisir un planning PDF</h2>
      <p class="empty">Choisis le dossier des plannings, sélectionne un PDF dans la liste, choisis le technicien, puis prévisualise ou génère l'ICS.</p>
      <p class="import-note">Une fois le fichier ICS généré, il faut l'importer dans ton agenda. Dans Outlook, utilise l'import de calendrier ou ouvre le fichier ICS pour l'ajouter au calendrier voulu.</p>
    """
    return page_shell(
        content,
        people=[],
        planning_dir=settings["planning_dir"],
        output_dir=settings["output_dir"],
    )


def parse_post(body: bytes) -> dict[str, str]:
    fields = urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[0].strip() for key, values in fields.items()}


def chosen_pdf(fields: dict[str, str]) -> Path:
    manual_pdf = fields.get("manual_pdf", "").strip()
    pdf_path = explicit_pdf_from_value(manual_pdf)
    if not pdf_path:
        raise ValueError("Choisis un PDF de planning.")
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF introuvable: {pdf_path}")
    return pdf_path


def chosen_output_dir(fields: dict[str, str]) -> Path:
    output_text = fields.get("output_dir", "").strip() or load_settings()["output_dir"]
    return Path(output_text)


def hidden_input(name: str, value: str) -> str:
    return f'<input type="hidden" name="{html.escape(name, quote=True)}" value="{html.escape(value, quote=True)}">'


def event_editor(result: ExtractionResult, fields: dict[str, str], summary_html: str) -> str:
    hidden_fields = [
        hidden_input("manual_pdf", fields.get("manual_pdf", "")),
        hidden_input("planning_dir", fields.get("planning_dir", "")),
        hidden_input("person", fields.get("person", "")),
        hidden_input("output_dir", fields.get("output_dir", "") or load_settings()["output_dir"]),
        hidden_input("edit_person_name", result.person_name),
        hidden_input("edit_pdf", str(result.pdf)),
        hidden_input("edit_week", str(result.week)),
        hidden_input("edit_year", str(result.year)),
        hidden_input("event_count", str(len(result.events))),
    ]

    rows = []
    for index, event in enumerate(result.events):
        rows.append(
            f"""
            <tr>
              <td class="event-enabled">
                <input type="checkbox" name="event_{index}_enabled" checked>
              </td>
              <td class="event-date">
                <input type="date" name="event_{index}_start_date" value="{event.start.date().isoformat()}" required>
                <input type="date" name="event_{index}_end_date" value="{event.end.date().isoformat()}" required>
              </td>
              <td class="event-time">
                <input type="time" name="event_{index}_start_time" value="{event.start.strftime('%H:%M')}" required>
                <input type="time" name="event_{index}_end_time" value="{event.end.strftime('%H:%M')}" required>
              </td>
              <td class="event-summary">
                <input type="text" name="event_{index}_summary" value="{html.escape(event.summary, quote=True)}" required>
              </td>
              <td class="event-description">
                <textarea name="event_{index}_description">{html.escape(event.description)}</textarea>
              </td>
            </tr>
            """
        )

    rows_html = "\n".join(rows) or """
      <tr><td colspan="5">Aucun événement extrait.</td></tr>
    """

    return f"""
      <h2>Prévisualisation</h2>
      <pre>{summary_html}</pre>
      <h2 style="margin-top: 22px;">Événements modifiables</h2>
      <form method="post">
        {''.join(hidden_fields)}
        <table>
          <thead>
            <tr>
              <th>Inclure</th>
              <th>Dates début / fin</th>
              <th>Heures début / fin</th>
              <th>Résumé</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {rows_html}
          </tbody>
        </table>
        <div class="actions">
          <button type="submit" name="action" value="export_edited">Exporter ICS modifié</button>
          <button class="secondary" type="submit" name="action" value="preview">Recalculer depuis le PDF</button>
        </div>
      </form>
    """


def parse_local_datetime(date_text: str, time_text: str, tz: ZoneInfo) -> datetime:
    return datetime.combine(date.fromisoformat(date_text), time.fromisoformat(time_text), tzinfo=tz)


def edited_result_from_fields(fields: dict[str, str]) -> ExtractionResult:
    tz = ZoneInfo(DEFAULT_TIMEZONE)
    count = int(fields.get("event_count", "0"))
    events: list[WorkEvent] = []
    for index in range(count):
        if fields.get(f"event_{index}_enabled") != "on":
            continue
        summary = fields.get(f"event_{index}_summary", "").strip()
        if not summary:
            raise ValueError(f"Résumé manquant pour l'événement {index + 1}.")
        start = parse_local_datetime(
            fields.get(f"event_{index}_start_date", ""),
            fields.get(f"event_{index}_start_time", ""),
            tz,
        )
        end = parse_local_datetime(
            fields.get(f"event_{index}_end_date", ""),
            fields.get(f"event_{index}_end_time", ""),
            tz,
        )
        if end <= start:
            raise ValueError(f"L'événement {index + 1} finit avant son début.")
        description = fields.get(f"event_{index}_description", "").strip()
        events.append(
            WorkEvent(
                day_label=start.strftime("%a"),
                summary=summary,
                description=description or "Modifié manuellement depuis la prévisualisation.",
                start=start,
                end=end,
                source_text=description,
            )
        )

    if not events:
        raise ValueError("Aucun événement sélectionné pour l'export.")

    first_date = events[0].start.date()
    pdf = Path(fields.get("edit_pdf") or fields.get("manual_pdf") or "")
    parsed_year, parsed_week = week_year_for_pdf(pdf) if pdf else (first_date.isocalendar().year, first_date.isocalendar().week)
    return ExtractionResult(
        pdf=pdf,
        person_name=fields.get("edit_person_name") or fields.get("person") or "Planning",
        matched_score=1.0,
        week=int(fields.get("edit_week") or parsed_week),
        year=int(fields.get("edit_year") or parsed_year),
        days=[
            DayExtraction(
                label="Modifié",
                date=first_date,
                raw_text="Événements modifiés depuis la prévisualisation.",
                included=events,
            )
        ],
        warnings=["ICS modifié manuellement depuis la prévisualisation."],
    )


def export_result(result: ExtractionResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ics_path = output_ics_path(output_dir, result)
    write_ics_file(ics_path, result)
    write_log(output_dir, result, ics_path)
    return ics_path


def run_generation(fields: dict[str, str]) -> bytes:
    selected_person = fields.get("person", "")
    manual_pdf = fields.get("manual_pdf", "")
    settings = load_settings()
    planning_dir_text = fields.get("planning_dir", "") or settings["planning_dir"]
    output_dir_text = fields.get("output_dir", "") or settings["output_dir"]
    action = fields.get("action") or "generate"
    try:
        explicit_pdf = chosen_pdf(fields)
        year, week = week_year_for_pdf(explicit_pdf)
        planning_dir_text = str(explicit_pdf.parent)
        save_settings({"planning_dir": planning_dir_text, "output_dir": output_dir_text})
        people = list(cached_people_for_pdf(str(explicit_pdf)))
        if not selected_person:
            raise ValueError("Choisis un technicien.")

        if action == "export_edited":
            result = edited_result_from_fields(fields)
            output_dir = chosen_output_dir(fields)
            save_settings({"planning_dir": planning_dir_text, "output_dir": str(output_dir)})
            ics_path = export_result(result, output_dir)
            summary_html = html.escape(format_summary(result))
            content = f"""
              <p class="ok">ICS modifié généré : <code>{html.escape(str(ics_path))}</code></p>
              <p class="import-note">Dernière étape : importe ce fichier ICS dans ton agenda. Le fichier est prêt, mais il n'est pas ajouté automatiquement dans Outlook ou Google Agenda.</p>
              <h2>Résumé exporté</h2>
              <pre>{summary_html}</pre>
            """
            return page_shell(
                content,
                people=people,
                selected_person=selected_person,
                manual_pdf=manual_pdf,
                planning_dir=planning_dir_text,
                output_dir=str(output_dir),
            )

        request = Request(person=selected_person, week=week, year=year)
        result = extract_planning(request, source_dir=explicit_pdf.parent, explicit_pdf=explicit_pdf, assume_yes=True)
        summary = format_summary(result)
        summary_html = html.escape(summary)

        if action == "preview":
            content = event_editor(result, fields, summary_html)
            return page_shell(
                content,
                people=people,
                selected_person=selected_person,
                manual_pdf=manual_pdf,
                planning_dir=planning_dir_text,
                output_dir=output_dir_text,
            )

        output_dir = chosen_output_dir(fields)
        save_settings({"planning_dir": planning_dir_text, "output_dir": str(output_dir)})
        ics_path = export_result(result, output_dir)
        content = f"""
          <p class="ok">ICS généré : <code>{html.escape(str(ics_path))}</code></p>
          <p class="import-note">Dernière étape : importe ce fichier ICS dans ton agenda. Le fichier est prêt, mais il n'est pas ajouté automatiquement dans Outlook ou Google Agenda.</p>
          <h2>Résumé</h2>
          <pre>{summary_html}</pre>
        """
        return page_shell(
            content,
            people=people,
            selected_person=selected_person,
            manual_pdf=manual_pdf,
            planning_dir=planning_dir_text,
            output_dir=str(output_dir),
        )
    except Exception as exc:
        people: list[str] = []
        try:
            explicit_pdf = explicit_pdf_from_value(manual_pdf)
            if explicit_pdf and explicit_pdf.exists():
                planning_dir_text = str(explicit_pdf.parent)
                people = list(cached_people_for_pdf(str(explicit_pdf)))
        except Exception:
            people = []
        content = f"""
          <p class="error">{html.escape(str(exc))}</p>
          <h2>À vérifier</h2>
          <p class="empty">Contrôle le PDF, le technicien et le dossier d'export.</p>
        """
        return page_shell(
            content,
            people=people,
            selected_person=selected_person,
            manual_pdf=manual_pdf,
            planning_dir=planning_dir_text,
            output_dir=output_dir_text,
        )


def render_people_api(query: str) -> bytes:
    params = urllib.parse.parse_qs(query)
    pdf = params.get("pdf", [""])[0]
    try:
        pdf_path = explicit_pdf_from_value(pdf)
        if not pdf_path:
            payload = {"people": []}
        elif not pdf_path.exists():
            raise FileNotFoundError(f"PDF introuvable: {pdf_path}")
        else:
            year, week = week_year_for_pdf(pdf_path)
            planning_dir = str(pdf_path.parent)
            save_settings({"planning_dir": planning_dir})
            payload = {
                "people": list(cached_people_for_pdf(str(pdf_path))),
                "year": year,
                "week": week,
                "planning_dir": planning_dir,
            }
    except Exception as exc:
        payload = {"people": [], "error": str(exc)}
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def render_planning_pdfs_api(query: str) -> bytes:
    params = urllib.parse.parse_qs(query)
    settings = load_settings()
    planning_dir = params.get("planning_dir", [settings["planning_dir"]])[0] or settings["planning_dir"]
    selected = params.get("selected", [""])[0].strip()
    try:
        save_settings({"planning_dir": planning_dir})
        pdfs = list_planning_pdfs(planning_dir)
        if selected and selected.lower() not in {path.lower() for path in pdfs} and Path(selected).exists():
            pdfs.insert(0, selected)
        payload = {
            "pdfs": [{"path": path_text, "label": pdf_label(path_text)} for path_text in pdfs],
            "planning_dir": planning_dir,
        }
    except Exception as exc:
        payload = {"pdfs": [], "error": str(exc), "planning_dir": planning_dir}
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def open_native_dialog(kind: str, initial: str = "") -> str:
    if kind not in {"pdf", "directory", "planning_directory"}:
        return ""

    title = "Choisir le dossier d'export ICS"
    if kind == "pdf":
        title = "Choisir un PDF de planning"
    elif kind == "planning_directory":
        title = "Choisir le dossier des plannings"

    if getattr(sys, "frozen", False):
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            try:
                initialdir = initial if initial and Path(initial).exists() else None
                if kind == "pdf":
                    return filedialog.askopenfilename(
                        title=title,
                        initialdir=initialdir,
                        filetypes=[("PDF", "*.pdf"), ("Tous les fichiers", "*.*")],
                    ) or ""
                return filedialog.askdirectory(
                    title=title,
                    initialdir=initialdir,
                ) or ""
            finally:
                root.destroy()
        except Exception:
            return ""

    script = r"""
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

kind = sys.argv[1]
initial = sys.argv[2] if len(sys.argv) > 2 else ""
title = sys.argv[3] if len(sys.argv) > 3 else "Choisir"
root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)
try:
    if kind == "pdf":
        path = filedialog.askopenfilename(
            title=title,
            initialdir=initial if initial and Path(initial).exists() else None,
            filetypes=[("PDF", "*.pdf"), ("Tous les fichiers", "*.*")]
        )
    else:
        path = filedialog.askdirectory(
            title=title,
            initialdir=initial if initial and Path(initial).exists() else None,
        )
    print(path or "", end="")
finally:
    root.destroy()
"""
    try:
        completed = subprocess.run(
            [sys.executable, "-c", script, kind, initial, title],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except Exception:
        return ""
    return completed.stdout.strip()


def render_choose_api(query: str) -> bytes:
    params = urllib.parse.parse_qs(query)
    kind = params.get("kind", [""])[0]
    settings = load_settings()
    current_pdf = explicit_pdf_from_value(params.get("pdf", [""])[0])
    planning_dir = params.get("planning_dir", [settings["planning_dir"]])[0] or settings["planning_dir"]
    output_dir = params.get("output_dir", [settings["output_dir"]])[0] or settings["output_dir"]

    if kind == "pdf" and current_pdf and current_pdf.exists():
        initial = str(current_pdf.parent)
    elif kind in {"pdf", "planning_directory"}:
        initial = planning_dir
    elif kind == "directory":
        initial = output_dir
    else:
        initial = ""

    path = open_native_dialog(kind, initial)
    payload = {"path": path}
    updates: dict[str, str] = {}
    if path and kind == "pdf":
        updates["planning_dir"] = str(Path(path).parent)
    elif path and kind == "planning_directory":
        updates["planning_dir"] = path
    elif path and kind == "directory":
        updates["output_dir"] = path
    if updates:
        payload.update(save_settings(updates))
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class PlanningHandler(BaseHTTPRequestHandler):
    server_version = "PlanningToICS/1.0"

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self.respond(render_home())
            return
        if parsed.path == "/api/people":
            self.respond(render_people_api(parsed.query), content_type="application/json; charset=utf-8")
            return
        if parsed.path == "/api/planning-pdfs":
            self.respond(render_planning_pdfs_api(parsed.query), content_type="application/json; charset=utf-8")
            return
        if parsed.path == "/api/choose":
            self.respond(render_choose_api(parsed.query), content_type="application/json; charset=utf-8")
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if parsed.path == "/api/settings":
            try:
                data = json.loads(body.decode("utf-8") or "{}")
                updates = {
                    key: str(value)
                    for key, value in data.items()
                    if key in SETTINGS_KEYS and isinstance(value, str) and value.strip()
                }
                payload = save_settings(updates)
            except Exception as exc:
                payload = {"error": str(exc)}
            self.respond(
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                content_type="application/json; charset=utf-8",
            )
            return
        fields = parse_post(body)
        self.respond(run_generation(fields))

    def respond(self, body: bytes, status: int = 200, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lance l'interface locale Planning To ICS.")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    port = find_free_port(args.port)
    server = ThreadingHTTPServer(("127.0.0.1", port), PlanningHandler)
    url = f"http://127.0.0.1:{port}/"

    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    print(f"Interface Planning To ICS: {url}")
    print("Ferme cette fenêtre pour arrêter l'interface.")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
