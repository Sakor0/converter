#!/usr/bin/env python3
"""
convert.py - Jeden interfejs do lokalnych konwersji plików, zamiast szukania
"convert X to Y online" za każdym razem.

Podstawowe użycie (auto-wykrywanie formatu po rozszerzeniu):
    python convert.py convert zdjecie.jpg zdjecie.png
    python convert.py convert piosenka.mp3 piosenka.wav
    python convert.py convert film.mp4 dzwiek.mp3
    python convert.py convert raport.docx raport.pdf
    python convert.py convert dane.csv dane.json

Dodatkowe narzędzia (patrz też: python convert.py -h):
    resize, strip-exif, trim, to-gif, normalize-audio, compress-video,
    merge-pdf, split-pdf, rotate-pdf, img-to-pdf, ocr-pdf, pack, unpack, download

Pełna lista wspieranych formatów i wymagań (ffmpeg/tesseract/libreoffice)
w README.md.
"""

import argparse
import os
import sys

from converters import images, media, documents, data as data_mod, archives, download as download_mod


def ext_of(path):
    return os.path.splitext(path)[1].lower()


def output_format_options(input_path):
    """Rozszerzenia, na które do_convert() faktycznie umie przekonwertować dany
    plik wejściowy (po rozszerzeniu) - lustro dispatchu w do_convert(), żeby GUI
    mogło zaproponować gotową listę formatów zamiast każenia użytkownikowi
    ręcznie dopisywać rozszerzenie w nazwie pliku wyjściowego."""
    in_ext = ext_of(input_path)

    if in_ext in images.IMAGE_EXTS:
        return sorted(images.IMAGE_EXTS - {in_ext}) + [".pdf"]

    if in_ext in media.AUDIO_EXTS or in_ext in media.VIDEO_EXTS:
        return sorted((media.AUDIO_EXTS | media.VIDEO_EXTS) - {in_ext})

    if in_ext == ".pdf":
        return [".docx"]

    if in_ext in (".docx", ".doc"):
        return [".pdf"]

    if in_ext in data_mod.DATA_EXTS:
        return sorted(out for (src, out) in data_mod.CONVERSIONS if src == in_ext)

    return []


# ---------------------------------------------------------------- convert ---
def do_convert(input_path, output_path, quality=90):
    """Dispatch po rozszerzeniu wejścia/wyjścia. Współdzielone przez CLI i GUI.
    Zgłasza ValueError zamiast kończyć proces, żeby GUI mogło pokazać błąd."""
    in_ext = ext_of(input_path)
    out_ext = ext_of(output_path)

    if in_ext in images.IMAGE_EXTS and out_ext in images.IMAGE_EXTS:
        images.convert(input_path, output_path, quality=quality)

    elif in_ext in images.IMAGE_EXTS and out_ext == ".pdf":
        documents.images_to_pdf(output_path, [input_path])

    elif (in_ext in media.AUDIO_EXTS or in_ext in media.VIDEO_EXTS) and \
         (out_ext in media.AUDIO_EXTS or out_ext in media.VIDEO_EXTS):
        media.convert(input_path, output_path)

    elif in_ext == ".pdf" and out_ext == ".docx":
        documents.pdf_to_docx(input_path, output_path)

    elif in_ext in (".docx", ".doc") and out_ext == ".pdf":
        documents.docx_to_pdf(input_path, output_path)

    elif in_ext in data_mod.DATA_EXTS and out_ext in data_mod.DATA_EXTS:
        fn = data_mod.CONVERSIONS.get((in_ext, out_ext))
        if not fn:
            raise ValueError(f"Brak bezpośredniej ścieżki {in_ext} -> {out_ext}. "
                              f"Spróbuj przez JSON jako format pośredni.")
        fn(input_path, output_path)

    else:
        raise ValueError(f"Nieobsługiwana konwersja: {in_ext} -> {out_ext}\n"
                          f"Zobacz README.md po listę wspieranych par formatów.")


