"""
documents.py - Operacje na PDF/DOCX.

Merge/split/rotate PDF oraz obraz->PDF działają w czystym Pythonie (pypdf,
Pillow). PDF->DOCX używa biblioteki pdf2docx (czysty Python, ale najlepiej
radzi sobie z PDF-ami tekstowymi, nie skanami). DOCX->PDF i OCR wymagają
zewnętrznych, darmowych programów zainstalowanych w systemie - patrz README.md.
"""

import os
import shutil
import subprocess
import sys

from PIL import Image
from pypdf import PdfReader, PdfWriter

DOC_EXTS = {".pdf", ".docx", ".doc"}

# Na Windows subprocess.run() bez tego domyślnie miga czarnym oknem konsoli -
# istotne przy uruchamianiu z GUI (pythonw).
_NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def merge_pdf(output_path, input_paths):
    writer = PdfWriter()
    for p in input_paths:
        reader = PdfReader(p)
        for page in reader.pages:
            writer.add_page(page)
    with open(output_path, "wb") as f:
        writer.write(f)


def split_pdf(input_path, output_dir):
    """Zapisuje każdą stronę jako osobny plik PDF, zwraca listę ścieżek."""
    reader = PdfReader(input_path)
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(input_path))[0]
    paths = []
    for i, page in enumerate(reader.pages, start=1):
        writer = PdfWriter()
        writer.add_page(page)
        out = os.path.join(output_dir, f"{base}_s{i:03d}.pdf")
        with open(out, "wb") as f:
            writer.write(f)
        paths.append(out)
    return paths


def rotate_pdf(input_path, output_path, degrees=90):
    reader = PdfReader(input_path)
    writer = PdfWriter()
    for page in reader.pages:
        page.rotate(degrees)
        writer.add_page(page)
    with open(output_path, "wb") as f:
        writer.write(f)


def images_to_pdf(output_path, image_paths):
    """Łączy jeden lub więcej obrazów w jeden PDF (jedna strona na obraz)."""
    images = [Image.open(p).convert("RGB") for p in image_paths]
    first, rest = images[0], images[1:]
    first.save(output_path, save_all=True, append_images=rest)


def pdf_to_docx(input_path, output_path):
    """Wymaga pip install pdf2docx. Najlepsze wyniki dla PDF-ów tekstowych (nie skanów)."""
    from pdf2docx import Converter
    cv = Converter(input_path)
    cv.convert(output_path)
    cv.close()


def docx_to_pdf(input_path, output_path):
    """Wymaga zainstalowanego (darmowego) LibreOffice - patrz README.md."""
    binary = shutil.which("libreoffice") or shutil.which("soffice")
    if binary is None:
        raise RuntimeError("LibreOffice nie znaleziony w PATH. Zobacz README.md.")

    outdir = os.path.dirname(os.path.abspath(output_path)) or "."
    result = subprocess.run(
        [binary, "--headless", "--convert-to", "pdf", "--outdir", outdir,
         os.path.abspath(input_path)],
        capture_output=True, text=True, **_NO_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice błąd:\n{result.stderr[-2000:]}")

    # LibreOffice zawsze nazywa wynik jak plik wejściowy - dopasuj nazwę jeśli inna
    generated = os.path.join(outdir, os.path.splitext(os.path.basename(input_path))[0] + ".pdf")
    if os.path.abspath(generated) != os.path.abspath(output_path):
        os.replace(generated, output_path)


def ocr_pdf_to_text(input_path, output_txt, lang="pol+eng"):
    """Wymaga tesseract-ocr + poppler (pdf2image) - patrz README.md."""
    import pytesseract
    from pdf2image import convert_from_path

    pages = convert_from_path(input_path)
    text_parts = [pytesseract.image_to_string(page, lang=lang) for page in pages]
    with open(output_txt, "w", encoding="utf-8") as f:
        f.write("\n\n".join(text_parts))
