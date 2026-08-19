"""
download.py - Pobieranie filmów z linków (YouTube, Facebook i inne serwisy
obsługiwane przez yt-dlp) na dysk lokalny. Wymaga pakietu yt-dlp (patrz
requirements.txt) oraz ffmpeg - do złączenia osobnych strumieni wideo/audio
w jeden plik i do wyciągania samego dźwięku (MP3).

Facebook: część filmów (prywatne albo widoczne tylko po zalogowaniu) wymaga
ciasteczek zalogowanej przeglądarki - yt-dlp umie je pobrać bezpośrednio
z przeglądarki (cookies_browser), bez ręcznego eksportu pliku cookies.txt.

Zawsze pobierany jest pojedynczy film spod danego URL (noplaylist=True) -
nawet jeśli link prowadzi do playlisty/wpisu w niej, nie ściągamy całej reszty.
"""

import os
import shutil
import sys

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

QUALITY_PRESETS = {
    # Kończące "/best" (bez żadnego filtra) to sieć bezpieczeństwa - część
    # serwisów (np. Facebook) nie zawsze podaje wysokość dla swoich "sd"/"hd"
    # formatów, i/albo nie ma osobnego strumienia audio do złączenia z wideo -
    # bez tego selektor dopasowujący TYLKO do znanej wysokości (jak na YouTube)
    # kończył się "Requested format is not available" mimo że film ma dostępne
    # formaty, po prostu nie w kształcie, jakiego oczekiwał selektor.
    "Najlepsza jakość": "bv*[height<=2160]+ba/b[height<=2160]/best",
    "1080p": "bv*[height<=1080]+ba/b[height<=1080]/b[height<=1080]/best",
    "720p": "bv*[height<=720]+ba/b[height<=720]/b[height<=720]/best",
    "480p": "bv*[height<=480]+ba/b[height<=480]/b[height<=480]/best",
}
AUDIO_ONLY_LABEL = "Tylko dźwięk (MP3)"
QUALITY_LABELS = list(QUALITY_PRESETS.keys()) + [AUDIO_ONLY_LABEL]

BROWSERS = ["chrome", "edge", "firefox", "brave", "opera", "opera_gx"]
BROWSER_LABELS = {
    "chrome": "Chrome", "edge": "Edge", "firefox": "Firefox", "brave": "Brave",
    "opera": "Opera", "opera_gx": "Opera GX",
}


def _opera_gx_profile_dir():
    """Opera GX to osobna instalacja, nie profil zwykłej Opery - yt-dlp zna tylko
    "opera" i domyślnie szuka w katalogu zwykłej Opery (.../Opera Software/Opera
    Stable), więc na koncie z samą Operą GX (bez zwykłej Opery) kończyło się to
    błędem "could not find cookies database". Opera GX używa tego samego formatu
    profilu co zwykła Opera/Chromium, więc wystarczy podać browser="opera" razem
    z jawną ścieżką do katalogu GX (yt-dlp wtedy szuka tam, a nie w domyślnym)."""
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA", ""), "Opera Software", "Opera GX Stable")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/com.operasoftware.OperaGX")
    return os.path.expanduser("~/.config/opera-gx")  # Opera GX nie ma oficjalnej wersji na Linuksa