def cmd_convert(args):
    try:
        do_convert(args.input, args.output, quality=args.quality)
    except ValueError as e:
        sys.exit(str(e))
    print(f"OK: {args.input} -> {args.output}")


# ------------------------------------------------------------- image tools --
def cmd_resize(args):
    images.resize(args.input, args.output, width=args.width, height=args.height)
    print(f"OK: {args.output}")


def cmd_strip_exif(args):
    images.strip_exif(args.input, args.output)
    print(f"OK: metadane usunięte -> {args.output}")


# -------------------------------------------------------- audio/video tools -
def cmd_trim(args):
    media.trim(args.input, args.output, args.start, args.end)
    print(f"OK: {args.output}")


def cmd_to_gif(args):
    media.to_gif(args.input, args.output, fps=args.fps, width=args.width)
    print(f"OK: {args.output}")


def cmd_normalize_audio(args):
    media.normalize_audio(args.input, args.output)
    print(f"OK: {args.output}")


def cmd_compress_video(args):
    media.compress_video(args.input, args.output, crf=args.crf)
    print(f"OK: {args.output}")


# ------------------------------------------------------------ document tools
def cmd_merge_pdf(args):
    documents.merge_pdf(args.output, args.inputs)
    print(f"OK: {len(args.inputs)} plików -> {args.output}")


def cmd_split_pdf(args):
    paths = documents.split_pdf(args.input, args.output_dir)
    print(f"OK: {len(paths)} stron -> {args.output_dir}")


def cmd_rotate_pdf(args):
    documents.rotate_pdf(args.input, args.output, degrees=args.degrees)
    print(f"OK: {args.output}")


def cmd_img_to_pdf(args):
    documents.images_to_pdf(args.output, args.inputs)
    print(f"OK: {len(args.inputs)} obrazów -> {args.output}")


def cmd_ocr_pdf(args):
    documents.ocr_pdf_to_text(args.input, args.output, lang=args.lang)
    print(f"OK: tekst zapisany -> {args.output}")


# ----------------------------------------------------------- pobieranie ----
def cmd_download(args):
    final_path, height, was_blocked = download_mod.download(
        args.url, args.output, quality_label=args.quality, cookies_browser=args.cookies_browser)
    if was_blocked and height:
        print(f"UWAGA: YouTube zablokował pobieranie w wyższej jakości i ograniczył ten film "
              f"do {height}p mimo wyboru {args.quality} (zwykle dotyczy mocno chronionych/"
              f"oficjalnych teledysków).")
    print(f"OK: {final_path}")


# ------------------------------------------------------------- archive tools
def cmd_pack(args):
    if args.output.endswith(".zip"):
        archives.pack_zip(args.output, args.inputs)
    else:
        archives.pack_tar(args.output, args.inputs, gz=args.output.endswith((".gz", ".tgz")))
    print(f"OK: {args.output}")


def cmd_unpack(args):
    if args.input.endswith(".zip"):
        archives.unpack_zip(args.input, args.output_dir)
    else:
        archives.unpack_tar(args.input, args.output_dir)
    print(f"OK: rozpakowano -> {args.output_dir}")


