"""
media.py - Konwersje audio/wideo przez ffmpeg (musi być zainstalowany w systemie,
patrz README.md). Jedna funkcja convert() obsługuje większość par formatów -
ffmpeg sam rozpoznaje kontener/kodek na podstawie rozszerzenia pliku wyjściowego,
w tym wyciąganie audio z wideo (np. input.mp4 -> output.mp3).
"""

import array
import json
import os
import shutil
import subprocess
import sys

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".webm", ".mkv"}

_AUDIO_CODEC_BY_EXT = {
    ".mp3": "libmp3lame",
    ".aac": "aac", ".m4a": "aac", ".mp4": "aac", ".mov": "aac", ".mkv": "aac", ".webm": "libvorbis",
    ".wav": "pcm_s16le",
    ".flac": "flac",
    ".ogg": "libvorbis",
}

# Na Windows subprocess.run() bez tego domyślnie miga czarnym oknem konsoli
# przy każdym wywołaniu ffmpeg/ffprobe - istotne przy uruchamianiu z GUI (pythonw).
_NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def _check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg nie jest zainstalowany lub nie jest w PATH. "
            "Zobacz README.md - sekcja instalacji."
        )


def _check_ffprobe():
    if shutil.which("ffprobe") is None:
        raise RuntimeError(
            "ffprobe nie jest zainstalowany lub nie jest w PATH "
            "(zwykle instalowany razem z ffmpeg)."
        )


def _run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, **_NO_WINDOW)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg błąd:\n{result.stderr[-2000:]}")


def get_duration(input_path):
    """Zwraca długość pliku audio/wideo w sekundach (wymaga ffprobe)."""
    _check_ffprobe()
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", input_path],
        capture_output=True, text=True, **_NO_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe błąd:\n{result.stderr[-2000:]}")
    return float(result.stdout.strip())


def get_waveform_peaks(input_path, num_points=600, track_index=0):
    """Dekoduje daną ścieżkę audio (track_index - który strumień audio, 0 = pierwszy)
    do mono/8kHz i zwraca num_points wartości [0..1] (szczytowa amplituda w danym
    przedziale czasu) do narysowania przebiegu fali. Wymaga ffmpeg. Zgłasza
    RuntimeError, jeśli plik nie ma takiej ścieżki audio."""
    _check_ffmpeg()
    cmd = ["ffmpeg", "-v", "error", "-i", input_path, "-map", f"0:a:{track_index}?",
           "-ac", "1", "-ar", "8000", "-f", "s16le", "pipe:1"]
    result = subprocess.run(cmd, capture_output=True, **_NO_WINDOW)
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError("Brak takiej ścieżki audio w tym pliku (albo błąd ffmpeg przy jej odczycie).")

    samples = array.array("h")
    usable_len = len(result.stdout) - (len(result.stdout) % 2)
    samples.frombytes(result.stdout[:usable_len])
    if not samples:
        raise RuntimeError("Pusta ścieżka audio.")

    n = len(samples)
    bucket = max(1, n // num_points)
    peaks = []
    for i in range(0, n, bucket):
        chunk = samples[i:i + bucket]
        peaks.append(max(abs(min(chunk)), abs(max(chunk))) / 32768.0)
    return peaks


def list_audio_tracks(input_path):
    """Zwraca listę ścieżek audio w pliku: [{'index': 0, 'label': 'Ścieżka 1'}, ...].
    'index' to numer ścieżki liczony tylko wśród strumieni audio (do użycia jako
    0:a:INDEX w ffmpeg) - nie mylić z bezwzględnym indeksem strumienia w pliku.
    Wymaga ffprobe. Pusta lista, jeśli plik nie ma żadnej ścieżki audio."""
    _check_ffprobe()
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream_tags=title,language",
         "-of", "json", input_path],
        capture_output=True, text=True, **_NO_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe błąd:\n{result.stderr[-2000:]}")

    data = json.loads(result.stdout or "{}")
    streams = data.get("streams", [])
    tracks = []
    for i, s in enumerate(streams):
        tags = s.get("tags", {})
        title = tags.get("title") or tags.get("language")
        label = f"Ścieżka {i + 1}" + (f" ({title})" if title else "")
        tracks.append({"index": i, "label": label})
    return tracks