# YouTube ostatnio agresywnie blokuje pobieranie (HTTP 403) strumieni zwróconych
# dla "web" - różne "kliencie" (tak jakby request szedł z apki mobilnej/TV)
# omijają to inaczej i mają różne pułapy jakości w metadanych, ALE część z nich
# (tv_embedded, android_vr) zwraca w metadanych wysokie rozdzielczości, których
# URL-e i tak kończą się 403 przy właściwym pobieraniu (samo wylistowanie
# formatów nie gwarantuje, że da się je ściągnąć) - stąd próbujemy po kolei
# i lądujemy na "android" jako gwarantowanie działającym, ale ograniczonym
# przez YouTube do ok. 360p dla części (zwłaszcza mocno chronionych/oficjalnych)
# filmów. Pełne 1080p+ na takich filmach wymagałoby PO Token providera - próbowane,
# nie pomogło nawet z poprawnie działającym providerem (patrz historia commitów),
# więc na razie zostaje jako znane ograniczenie.
#
# To wszystko dotyczy TYLKO YouTube - dla innych serwisów (Facebook itd.)
# parametr "player_client" jest po prostu ignorowany przez yt-dlp, więc
# próbowanie tam kilku wariantów byłoby stratą czasu bez żadnej korzyści.
_YOUTUBE_CLIENT_ATTEMPTS = [["tv_embedded"], ["android_vr"], ["android"]]


def _is_youtube_url(url):
    return "youtube.com" in url or "youtu.be" in url


def _check_available():
    if yt_dlp is None:
        raise RuntimeError(
            "Pakiet yt-dlp nie jest zainstalowany. Zainstaluj: pip install yt-dlp "
            "(albo pip install -r requirements.txt)."
        )
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg nie jest zainstalowany lub nie jest w PATH - potrzebny do złączenia "
            "wideo+audio i do wyciągania samego dźwięku. Zobacz README.md."
        )


def _base_opts(cookies_browser=None, player_clients=None):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        # 20s zamiast czekania w nieskończoność na zawieszone połączenie - błąd
        # zamiast cichego "nic się nie dzieje" w GUI.
        "socket_timeout": 20,
        "extractor_args": {"youtube": {"player_client": player_clients or ["android", "web"]}},
    }
    if cookies_browser and cookies_browser != "Brak":
        if cookies_browser == "opera_gx":
            opts["cookiesfrombrowser"] = ("opera", _opera_gx_profile_dir())
        else:
            opts["cookiesfrombrowser"] = (cookies_browser,)
    return opts


def _is_blocked_error(exc):
    text = str(exc)
    return "403" in text or "Forbidden" in text or "not available" in text


def _snapshot_output_files(out_base):
    """Nazwy plików już obecnych przy out_base (dowolne rozszerzenie, np.
    "nazwa.mp4", "nazwa.f398.mp4") - punkt odniesienia sprzed próby pobrania,
    żeby później dało się bezpiecznie odróżnić "to zostawiła ta nieudana
    próba" od "to już tu było i nie ma z nami nic wspólnego"."""
    directory = os.path.dirname(out_base) or "."
    prefix = os.path.basename(out_base) + "."
    try:
        return {name for name in os.listdir(directory) if name.startswith(prefix)}
    except OSError:
        return set()


def _cleanup_new_files(out_base, before_snapshot):
    """Usuwa pliki, które pojawiły się przy out_base od czasu before_snapshot -
    zarówno osobne strumienie wideo z próby, która oberwała 403 w trakcie
    (np. "nazwa.f398.mp4", zanim doszło do złączenia z audio), jak i surowy
    plik pobrany PRZED konwersją, gdy sam post-processing (np. wyciąganie
    MP3) się nie powiedzie - w obu przypadkach yt-dlp nie ma szansy posprzątać
    po sobie tak jak robi to po pełnym sukcesie. Woła się tylko po nieudanej
    próbie, więc nigdy nie usuwa świeżo powstałego final_path po sukcesie -
    i nigdy nie rusza pliku, który już tam był przed wywołaniem download()."""
    directory = os.path.dirname(out_base) or "."
    for name in _snapshot_output_files(out_base) - before_snapshot:
        try:
            os.remove(os.path.join(directory, name))
        except OSError:
            pass


