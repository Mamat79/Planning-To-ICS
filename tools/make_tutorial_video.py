"""Create the silent French tutorial video for the Planning To ICS release."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1920, 1080
NAVY = "#102a43"
BLUE = "#0f5aa6"
TEAL = "#146c5f"
PALE = "#ffffff"
INK = "#202124"
MUTED = "#62676f"
GREEN = "#f1faf7"
LINE = "#d9dde3"
SOFT = "#f6f7f9"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = Path(r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf")
    return ImageFont.truetype(path, size)


def text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int, fill=INK, bold=False, anchor=None) -> None:
    draw.text(xy, value, font=font(size, bold), fill=fill, anchor=anchor)


def panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill="white", outline=LINE, radius=12) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)


def button(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str, fill=TEAL, light=False) -> None:
    draw.rounded_rectangle(box, radius=6, fill=fill, outline=(TEAL if light else fill), width=1)
    text(draw, ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2), label, 18, fill=(TEAL if light else "white"), bold=True, anchor="mm")


def checkbox(draw: ImageDraw.ImageDraw, center: tuple[int, int], checked: bool) -> None:
    x, y = center
    draw.rounded_rectangle(
        (x - 9, y - 9, x + 9, y + 9),
        radius=3,
        fill=TEAL if checked else "white",
        outline=TEAL,
        width=2,
    )
    if checked:
        draw.line((x - 5, y, x - 1, y + 4), fill="white", width=2)
        draw.line((x - 1, y + 4, x + 6, y - 5), fill="white", width=2)


def base_slide(title: str, step: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), PALE)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 92), fill="#fbfbfc")
    draw.line((0, 91, WIDTH, 91), fill=LINE, width=2)
    text(draw, (48, 44), "Planning To ICS", 31, NAVY, True, "lm")
    text(draw, (300, 44), "V1.08", 16, TEAL, False, "lm")
    text(draw, (WIDTH - 48, 37), "by Mamat", 17, MUTED, False, "rm")
    text(draw, (WIDTH - 48, 60), "et ses agents", 11, MUTED, False, "rm")
    text(draw, (WIDTH - 48, 77), step, 14, MUTED, False, "rm")
    draw.rectangle((0, 92, 430, 930), fill=SOFT)
    draw.line((429, 92, 429, 930), fill=LINE, width=2)
    if title:
        text(draw, (470, 126), title, 27, NAVY, True)
    return image, draw


def subtitle(draw: ImageDraw.ImageDraw, value: str) -> None:
    draw.rounded_rectangle((470, 850, 1855, 920), radius=8, fill="#17354d", outline="#7892a5", width=1)
    draw.rectangle((490, 865, 496, 905), fill="#65c6b4")
    draw.multiline_text((518, 858), value, font=font(19), fill="white", spacing=3)


def field(draw: ImageDraw.ImageDraw, y: int, label: str, value: str, button_label: str | None = None) -> None:
    text(draw, (24, y), label, 16, MUTED)
    panel(draw, (24, y + 20, 305 if button_label else 405, y + 62), fill="white", radius=6)
    text(draw, (40, y + 41), value, 16, INK, False, "lm")
    if button_label:
        button(draw, (314, y + 20, 405, y + 62), button_label, "white", light=True)


def draw_app_shell(draw: ImageDraw.ImageDraw, pdf: str = "planning-exemple-semaine.pdf", person: str = "Technicien 1", selected: bool = True) -> None:
    field(draw, 128, "Dossier des plannings", r"D:\Plannings", "Parcourir")
    text(draw, (24, 238), "PDF trouvés dans ce dossier", 16, MUTED)
    panel(draw, (24, 258, 405, 302), fill="white", radius=6)
    text(draw, (40, 280), pdf, 16, INK, False, "lm")
    text(draw, (40, 294), "Semaine 30 - 2026", 13, MUTED, False, "lm")
    field(draw, 330, "PDF de planning", "D:\\Plannings\\" + pdf, "Parcourir")
    text(draw, (24, 440), "Technicien", 16, MUTED)
    panel(draw, (24, 460, 405, 502), fill="white", radius=6)
    text(draw, (40, 481), person, 16, INK, False, "lm")
    text(draw, (385, 481), "⌄", 18, MUTED, False, "mm")
    field(draw, 530, "Exporter vers", r"D:\Exports", "Parcourir")
    button(draw, (24, 635, 145, 680), "Générer ICS", TEAL)
    button(draw, (155, 635, 405, 680), "Prévisualiser et modifier", "white", light=True)
    button(draw, (24, 692, 274, 737), "Ajouter des techniciens", "white", light=True)
    text(draw, (24, 790), "Le dernier dossier choisi est mémorisé.", 14, MUTED)


def draw_summary(draw: ImageDraw.ImageDraw, status: str = "ICS généré : D:\\Exports\\Planning_Technicien_S30_2026.ics", title: str = "Résumé") -> None:
    panel(draw, (470, 158, 1880, 208), fill="white", outline="#9bcfbd", radius=6)
    text(draw, (495, 183), status, 16, "#174f3f", False, "lm")
    text(draw, (470, 255), title, 25, NAVY, True)
    panel(draw, (470, 282, 1880, 845), fill="white", outline=LINE, radius=6)
    rows = [
        "Lun 20/07 : 09:00-18:00 Mission exemple (-1h)",
        "Mar 21/07 : 09:00-17:00 Préparation Paris",
        "Mer 22/07 : 21:00-01:00 Projet nuit",
        "Jeu 23/07 : 08:00-12:00 Mission exemple",
        "",
        "Alertes :",
        "- pause de 01:00 détectée et conservée dans le titre",
    ]
    draw.multiline_text((495, 320), "\n".join(rows), font=font(17), fill=INK, spacing=8)


def slide_cover() -> Image.Image:
    image, draw = base_slide("Générer un planning Outlook en quelques clics", "Tutoriel V1.08")
    draw_app_shell(draw)
    draw_summary(draw, "Prêt à traiter : planning-exemple-semaine.pdf")
    panel(draw, (735, 355, 1600, 690), fill="#f1faf7", outline="#9bcfbd", radius=6)
    text(draw, (790, 420), "PDF  →  ICS  →  Outlook", 54, NAVY, True)
    text(draw, (790, 525), "Du PDF à l’agenda Outlook, étape par étape.", 25, MUTED)
    button(draw, (790, 590, 1010, 642), "Démarrer", TEAL)
    subtitle(draw, "Choisis un PDF, sélectionne le technicien, puis génère l’ICS.\nOuvre ensuite le fichier pour l’ajouter dans Outlook.")
    return image


def slide_open() -> Image.Image:
    image, draw = base_slide("Ouvrir l’application", "1 / 7")
    draw_app_shell(draw)
    draw_summary(draw, "Dossier mémorisé : D:\\Plannings", "Résumé")
    panel(draw, (730, 360, 1635, 590), fill="#f1faf7", outline="#9bcfbd", radius=6)
    text(draw, (780, 420), "Dossier des plannings", 25, INK, True)
    text(draw, (780, 472), "Le dernier emplacement choisi est retrouvé au prochain lancement.", 21, MUTED)
    subtitle(draw, "Lance Planning to ICS depuis le menu Démarrer ou le raccourci.\nLe dernier dossier utilisé est retrouvé automatiquement.")
    return image


def slide_pdf() -> Image.Image:
    image, draw = base_slide("Choisir le PDF à traiter", "2 / 7")
    draw_app_shell(draw, "planning-exemple-semaine.pdf")
    panel(draw, (470, 158, 1880, 845), fill="white", outline=LINE, radius=6)
    text(draw, (500, 205), "PDF trouvés dans ce dossier", 25, NAVY, True)
    text(draw, (500, 245), r"D:\Plannings", 16, MUTED)
    rows = ["planning-exemple-semaine.pdf", "planning-semaine-31.pdf", "planning-semaine-32.pdf"]
    for index, value in enumerate(rows):
        y = 300 + index * 76
        panel(draw, (500, y, 1835, y + 54), fill=("#f1faf7" if index == 0 else "white"), outline=(TEAL if index == 0 else LINE), radius=6)
        text(draw, (530, y + 27), value, 17, INK, index == 0, "lm")
        text(draw, (1780, y + 27), "Sélectionné" if index == 0 else "", 15, TEAL, False, "rm")
    button(draw, (500, 565, 635, 610), "Parcourir", "white", light=True)
    subtitle(draw, "Sélectionne le PDF voulu dans la liste.\nLe fichier est demandé à chaque nouvelle génération.")
    return image


def slide_person() -> Image.Image:
    image, draw = base_slide("Sélectionner le technicien principal", "3 / 7")
    draw_app_shell(draw, person="Technicien 1")
    panel(draw, (470, 158, 1880, 845), fill="white", outline=LINE, radius=6)
    text(draw, (500, 205), "Techniciens détectés dans le PDF", 25, NAVY, True)
    panel(draw, (500, 245, 1835, 297), fill=SOFT, radius=6)
    text(draw, (530, 271), "Rechercher un nom…", 17, MUTED, False, "lm")
    for index, value in enumerate(["Technicien 1", "Technicien 2", "Technicien 3"]):
        y = 330 + index * 76
        panel(draw, (500, y, 1835, y + 54), fill=("#f1faf7" if index == 0 else "white"), outline=(TEAL if index == 0 else LINE), radius=6)
        text(draw, (530, y + 27), value, 17, INK, index == 0, "lm")
        text(draw, (1780, y + 27), "✓" if index == 0 else "", 22, TEAL, True, "rm")
    subtitle(draw, "Choisis le technicien principal. Tu peux l’exporter seul\nou utiliser Ajouter des techniciens pour compléter la sélection.")
    return image


def slide_multiple() -> Image.Image:
    image, draw = base_slide("Ajouter des techniciens", "4 / 7")
    draw_app_shell(draw, person="Technicien 1")
    panel(draw, (470, 158, 1880, 845), fill="white", outline=LINE, radius=6)
    text(draw, (500, 205), "Sélectionner les techniciens", 25, NAVY, True)
    panel(draw, (500, 240, 1835, 292), fill=SOFT, radius=6)
    text(draw, (525, 266), "Rechercher un technicien...", 16, MUTED, False, "lm")
    checkbox(draw, (1030, 266), True)
    text(draw, (1052, 266), "Cocher les techniciens ayant les mêmes missions", 16, TEAL, True, "lm")
    headers = [(520, "Inclure"), (665, "Technicien"), (980, "Événements"), (1190, "Missions"), (1670, "Mission commune")]
    for x, value in headers:
        text(draw, (x, 335), value, 14, MUTED, True)
    rows = [
        (True, "Technicien 1", "4", "Mission A ; Mission B", "Principal"),
        (True, "Technicien 2", "3", "Mission A", "Oui"),
        (True, "Technicien 3", "2", "Mission B", "Oui"),
        (False, "Technicien 4", "1", "Mission C", "Non"),
    ]
    for index, row in enumerate(rows):
        y = 390 + index * 72
        draw.line((500, y - 25, 1835, y - 25), fill=LINE, width=2)
        checkbox(draw, (540, y), row[0])
        for x, value in zip((665, 1010, 1190, 1705), row[1:]):
            text(draw, (x, y), value, 16, INK, x == 665, "lm")
    button(draw, (500, 705, 720, 752), "Exporter directement", TEAL)
    button(draw, (735, 705, 1005, 752), "Prévisualiser et modifier", "white", light=True)
    subtitle(draw, "Coche les personnes voulues ou sélectionne automatiquement\ncelles qui partagent une mission avec le technicien principal.")
    return image


def slide_preview() -> Image.Image:
    image, draw = base_slide("Prévisualiser et corriger", "5 / 7")
    draw_app_shell(draw)
    panel(draw, (470, 158, 1880, 845), fill="white", outline=LINE, radius=6)
    text(draw, (500, 205), "Prévisualisation des événements", 25, NAVY, True)
    headers = [(500, "Jour"), (685, "Début"), (815, "Fin"), (970, "Titre"), (1450, "Description")]
    for x, value in headers:
        text(draw, (x, 255), value, 15, MUTED, True)
    rows = [
        ("Lun 20/07", "09:00", "18:00", "Mission exemple (-1h)", "Pause affichée dans le titre"),
        ("Mar 21/07", "09:00", "17:00", "Préparation Paris", "Mission et lieu"),
        ("Mer 22/07", "21:00", "01:00", "Projet nuit", "Fin le lendemain"),
    ]
    for index, row in enumerate(rows):
        y = 310 + index * 95
        draw.line((490, y - 22, 1840, y - 22), fill=LINE, width=2)
        for x, value in zip((500, 685, 815, 970, 1450), row):
            text(draw, (x, y), value, 16, INK, x == 970, "lm")
    button(draw, (500, 665, 635, 710), "Modifier", "white", light=True)
    button(draw, (645, 665, 780, 710), "Générer ICS", TEAL)
    subtitle(draw, "Vérifie les événements, puis modifie si nécessaire le titre,\nles horaires ou la description avant de générer.")
    return image


def slide_export() -> Image.Image:
    image, draw = base_slide("Générer le fichier ICS", "6 / 7")
    draw_app_shell(draw)
    draw_summary(draw, "ICS généré : D:\\Exports\\Planning_Technicien_S30_2026.ics")
    panel(draw, (720, 365, 1605, 620), fill=GREEN, outline="#9bcfbd", radius=6)
    text(draw, (770, 430), "Le fichier est prêt à être importé", 27, NAVY, True)
    text(draw, (770, 495), "Planning_Technicien_S30_2026.ics", 21, "#174f3f", True)
    text(draw, (770, 550), "Ouvre-le pour l’ajouter à ton agenda.", 20, MUTED)
    subtitle(draw, "Clique sur Générer ICS. Le fichier est écrit en UTF-8\net peut ensuite être ouvert dans Outlook.")
    return image


def slide_outlook() -> Image.Image:
    image, draw = base_slide("Importer dans Outlook", "7 / 7")
    draw.rectangle((430, 92, WIDTH, 155), fill="#062551")
    text(draw, (470, 123), "Outlook", 25, "white", True, "lm")
    text(draw, (700, 123), "Calendrier", 17, "#d8e3ef", False, "lm")
    panel(draw, (470, 190, 1880, 845), fill="white", outline=LINE, radius=6)
    panel(draw, (500, 225, 1835, 280), fill=SOFT, radius=5)
    text(draw, (530, 252), "Planning_Technicien_S30_2026.ics", 17, INK, True, "lm")
    button(draw, (500, 315, 735, 362), "Ajouter au calendrier", "#123b76")
    panel(draw, (500, 405, 1250, 760), fill="white", outline=LINE, radius=6)
    text(draw, (545, 455), "Calendrier", 15, MUTED)
    text(draw, (545, 500), "Prévisionnel", 23, NAVY, True)
    draw.line((545, 535, 1200, 535), fill=LINE, width=2)
    text(draw, (545, 585), "Mission exemple (-1h)", 22, INK, True)
    text(draw, (545, 635), "Lun 20 juillet 2026 09:00 - 18:00", 17, MUTED)
    text(draw, (545, 690), "Source : planning-exemple-semaine.pdf", 16, MUTED)
    panel(draw, (1300, 405, 1835, 760), fill=SOFT, outline=LINE, radius=6)
    text(draw, (1340, 455), "Aperçu de l’événement", 18, NAVY, True)
    text(draw, (1340, 510), "Vérifie le calendrier proposé", 16, MUTED)
    text(draw, (1340, 545), "puis confirme l’import.", 16, MUTED)
    subtitle(draw, "Ouvre le fichier .ics, vérifie le calendrier proposé,\npuis clique sur Ajouter au calendrier.")
    return image


def slide_done() -> Image.Image:
    image, draw = base_slide("C’est terminé", "Fin")
    draw_app_shell(draw)
    draw_summary(draw, "Import terminé dans Outlook", "Résumé")
    panel(draw, (720, 365, 1605, 620), fill=GREEN, outline="#9bcfbd", radius=6)
    text(draw, (1160, 430), "✓", 72, TEAL, True, "mm")
    text(draw, (1160, 520), "Ton planning est dans Outlook", 30, NAVY, True, "mm")
    text(draw, (1160, 570), "Tu peux maintenant le consulter et le modifier.", 19, MUTED, False, "mm")
    subtitle(draw, "Conseil : conserve le PDF source et le fichier ICS généré\npour pouvoir refaire un export si le planning change.")
    return image


def build_frames(folder: Path) -> list[Path]:
    slides = [
        slide_cover(),
        slide_open(),
        slide_pdf(),
        slide_person(),
        slide_multiple(),
        slide_preview(),
        slide_export(),
        slide_outlook(),
        slide_done(),
    ]
    paths: list[Path] = []
    for index, image in enumerate(slides, start=1):
        path = folder / f"frame_{index:02d}.png"
        image.save(path, format="PNG", optimize=True)
        paths.append(path)
    return paths


def create_video(output: Path, ffmpeg: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="planning_to_ics_tutorial_") as temp:
        folder = Path(temp)
        frames = build_frames(folder)
        concat = folder / "slides.txt"
        lines: list[str] = []
        for frame in frames:
            lines.append(f"file '{frame.as_posix()}'")
            lines.append("duration 4")
        lines.append(f"file '{frames[-1].as_posix()}'")
        concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
        command = [
            ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)
        ]
        subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    args = parser.parse_args()
    create_video(args.output, args.ffmpeg)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
