"""
translations.py - Przelaczanie jezyka GUI (polski/angielski) na zywo, bez
zamykania programu.

Polski tekst w kodzie GUI jest jednoczesnie kluczem slownika: t(text) zwraca
angielskie tlumaczenie, gdy aktualny jezyk to "en", a oryginalny (polski)
tekst bez zmian w przeciwnym razie - albo gdy tlumaczenia brakuje (bezpieczny
fallback zamiast bledu/pustego tekstu, gdyby ktos dopisal nowy polski string
i zapomnial o tlumaczeniu).

Zmiana jezyka (set_language) sama w sobie NIE odswieza juz zbudowanych
widgetow - to gui.py (App._rebuild_ui) niszczy i buduje UI od nowa po
zmianie, dzieki czemu kazdy t(...) w kodzie budujacym widgety zostaje
wywolany ponownie z nowym jezykiem.
"""

_state = {"lang": "pl"}


def get_language():
    return _state["lang"]


def set_language(lang):
    if lang not in ("pl", "en"):
        raise ValueError(f"Nieznany jezyk: {lang!r}")
    _state["lang"] = lang


def t(text):
    """Tlumaczy polski tekst na angielski, jesli aktualny jezyk to 'en'."""
    if _state["lang"] == "en":
        return EN.get(text, text)
    return text