def get_info(url, cookies_browser=None):
    """Pobiera metadane linku bez ściągania pliku: tytuł i długość (sekundy,
    None jeśli nieznana - np. transmisja na żywo). Zgłasza RuntimeError przy
    złym linku albo braku dostępu (np. film wymaga logowania na Facebooku)."""
    _check_available()
    try:
        with yt_dlp.YoutubeDL(_base_opts(cookies_browser)) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(f"Nie udało się odczytać linku: {e}") from e

    if not info:
        raise RuntimeError("Nie udało się odczytać informacji o linku.")
    return {
        "title": info.get("title") or "(bez tytułu)",
        "duration": info.get("duration"),
        "uploader": info.get("uploader"),
    }


def download(url, output_path, quality_label="Najlepsza jakość", cookies_browser=None,
             progress_hook=None):
    """Pobiera pojedynczy film spod url. Rozszerzenie ostatecznego pliku zależy
    od wyboru: dla AUDIO_ONLY_LABEL zawsze .mp3, w przeciwnym razie rozszerzenie
    z output_path (domyślnie .mp4, jeśli go nie podano).

    Niektóre filmy z YouTube (zwłaszcza mocno chronione, oficjalne teledyski)
    są ograniczone do ok. 360p niezależnie od wybranej jakości, blokując (HTTP
    403) URL-e wyższych rozdzielczości mimo że są wylistowane w metadanych -
    to ograniczenie samego YouTube/yt-dlp, nie błąd w tej funkcji. Dla linków
    z YouTube próbujemy więc po kolei kilku "klientów" (_YOUTUBE_CLIENT_ATTEMPTS)
    i zwracamy to, co faktycznie udało się ściągnąć; inne serwisy (np. Facebook)
    nie mają tego problemu, więc dostają tylko jedną, normalną próbę.

    progress_hook(dict), jeśli podany, jest wywoływane przez yt-dlp w trakcie
    pobierania (surowy status - patrz yt_dlp.YoutubeDL 'progress_hooks').
    Wywoływane synchronicznie w wątku, w którym uruchomiono download().

    Zwraca (final_path, achieved_height, was_blocked):
    - achieved_height: None dla samego dźwięku albo gdy YouTube go nie ujawnił.
    - was_blocked: True, jeśli pierwsza (najbardziej obiecująca pod względem
      jakości) próba została odrzucona (HTTP 403) i zadziałał dopiero fallback -
      odróżnia "YouTube ograniczył ten film" od "ten film po prostu nie ma
      wyższej rozdzielczości w źródle" (np. stare, niskiej jakości nagrania)."""
    _check_available()
    out_base, out_ext = os.path.splitext(output_path)

    is_audio = quality_label == AUDIO_ONLY_LABEL
    if is_audio:
        final_path = out_base + ".mp3"
    else:
        final_path = out_base + (out_ext or ".mp4")

    attempts = _YOUTUBE_CLIENT_ATTEMPTS if _is_youtube_url(url) else [None]
    before_snapshot = _snapshot_output_files(out_base)

    last_error = None
    for attempt_index, clients in enumerate(attempts):
        opts = _base_opts(cookies_browser, player_clients=clients)
        opts["outtmpl"] = out_base + ".%(ext)s"
        opts["overwrites"] = True
        if progress_hook:
            opts["progress_hooks"] = [progress_hook]

        if is_audio:
            opts["format"] = "ba/b"
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        else:
            opts["format"] = QUALITY_PRESETS.get(quality_label, QUALITY_PRESETS["Najlepsza jakość"])
            opts["merge_output_format"] = out_ext.lstrip(".") or "mp4"

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            achieved_height = None if is_audio else info.get("height")
            return final_path, achieved_height, attempt_index > 0
        except yt_dlp.utils.DownloadError as e:
            last_error = e
            _cleanup_new_files(out_base, before_snapshot)
            if _is_blocked_error(e):
                continue
            raise RuntimeError(f"Błąd pobierania: {e}") from e

    if len(attempts) > 1:
        raise RuntimeError(f"Błąd pobierania (YouTube zablokował wszystkie wypróbowane sposoby): {last_error}")
    raise RuntimeError(f"Błąd pobierania: {last_error}")
