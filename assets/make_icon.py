#!/usr/bin/env python3
"""
make_icon.py - Generuje ikone aplikacji (assets/icon.png i assets/icon.ico) -
dwie strzalki uklejajace sie w petle "konwersji/wymiany", w kolorach juz
uzywanych w GUI (akcent #3b8ed0 to ten sam niebieski co busy-dot w pasku
statusu, tlo #1a1f27 to ciemny neutralny odcien pasujacy do dark mode
customtkinter) - zeby ikona wygladala jak naturalna czesc aplikacji, a nie
doczepiona z zewnatrz.

Uzycie:
    python assets/make_icon.py
Wynik:
    assets/icon.png (1024x1024, do README/innych zastosowan)
    assets/icon.ico (16/32/48/256px, do PyInstaller --icon i okna GUI)
"""

import math
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))

SCALE = 4
BASE = 256
SIZE = BASE * SCALE

BG = (26, 31, 39, 255)          # #1a1f27
ACCENT = (59, 142, 208, 255)    # #3b8ed0 - ten sam niebieski co status_dot (busy) w gui.py
ACCENT2 = (127, 184, 232, 255)  # #7fb8e8 - jasniejszy niebieski z zaznaczenia na przebiegu fali


def _arrow_triangle(draw, center, radius, angle_deg, stroke_w, color):
    """Grot strzalki styczny do okregu w angle_deg, skierowany zgodnie z
    kierunkiem rosnacego kata (zgodnie z ruchem wskazowek zegara - tak samo
    jak PIL rysuje draw.arc)."""
    theta = math.radians(angle_deg)
    px = center[0] + radius * math.cos(theta)
    py = center[1] + radius * math.sin(theta)
    tx, ty = -math.sin(theta), math.cos(theta)
    nx, ny = math.cos(theta), math.sin(theta)

    length = stroke_w * 1.7
    width = stroke_w * 1.6
    tip = (px + tx * length * 0.6, py + ty * length * 0.6)
    back_l = (px - tx * length * 0.4 + nx * width / 2, py - ty * length * 0.4 + ny * width / 2)
    back_r = (px - tx * length * 0.4 - nx * width / 2, py - ty * length * 0.4 - ny * width / 2)
    draw.polygon([tip, back_l, back_r], fill=color)


def render():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    radius = int(SIZE * 0.22)
    draw.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=radius, fill=BG)

    cx, cy = SIZE / 2, SIZE / 2
    r = SIZE * 0.27
    stroke = int(SIZE * 0.085)

    draw.arc([cx - r, cy - r, cx + r, cy + r], start=195, end=345, fill=ACCENT, width=stroke)
    _arrow_triangle(draw, (cx, cy), r, 345, stroke, ACCENT)

    draw.arc([cx - r, cy - r, cx + r, cy + r], start=15, end=165, fill=ACCENT2, width=stroke)
    _arrow_triangle(draw, (cx, cy), r, 165, stroke, ACCENT2)

    cap_r = stroke / 2
    for angle, color in [(195, ACCENT), (15, ACCENT2)]:
        theta = math.radians(angle)
        px = cx + r * math.cos(theta)
        py = cy + r * math.sin(theta)
        draw.ellipse([px - cap_r, py - cap_r, px + cap_r, py + cap_r], fill=color)

    return img.resize((BASE * 4, BASE * 4), Image.LANCZOS)


def main():
    img = render()

    png_path = os.path.join(HERE, "icon.png")
    img.save(png_path)
    print(f"Zapisano {png_path} ({img.size[0]}x{img.size[1]})")

    ico_path = os.path.join(HERE, "icon.ico")
    icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=icon_sizes)
    print(f"Zapisano {ico_path} ({', '.join(f'{w}x{h}' for w, h in icon_sizes)})")


if __name__ == "__main__":
    main()
