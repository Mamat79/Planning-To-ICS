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
import time as time_module
import urllib.parse
import urllib.request
import webbrowser
import zipfile
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
    diagnose_events,
    ExtractionResult,
    Request,
    WorkEvent,
    build_ics,
    combined_output_ics_path,
    combined_period_label,
    extract_all_plannings,
    extract_planning,
    format_summary,
    list_people_for_week,
    name_match_score,
    normalize_text,
    output_ics_path,
    week_year_from_pdf,
    week_year_from_path,
    write_combined_ics_file,
    write_ics_file,
    write_log,
)

APP_VERSION = "V1.08"
SETTINGS_KEYS = {"planning_dir", "output_dir"}
APP_WINDOW: Any | None = None


def settings_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Planning To ICS" / "settings.json"
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


def reset_settings() -> dict[str, str]:
    path = settings_path()
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    return default_settings()


def import_settings(data: object) -> dict[str, str]:
    if not isinstance(data, dict):
        raise ValueError("Fichier de réglages invalide.")
    updates = {
        key: value.strip()
        for key, value in data.items()
        if key in SETTINGS_KEYS and isinstance(value, str) and value.strip()
    }
    if not updates:
        raise ValueError("Aucun dossier valide dans le fichier de réglages.")
    return save_settings(updates)