# --------------------------------------------------------------------- main -
def build_parser():
    p = argparse.ArgumentParser(
        prog="convert.py",
        description="Lokalny, darmowy toolkit do konwersji plików - bez wgrywania na obce serwery.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("convert", help="ogólna konwersja X -> Y (po rozszerzeniu)")
    c.add_argument("input")
    c.add_argument("output")
    c.add_argument("--quality", type=int, default=90, help="jakość JPG/WEBP (1-100)")
    c.set_defaults(func=cmd_convert)

    r = sub.add_parser("resize", help="zmiana rozmiaru obrazu")
    r.add_argument("input")
    r.add_argument("output")
    r.add_argument("--width", type=int)
    r.add_argument("--height", type=int)
    r.set_defaults(func=cmd_resize)

    se = sub.add_parser("strip-exif", help="usuwa metadane EXIF ze zdjęcia")
    se.add_argument("input")
    se.add_argument("output")
    se.set_defaults(func=cmd_strip_exif)

    t = sub.add_parser("trim", help="wycina fragment audio/wideo")
    t.add_argument("input")
    t.add_argument("output")
    t.add_argument("--start", required=True, help="np. 00:00:10")
    t.add_argument("--end", required=True, help="np. 00:00:30")
    t.set_defaults(func=cmd_trim)

    g = sub.add_parser("to-gif", help="wideo -> animowany GIF")
    g.add_argument("input")
    g.add_argument("output")
    g.add_argument("--fps", type=int, default=10)
    g.add_argument("--width", type=int, default=480)
    g.set_defaults(func=cmd_to_gif)

    na = sub.add_parser("normalize-audio", help="wyrównuje głośność nagrania")
    na.add_argument("input")
    na.add_argument("output")
    na.set_defaults(func=cmd_normalize_audio)

    cv = sub.add_parser("compress-video", help="kompresuje wideo (mniejszy plik)")
    cv.add_argument("input")
    cv.add_argument("output")
    cv.add_argument("--crf", type=int, default=28, help="18-28, niżej = lepsza jakość")
    cv.set_defaults(func=cmd_compress_video)

    mp = sub.add_parser("merge-pdf", help="łączy kilka PDF-ów w jeden")
    mp.add_argument("output")
    mp.add_argument("inputs", nargs="+")
    mp.set_defaults(func=cmd_merge_pdf)

    sp = sub.add_parser("split-pdf", help="rozdziela PDF na pojedyncze strony")
    sp.add_argument("input")
    sp.add_argument("output_dir")
    sp.set_defaults(func=cmd_split_pdf)

    rp = sub.add_parser("rotate-pdf", help="obraca strony PDF")
    rp.add_argument("input")
    rp.add_argument("output")
    rp.add_argument("--degrees", type=int, default=90)
    rp.set_defaults(func=cmd_rotate_pdf)

    ip = sub.add_parser("img-to-pdf", help="łączy obrazy w jeden PDF")
    ip.add_argument("output")
    ip.add_argument("inputs", nargs="+")
    ip.set_defaults(func=cmd_img_to_pdf)

    op = sub.add_parser("ocr-pdf", help="wyciąga tekst ze skanu PDF (OCR)")
    op.add_argument("input")
    op.add_argument("output", help="plik .txt")
    op.add_argument("--lang", default="pol+eng")
    op.set_defaults(func=cmd_ocr_pdf)

    dl = sub.add_parser("download", help="pobiera film z linku (YouTube, Facebook, ...) przez yt-dlp")
    dl.add_argument("url")
    dl.add_argument("output", help="ścieżka wyjściowa (rozszerzenie ignorowane dla samego dźwięku - zawsze .mp3)")
    dl.add_argument("--quality", choices=download_mod.QUALITY_LABELS, default="Najlepsza jakość")
    dl.add_argument("--cookies-browser", choices=download_mod.BROWSERS, default=None,
                     help="pobierz ciasteczka z tej przeglądarki (przydatne dla części filmów z Facebooka)")
    dl.set_defaults(func=cmd_download)

    pk = sub.add_parser("pack", help="pakuje pliki/foldery do ZIP lub TAR.GZ")
    pk.add_argument("output")
    pk.add_argument("inputs", nargs="+")
    pk.set_defaults(func=cmd_pack)

    up = sub.add_parser("unpack", help="rozpakowuje ZIP lub TAR.GZ")
    up.add_argument("input")
    up.add_argument("output_dir")
    up.set_defaults(func=cmd_unpack)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as e:
        sys.exit(f"Błąd: {e}")


if __name__ == "__main__":
    main()
