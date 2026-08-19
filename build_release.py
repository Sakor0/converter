#!/usr/bin/env python3
"""
build_release.py - Buduje samodzielna paczke gui.py (PyInstaller, folder
"onedir" + ffmpeg/ffprobe dolaczone obok programu) i pakuje ja w jeden ZIP,
zeby dalo sie pobrac i uruchomic local_converter.exe bez instalowania Pythona
ani reczno konfigurowania ffmpeg.

VLC, LibreOffice, Tesseract i Poppler NIE sa dolaczane (za duze/za ciezkie do
spakowania sensownie) - odpowiadajace im funkcje (podglad w zakladce Trim,
DOCX->PDF, OCR) dzialaja tylko jesli sa zainstalowane osobno w systemie,
dokladnie tak jak przy uruchomieniu z kodu zrodlowego (patrz README.md).

Uzycie:
    python build_release.py
Wynik:
    dist/local_converter/          <- folder z local_converter.exe i zaleznosciami
    local_converter-windows.zip    <- ten sam folder spakowany do pobrania
"""

import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
FFMPEG_DIR = r"C:\ffmpeg\bin"


def find_ffmpeg_binaries():
    ffmpeg = shutil.which("ffmpeg") or os.path.join(FFMPEG_DIR, "ffmpeg.exe")
    ffprobe = shutil.which("ffprobe") or os.path.join(FFMPEG_DIR, "ffprobe.exe")
    missing = [p for p in (ffmpeg, ffprobe) if not os.path.isfile(p)]
    if missing:
        sys.exit(f"Nie znaleziono: {missing}. Zainstaluj ffmpeg (patrz README.md) i sprobuj ponownie.")
    return ffmpeg, ffprobe


def main():
    ffmpeg, ffprobe = find_ffmpeg_binaries()
    print(f"Uzywam ffmpeg: {ffmpeg}")
    print(f"Uzywam ffprobe: {ffprobe}")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        os.path.join(ROOT, "gui.py"),
        "--name", "local_converter",
        "--noconsole",
        "--noconfirm",
        "--clean",
        "--collect-all", "customtkinter",
        "--collect-all", "tkinterdnd2",
        "--add-binary", f"{ffmpeg};.",
        "--add-binary", f"{ffprobe};.",
        "--distpath", os.path.join(ROOT, "dist"),
        "--workpath", os.path.join(ROOT, "build"),
        "--specpath", ROOT,
    ]
    print("Buduje:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)

    dist_dir = os.path.join(ROOT, "dist", "local_converter")
    zip_path = os.path.join(ROOT, "local_converter-windows.zip")
    if os.path.isfile(zip_path):
        os.remove(zip_path)

    print(f"Pakuje {dist_dir} -> {zip_path}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _dirnames, filenames in os.walk(dist_dir):
            for fname in filenames:
                full = os.path.join(dirpath, fname)
                rel = os.path.join("local_converter", os.path.relpath(full, dist_dir))
                zf.write(full, rel)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"Gotowe: {zip_path} ({size_mb:.0f} MB)")


if __name__ == "__main__":
    main()