def build_mixed_preview(input_path, track_gains, output_path, start=None, end=None):
    """Tworzy plik (z obrazem, jeśli input go ma) z audio będącym miksem wszystkich
    ścieżek input_path przemnożonych przez odpowiadające im wzmocnienia z listy
    track_gains (0.0 = wyciszona, 1.0 = normalna głośność, >1.0 = wzmocniona),
    opcjonalnie przyciętym do zakresu [start, end] (jak w trim()). Kodek audio
    dobierany jest po rozszerzeniu output_path; wideo (jeśli obecne i output_path
    ma rozszerzenie wideo) jest kopiowane bezstratnie."""
    _check_ffmpeg()
    if not track_gains:
        raise ValueError("Brak ścieżek audio do zmiksowania.")
    out_ext = os.path.splitext(output_path)[1].lower()

    cmd = ["ffmpeg", "-y"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if end is not None:
        cmd += ["-to", str(end)]
    cmd += ["-i", input_path]

    n = len(track_gains)
    parts = [f"[0:a:{i}]volume={gain}[a{i}]" for i, gain in enumerate(track_gains)]
    if n > 1:
        inputs = "".join(f"[a{i}]" for i in range(n))
        parts.append(f"{inputs}amix=inputs={n}:duration=longest:dropout_transition=0[aout]")
        audio_map = "[aout]"
    else:
        audio_map = "[a0]"

    cmd += ["-filter_complex", ";".join(parts), "-map", audio_map]
    if out_ext in VIDEO_EXTS:
        cmd += ["-map", "0:v?", "-c:v", "copy"]
    cmd += ["-c:a", _AUDIO_CODEC_BY_EXT.get(out_ext, "aac"), output_path]
    _run(cmd)


def convert(input_path, output_path, extra_args=None):
    """Ogólna konwersja audio<->audio, wideo<->wideo, wideo->audio (wyciąga ścieżkę dźwiękową)."""
    _check_ffmpeg()
    cmd = ["ffmpeg", "-y", "-i", input_path]
    if extra_args:
        cmd += extra_args
    cmd.append(output_path)
    _run(cmd)


def trim(input_path, output_path, start, end):
    """start/end w formacie 'HH:MM:SS' lub sekundach, np. trim(in, out, '00:00:10', '00:00:30')."""
    _check_ffmpeg()
    cmd = ["ffmpeg", "-y", "-i", input_path, "-ss", str(start), "-to", str(end),
           "-c", "copy", output_path]
    _run(cmd)


def extract_audio(input_video, output_audio):
    """np. extract_audio('film.mp4', 'sciezka.mp3')"""
    convert(input_video, output_audio)


def extract_audio_clip(input_path, output_path, start=None, end=None):
    """Wyciąga ścieżkę dźwiękową (format wyjściowy wg rozszerzenia output_path,
    np. MP3), opcjonalnie przycinając do zakresu [start, end] (jak w trim() -
    'HH:MM:SS' albo sekundy, każdy z nich opcjonalny). W przeciwieństwie do
    trim() zawsze przekodowuje audio (nie -c copy), więc działa też między
    różnymi formatami (np. wideo MP4 -> MP3), nie tylko przy przycinaniu tego
    samego formatu."""
    _check_ffmpeg()
    cmd = ["ffmpeg", "-y", "-i", input_path]
    if start is not None:
        cmd += ["-ss", str(start)]
    if end is not None:
        cmd += ["-to", str(end)]
    cmd += ["-vn", output_path]
    _run(cmd)


def to_gif(input_video, output_gif, fps=10, width=480):
    """Konwertuje fragment/całość wideo na animowany GIF."""
    _check_ffmpeg()
    vf = f"fps={fps},scale={width}:-1:flags=lanczos"
    cmd = ["ffmpeg", "-y", "-i", input_video, "-vf", vf, output_gif]
    _run(cmd)


def normalize_audio(input_path, output_path):
    """Wyrównuje głośność do standardu EBU R128 (loudnorm)."""
    convert(input_path, output_path, extra_args=["-af", "loudnorm"])


def compress_video(input_path, output_path, crf=28):
    """Niższy crf = lepsza jakość / większy plik. 18-28 to sensowny zakres."""
    convert(input_path, output_path, extra_args=["-vcodec", "libx264", "-crf", str(crf)])
