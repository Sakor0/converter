"""
images.py - Konwersje i operacje na obrazach (Pillow, czysty Python,
bez zewnętrznych binarek).

Obsługiwane formaty: JPG, PNG, WEBP, BMP, GIF, TIFF, ICO.
"""

import os
from PIL import Image

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".tif", ".ico"}


def convert(input_path, output_path, quality=90):
    """Konwertuje między formatami obrazu. quality dotyczy JPG/WEBP (1-100)."""
    img = Image.open(input_path)
    ext = os.path.splitext(output_path)[1].lower()

    # JPG nie obsługuje przezroczystości - trzeba spłaszczyć na białe tło
    if ext in (".jpg", ".jpeg") and img.mode in ("RGBA", "P", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        img = background

    save_kwargs = {}
    if ext in (".jpg", ".jpeg", ".webp"):
        save_kwargs["quality"] = quality
    img.save(output_path, **save_kwargs)


def resize(input_path, output_path, width=None, height=None, keep_aspect=True):
    """Zmienia rozmiar. Podaj width LUB height + keep_aspect=True, żeby zachować proporcje."""
    img = Image.open(input_path)
    w, h = img.size
    if keep_aspect and width and not height:
        height = round(h * (width / w))
    elif keep_aspect and height and not width:
        width = round(w * (height / h))
    img = img.resize((width or w, height or h), Image.LANCZOS)
    img.save(output_path)


def strip_exif(input_path, output_path):
    """Usuwa metadane EXIF (GPS, model telefonu, data itd.) - przydatne przed wysłaniem zdjęcia."""
    img = Image.open(input_path)
    data = list(img.getdata())
    clean = Image.new(img.mode, img.size)
    clean.putdata(data)
    clean.save(output_path)