# Polski tekst (klucz) -> angielskie tlumaczenie.
EN = {
    # --- wspolne / labeled_row ---
    "Plik wejściowy:": "Input file:",
    "Plik wyjściowy:": "Output file:",
    "Format wyjściowy:": "Output format:",
    "Jakość (JPG/WEBP):": "Quality (JPG/WEBP):",
    "Szerokość (px):": "Width (px):",
    "Wysokość (px):": "Height (px):",
    "Początek (HH:MM:SS):": "Start (HH:MM:SS):",
    "Koniec (HH:MM:SS):": "End (HH:MM:SS):",
    "Plik wideo:": "Video file:",
    "FPS:": "FPS:",
    "Plik wyjściowy (.gif):": "Output file (.gif):",
    "Plik audio:": "Audio file:",
    "CRF (18-28, niżej = lepsza jakość):": "CRF (18-28, lower = better quality):",
    "Początek (opcjonalnie):": "Start (optional):",
    "Koniec (opcjonalnie):": "End (optional):",
    "Plik wyjściowy (.mp3):": "Output file (.mp3):",
    "Plik PDF:": "PDF file:",
    "Folder wyjściowy:": "Output folder:",
    "Stopnie:": "Degrees:",
    "Język (tesseract):": "Language (tesseract):",
    "Plik wyjściowy (.txt):": "Output file (.txt):",
    "Plik archiwum:": "Archive file:",
    "Link:": "Link:",
    "Jakość:": "Quality:",

    # --- ogolne / wielokrotnie uzywane ---
    "Przeglądaj...": "Browse...",
    "Zapisz jako...": "Save as...",
    "Wybierz folder...": "Choose folder...",
    "Brakuje danych": "Missing data",
    "Podaj plik wejściowy i wyjściowy.": "Provide an input and output file.",
    "wybierz plik lub przeciągnij go tutaj...": "choose a file or drag it here...",
    "Wszystkie pliki": "All files",
    "Zapisano:": "Saved:",
    "Błąd": "Error",
    "Gotowy.": "Ready.",
    "Gotowe.": "Done.",
    "Przetwarzanie...": "Processing...",
    "Obrazy": "Images",
    "Audio": "Audio",
    "Wideo": "Video",
    "Audio/Wideo": "Audio/Video",
    "Wideo/Audio": "Video/Audio",
    "Archiwa": "Archives",
    "Tekst": "Text",

    # --- sidebar / status bar / App ---
    "wszystko lokalnie, offline": "everything local, offline",
    "Konwersja": "Conversion",
    "Audio / Wideo": "Audio / Video",
    "Dokumenty (PDF)": "Documents (PDF)",
    "Pobierz z linku": "Download from link",

    # --- Konwersja ---
    "Konwersja ogólna (format rozpoznawany po rozszerzeniu)": "General conversion (format detected from extension)",
    "Obrazy, audio/wideo, PDF↔DOCX, CSV/JSON/XLSX/YAML - jedna komenda.":
        "Images, audio/video, PDF↔DOCX, CSV/JSON/XLSX/YAML - one command.",
    "nazwa uzupełni się sama po wyborze formatu wyżej": "name will fill in automatically once you pick a format above",
    "- wybierz plik wejściowy -": "- choose an input file -",
    "(brak obsługiwanej konwersji dla tego pliku)": "(no supported conversion for this file)",
    "Konwertuję...": "Converting...",
    "Konwertuj": "Convert",

    # --- Obrazy ---
    "Zmień rozmiar obrazu (proporcje zachowane, jeśli podasz tylko jeden wymiar)":
        "Resize an image (aspect ratio kept if you only give one dimension)",
    "np. 1280": "e.g. 1280",
    "zostaw puste, by zachować proporcje": "leave empty to keep aspect ratio",
    "Podaj szerokość lub wysokość.": "Provide a width or height.",
    "Zmieniam rozmiar...": "Resizing...",
    "Zmień rozmiar": "Resize",
    "Usuń metadane EXIF (GPS, model telefonu, data) przed wysłaniem zdjęcia":
        "Strip EXIF metadata (GPS, phone model, date) before sharing a photo",
    "Usuwam metadane...": "Stripping metadata...",
    "Usuń EXIF": "Strip EXIF",

    # --- Audio/Wideo: Trim ---
    "✂ Przytnij fragment audio/wideo (MP3, MP4, WAV, MOV, ...)": "✂ Trim an audio/video clip (MP3, MP4, WAV, MOV, ...)",
    "Długość pliku: -": "File length: -",
    "Długość pliku: wczytywanie...": "File length: loading...",
    "Długość pliku: {s}": "File length: {s}",
    "📂 Plik źródłowy": "📂 Source file",
    "Otwórz w domyślnym odtwarzaczu systemu": "Open in the system's default player",
    "🎬 Podgląd i odtwarzanie": "🎬 Preview & playback",
    "⚠ Podgląd/odtwarzanie niedostępne ({e}). Zainstaluj VLC Media Player, "
    "żeby móc odtwarzać pliki w tej zakładce.":
        "⚠ Preview/playback unavailable ({e}). Install VLC Media Player to play files in this tab.",
    "▶ Odtwórz": "▶ Play",
    "⏸ Pauza": "⏸ Pause",
    "⏹ Stop": "⏹ Stop",
    "⏮ Zaznacz początek tutaj": "⏮ Mark start here",
    "Zaznacz koniec tutaj ⏭": "Mark end here ⏭",
    "〰 Zakres przycięcia": "〰 Trim range",
    "przeciągnij uchwyty (brzegi) albo całe zaznaczenie, żeby ustawić zakres - "
    "uchwyty przyciągają się do suwaka odtwarzania, gdy są blisko niego":
        "drag the handles (edges) or the whole selection to set the range - "
        "handles snap to the playback slider when close to it",
    "💾 Zapis wyniku": "💾 Save result",
    "✂ Wytnij fragment": "✂ Trim clip",
    "Bez zmian w mikserze cięcie jest bezstratne i błyskawiczne (bez przekodowania),\n"
    "ale przy wideo start fragmentu może się przesunąć o ułamek sekundy do najbliższej\n"
    "klatki kluczowej. Jeśli dostosujesz głośność/wyciszenie ścieżek, dźwięk zostanie\n"
    "przekodowany na nowo (żeby zapisać zmiksowany wynik) - trwa to dłużej.":
        "Without mixer changes, trimming is lossless and instant (no re-encoding),\n"
        "but for video the clip's start may shift by a fraction of a second to the nearest\n"
        "keyframe. If you adjust track volume/mute, the audio gets re-encoded\n"
        "(to save the mixed result) - that takes longer.",
    "Przeliczam podgląd miksu ścieżek...": "Recalculating the track-mix preview...",
    "🎚 Ścieżki audio ({n}) - dostosuj głośność/wyciszenie": "🎚 Audio tracks ({n}) - adjust volume/mute",
    "↺ Reset miksu": "↺ Reset mix",
    "Wycisz": "Mute",
    "Wczytuję ścieżkę {n}...": "Loading track {n}...",
    "wczytywanie przebiegu fali...": "loading waveform...",
    "Odczytuję długość pliku (ffprobe)...": "Reading file length (ffprobe)...",
    "Generuję podgląd ścieżki dźwiękowej...": "Generating audio waveform preview...",
    "Sprawdzam ścieżki audio...": "Checking audio tracks...",
    "Brak pliku": "No file",
    "Najpierw wybierz plik wejściowy.": "Choose an input file first.",
    "Uzupełnij plik wejściowy, wyjściowy oraz start/koniec.": "Fill in the input file, output file, and start/end.",
    "Przycinanie z miksem ścieżek {i} [{s} -> {e}] -> {o}": "Trimming with track mix {i} [{s} -> {e}] -> {o}",
    "Przycinam i miksuję ścieżki (ffmpeg)...": "Trimming and mixing tracks (ffmpeg)...",
    "Przycinanie {i} [{s} -> {e}] -> {o}": "Trimming {i} [{s} -> {e}] -> {o}",
    "Przycinam plik (ffmpeg)...": "Trimming file (ffmpeg)...",
    "wybierz plik, żeby zobaczyć przebieg fali": "choose a file to see the waveform",
    "brak podglądu ścieżki dźwiękowej": "no audio waveform preview",

    # --- Audio/Wideo: MP3 / GIF / normalize / compress ---
    "Wideo/audio → MP3 (opcjonalnie tylko fragment)": "Video/audio → MP3 (optionally just a clip)",
    "puste = od początku, np. 00:00:10": "empty = from the start, e.g. 00:00:10",
    "puste = do końca, np. 00:01:30": "empty = to the end, e.g. 00:01:30",
    "Zły format czasu": "Bad time format",
    "Początek/koniec podaj jako HH:MM:SS albo w sekundach.": "Give start/end as HH:MM:SS or in seconds.",
    "Wyciągam dźwięk (MP3)...": "Extracting audio (MP3)...",
    "Wyciągnij MP3": "Extract MP3",
    "Przytnij (Trim)": "Trim",
    "Wideo → MP3": "Video → MP3",
    "Wideo → GIF": "Video → GIF",
    "Wideo → animowany GIF": "Video → animated GIF",
    "Generuję GIF...": "Generating GIF...",
    "Konwertuj na GIF": "Convert to GIF",
    "Wyrównaj głośność": "Normalize volume",
    "Wyrównaj głośność nagrania (EBU R128 loudnorm)": "Normalize recording volume (EBU R128 loudnorm)",
    "Wyrównuję głośność...": "Normalizing volume...",
    "Kompresuj wideo": "Compress video",
    "Kompresuj wideo (mniejszy plik)": "Compress video (smaller file)",
    "Kompresuję wideo...": "Compressing video...",
    "Kompresuj": "Compress",

    # --- Dokumenty (PDF) ---
    "Połącz kilka PDF-ów w jeden (kolejność jak na liście)": "Merge several PDFs into one (order as in the list)",
    "Dodaj min. 2 pliki PDF i podaj plik wyjściowy.": "Add at least 2 PDF files and provide an output file.",
    "Łączę {n} plików PDF...": "Merging {n} PDF files...",
    "Połącz PDF-y": "Merge PDFs",
    "Połącz PDF": "Merge PDF",
    "Rozdziel PDF na pojedyncze strony": "Split a PDF into individual pages",
    "Podaj plik PDF i folder wyjściowy.": "Provide a PDF file and an output folder.",
    "Zapisano {n} stron -> {d}": "Saved {n} pages -> {d}",
    "Rozdzielam PDF...": "Splitting PDF...",
    "Rozdziel na strony": "Split into pages",
    "Rozdziel PDF": "Split PDF",
    "Obróć strony PDF": "Rotate PDF pages",
    "Obracam strony...": "Rotating pages...",
    "Obróć": "Rotate",
    "Obróć PDF": "Rotate PDF",
    "Połącz obrazy w jeden PDF (kolejność jak na liście)": "Merge images into one PDF (order as in the list)",
    "Dodaj co najmniej jeden obraz i podaj plik wyjściowy.": "Add at least one image and provide an output file.",
    "Tworzę PDF z {n} obrazów...": "Creating a PDF from {n} images...",
    "Utwórz PDF": "Create PDF",
    "Obrazy → PDF": "Images → PDF",
    "OCR - wyciągnij tekst ze skanu PDF (wymaga Tesseract + Poppler)":
        "OCR - extract text from a scanned PDF (requires Tesseract + Poppler)",
    "Rozpoznaję tekst (OCR)...": "Recognizing text (OCR)...",
    "Rozpoznaj tekst": "Recognize text",

    # --- Archiwa ---
    "Spakuj pliki/foldery do ZIP lub TAR.GZ": "Pack files/folders into ZIP or TAR.GZ",
    "Dodaj pliki/foldery i podaj nazwę archiwum.": "Add files/folders and provide an archive name.",
    "Pakuję {n} pozycji...": "Packing {n} items...",
    "Spakuj": "Pack",
    "Rozpakuj ZIP lub TAR.GZ": "Unpack a ZIP or TAR.GZ",
    "Podaj plik archiwum i folder wyjściowy.": "Provide an archive file and an output folder.",
    "Rozpakowano -> {d}": "Unpacked -> {d}",
    "Rozpakowuję...": "Unpacking...",
    "Rozpakuj": "Unpack",

    # --- Pobierz z linku ---
    "Pobierz film z linku (YouTube, Facebook i inne wspierane przez yt-dlp)":
        "Download a video from a link (YouTube, Facebook, and others supported by yt-dlp)",
    "Pobieranie z tych serwisów łamie ich regulaminy nawet do użytku prywatnego -\n"
    "to Twoja decyzja, czy i co pobierasz.":
        "Downloading from these services breaks their terms of service even for private use -\n"
        "it's your call whether and what you download.",
    "wklej link do filmu (YouTube, Facebook, ...)": "paste a video link (YouTube, Facebook, ...)",
    "Sprawdź": "Check",
    "Najlepsza jakość": "Best quality",
    "Tylko dźwięk (MP3)": "Audio only (MP3)",
    "Użyj ciasteczek z przeglądarki (część filmów z Facebooka tego wymaga)":
        "Use cookies from a browser (some Facebook videos require this)",
    "Chrome/Edge/Opera/Opera GX/Brave blokują odczyt ciasteczek, gdy przeglądarka "
    "jest otwarta - zamknij ją przed pobieraniem (Firefox tego nie wymaga).":
        "Chrome/Edge/Opera/Opera GX/Brave block reading cookies while the browser "
        "is open - close it before downloading (Firefox doesn't need this).",
    "nazwa uzupełni się po sprawdzeniu linku": "name will fill in once the link is checked",
    "Brak linku": "No link",
    "Wklej link do filmu.": "Paste a video link.",
    "nieznana (transmisja na żywo?)": "unknown (live stream?)",
    "„{title}”{uploader} • długość: {dur}": "“{title}”{uploader} • length: {dur}",
    "Sprawdzam link...": "Checking link...",
    "Pobieram... {pct}%": "Downloading... {pct}%",
    "Pobieram... {mb} MB": "Downloading... {mb} MB",
    "Przetwarzam (łączę wideo+audio / konwertuję)...": "Processing (merging video+audio / converting)...",
    "Podaj link i plik wyjściowy (albo najpierw kliknij Sprawdź).":
        "Provide a link and an output file (or click Check first).",
    "⚠ YouTube zablokował pobieranie w wyższej jakości i ograniczył ten "
    "film do {h}p mimo wyboru {q} (zwykle dotyczy mocno "
    "chronionych/oficjalnych teledysków).":
        "⚠ YouTube blocked downloading in higher quality and capped this "
        "video at {h}p despite choosing {q} (usually happens with heavily "
        "protected/official music videos).",
    "Pobieram {u} -> {o}": "Downloading {u} -> {o}",
    "Pobieram (może to chwilę potrwać, w zależności od długości i jakości)...":
        "Downloading (this may take a while, depending on length and quality)...",
    "⬇ Pobierz": "⬇ Download",

    # --- FileListBox ---
    "+ Dodaj pliki": "+ Add files",
    "+ Dodaj folder": "+ Add folder",
    "Usuń zaznaczone": "Remove selected",
    "Wyczyść": "Clear",
    "💡 możesz też przeciągnąć pliki (lub foldery) z Eksploratora bezpośrednio na listę":
        "💡 you can also drag files (or folders) from Explorer straight onto the list",
}
