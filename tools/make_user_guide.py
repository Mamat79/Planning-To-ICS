"""Generate the short French user guide distributed with Planning to ICS."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


TEAL = colors.HexColor("#0F766E")
TEAL_DARK = colors.HexColor("#115E59")
INK = colors.HexColor("#17202A")
MUTED = colors.HexColor("#52606D")
LINE = colors.HexColor("#D7DEE5")
SOFT = colors.HexColor("#F3F6F8")
PALE_TEAL = colors.HexColor("#E8F5F1")
WHITE = colors.white
GUIDE_VERSION = "V2.0"


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "GuideTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=26,
            leading=31,
            textColor=INK,
            alignment=TA_CENTER,
            spaceAfter=5 * mm,
        ),
        "subtitle": ParagraphStyle(
            "GuideSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=17,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=8 * mm,
        ),
        "h1": ParagraphStyle(
            "GuideH1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=19,
            leading=23,
            textColor=INK,
            spaceBefore=2 * mm,
            spaceAfter=5 * mm,
        ),
        "h2": ParagraphStyle(
            "GuideH2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=TEAL_DARK,
            spaceBefore=3 * mm,
            spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "GuideBody",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=15,
            textColor=INK,
            spaceAfter=2.5 * mm,
        ),
        "small": ParagraphStyle(
            "GuideSmall",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=MUTED,
        ),
        "step_number": ParagraphStyle(
            "StepNumber",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=WHITE,
            alignment=TA_CENTER,
        ),
        "step": ParagraphStyle(
            "StepText",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=14.5,
            textColor=INK,
        ),
        "button": ParagraphStyle(
            "ButtonText",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            textColor=TEAL_DARK,
            alignment=TA_CENTER,
        ),
    }


def step_table(number: int, text: str, guide_styles: dict[str, ParagraphStyle]) -> Table:
    table = Table(
        [
            [
                Paragraph(str(number), guide_styles["step_number"]),
                Paragraph(text, guide_styles["step"]),
            ]
        ],
        colWidths=[10 * mm, 158 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), TEAL),
                ("BACKGROUND", (1, 0), (1, 0), SOFT),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("LEFTPADDING", (0, 0), (0, 0), 2 * mm),
                ("RIGHTPADDING", (0, 0), (0, 0), 2 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
                ("LEFTPADDING", (1, 0), (1, 0), 4 * mm),
                ("RIGHTPADDING", (1, 0), (1, 0), 4 * mm),
            ]
        )
    )
    return table


def callout(text: str, guide_styles: dict[str, ParagraphStyle]) -> Table:
    box = Table([[Paragraph(text, guide_styles["body"])]], colWidths=[168 * mm])
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE_TEAL),
                ("BOX", (0, 0), (-1, -1), 0.8, TEAL),
                ("LEFTPADDING", (0, 0), (-1, -1), 5 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 4 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
            ]
        )
    )
    return box


def action_row(labels: list[str], guide_styles: dict[str, ParagraphStyle]) -> Table:
    cells = [Paragraph(label, guide_styles["button"]) for label in labels]
    widths = [168 * mm / len(cells)] * len(cells)
    table = Table([cells], colWidths=widths)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), WHITE),
                ("BOX", (0, 0), (-1, -1), 0.8, TEAL),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
            ]
        )
    )
    return table


def draw_page(canvas, document) -> None:
    canvas.saveState()
    width, _height = A4
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(20 * mm, 15 * mm, width - 20 * mm, 15 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(20 * mm, 9.5 * mm, f"Planning to ICS {GUIDE_VERSION}")
    canvas.drawCentredString(width / 2, 9.5 * mm, "By Mamat")
    canvas.setFont("Helvetica", 6.5)
    canvas.drawCentredString(width / 2, 6.5 * mm, "et ses agents")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(width - 20 * mm, 9.5 * mm, f"Page {document.page}")
    canvas.restoreState()


def build_guide(output: Path, version: str = "V2.0") -> Path:
    global GUIDE_VERSION
    GUIDE_VERSION = version
    output.parent.mkdir(parents=True, exist_ok=True)
    guide_styles = styles()
    document = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=21 * mm,
        leftMargin=21 * mm,
        topMargin=18 * mm,
        bottomMargin=21 * mm,
        title=f"Notice Planning to ICS {version}",
        author="Mamat et ses agents",
        subject="Générer puis importer un planning ICS",
    )

    story = [
        Spacer(1, 15 * mm),
        Paragraph("Planning to ICS", guide_styles["title"]),
        Paragraph(f"Notice rapide - {version}", guide_styles["subtitle"]),
        callout(
            "<b>But :</b> choisir un planning PDF, vérifier les vacations d'un ou plusieurs "
            "techniciens, générer les fichiers ICS, puis les importer dans l'agenda voulu.",
            guide_styles,
        ),
        Spacer(1, 8 * mm),
        Paragraph("1. Préparer l'export", guide_styles["h1"]),
        step_table(
            1,
            "Choisir le <b>Dossier des plannings</b>. Tous les PDF du dossier et de ses "
            "sous-dossiers apparaissent dans la liste.",
            guide_styles,
        ),
        Spacer(1, 3 * mm),
        step_table(
            2,
            "Sélectionner le <b>PDF de planning</b>. Il est aussi possible d'utiliser "
            "<b>Parcourir</b> ou de déposer directement un PDF dans la zone prévue.",
            guide_styles,
        ),
        Spacer(1, 3 * mm),
        step_table(
            3,
            "Choisir le <b>Technicien</b> principal, puis le dossier <b>Exporter vers</b>. "
            "Ces dossiers sont mémorisés pour le prochain lancement.",
            guide_styles,
        ),
        Spacer(1, 7 * mm),
        Paragraph("Contrôle utile", guide_styles["h2"]),
        Paragraph(
            "Vérifier que la semaine et l'année affichées correspondent au PDF choisi. "
            "La génération utilise toujours le fichier sélectionné, pas un ancien planning.",
            guide_styles["body"],
        ),
        PageBreak(),
        Paragraph("2. Choisir le parcours", guide_styles["h1"]),
        Paragraph("Un seul technicien", guide_styles["h2"]),
        action_row(["Générer ICS", "Prévisualiser et modifier"], guide_styles),
        Spacer(1, 3 * mm),
        Paragraph(
            "<b>Générer ICS</b> crée directement le fichier. <b>Prévisualiser et modifier</b> "
            "ouvre le tableau des événements : chaque ligne peut être décochée et son titre, "
            "sa date, ses heures ou sa description peuvent être corrigés avant l'export.",
            guide_styles["body"],
        ),
        Spacer(1, 4 * mm),
        Paragraph("Plusieurs semaines", guide_styles["h2"]),
        Paragraph(
            "Choisir le technicien principal puis cliquer sur <b>Plusieurs semaines</b>. "
            "Cocher les plannings hebdomadaires dans la fenêtre de sélection. "
            "Chaque semaine peut être corrigée avant la création d'un seul fichier ICS.",
            guide_styles["body"],
        ),
        Spacer(1, 4 * mm),
        Paragraph("Plusieurs techniciens", guide_styles["h2"]),
        step_table(
            1,
            "Choisir d'abord le technicien principal puis cliquer sur "
            "<b>Ajouter des techniciens</b>.",
            guide_styles,
        ),
        Spacer(1, 3 * mm),
        step_table(
            2,
            "Dans le tableau, cocher les personnes à inclure. La recherche, "
            "<b>Tout sélectionner</b> et <b>Tout désélectionner</b> facilitent le choix.",
            guide_styles,
        ),
        Spacer(1, 3 * mm),
        step_table(
            3,
            "L'option <b>Cocher les techniciens ayant les mêmes missions</b> sélectionne "
            "automatiquement les personnes partageant au moins une mission avec le technicien principal.",
            guide_styles,
        ),
        Spacer(1, 3 * mm),
        step_table(
            4,
            "Choisir <b>Exporter directement</b> ou <b>Prévisualiser et modifier</b>. "
            "La prévisualisation affiche un tableau modifiable séparé pour chaque technicien.",
            guide_styles,
        ),
        Spacer(1, 5 * mm),
        callout(
            "L'export multiple crée <b>un fichier ICS par technicien</b> et un <b>fichier ZIP</b> "
            "qui les regroupe. Les modifications d'un technicien n'affectent pas les autres.",
            guide_styles,
        ),
        PageBreak(),
        Paragraph("3. Importer dans Outlook", guide_styles["h1"]),
        Paragraph("Nouvel Outlook et Outlook sur le web", guide_styles["h2"]),
        step_table(
            1,
            "Ouvrir <b>Calendrier</b>, puis <b>Ajouter un calendrier</b>.",
            guide_styles,
        ),
        Spacer(1, 3 * mm),
        step_table(
            2,
            "Choisir <b>Charger à partir d'un fichier</b>, cliquer sur <b>Parcourir</b>, "
            "sélectionner le fichier <b>.ics</b>, puis cliquer sur <b>Ouvrir</b>.",
            guide_styles,
        ),
        Spacer(1, 3 * mm),
        step_table(
            3,
            "Choisir le calendrier de destination, puis cliquer sur <b>Importer</b>.",
            guide_styles,
        ),
        Spacer(1, 5 * mm),
        Paragraph("Outlook classique pour Windows", guide_styles["h2"]),
        step_table(
            1,
            "Ouvrir <b>Fichier &gt; Ouvrir et exporter &gt; Importer/Exporter</b>.",
            guide_styles,
        ),
        Spacer(1, 3 * mm),
        step_table(
            2,
            "Choisir <b>Importer un fichier iCalendar (.ics) ou vCalendar (.vcs)</b>, "
            "puis cliquer sur <b>Suivant</b>.",
            guide_styles,
        ),
        Spacer(1, 3 * mm),
        step_table(
            3,
            "Sélectionner le fichier ICS, cliquer sur <b>OK</b>, puis confirmer "
            "<b>Ouvrir en tant que nouveau</b> ou l'import proposé.",
            guide_styles,
        ),
        Spacer(1, 5 * mm),
        Paragraph("Ouverture directe", guide_styles["h2"]),
        Paragraph(
            "Après l'export, le bouton <b>Ouvrir l'ICS</b> ouvre le "
            "fichier avec l'application de calendrier définie par défaut. Un double-clic sur "
            "le fichier ICS utilise la même méthode.",
            guide_styles["body"],
        ),
        Spacer(1, 6 * mm),
        callout(
            "<b>Important :</b> ne pas glisser le fichier ICS directement dans la grille du nouvel "
            "Outlook : cette méthode peut mal afficher les accents. Utiliser le bouton d'ouverture "
            "ou <b>Ajouter un calendrier &gt; Charger à partir d'un fichier</b>. "
            "Un import ICS est une copie des événements à cet instant. "
            "Si le planning change, générer un nouvel ICS et vérifier le résultat avant de l'importer.",
            guide_styles,
        ),
        Spacer(1, 7 * mm),
        Paragraph("En cas de doute", guide_styles["h2"]),
        Paragraph(
            "Utiliser la prévisualisation avant l'export. Contrôler particulièrement les vacations "
            "de nuit, les pauses, les chevauchements et les alertes affichées par l'application.",
            guide_styles["body"],
        ),
        Paragraph(
            "Aide Microsoft - nouvel Outlook : <link href='https://support.microsoft.com/fr-fr/outlook/"
            "import-or-subscribe-to-a-calendar-in-outlook-com-or-outlook-on-the-web' "
            "color='#0F766E'>charger un fichier ICS</link>. "
            "Outlook classique : <link href='https://support.microsoft.com/fr-fr/office/"
            "importer-des-calendriers-dans-outlook-8e8364e1-400e-4c0f-a573-fe76b5a2d379' "
            "color='#0F766E'>importer un calendrier</link>.",
            guide_styles["small"],
        ),
    ]

    document.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=Path("output/pdf/Planning_to_ICS_V2.0_Notice.pdf"),
    )
    parser.add_argument(
        "--version",
        default="",
        help="Version affichée dans la notice (déduite du nom de fichier si omise).",
    )
    args = parser.parse_args()
    inferred = re.search(r"_V([^_]+)_Notice", args.output.name, re.IGNORECASE)
    version = args.version.strip() or (f"V{inferred.group(1)}" if inferred else "V2.0")
    print(build_guide(args.output, version=version).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
