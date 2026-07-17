"""Create the silent French tutorial video for the Planning To ICS release."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1920, 1080
NAVY = "#082b52"
BLUE = "#0f5aa6"
TEAL = "#0b766b"
PALE = "#f4f7fa"
INK = "#1c2d3f"
MUTED = "#607286"
GREEN = "#dff4e7"
LINE = "#d4dee8"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = Path(r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf")
    return ImageFont.truetype(path, size)


def text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int, fill=INK, bold=False, anchor=None) -> None:
    draw.text(xy, value, font=font(size, bold), fill=fill, anchor=anchor)


def panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill="white", outline=LINE, radius=12) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)


def button(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str, fill=TEAL, light=False) -> None:
    draw.rounded_rectangle(box, radius=8, fill=fill, outline=fill)
    text(draw, ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2), label, 24, fill=(TEAL if light else "white"), bold=True, anchor="mm")


def base_slide(title: str, step: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), PALE)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 92), fill=NAVY)
    text(draw, (70, 44), "Planning to ICS", 34, "white", True, "lm")
    text(draw, (WIDTH - 70, 44), step, 25, "#c9d8e8", False, "rm")
    text(draw, (80, 150), title, 46, NAVY, True)
    return image, draw


def subtitle(draw: ImageDraw.ImageDraw, value: str) -> None:
    draw.rectangle((0, 930, WIDTH, HEIGHT), fill=NAVY)
    draw.rectangle((80, 962, 92, 1020), fill="#60c7b5")
    draw.multiline_text((125, 955), value, font=font(28), fill="white", spacing=5)


def draw_app_shell(draw: ImageDraw.ImageDraw) -> None:
    panel(draw, (80, 225, 500, 875), fill="#f8fafc")
    text(draw, (120, 270), "Planning To ICS", 28, NAVY, True)
    text(draw, (120, 325), "Dossier des plannings", 20, MUTED)
    panel(draw, (120, 350, 460, 408), fill="white")
    text(draw, (145, 379), "D:\\Plannings", 22, INK, False, "lm")
    button(draw, (120, 445, 280, 500), "Parcourir", BLUE)
    text(draw, (120, 560), "PDF de planning", 20, MUTED)
    panel(draw, (120, 585, 460, 645), fill="white")
    text(draw, (145, 615), "planning-exemple-semaine.pdf", 19, INK, False, "lm")
    text(draw, (120, 710), "Technicien", 20, MUTED)
    panel(draw, (120, 735, 460, 795), fill="white")
    text(draw, (145, 765), "Choisir dans le PDF", 19, INK, False, "lm")


def slide_cover() -> Image.Image:
    image, draw = base_slide("Générer un planning Outlook en quelques clics", "Tutoriel V1.07")
    panel(draw, (220, 265, 1700, 790), fill="white", outline="#cbd8e5", radius=18)
    draw.rectangle((220, 265, 1700, 350), fill="#e8f3f1")
    text(draw, (300, 420), "PDF  →  ICS  →  Outlook", 70, NAVY, True)
    text(draw, (300, 540), "Une vidéo courte, sans audio, avec sous-titres.", 32, MUTED)
    button(draw, (300, 635, 650, 705), "Planning to ICS", TEAL)
    subtitle(draw, "Dans cette vidéo : choisir le PDF, sélectionner le technicien,\nprévisualiser, générer l’ICS et l’importer dans Outlook.")
    return image


def slide_open() -> Image.Image:
    image, draw = base_slide("Ouvrir l’application", "1 / 6")
    draw_app_shell(draw)
    panel(draw, (590, 225, 1800, 875), fill="white")
    text(draw, (660, 285), "Planning to ICS", 34, NAVY, True)
    text(draw, (660, 350), "L’interface se souvient des derniers dossiers utilisés.", 27, MUTED)
    panel(draw, (660, 430, 1640, 570), fill="#eef7f5", outline="#b7ddd5")
    text(draw, (730, 475), "1", 42, TEAL, True)
    text(draw, (810, 478), "Dossier des plannings", 28, INK, True)
    text(draw, (810, 525), "Le dossier choisi reste mémorisé au prochain lancement.", 22, MUTED)
    subtitle(draw, "Lance Planning to ICS depuis le menu Démarrer ou le raccourci.\nLe dernier dossier utilisé est retrouvé automatiquement.")
    return image


def slide_pdf() -> Image.Image:
    image, draw = base_slide("Choisir le PDF à traiter", "2 / 6")
    draw_app_shell(draw)
    panel(draw, (590, 225, 1800, 875), fill="white")
    text(draw, (660, 285), "PDF trouvés dans ce dossier", 30, NAVY, True)
    rows = ["planning-exemple-semaine.pdf", "planning-semaine-31.pdf", "planning-semaine-32.pdf"]
    for index, value in enumerate(rows):
        y = 360 + index * 90
        panel(draw, (660, y, 1660, y + 62), fill=("#e2f4f0" if index == 0 else "white"), outline=(TEAL if index == 0 else LINE))
        text(draw, (700, y + 31), value, 23, INK, index == 0, "lm")
        text(draw, (1580, y + 31), "Sélectionné" if index == 0 else "", 18, TEAL, False, "rm")
    button(draw, (660, 690, 900, 750), "Parcourir", BLUE)
    subtitle(draw, "Sélectionne le PDF voulu dans la liste.\nLe fichier est demandé à chaque nouvelle génération.")
    return image


def slide_person() -> Image.Image:
    image, draw = base_slide("Sélectionner le technicien", "3 / 6")
    draw_app_shell(draw)
    panel(draw, (590, 225, 1800, 875), fill="white")
    text(draw, (660, 285), "Techniciens détectés dans le PDF", 30, NAVY, True)
    panel(draw, (660, 350, 1660, 415), fill="#f8fafc")
    text(draw, (700, 382), "Rechercher un nom…", 22, MUTED, False, "lm")
    for index, value in enumerate(["Technicien 1", "Technicien 2", "Technicien 3"]):
        y = 465 + index * 86
        panel(draw, (660, y, 1660, y + 58), fill=("#e2f4f0" if index == 0 else "white"), outline=(TEAL if index == 0 else LINE))
        text(draw, (705, y + 29), value, 23, INK, index == 0, "lm")
        text(draw, (1580, y + 29), "✓" if index == 0 else "", 28, TEAL, True, "rm")
    subtitle(draw, "Choisis le technicien à exporter.\nLes dates sont lues dans le PDF sélectionné.")
    return image


def slide_preview() -> Image.Image:
    image, draw = base_slide("Prévisualiser et corriger", "4 / 6")
    panel(draw, (100, 230, 1810, 875), fill="white")
    text(draw, (155, 285), "Prévisualisation des événements", 30, NAVY, True)
    headers = [(155, "Jour"), (330, "Début"), (555, "Fin"), (770, "Titre"), (1480, "Description")]
    for x, value in headers:
        text(draw, (x, 350), value, 20, MUTED, True)
    rows = [
        ("Lun 20/07", "09:00", "18:00", "Mission exemple (-1h)", "Pause affichée dans le titre"),
        ("Mar 21/07", "09:00", "17:00", "Préparation Paris", "Mission et lieu"),
        ("Mer 22/07", "21:00", "01:00", "Projet nuit", "Fin le lendemain"),
    ]
    for index, row in enumerate(rows):
        y = 405 + index * 105
        draw.line((145, y - 20, 1740, y - 20), fill=LINE, width=2)
        for x, value in zip((155, 330, 555, 770, 1480), row):
            text(draw, (x, y), value, 20, INK, x == 770, "lm")
    button(draw, (150, 750, 430, 815), "Générer ICS", TEAL)
    button(draw, (460, 750, 650, 815), "Modifier", BLUE)
    subtitle(draw, "Vérifie les événements, puis modifie si nécessaire le titre,\nles horaires ou la description avant de générer.")
    return image


def slide_export() -> Image.Image:
    image, draw = base_slide("Générer le fichier ICS", "5 / 6")
    panel(draw, (180, 255, 1740, 790), fill="white")
    text(draw, (270, 330), "Dossier d’export", 24, MUTED)
    panel(draw, (270, 370, 1320, 430), fill="#f8fafc")
    text(draw, (310, 400), "D:\\Exports", 25, INK, False, "lm")
    button(draw, (1380, 370, 1600, 430), "Parcourir", BLUE)
    button(draw, (270, 525, 620, 600), "Générer ICS", TEAL)
    panel(draw, (270, 650, 1600, 735), fill=GREEN, outline="#a9d7b8")
    text(draw, (315, 693), "ICS généré : Planning_Technicien_S30_2026.ics", 23, "#1d6540", True, "lm")
    subtitle(draw, "Clique sur Générer ICS. Le fichier est écrit en UTF-8\net peut ensuite être ouvert dans Outlook.")
    return image


def slide_outlook() -> Image.Image:
    image, draw = base_slide("Importer dans Outlook", "6 / 6")
    panel(draw, (130, 230, 1790, 865), fill="white")
    draw.rectangle((130, 230, 1790, 320), fill=NAVY)
    text(draw, (190, 275), "Outlook", 31, "white", True, "lm")
    panel(draw, (210, 365, 1690, 490), fill="#f4f7fb")
    text(draw, (270, 425), "Planning_Technicien_S30_2026.ics", 27, INK, True, "lm")
    button(draw, (270, 555, 650, 625), "Ajouter au calendrier", BLUE)
    panel(draw, (810, 535, 1580, 735), fill="#eef7f5", outline="#b7ddd5")
    text(draw, (870, 585), "Calendrier sélectionné", 22, MUTED)
    text(draw, (870, 635), "Prévisionnel RF", 30, NAVY, True)
    text(draw, (870, 690), "Vérifie l’agenda puis confirme l’ajout.", 21, INK)
    subtitle(draw, "Ouvre le fichier .ics, vérifie le calendrier proposé,\npuis clique sur Ajouter au calendrier.")
    return image


def slide_done() -> Image.Image:
    image, draw = base_slide("C’est terminé", "Fin")
    panel(draw, (250, 285, 1670, 760), fill="white", outline="#b7ddd5", radius=18)
    text(draw, (960, 415), "✓", 100, TEAL, True, "mm")
    text(draw, (960, 545), "Ton planning est dans Outlook", 44, NAVY, True, "mm")
    text(draw, (960, 620), "Tu peux maintenant le consulter et le modifier comme un agenda classique.", 24, MUTED, False, "mm")
    subtitle(draw, "Conseil : conserve le PDF source et le fichier ICS généré\npour pouvoir refaire un export si le planning change.")
    return image


def build_frames(folder: Path) -> list[Path]:
    slides = [slide_cover(), slide_open(), slide_pdf(), slide_person(), slide_preview(), slide_export(), slide_outlook(), slide_done()]
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
