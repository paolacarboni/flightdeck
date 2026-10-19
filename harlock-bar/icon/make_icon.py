"""Disegna l'icona della barra dei menu: la faccia di Capitan Harlock in pixel art, 18×18.

Uso: /usr/bin/python3 icon/make_icon.py
Scrive icon/harlock.png (40×40 a 144 dpi, cioè 20 punti @2x, con la faccia
a 36 pixel e un margine trasparente) e icon/harlock-preview.png (ingrandita).
"""
from pathlib import Path

from PIL import Image

PALETTE = {
    "K": (10, 10, 14),  # contorno e benda
    "h": (64, 30, 12),  # capelli in ombra
    "H": (122, 62, 26),  # capelli
    "L": (184, 104, 46),  # capelli in luce
    "S": (232, 178, 136),  # pelle
    "s": (176, 120, 86),  # pelle in ombra
    "W": (236, 240, 246),  # bianco dell'occhio
    "X": (150, 34, 36),  # cicatrice
    "R": (196, 36, 46),  # colletto rosso
    "Y": (233, 184, 48),  # bordo giallo
    "k": (24, 28, 40),  # divisa
}

# Frangia lunga sugli occhi, benda sull'occhio destro (a sinistra per chi guarda) con la fascia in
# diagonale, cicatrice in diagonale sulla guancia sinistra, colletto rosso alto.
FACE = [
    "....hhhhhhhhh.....",
    "...hHHHHLLHHHh....",
    "..hHHLLHHHHHHHh...",
    ".hHHLHHHHHLHHHHh..",
    ".hHHHHHLHHHHHHHHh.",
    "hHHHhHHHHhHHHhHHh.",
    "hHHhKKKKhSHHhSHHHh",
    "hHhKKKKSSSSKKKhHHh",
    "hHhKKKKSSSSKWShHHh",
    "hHhKKKKSSSSsSXShHh",
    "hHhhKKsSSSSSXSShHh",
    ".hHhsSSSSSSXSSShHh",
    ".hHhhsSSKKKSSSshHh",
    ".hHHhhsSSSSSSshhHh",
    "RhHHRhhsssssshRhh.",
    "RRhRRYRkkkkkRYRRh.",
    "RRRRRYkkkkkkkYRRR.",
    "RRRRYkkkkkkkkkYRRR",
]

SIZE = 18
SCALE = 2
CANVAS = 40  # pixel dell'icona @2x: 20 punti
FACE_PX = 36  # faccia a 18 punti, nitida (2 pixel per cella), con margine


def draw(rows, scale):
    img = Image.new("RGBA", (SIZE * scale, SIZE * scale), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        assert len(row) == SIZE, "riga %d lunga %d" % (y, len(row))
        for x, ch in enumerate(row):
            if ch in PALETTE:
                for dy in range(scale):
                    for dx in range(scale):
                        img.putpixel((x * scale + dx, y * scale + dy), PALETTE[ch] + (255,))
    return img


def main():
    here = Path(__file__).resolve().parent
    icon = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    margin = (CANVAS - FACE_PX) // 2
    icon.paste(draw(FACE, SCALE).resize((FACE_PX, FACE_PX), Image.NEAREST), (margin, margin))
    icon.save(here / "harlock.png", dpi=(144, 144))
    icon.resize((CANVAS * 8, CANVAS * 8), Image.NEAREST).save(here / "harlock-icon-preview.png")
    draw(FACE, 16).save(here / "harlock-preview.png")


if __name__ == "__main__":
    main()
