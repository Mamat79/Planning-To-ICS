from __future__ import annotations

import os
from pathlib import Path

import pytest

import planning_ui


REAL_PDF_ROOT = os.environ.get("PLANNING_TO_ICS_REAL_PDF_DIR", "").strip()


@pytest.mark.skipif(not REAL_PDF_ROOT, reason="PLANNING_TO_ICS_REAL_PDF_DIR non défini")
def test_recent_real_plannings_are_recognized() -> None:
    root = Path(REAL_PDF_ROOT)
    candidates = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix.lower() == ".pdf"
            and ("son_ext" in path.name.lower() or "son ext" in path.name.lower())
        ),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )[:3]
    assert candidates, f"Aucun planning SON EXT trouvé dans {root}"

    for pdf in candidates:
        year, week = planning_ui.week_year_for_pdf(pdf)
        people = planning_ui.cached_people_for_pdf(str(pdf))
        assert year >= 2020
        assert 1 <= week <= 53
        assert people, f"Aucun technicien détecté dans {pdf.name}"