def version_key(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", value)
    return tuple(int(number) for number in numbers) or (0,)


def check_for_update() -> dict[str, object]:
    request = urllib.request.Request(
        "https://api.github.com/repos/Mamat79/Planning-To-ICS/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Planning-To-ICS"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        latest = str(payload.get("tag_name", ""))
        release_url = str(payload.get("html_url", "https://github.com/Mamat79/Planning-To-ICS/releases"))
        return {
            "current": APP_VERSION,
            "latest": latest,
            "release_url": release_url,
            "update_available": version_key(latest) > version_key(APP_VERSION),
            "message": "Ouvre la page des Releases pour télécharger la nouvelle version.",
        }
    except Exception as exc:
        return {"current": APP_VERSION, "latest": "", "update_available": False, "error": str(exc)}


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
def _cached_people_for_pdf(pdf_path_text: str, modified_ns: int, size: int) -> tuple[str, ...]:
    del modified_ns, size
    pdf_path = Path(pdf_path_text)
    year, week = week_year_for_pdf(pdf_path)
    return tuple(list_people_for_week(pdf_path.parent, week=week, year=year, explicit_pdf=pdf_path))


def cached_people_for_pdf(pdf_path_text: str) -> tuple[str, ...]:
    pdf_path = explicit_pdf_from_value(pdf_path_text)
    if not pdf_path:
        return tuple()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF introuvable: {pdf_path}")
    stat = pdf_path.stat()
    return _cached_people_for_pdf(str(pdf_path), stat.st_mtime_ns, stat.st_size)


def week_year_for_pdf(pdf_path: Path) -> tuple[int, int]:
    parsed = week_year_from_pdf(pdf_path)
    if parsed:
        return parsed

    parsed = week_year_from_path(pdf_path)
    if parsed:
        return parsed

    raise ValueError(
        "PDF lisible, mais la semaine et l'année du planning sont introuvables. "
        "Vérifie qu'il s'agit bien d'un Planning des Techniciens."
    )


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
    suffix = f" - S{parsed[1]:02d} {parsed[0]}" if parsed else ""
    return f"{path.name}{suffix}"


def list_planning_pdfs(planning_dir: str) -> list[str]:
    root = Path(planning_dir).expanduser()
    if not root.exists():
        return []
    if root.is_file():
        return [str(root)] if root.suffix.lower() == ".pdf" else []
    pdfs = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() == ".pdf"
    ]
    pdfs.sort(key=lambda path: (path.stat().st_mtime, path.name.lower()), reverse=True)
    return [str(path) for path in pdfs]


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
    multi_pdfs: list[str] | None = None,
    planning_dir: str = "",
    output_dir: str = "",
) -> bytes:
    settings = load_settings()
    manual_pdf_value = html.escape(manual_pdf, quote=True)
    planning_dir_value = html.escape(planning_dir or settings["planning_dir"], quote=True)
    output_dir_value = html.escape(output_dir or settings["output_dir"], quote=True)
    multi_pdf_paths = multi_pdfs or []
    multi_pdfs_value = html.escape("\n".join(multi_pdf_paths), quote=True)
    multi_pdfs_status = (
        f"{len(multi_pdf_paths)} PDF sélectionnés"
        if multi_pdf_paths
        else "Aucun lot de semaines sélectionné"
    )
    pdfs = pdfs if pdfs is not None else list_planning_pdfs(planning_dir or settings["planning_dir"])
    body = f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Planning to ICS</title>
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
      font-style: italic;
      white-space: nowrap;
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      line-height: 1.05;
    }}
    .signature-main {{
      font-size: 13px;
    }}
    .signature-agents {{
      font-size: 10px;
      margin-top: 2px;
    }}
    .header-actions {{
      display: flex;
      align-items: center;
      gap: 14px;
    }}
    .header-actions button {{
      min-height: 30px;
      padding: 5px 9px;
      font-size: 12px;
      font-weight: 500;
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
    select, input[type="text"], input[type="search"], input[type="date"], input[type="time"], textarea {{
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
    select:focus, input[type="text"]:focus, input[type="search"]:focus, input[type="date"]:focus, input[type="time"]:focus, textarea:focus {{
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
    button.ghost {{
      border-color: #b7bdc7;
      background: #fff;
      color: var(--muted);
    }}
    button:hover {{ border-color: var(--accent-strong); background: var(--accent-strong); }}
    button.secondary:hover {{ background: #eef7f5; color: var(--accent-strong); }}
    button.ghost:hover {{ border-color: #8f96a3; background: #f2f4f7; color: var(--text); }}
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
    .pdf-status {{
      min-height: 40px;
      margin: -8px 0 16px;
      padding: 9px 11px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
      overflow-wrap: anywhere;
    }}
    .pdf-status.loading {{ border-color: #b9c8dc; color: #3f5f84; }}
    .pdf-status.compatible {{ border-color: #9bcfbd; color: #174f3f; background: #f1faf7; }}
    .pdf-status.unsupported, .pdf-status.error {{ border-color: #f0b2ad; color: var(--error); background: #fff7f6; }}
    .drop-zone {{
      margin: -4px 0 16px;
      padding: 12px;
      border: 1px dashed #9ca9b7;
      border-radius: 6px;
      background: rgba(255, 255, 255, .7);
      color: var(--muted);
      font-size: 12px;
      text-align: center;
      transition: border-color .15s, background .15s;
    }}
    .drop-zone.active {{
      border-color: var(--accent);
      background: #eef7f5;
      color: var(--accent-strong);
    }}
    .multi-pdf-picker {{
      display: flex;
      align-items: center;
      gap: 9px;
      margin: 0 0 16px;
    }}
    .multi-pdf-picker button {{ min-height: 34px; padding: 6px 9px; }}
    .multi-pdf-picker span {{ color: var(--muted); font-size: 12px; }}
    .multi-toggle {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0;
      color: var(--muted);
      font-size: 12px;
    }}
    .multi-toggle input {{ width: 16px; height: 16px; margin: 0; accent-color: var(--accent); }}
    .multi-panel {{
      margin: 0 0 16px;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: rgba(255, 255, 255, .75);
    }}
    .multi-panel[hidden] {{ display: none; }}
    .multi-search {{ margin-bottom: 8px !important; min-height: 36px !important; }}
    .multi-panel select {{ min-height: 105px; margin-bottom: 8px; }}
    .compact-actions {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    .compact-actions button {{ min-height: 30px; padding: 5px 8px; font-size: 12px; }}
    .selection-toolbar {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      margin: 0 0 14px;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--soft);
    }}
    .selection-toolbar .multi-toggle {{ margin-left: auto; }}
    .technician-editor {{
      margin: 0 0 22px;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--soft);
    }}
    .technician-editor h3 {{ margin: 0 0 12px; font-size: 16px; }}
    .mission-list {{ color: var(--muted); line-height: 1.4; }}
    .status-badge {{
      display: inline-block;
      padding: 2px 6px;
      border-radius: 4px;
      background: #e8f5f1;
      color: #174f3f;
      font-size: 11px;
      font-weight: 600;
    }}
    .settings-tools {{
      display: flex;
      gap: 7px;
      flex-wrap: wrap;
      margin-top: 12px;
    }}
    .settings-tools button {{ min-height: 32px; padding: 5px 8px; font-size: 12px; }}
    .diagnostic-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
      gap: 8px;
      margin: 0 0 16px;
    }}
    .diagnostic-card {{
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--soft);
    }}
    .diagnostic-card strong {{ display: block; font-size: 18px; color: var(--text); }}
    .diagnostic-card span {{ color: var(--muted); font-size: 12px; }}
    .diagnostic-warning {{
      margin: 0 0 16px;
      padding: 10px 12px;
      border: 1px solid #e3c98d;
      border-radius: 6px;
      background: #fff9e8;
      color: #765b16;
      font-size: 13px;
      line-height: 1.4;
    }}
    .toast {{
      position: fixed;
      right: 18px;
      bottom: 18px;
      z-index: 10;
      max-width: 360px;
      padding: 11px 14px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #202124;
      color: #fff;
      box-shadow: 0 8px 24px rgba(0, 0, 0, .16);
      font-size: 13px;
    }}
    .toast[hidden] {{ display: none; }}
    button:disabled {{ opacity: .65; cursor: wait; }}
    .progress-indicator {{
      display: none;
      margin: 12px 0 0;
      color: var(--muted);
      font-size: 12px;
    }}
    body.busy .progress-indicator {{ display: block; }}
    .progress-indicator::before {{
      content: "";
      display: inline-block;
      width: 9px;
      height: 9px;
      margin-right: 7px;
      border: 2px solid var(--line);
      border-top-color: var(--accent);
      border-radius: 50%;
      vertical-align: -1px;
      animation: planning-spin .8s linear infinite;
    }}
    @keyframes planning-spin {{ to {{ transform: rotate(360deg); }} }}
    body.dark {{
      --text: #edf1f5;
      --muted: #b5bec8;
      --line: #47515c;
      --soft: #252b31;
      --accent: #5cc4af;
      --accent-strong: #8be1cc;
      background: #1b2025;
      color: var(--text);
    }}
    body.dark header, body.dark section, body.dark pre, body.dark table,
    body.dark select, body.dark input[type="text"], body.dark input[type="search"], body.dark input[type="date"],
    body.dark input[type="time"], body.dark textarea {{ background: #252b31; color: var(--text); }}
    body.dark header {{ border-color: var(--line); }}
    body.dark form {{ background: #20262b; border-color: var(--line); }}
    body.dark th {{ background: #303840; color: var(--muted); }}
    body.dark .multi-panel, body.dark .diagnostic-card, body.dark .drop-zone,
    body.dark .selection-toolbar, body.dark .technician-editor {{ background: #2b3239; }}
    body.dark button.secondary, body.dark button.ghost {{ background: #252b31; color: var(--accent); }}
    body.dark .import-note {{ background: #203a35; color: #bfe9dd; }}
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
    <h1>Planning to ICS <span class="version">{APP_VERSION}</span></h1>
    <div class="header-actions">
      <button class="ghost" id="theme_toggle" type="button">Mode sombre</button>
      <button class="ghost" id="check_update" type="button">Vérifier la version</button>
      <div class="signature"><span class="signature-main">by Mamat</span><span class="signature-agents">et ses agents</span></div>
    </div>
  </header>
  <main>
    <form id="main_form" method="post">
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
      <div class="pdf-status" id="pdf_info" role="status">Choisis un PDF pour vérifier son contenu.</div>
      <div class="drop-zone" id="drop_zone">Glisse-dépose un PDF ici</div>
      <input id="multi_pdfs" name="multi_pdfs" type="hidden" value="{multi_pdfs_value}">
      <div class="multi-pdf-picker">
        <button class="secondary" id="browse_multi_pdfs" type="button">Choisir plusieurs PDF</button>
        <span id="multi_pdf_info">{multi_pdfs_status}</span>
      </div>

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
        <button class="secondary" type="submit" name="action" value="preview">Prévisualiser et modifier</button>
        <button class="secondary" type="submit" name="action" value="preview_multiweek">Plusieurs semaines</button>
        <button class="secondary" type="submit" name="action" value="choose_multiple">Ajouter des techniciens</button>
        <button class="ghost" type="submit" name="action" value="quit" formnovalidate>Quitter l'application</button>
      </div>
      <div class="progress-indicator" role="status" aria-live="polite">Analyse du PDF en cours...</div>
      <p class="import-note">Après génération, utilise « Ouvrir l'ICS » ou, dans le nouvel Outlook, « Ajouter un calendrier > Charger à partir d'un fichier ». Évite le glisser-déposer, qui peut mal interpréter les accents.</p>
      <div class="settings-tools">
        <button class="ghost" id="export_settings" type="button">Exporter mes réglages</button>
        <button class="ghost" id="import_settings" type="button">Importer mes réglages</button>
        <button class="ghost" id="reset_settings" type="button">Réinitialiser</button>
        <input id="settings_file" type="file" accept="application/json,.json" hidden>
      </div>
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
    const browseMultiPdfsButton = document.getElementById("browse_multi_pdfs");
    const browseOutputButton = document.getElementById("browse_output");
    const mainForm = document.getElementById("main_form");
    const dropZone = document.getElementById("drop_zone");
    const multiPdfsInput = document.getElementById("multi_pdfs");
    const multiPdfInfo = document.getElementById("multi_pdf_info");
    const settingsFile = document.getElementById("settings_file");
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.hidden = true;
    document.body.appendChild(toast);

    function showToast(message) {{
      toast.textContent = message;
      toast.hidden = false;
      window.clearTimeout(showToast.timer);
      showToast.timer = window.setTimeout(() => {{ toast.hidden = true; }}, 4200);
    }}

    let savedTheme = "";
    try {{ savedTheme = localStorage.getItem("planning-to-ics-theme") || ""; }} catch (error) {{}}
    if (savedTheme === "dark") document.body.classList.add("dark");
    document.getElementById("theme_toggle").addEventListener("click", () => {{
      document.body.classList.toggle("dark");
      try {{
        localStorage.setItem("planning-to-ics-theme", document.body.classList.contains("dark") ? "dark" : "light");
      }} catch (error) {{}}
    }});

    document.getElementById("check_update").addEventListener("click", async (event) => {{
      const button = event.currentTarget;
      button.disabled = true;
      button.textContent = "Vérification...";
      try {{
        const response = await fetch("/api/update");
        const data = await response.json();
        if (data.update_available) {{
          showToast(`Nouvelle version disponible : ${{data.latest}}. ${{data.message}}`);
        }} else if (data.latest) {{
          showToast(`Cette version est à jour (${{data.latest}}).`);
        }} else {{
          showToast(data.error || "Impossible de vérifier la version.");
        }}
      }} catch (error) {{
        showToast("Vérification impossible hors connexion.");
      }} finally {{
        button.disabled = false;
        button.textContent = "Vérifier la version";
      }}
    }});

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
      pdfInfo.className = "pdf-status loading";
      pdfInfo.textContent = "Analyse du PDF en cours...";
      if (!pdf) {{
        personSelect.innerHTML = '<option value="">Choisir...</option>';
        pdfInfo.className = "pdf-status";
        pdfInfo.textContent = "Choisis un PDF pour vérifier son contenu.";
        return;
      }}
      try {{
        const params = new URLSearchParams({{ pdf }});
        const response = await fetch(`/api/people?${{params.toString()}}`);
        const data = await response.json();
        personSelect.innerHTML = '<option value="">Choisir...</option>';
        pdfInfo.className = `pdf-status ${{data.status || "error"}}`;
        pdfInfo.textContent = data.message || data.error || "Impossible d'analyser ce PDF.";
        if (data.planning_dir) {{
          planningDirInput.value = data.planning_dir;
        }}
        for (const person of data.people || []) {{
          const option = document.createElement("option");
          option.value = person;
          option.textContent = person;
          personSelect.appendChild(option);
        }}
      }} catch (error) {{
        personSelect.innerHTML = '<option value="">Choisir...</option>';
        pdfInfo.className = "pdf-status error";
        pdfInfo.textContent = "L'analyse du PDF a échoué. Réessaie ou choisis un autre fichier.";
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
      if (kind === "pdfs" && Array.isArray(data.paths) && data.paths.length) {{
        multiPdfsInput.value = data.paths.join("\n");
        multiPdfInfo.textContent = `${{data.paths.length}} PDF sélectionnés`;
        manualPdfInput.value = data.paths[0];
        if (data.planning_dir) planningDirInput.value = data.planning_dir;
        await loadPdfs();
        await loadPeople();
        return;
      }}
      if (data.path) {{
        if (kind === "pdf") {{
          clearMultiPdfs();
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

    function clearMultiPdfs() {{
      multiPdfsInput.value = "";
      multiPdfInfo.textContent = "Aucun lot de semaines sélectionné";
    }}

    pdfSelect.addEventListener("change", async () => {{
      if (pdfSelect.value) {{
        clearMultiPdfs();
        manualPdfInput.value = pdfSelect.value;
        await loadPeople();
      }}
    }});
    manualPdfInput.addEventListener("change", async () => {{
      clearMultiPdfs();
      await loadPeople();
    }});
    planningDirInput.addEventListener("change", async () => {{
      await rememberSettings({{ planning_dir: planningDirInput.value.trim() }});
      clearMultiPdfs();
      manualPdfInput.value = "";
      personSelect.innerHTML = '<option value="">Choisir...</option>';
      pdfInfo.className = "pdf-status";
      pdfInfo.textContent = "Choisis un PDF pour vérifier son contenu.";
      await loadPdfs();
    }});
    outputInput.addEventListener("change", () => rememberSettings({{ output_dir: outputInput.value.trim() }}));
    browsePlanningDirButton.addEventListener("click", () => choose("planning_directory"));
    browsePdfButton.addEventListener("click", () => choose("pdf"));
    browseMultiPdfsButton.addEventListener("click", () => choose("pdfs"));
    browseOutputButton.addEventListener("click", () => choose("directory"));
    const peopleChoices = Array.from(document.querySelectorAll(".person-choice"));
    const sameMissionToggle = document.getElementById("same_mission_toggle");
    const selectAllTable = document.getElementById("select_all_people_table");
    const clearPeopleTable = document.getElementById("clear_people_table");
    const peopleTableSearch = document.getElementById("people_table_search");
    if (sameMissionToggle) {{
      sameMissionToggle.addEventListener("change", () => {{
        peopleChoices.forEach(choice => {{
          if (choice.dataset.common === "true") {{
            choice.checked = sameMissionToggle.checked || choice.dataset.principal === "true";
          }}
        }});
      }});
    }}
    if (selectAllTable) {{
      selectAllTable.addEventListener("click", () => peopleChoices.forEach(choice => choice.checked = true));
    }}
    if (clearPeopleTable) {{
      clearPeopleTable.addEventListener("click", () => peopleChoices.forEach(choice => choice.checked = false));
    }}
    if (peopleTableSearch) {{
      peopleTableSearch.addEventListener("input", () => {{
        const query = peopleTableSearch.value.trim().toLocaleLowerCase();
        document.querySelectorAll(".person-row").forEach(row => {{
          row.hidden = query !== "" && !row.textContent.toLocaleLowerCase().includes(query);
        }});
      }});
    }}

    function droppedPath(dataTransfer) {{
      const file = dataTransfer.files && dataTransfer.files[0];
      if (file && file.path) return file.path;
      const uri = (dataTransfer.getData("text/uri-list") || "").split("\\n").find(value => value && !value.startsWith("#"));
      if (!uri) return "";
      const decoded = decodeURIComponent(uri.trim());
      if (!decoded.startsWith("file://")) return decoded;
      return decoded.slice(7).replace(new RegExp("^/([A-Za-z]:)"), "$1");
    }}
    ["dragenter", "dragover"].forEach(name => dropZone.addEventListener(name, event => {{
      event.preventDefault();
      dropZone.classList.add("active");
    }}));
    ["dragleave", "drop"].forEach(name => dropZone.addEventListener(name, event => {{
      event.preventDefault();
      dropZone.classList.remove("active");
    }}));
    async function uploadDroppedPdf(file) {{
      if (!file || !file.name.toLowerCase().endsWith(".pdf")) {{
        showToast("Dépose un fichier PDF.");
        return;
      }}
      dropZone.textContent = "Import du PDF en cours...";
      try {{
        const params = new URLSearchParams({{
          planning_dir: planningDirInput.value.trim(),
          filename: file.name
        }});
        const response = await fetch(`/api/drop-pdf?${{params.toString()}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/pdf" }},
          body: file
        }});
        const data = await response.json();
        if (!response.ok || data.error) throw new Error(data.error || "Import impossible.");
        clearMultiPdfs();
        manualPdfInput.value = data.path;
        planningDirInput.value = data.planning_dir || planningDirInput.value;
        await loadPdfs();
        await loadPeople();
        showToast(`PDF importé : ${{data.name || file.name}}`);
      }} catch (error) {{
        showToast(error.message || "Le PDF n'a pas pu être importé.");
      }} finally {{
        dropZone.textContent = "Glisse-dépose un PDF ici";
      }}
    }}
    dropZone.addEventListener("drop", async event => {{
      const file = event.dataTransfer.files && event.dataTransfer.files[0];
      if (file) {{
        await uploadDroppedPdf(file);
        return;
      }}
      const path = droppedPath(event.dataTransfer);
      if (!path || !path.toLowerCase().endsWith(".pdf")) {{
        showToast("Dépose un fichier PDF.");
        return;
      }}
      clearMultiPdfs();
      manualPdfInput.value = path;
      await loadPdfs();
      await loadPeople();
    }});

    mainForm.addEventListener("submit", event => {{
      const submitter = event.submitter;
      if (!submitter) return;
      if (["generate", "preview", "preview_multiweek", "choose_multiple"].includes(submitter.value)) {{
        if (mainForm.dataset.submitting === "true") {{
          event.preventDefault();
          return;
        }}
        mainForm.dataset.submitting = "true";
        submitter.textContent = "Analyse en cours...";
        document.body.classList.add("busy");
      }}
    }});

    document.getElementById("export_settings").addEventListener("click", async () => {{
      const response = await fetch("/api/settings");
      const data = await response.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], {{type: "application/json"}});
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "planning-to-ics-settings.json";
      link.click();
      URL.revokeObjectURL(link.href);
    }});
    document.getElementById("import_settings").addEventListener("click", () => settingsFile.click());
    settingsFile.addEventListener("change", async () => {{
      const file = settingsFile.files && settingsFile.files[0];
      if (!file) return;
      try {{
        const imported = JSON.parse(await file.text());
        const response = await fetch("/api/settings", {{
          method: "POST",
          headers: {{"Content-Type": "application/json"}},
          body: JSON.stringify({{action: "import", settings: imported}})
        }});
        const data = await response.json();
        if (data.error) throw new Error(data.error);
        planningDirInput.value = data.planning_dir;
        outputInput.value = data.output_dir;
        await loadPdfs();
        showToast("Réglages importés.");
      }} catch (error) {{
        showToast("Fichier de réglages invalide.");
      }} finally {{ settingsFile.value = ""; }}
    }});
    document.getElementById("reset_settings").addEventListener("click", async () => {{
      if (!window.confirm("Réinitialiser les dossiers mémorisés ?")) return;
      const response = await fetch("/api/settings", {{
        method: "POST",
        headers: {{"Content-Type": "application/json"}},
        body: JSON.stringify({{action: "reset"}})
      }});
      const data = await response.json();
      planningDirInput.value = data.planning_dir;
      outputInput.value = data.output_dir;
      manualPdfInput.value = "";
      await loadPdfs();
      showToast("Réglages réinitialisés.");
    }});
  </script>
</body>
</html>"""
    return body.encode("utf-8")


def render_home() -> bytes:
    settings = load_settings()
    content = """
      <h2>Choisir un planning PDF</h2>
      <p class="empty">Choisis un PDF pour une semaine, ou « Choisir plusieurs PDF » pour réunir plusieurs semaines du même technicien.</p>
      <p class="import-note">Une fois l'ICS généré, ouvre-le avec le bouton de l'application ou utilise « Ajouter un calendrier &gt; Charger à partir d'un fichier » dans le nouvel Outlook. Évite de le glisser dans la grille du calendrier : cette méthode peut abîmer les accents.</p>
    """
    return page_shell(
        content,
        people=[],
        planning_dir=settings["planning_dir"],
        output_dir=settings["output_dir"],
    )


def render_shutdown_page() -> bytes:
    content = """
      <h2>Application arrêtée</h2>
      <p class="empty">Planning to ICS va maintenant fermer cette fenêtre.</p>
      <script>
        window.addEventListener('load', () => {
          setTimeout(() => {
            fetch('/shutdown', {method: 'POST', keepalive: true}).catch(() => {});
          }, 250);
        });
      </script>
    """
    return page_shell(content, people=[])


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


def chosen_multi_pdfs(fields: dict[str, str]) -> list[Path]:
    values = [value.strip() for value in fields.get("multi_pdfs", "").splitlines() if value.strip()]
    paths = [Path(value) for value in dict.fromkeys(values)]
    if len(paths) < 2:
        raise ValueError("Choisis au moins deux PDF pour regrouper plusieurs semaines.")
    for path in paths:
        if path.suffix.lower() != ".pdf" or not path.is_file():
            raise FileNotFoundError(f"PDF introuvable: {path}")
    return paths


def chosen_output_dir(fields: dict[str, str]) -> Path:
    output_text = fields.get("output_dir", "").strip() or load_settings()["output_dir"]
    return Path(output_text)


def hidden_input(name: str, value: str) -> str:
    return f'<input type="hidden" name="{html.escape(name, quote=True)}" value="{html.escape(value, quote=True)}">'


def diagnostics_html(result: ExtractionResult) -> str:
    diagnostics = diagnose_events(result.events)
    warning_details = [
        *diagnostics.duplicate_details,
        *diagnostics.overlap_details,
        *diagnostics.collision_details,
    ]
    warning_html = ""
    if warning_details:
        warning_html = (
            '<div class="diagnostic-warning"><strong>À vérifier :</strong><br>'
            + "<br>".join(html.escape(detail) for detail in warning_details[:8])
            + ("<br>..." if len(warning_details) > 8 else "")
            + "</div>"
        )
    return f"""
      <div class="diagnostic-grid">
        <div class="diagnostic-card"><strong>{diagnostics.event_count}</strong><span>événements</span></div>
        <div class="diagnostic-card"><strong>{sum(bool(day.ignored_reason) for day in result.days)}</strong><span>jours ignorés</span></div>
        <div class="diagnostic-card"><strong>{diagnostics.overnight_count}</strong><span>événement(s) de nuit</span></div>
        <div class="diagnostic-card"><strong>{diagnostics.duplicate_count}</strong><span>doublon(s)</span></div>
        <div class="diagnostic-card"><strong>{diagnostics.overlap_count}</strong><span>chevauchement(s)</span></div>
      </div>
      {warning_html}
    """


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
      {diagnostics_html(result)}
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


def multi_event_editor(
    results: list[ExtractionResult],
    fields: dict[str, str],
    errors: list[str],
    *,
    multiweek: bool = False,
) -> str:
    hidden_fields = [
        hidden_input("manual_pdf", fields.get("manual_pdf", "")),
        hidden_input("planning_dir", fields.get("planning_dir", "")),
        hidden_input("output_dir", fields.get("output_dir", "") or load_settings()["output_dir"]),
        hidden_input("person", fields.get("person", "")),
        hidden_input("multi_result_count", str(len(results))),
    ]
    if multiweek:
        hidden_fields.append(hidden_input("multi_pdfs", fields.get("multi_pdfs", "")))
    editors: list[str] = []
    for result_index, result in enumerate(results):
        prefix = f"tech_{result_index}_"
        hidden_fields.extend(
            [
                hidden_input(f"{prefix}edit_person_name", result.person_name),
                hidden_input(f"{prefix}edit_pdf", str(result.pdf)),
                hidden_input(f"{prefix}edit_week", str(result.week)),
                hidden_input(f"{prefix}edit_year", str(result.year)),
                hidden_input(f"{prefix}event_count", str(len(result.events))),
            ]
        )
        rows: list[str] = []
        for event_index, event in enumerate(result.events):
            event_prefix = f"{prefix}event_{event_index}_"
            rows.append(
                f"""
                <tr>
                  <td class="event-enabled"><input type="checkbox" name="{event_prefix}enabled" checked></td>
                  <td class="event-date">
                    <input type="date" name="{event_prefix}start_date" value="{event.start.date().isoformat()}" required>
                    <input type="date" name="{event_prefix}end_date" value="{event.end.date().isoformat()}" required>
                  </td>
                  <td class="event-time">
                    <input type="time" name="{event_prefix}start_time" value="{event.start.strftime('%H:%M')}" required>
                    <input type="time" name="{event_prefix}end_time" value="{event.end.strftime('%H:%M')}" required>
                  </td>
                  <td class="event-summary"><input type="text" name="{event_prefix}summary"
                      value="{html.escape(event.summary, quote=True)}" required></td>
                  <td class="event-description"><textarea name="{event_prefix}description">{html.escape(event.description)}</textarea></td>
                </tr>
                """
            )
        rows_html = "".join(rows) or '<tr><td colspan="5">Aucun événement extrait.</td></tr>'
        editor_title = html.escape(result.person_name)
        if multiweek:
            editor_title = (
                f"S{result.week:02d} {result.year} - {html.escape(result.pdf.name)}"
            )
        editors.append(
            f"""
            <div class="technician-editor">
              <h3>{editor_title}</h3>
              {diagnostics_html(result)}
              <table>
                <thead><tr><th>Inclure</th><th>Dates début / fin</th><th>Heures début / fin</th><th>Résumé</th><th>Description</th></tr></thead>
                <tbody>{rows_html}</tbody>
              </table>
            </div>
            """
        )
    error_html = ""
    error_label = "Semaines non prévisualisées" if multiweek else "Techniciens non prévisualisés"
    if errors:
        error_html = (
            f'<div class="diagnostic-warning"><strong>{error_label} :</strong><br>'
            + "<br>".join(html.escape(error) for error in errors)
            + "</div>"
        )
    title = (
        f"Prévisualisation de {len(results)} semaine(s)"
        if multiweek
        else f"Prévisualisation de {len(results)} technicien(s)"
    )
    explanation = (
        "Toutes les semaines seront réunies dans un seul ICS. Chaque événement peut être décoché ou modifié."
        if multiweek
        else "Chaque événement peut être décoché ou modifié avant l'export."
    )
    export_action = "export_multiweek_edited" if multiweek else "export_multiple_edited"
    export_label = "Exporter un seul ICS multi-semaines" if multiweek else "Exporter les ICS et le ZIP"
    back_action = "preview_multiweek" if multiweek else "choose_multiple"
    back_label = "Recalculer depuis les PDF" if multiweek else "Modifier la sélection"
    return f"""
      <h2>{title}</h2>
      <p class="empty">{explanation}</p>
      {error_html}
      <form method="post">
        {''.join(hidden_fields)}
        {''.join(editors)}
        <div class="actions">
          <button type="submit" name="action" value="{export_action}">{export_label}</button>
          <button class="secondary" type="submit" name="action" value="{back_action}">{back_label}</button>
        </div>
      </form>
    """


def parse_local_datetime(date_text: str, time_text: str, tz: ZoneInfo) -> datetime:
    return datetime.combine(date.fromisoformat(date_text), time.fromisoformat(time_text), tzinfo=tz)


def edited_result_from_fields(fields: dict[str, str], prefix: str = "") -> ExtractionResult:
    def field(name: str, default: str = "") -> str:
        return fields.get(f"{prefix}{name}", default)

    tz = ZoneInfo(DEFAULT_TIMEZONE)
    count = int(field("event_count", "0"))
    events: list[WorkEvent] = []
    for index in range(count):
        if field(f"event_{index}_enabled") != "on":
            continue
        summary = field(f"event_{index}_summary").strip()
        if not summary:
            raise ValueError(f"Résumé manquant pour l'événement {index + 1}.")
        start = parse_local_datetime(
            field(f"event_{index}_start_date"),
            field(f"event_{index}_start_time"),
            tz,
        )
        end = parse_local_datetime(
            field(f"event_{index}_end_date"),
            field(f"event_{index}_end_time"),
            tz,
        )
        if end <= start:
            raise ValueError(f"L'événement {index + 1} finit avant son début.")
        description = field(f"event_{index}_description").strip()
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
    pdf = Path(field("edit_pdf") or fields.get("manual_pdf") or "")
    edit_week = field("edit_week").strip()
    edit_year = field("edit_year").strip()
    if edit_week and edit_year:
        parsed_week = int(edit_week)
        parsed_year = int(edit_year)
    elif pdf and pdf.is_file():
        parsed_year, parsed_week = week_year_for_pdf(pdf)
    else:
        parsed_year = first_date.isocalendar().year
        parsed_week = first_date.isocalendar().week
    return ExtractionResult(
        pdf=pdf,
        person_name=field("edit_person_name") or fields.get("person") or "Planning",
        matched_score=1.0,
        week=parsed_week,
        year=parsed_year,
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


def edited_multiple_results_from_fields(fields: dict[str, str]) -> list[ExtractionResult]:
    count = int(fields.get("multi_result_count", "0"))
    if count <= 0:
        raise ValueError("Aucune prévisualisation multiple à exporter.")
    return [edited_result_from_fields(fields, prefix=f"tech_{index}_") for index in range(count)]


def export_result(result: ExtractionResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ics_path = output_ics_path(output_dir, result)
    write_ics_file(ics_path, result)
    write_log(output_dir, result, ics_path)
    return ics_path


MISSION_SUFFIX_RE = re.compile(r"\s+\((?:\d+/\d+|-\d+h(?:\d{2})?)\)$")


def mission_title(summary: str) -> str:
    title = summary.strip()
    while True:
        cleaned = MISSION_SUFFIX_RE.sub("", title).strip()
        if cleaned == title:
            return title
        title = cleaned


def mission_keys(result: ExtractionResult) -> set[str]:
    return {normalize_text(mission_title(event.summary)) for event in result.events if event.summary.strip()}


def mission_titles(result: ExtractionResult) -> list[str]:
    titles: dict[str, str] = {}
    for event in result.events:
        title = mission_title(event.summary)
        key = normalize_text(title)
        if key and key not in titles:
            titles[key] = title
    return list(titles.values())


def same_person_name(first: str, second: str) -> bool:
    return name_match_score(first, second) >= 0.95


def people_sharing_missions(results: list[ExtractionResult], principal_name: str) -> set[str]:
    principal = next(
        (result for result in results if same_person_name(result.person_name, principal_name)),
        None,
    )
    if principal is None:
        return set()
    principal_missions = mission_keys(principal)
    return {
        result.person_name
        for result in results
        if mission_keys(result) & principal_missions
    }


def extract_results_for_people(
    pdf: Path, people: list[str], week: int, year: int
) -> tuple[list[ExtractionResult], list[str]]:
    results: list[ExtractionResult] = []
    errors: list[str] = []
    available_results = extract_all_plannings(pdf, week, year)
    for person in people:
        matches = sorted(
            (
                (name_match_score(person, result.person_name), result)
                for result in available_results
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        if not matches or matches[0][0] < 0.72:
            errors.append(f"{person} : aucune ligne correspondante trouvée.")
            continue
        results.append(matches[0][1])
    return results, errors


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
                errors.append(f"{pdf.name} : la semaine S{week:02d} {year} est déjà sélectionnée.")
                continue
            result = extract_planning(
                Request(person=person, week=week, year=year),
                source_dir=pdf.parent,
                explicit_pdf=pdf,
                assume_yes=True,
            )
            seen_periods.add(period)
            results.append(result)
        except Exception as exc:
            errors.append(f"{pdf.name} : {exc}")
    results.sort(key=lambda result: (result.year, result.week))
    return results, errors


def people_selection_table(
    results: list[ExtractionResult], principal_name: str, fields: dict[str, str], errors: list[str]
) -> str:
    common_people = {normalize_text(name) for name in people_sharing_missions(results, principal_name)}
    hidden_fields = [
        hidden_input("manual_pdf", fields.get("manual_pdf", "")),
        hidden_input("planning_dir", fields.get("planning_dir", "")),
        hidden_input("output_dir", fields.get("output_dir", "") or load_settings()["output_dir"]),
        hidden_input("person", principal_name),
    ]
    rows: list[str] = []
    for index, result in enumerate(results):
        person_key = normalize_text(result.person_name)
        is_principal = same_person_name(result.person_name, principal_name)
        is_common = person_key in common_people
        checked = " checked" if is_principal else ""
        principal_attr = "true" if is_principal else "false"
        common_attr = "true" if is_common else "false"
        common_label = '<span class="status-badge">Principal</span>' if is_principal else ("Oui" if is_common else "Non")
        titles = mission_titles(result)
        missions = " ; ".join(titles[:5]) or "Aucune mission exportable"
        if len(titles) > 5:
            missions += " ; ..."
        rows.append(
            f"""
            <tr class="person-row">
              <td class="event-enabled"><input class="person-choice" type="checkbox"
                  name="person_select_{index}" value="{html.escape(result.person_name, quote=True)}"
                  data-common="{common_attr}" data-principal="{principal_attr}"{checked}></td>
              <td><strong>{html.escape(result.person_name)}</strong></td>
              <td>{len(result.events)}</td>
              <td class="mission-list">{html.escape(missions)}</td>
              <td>{common_label}</td>
            </tr>
            """
        )
    error_html = ""
    if errors:
        error_html = (
            '<div class="diagnostic-warning"><strong>Techniciens non analysés :</strong><br>'
            + "<br>".join(html.escape(error) for error in errors)
            + "</div>"
        )
    return f"""
      <h2>Sélectionner les techniciens</h2>
      <p class="empty">Le technicien principal est déjà coché. Choisis les autres personnes à inclure.</p>
      {error_html}
      <form method="post">
        {''.join(hidden_fields)}
        <div class="selection-toolbar">
          <input class="multi-search" id="people_table_search" type="search" placeholder="Rechercher un technicien..." aria-label="Rechercher un technicien">
          <button class="ghost" id="select_all_people_table" type="button">Tout sélectionner</button>
          <button class="ghost" id="clear_people_table" type="button">Tout désélectionner</button>
          <label class="multi-toggle"><input id="same_mission_toggle" type="checkbox">
            Cocher les techniciens ayant les mêmes missions que {html.escape(principal_name)}</label>
        </div>
        <table>
          <thead><tr><th>Inclure</th><th>Technicien</th><th>Événements</th><th>Missions</th><th>Mission commune</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
        <div class="actions">
          <button type="submit" name="action" value="export_multiple">Exporter directement</button>
          <button class="secondary" type="submit" name="action" value="preview_multiple">Prévisualiser et modifier</button>
        </div>
      </form>
    """


def selected_people_from_fields(fields: dict[str, str]) -> list[str]:
    checked = [
        value.strip()
        for key, value in sorted(fields.items())
        if key.startswith("person_select_") and value.strip()
    ]
    if checked:
        return list(dict.fromkeys(checked))
    raw = fields.get("people_multi_csv", "")
    people = [line.strip() for line in raw.splitlines() if line.strip()]
    return list(dict.fromkeys(people))


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


def export_combined_results(results: list[ExtractionResult], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = combined_output_ics_path(output_dir, results)
    write_combined_ics_file(path, results)
    for result in results:
        write_log(output_dir, result, path)
    return path


def open_export_target(ics_path: Path, show_folder: bool) -> Path:
    if not ics_path.is_file() or ics_path.suffix.lower() != ".ics":
        raise FileNotFoundError(f"Fichier ICS introuvable: {ics_path}")
    target = ics_path.parent if show_folder else ics_path
    if os.name == "nt":
        os.startfile(str(target))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])
    return target


def export_actions_html(ics_path: Path, fields: dict[str, str]) -> str:
    hidden = [
        hidden_input("export_path", str(ics_path)),
        hidden_input("manual_pdf", fields.get("manual_pdf", "")),
        hidden_input("planning_dir", fields.get("planning_dir", "")),
        hidden_input("person", fields.get("person", "")),
        hidden_input("output_dir", fields.get("output_dir", "")),
        hidden_input("multi_pdfs", fields.get("multi_pdfs", "")),
    ]
    return f"""
      <form method="post">
        {''.join(hidden)}
        <div class="actions">
          <button type="submit" name="action" value="open_ics">Ouvrir dans Outlook / agenda</button>
          <button class="secondary" type="submit" name="action" value="open_folder">Afficher dans le dossier</button>
        </div>
      </form>
    """


def run_generation(fields: dict[str, str]) -> bytes:
    selected_person = fields.get("person", "")
    manual_pdf = fields.get("manual_pdf", "")
    settings = load_settings()
    planning_dir_text = fields.get("planning_dir", "") or settings["planning_dir"]
    output_dir_text = fields.get("output_dir", "") or settings["output_dir"]
    action = fields.get("action") or "generate"
    try:
        if action in {"open_ics", "open_folder"}:
            ics_path = Path(fields.get("export_path", ""))
            target = open_export_target(ics_path, show_folder=action == "open_folder")
            people: list[str] = []
            explicit_pdf = explicit_pdf_from_value(manual_pdf)
            if explicit_pdf and explicit_pdf.exists():
                people = list(cached_people_for_pdf(str(explicit_pdf)))
            label = "Dossier ouvert" if action == "open_folder" else "Fichier ICS ouvert"
            content = f"""
              <p class="ok">{label} : <code>{html.escape(str(target))}</code></p>
              <p class="import-note">Dans Outlook, vérifie le calendrier de destination puis confirme l'ajout. Cette méthode préserve les accents, contrairement au glisser-déposer dans la grille du nouvel Outlook.</p>
            """
            return page_shell(
                content,
                people=people,
                selected_person=selected_person,
                manual_pdf=manual_pdf,
                planning_dir=planning_dir_text,
                output_dir=output_dir_text,
            )

        explicit_pdf = chosen_pdf(fields)
        year, week = week_year_for_pdf(explicit_pdf)
        planning_dir_text = str(explicit_pdf.parent)
        save_settings({"planning_dir": planning_dir_text, "output_dir": output_dir_text})
        people = list(cached_people_for_pdf(str(explicit_pdf)))
        if action == "preview_multiweek":
            if not selected_person:
                raise ValueError("Choisis le technicien à rechercher dans toutes les semaines.")
            pdf_paths = chosen_multi_pdfs(fields)
            weekly_results, extraction_errors = extract_results_for_pdfs(pdf_paths, selected_person)
            if not weekly_results:
                raise ValueError("Aucune semaine n'a pu être analysée pour ce technicien.")
            content = multi_event_editor(
                weekly_results,
                fields,
                extraction_errors,
                multiweek=True,
            )
            return page_shell(
                content,
                people=people,
                selected_person=selected_person,
                manual_pdf=manual_pdf,
                multi_pdfs=[str(path) for path in pdf_paths],
                planning_dir=planning_dir_text,
                output_dir=output_dir_text,
            )

        if action == "choose_multiple":
            if not selected_person:
                raise ValueError("Choisis d'abord le technicien principal.")
            all_results, extraction_errors = extract_results_for_people(explicit_pdf, people, week, year)
            if not any(same_person_name(result.person_name, selected_person) for result in all_results):
                raise ValueError("Le technicien principal n'a pas pu être analysé.")
            content = people_selection_table(all_results, selected_person, fields, extraction_errors)
            return page_shell(
                content,
                people=people,
                selected_person=selected_person,
                manual_pdf=manual_pdf,
                multi_pdfs=[
                    value.strip()
                    for value in fields.get("multi_pdfs", "").splitlines()
                    if value.strip()
                ],
                planning_dir=planning_dir_text,
                output_dir=output_dir_text,
            )

        if action in {"export_multiple", "preview_multiple"}:
            selected_people = selected_people_from_fields(fields)
            if not selected_people:
                raise ValueError("Sélectionne au moins un technicien.")
            multiple_results, extraction_errors = extract_results_for_people(
                explicit_pdf, selected_people, week, year
            )
            if not multiple_results:
                raise ValueError("Aucun technicien n'a pu être analysé.")
            if action == "preview_multiple":
                content = multi_event_editor(multiple_results, fields, extraction_errors)
                return page_shell(
                    content,
                    people=people,
                    selected_person=selected_person,
                    manual_pdf=manual_pdf,
                    planning_dir=planning_dir_text,
                    output_dir=output_dir_text,
                )
            output_dir = chosen_output_dir(fields)
            paths, zip_path = export_multiple_results(multiple_results, output_dir, week, year)
            path_items = "".join(f"<li><code>{html.escape(str(path))}</code></li>" for path in paths)
            error_block = ""
            if extraction_errors:
                error_block = (
                    '<div class="diagnostic-warning"><strong>Techniciens non exportés :</strong><br>'
                    + "<br>".join(html.escape(error) for error in extraction_errors)
                    + "</div>"
                )
            content = f"""
              <p class="ok">{len(paths)} fichier(s) ICS généré(s) et regroupé(s) dans : <code>{html.escape(str(zip_path))}</code></p>
              {error_block}
              <h2>Fichiers créés</h2>
              <ul>{path_items}</ul>
              <p class="import-note">Tu peux ouvrir le ZIP, puis importer chaque fichier ICS dans l'agenda voulu.</p>
            """
            save_settings({"planning_dir": planning_dir_text, "output_dir": str(output_dir)})
            return page_shell(
                content,
                people=people,
                selected_person=selected_person,
                manual_pdf=manual_pdf,
                planning_dir=planning_dir_text,
                output_dir=str(output_dir),
            )

        if action == "export_multiple_edited":
            multiple_results = edited_multiple_results_from_fields(fields)
            output_dir = chosen_output_dir(fields)
            paths, zip_path = export_multiple_results(multiple_results, output_dir, week, year)
            path_items = "".join(f"<li><code>{html.escape(str(path))}</code></li>" for path in paths)
            content = f"""
              <p class="ok">{len(paths)} fichier(s) ICS modifié(s) généré(s) dans : <code>{html.escape(str(zip_path))}</code></p>
              <h2>Fichiers créés</h2>
              <ul>{path_items}</ul>
              <p class="import-note">Ouvre le ZIP puis importe chaque fichier ICS dans l'agenda voulu.</p>
            """
            save_settings({"planning_dir": planning_dir_text, "output_dir": str(output_dir)})
            return page_shell(
                content,
                people=people,
                selected_person=selected_person,
                manual_pdf=manual_pdf,
                planning_dir=planning_dir_text,
                output_dir=str(output_dir),
            )

        if action == "export_multiweek_edited":
            weekly_results = edited_multiple_results_from_fields(fields)
            output_dir = chosen_output_dir(fields)
            ics_path = export_combined_results(weekly_results, output_dir)
            period = combined_period_label(weekly_results)
            save_settings({"planning_dir": planning_dir_text, "output_dir": str(output_dir)})
            content = f"""
              <p class="ok">ICS multi-semaines généré : <code>{html.escape(str(ics_path))}</code></p>
              <p class="empty">{len(weekly_results)} semaine(s) réunie(s), période {html.escape(period)}.</p>
              <p class="import-note">Utilise le bouton ci-dessous ou, dans le nouvel Outlook, « Ajouter un calendrier &gt; Charger à partir d'un fichier ». Ne glisse pas le fichier dans la grille du calendrier.</p>
              {export_actions_html(ics_path, fields)}
            """
            return page_shell(
                content,
                people=people,
                selected_person=selected_person,
                manual_pdf=manual_pdf,
                multi_pdfs=[
                    value.strip()
                    for value in fields.get("multi_pdfs", "").splitlines()
                    if value.strip()
                ],
                planning_dir=planning_dir_text,
                output_dir=str(output_dir),
            )

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
              <p class="import-note">Utilise « Ouvrir dans Outlook / agenda » ou, dans le nouvel Outlook, « Ajouter un calendrier &gt; Charger à partir d'un fichier ». Évite le glisser-déposer, qui peut mal interpréter les accents.</p>
              {export_actions_html(ics_path, fields)}
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
          <p class="import-note">Utilise « Ouvrir dans Outlook / agenda » ou, dans le nouvel Outlook, « Ajouter un calendrier &gt; Charger à partir d'un fichier ». Évite le glisser-déposer, qui peut mal interpréter les accents.</p>
          {export_actions_html(ics_path, fields)}
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
            multi_pdfs=[
                value.strip()
                for value in fields.get("multi_pdfs", "").splitlines()
                if value.strip()
            ],
            planning_dir=planning_dir_text,
            output_dir=output_dir_text,
        )


def render_people_api(query: str) -> bytes:
    params = urllib.parse.parse_qs(query)
    pdf = params.get("pdf", [""])[0]
    try:
        pdf_path = explicit_pdf_from_value(pdf)
        if not pdf_path:
            payload = {
                "people": [],
                "status": "idle",
                "message": "Choisis un PDF pour vérifier son contenu.",
            }
        elif not pdf_path.exists():
            raise FileNotFoundError(f"PDF introuvable: {pdf_path}")
        else:
            year, week = week_year_for_pdf(pdf_path)
            planning_dir = str(pdf_path.parent)
            save_settings({"planning_dir": planning_dir})
            people = list(cached_people_for_pdf(str(pdf_path)))
            if people:
                status = "compatible"
                message = (
                    f"Planning compatible - S{week:02d} {year} - "
                    f"{len(people)} technicien{'s' if len(people) > 1 else ''} trouvé{'s' if len(people) > 1 else ''}."
                )
            else:
                status = "unsupported"
                message = (
                    f"PDF lisible et semaine S{week:02d} {year} reconnue, "
                    "mais aucun technicien n'a été trouvé. Ce format de planning n'est pas pris en charge."
                )
            payload = {
                "people": people,
                "year": year,
                "week": week,
                "planning_dir": planning_dir,
                "status": status,
                "message": message,
            }
    except Exception as exc:
        message = str(exc)
        status = "unsupported" if "PDF lisible" in message or "scanné" in message else "error"
        payload = {"people": [], "status": status, "message": message, "error": message}
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


def open_native_dialog(kind: str, initial: str = "") -> str | list[str]:
    if kind not in {"pdf", "pdfs", "directory", "planning_directory"}:
        return ""

    title = "Choisir le dossier d'export ICS"
    if kind == "pdf":
        title = "Choisir un PDF de planning"
    elif kind == "pdfs":
        title = "Choisir plusieurs PDF de planning"
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
                if kind == "pdfs":
                    return list(
                        filedialog.askopenfilenames(
                            title=title,
                            initialdir=initialdir,
                            filetypes=[("PDF", "*.pdf"), ("Tous les fichiers", "*.*")],
                        )
                    )
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
import json
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
        print(path or "", end="")
    elif kind == "pdfs":
        paths = filedialog.askopenfilenames(
            title=title,
            initialdir=initial if initial and Path(initial).exists() else None,
            filetypes=[("PDF", "*.pdf"), ("Tous les fichiers", "*.*")]
        )
        print(json.dumps(list(paths), ensure_ascii=False), end="")
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
    output = completed.stdout.strip()
    if kind == "pdfs":
        try:
            parsed = json.loads(output or "[]")
        except json.JSONDecodeError:
            return []
        return [str(path) for path in parsed if isinstance(path, str) and path]
    return output


def render_choose_api(query: str) -> bytes:
    params = urllib.parse.parse_qs(query)
    kind = params.get("kind", [""])[0]
    settings = load_settings()
    current_pdf = explicit_pdf_from_value(params.get("pdf", [""])[0])
    planning_dir = params.get("planning_dir", [settings["planning_dir"]])[0] or settings["planning_dir"]
    output_dir = params.get("output_dir", [settings["output_dir"]])[0] or settings["output_dir"]

    if kind in {"pdf", "pdfs"} and current_pdf and current_pdf.exists():
        initial = str(current_pdf.parent)
    elif kind in {"pdf", "pdfs", "planning_directory"}:
        initial = planning_dir
    elif kind == "directory":
        initial = output_dir
    else:
        initial = ""

    selection = open_native_dialog(kind, initial)
    if kind == "pdfs":
        paths = selection if isinstance(selection, list) else []
        payload = {"paths": paths}
        path = paths[0] if paths else ""
    else:
        path = selection if isinstance(selection, str) else ""
        payload = {"path": path}
    updates: dict[str, str] = {}
    if path and kind in {"pdf", "pdfs"}:
        updates["planning_dir"] = str(Path(path).parent)
    elif path and kind == "planning_directory":
        updates["planning_dir"] = path
    elif path and kind == "directory":
        updates["output_dir"] = path
    if updates:
        payload.update(save_settings(updates))
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


MAX_DROPPED_PDF_BYTES = 100 * 1024 * 1024


def save_dropped_pdf(filename: str, data: bytes, destination_dir: str) -> Path:
    """Copy a browser-provided PDF into the selected planning folder."""
    if not data:
        raise ValueError("Le fichier PDF est vide.")
    if len(data) > MAX_DROPPED_PDF_BYTES:
        raise ValueError("Le PDF dépasse la taille maximale autorisée de 100 Mo.")

    source_name = Path(urllib.parse.unquote(filename)).name
    source_path = Path(source_name)
    if source_path.suffix.lower() != ".pdf":
        raise ValueError("Seuls les fichiers PDF peuvent être déposés ici.")
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", source_path.stem).strip(" .") or "planning"
    target_dir = Path(destination_dir).expanduser() if destination_dir.strip() else Path.cwd()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{stem}.pdf"
    if target.exists():
        if target.read_bytes() == data:
            return target
        counter = 2
        while True:
            candidate = target_dir / f"{stem}_importe_{counter}.pdf"
            if not candidate.exists():
                target = candidate
                break
            counter += 1
    target.write_bytes(data)
    return target


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
        if parsed.path == "/api/settings":
            self.respond(
                json.dumps(load_settings(), ensure_ascii=False).encode("utf-8"),
                content_type="application/json; charset=utf-8",
            )
            return
        if parsed.path == "/api/update":
            self.respond(
                json.dumps(check_for_update(), ensure_ascii=False).encode("utf-8"),
                content_type="application/json; charset=utf-8",
            )
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        if parsed.path == "/api/drop-pdf":
            if length > MAX_DROPPED_PDF_BYTES:
                self.rfile.read(length)
                payload = {"error": "Le PDF dépasse la taille maximale autorisée de 100 Mo."}
                self.respond(
                    json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    status=413,
                    content_type="application/json; charset=utf-8",
                )
                return
            body = self.rfile.read(length)
            try:
                params = urllib.parse.parse_qs(parsed.query)
                destination_dir = params.get("planning_dir", [load_settings()["planning_dir"]])[0]
                filename = params.get("filename", ["planning.pdf"])[0]
                path = save_dropped_pdf(filename, body, destination_dir)
                payload = {"path": str(path), "name": path.name, "planning_dir": str(path.parent)}
                status = 200
            except Exception as exc:
                payload = {"error": str(exc)}
                status = 400
            self.respond(
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                status=status,
                content_type="application/json; charset=utf-8",
            )
            return
        body = self.rfile.read(length)
        if parsed.path == "/api/settings":
            try:
                data = json.loads(body.decode("utf-8") or "{}")
                action = data.get("action") if isinstance(data, dict) else None
                if action == "reset":
                    payload = reset_settings()
                elif action == "import":
                    payload = import_settings(data.get("settings"))
                else:
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
        if parsed.path == "/shutdown":
            self._shutdown_after_response = True
            self.respond(b"OK", content_type="text/plain; charset=utf-8")
            return
        fields = parse_post(body)
        if fields.get("action") == "quit":
            self.respond(render_shutdown_page())
            return
        self.respond(run_generation(fields))

    def respond(self, body: bytes, status: int = 200, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
        self.close_connection = True

    def finish(self) -> None:
        try:
            super().finish()
        finally:
            if getattr(self, "_shutdown_after_response", False):
                server = self.server

                def stop_application() -> None:
                    time_module.sleep(0.15)
                    server.shutdown()
                    if APP_WINDOW is not None:
                        try:
                            APP_WINDOW.destroy()
                        except Exception:
                            pass

                threading.Thread(target=stop_application, daemon=True).start()

    def log_message(self, format: str, *args: Any) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lance l'interface locale Planning to ICS.")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--browser", action="store_true", help="Ouvre l'interface dans le navigateur.")
    parser.add_argument("--no-browser", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def preferred_webview_gui() -> str | None:
    if sys.platform == "win32":
        return "edgechromium"
    if sys.platform == "darwin":
        return "cocoa"
    return None


def main() -> int:
    global APP_WINDOW
    args = parse_args()
    port = find_free_port(args.port)
    server = ThreadingHTTPServer(("127.0.0.1", port), PlanningHandler)
    url = f"http://127.0.0.1:{port}/"

    print(f"Interface Planning to ICS: {url}")
    if args.no_browser:
        try:
            server.serve_forever()
        finally:
            server.server_close()
        return 0

    if args.browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        try:
            server.serve_forever()
        finally:
            server.server_close()
        return 0

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        try:
            import webview

            APP_WINDOW = webview.create_window(
                "Planning to ICS",
                url,
                width=1280,
                height=820,
                min_size=(860, 620),
                background_color="#ffffff",
            )
            gui = preferred_webview_gui()
            if gui:
                webview.start(gui=gui, debug=False)
            else:
                webview.start(debug=False)
        except Exception:
            APP_WINDOW = None
            webbrowser.open(url)
            server_thread.join()
    finally:
        server.shutdown()
        server_thread.join(timeout=5)
        server.server_close()
        APP_WINDOW = None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
