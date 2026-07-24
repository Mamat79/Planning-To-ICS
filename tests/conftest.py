from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle


def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text.replace("\n", "<br/>"), style)


FRENCH_MONTHS = {
    1: "Janv.",
    2: "Févr.",
    3: "Mars",
    4: "Avr.",
    5: "Mai",
    6: "Juin",
    7: "Juil.",
    8: "Août",
    9: "Sept.",
    10: "Oct.",
    11: "Nov.",
    12: "Déc.",
}
FRENCH_DAYS = ("Lun.", "Mar.", "Mer.", "Jeu.", "Ven.", "Sam.", "Dim.")


def build_planning_pdf(
    path: Path,
    second_person: str = "MARTIN\nBOB",
    *,
    year: int = 2026,
    week: int = 30,
) -> None:
    style = ParagraphStyle("cell", fontName="Helvetica", fontSize=7, leading=8)
    header_style = ParagraphStyle("header", parent=style, fontName="Helvetica-Bold")
    monday = date.fromisocalendar(year, week, 1)
    days = []
    for offset, day_name in enumerate(FRENCH_DAYS):
        current = monday + timedelta(days=offset)
        days.append(f"{day_name} {current.day} {FRENCH_MONTHS[current.month]}")
    data = [
        [paragraph(f"{year}\nSemaine {week}", header_style)]
        + [paragraph(day, header_style) for day in days]
        + [paragraph("Total", header_style)],
        [
            paragraph("DUPONT\nALICE", header_style),
            paragraph("Alice Dupont - Hôtel Étoilé\n9h00\n01:00 08:00\n18h00", style),
            paragraph("RH", style),
            paragraph("RH", style),
            paragraph("RH", style),
            paragraph("RH", style),
            paragraph("RH", style),
            paragraph("RH", style),
            paragraph("08:00", style),
        ],
        [
            paragraph(second_person, header_style),
            paragraph("RH", style),
            paragraph("Mission test\n14h00\n00:00 04:00\n18h00", style),
            paragraph("RH", style),
            paragraph("RH", style),
            paragraph("RH", style),
            paragraph("RH", style),
            paragraph("RH", style),
            paragraph("04:00", style),
        ],
    ]
    table = Table(data, colWidths=[90] + [105] * 7 + [45], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.7, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dce6f1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    document = SimpleDocTemplate(str(path), pagesize=landscape(A3), title="Planning des Techniciens")
    document.build(
        [
            Paragraph("Planning des Techniciens", ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=18)),
            table,
        ]
    )


@pytest.fixture
def planning_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "document-sans-date-dans-le-nom.pdf"
    build_planning_pdf(path)
    return path
