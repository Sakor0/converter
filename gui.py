#!/usr/bin/env python3
"""
gui.py - Graficzny interfejs do local_converter.

Ta sama logika co convert.py (moduły w converters/), tylko okienkowo,
z podglądem postępu na żywo (log na dole okna). Wymaga dodatkowo
customtkinter - patrz requirements.txt.

Uruchomienie:
    python gui.py
"""

import json
import os
import sys
import tempfile
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk
import vlc
from tkinterdnd2 import DND_FILES, TkinterDnD

from converters import images, media, documents, data as data_mod, archives, download as download_mod
from convert import do_convert, output_format_options


def _bootstrap_bundled_path():
    """Gdy uruchomione jako spakowany .exe (PyInstaller), dokłada folder obok
    programu na początek PATH - to tam ląduje dołączony ffmpeg/ffprobe (patrz
    build_release.py). Bez tego shutil.which("ffmpeg") w converters/ nic by nie
    znalazł i spakowana wersja wymagałaby ręcznie zainstalowanego ffmpeg tak
    samo jak uruchomienie z kodu źródłowego - a to przekreślałoby sens
    pakowania "jedna paczka, od razu działa"."""
    if getattr(sys, "frozen", False):
        bundled_dir = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
        os.environ["PATH"] = bundled_dir + os.pathsep + os.environ.get("PATH", "")


_bootstrap_bundled_path()

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# --------------------------------------------------------------- settings --
# Ustawienia (m.in. ostatnio użyty folder zapisu) trzymane per-komputer w profilu
# użytkownika, niezależnie od tego skąd program jest uruchamiany/skopiowany.
_SETTINGS_DIR = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~/.config"), "local_converter")
_SETTINGS_PATH = os.path.join(_SETTINGS_DIR, "settings.json")


def _load_settings():
    try:
        with open(_SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_settings(settings):
    os.makedirs(_SETTINGS_DIR, exist_ok=True)
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def get_default_save_dir():
    """Ostatnio użyty folder zapisu (zapamiętany trwale), a jeśli go nie ma - Pulpit."""
    last_dir = _load_settings().get("last_output_dir")
    if last_dir and os.path.isdir(last_dir):
        return last_dir
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    return desktop if os.path.isdir(desktop) else os.path.expanduser("~")


def set_last_output_dir(directory):
    if not directory or not os.path.isdir(directory):
        return
    settings = _load_settings()
    settings["last_output_dir"] = directory
    _save_settings(settings)


# --------------------------------------------------------------- helpers ---
def ext_of(path):
    return os.path.splitext(path)[1].lower()


def suggest_output(input_path, suffix="_wynik", new_ext=None):
    base, ext = os.path.splitext(input_path)
    return f"{base}{suffix}{new_ext or ext}"


_INVALID_FILENAME_CHARS = '\\/:*?"<>|'


def sanitize_filename(name, max_len=120):
    """Tytuł filmu -> bezpieczna nazwa pliku (bez znaków niedozwolonych
    w nazwach plików na Windows, przycięta do rozsądnej długości)."""
    cleaned = "".join("_" if ch in _INVALID_FILENAME_CHARS else ch for ch in name)
    cleaned = cleaned.strip().strip(".") or "pobrany_film"
    return cleaned[:max_len]


def format_hhmmss(seconds):
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_time_precise(seconds):
    """Format z ułamkiem sekundy (HH:MM:SS.ss) - do pól synchronizowanych
    z przeciąganiem uchwytów na przebiegu fali."""
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:05.2f}"


def parse_time_to_seconds(text):
    """Odwrotność format_time_precise/format_hhmmss - przyjmuje HH:MM:SS(.ss)
    albo samą liczbę sekund. Zgłasza ValueError przy niepoprawnym formacie."""
    text = text.strip()
    if not text:
        raise ValueError("puste pole czasu")
    if ":" in text:
        parts = [float(p) for p in text.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0.0)
        h, m, s = parts[-3:]
        return h * 3600 + m * 60 + s
    return float(text)


def open_with_default_app(path):
    if sys.platform == "win32":
        os.startfile(path)  # nosec - użytkownik sam wskazuje własny plik
    elif sys.platform == "darwin":
        import subprocess
        subprocess.run(["open", path])
    else:
        import subprocess
        subprocess.run(["xdg-open", path])


def resolve_output_path(raw_path):
    """Jeśli użytkownik wpisał samą nazwę pliku/folderu (bez ścieżki), dokłada
    domyślny/ostatnio użyty folder zamiast polegać na niejednoznacznym cwd
    procesu - to właśnie ten przypadek potrafił wcześniej 'zawieszać' operację
    na nieprzewidywalnym/niezapisywalnym katalogu roboczym."""
    raw_path = raw_path.strip()
    if os.path.isabs(raw_path):
        path = raw_path
        set_last_output_dir(os.path.dirname(path))
    else:
        path = os.path.join(get_default_save_dir(), raw_path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return path


def browse_open(entry, filetypes=None):
    path = filedialog.askopenfilename(filetypes=filetypes or [("Wszystkie pliki", "*.*")])
    if path:
        entry.delete(0, "end")
        entry.insert(0, path)


def parse_dnd_files(data):
    """Parsuje ścieżki ze zdarzenia <<Drop>> tkinterdnd2 - pliki są oddzielone
    spacją, a te zawierające spacje w nazwie są owinięte w {}."""
    paths, token, in_brace = [], "", False
    for ch in data:
        if ch == "{":
            in_brace = True
            token = ""
        elif ch == "}":
            in_brace = False
            paths.append(token)
            token = ""
        elif ch == " " and not in_brace:
            if token:
                paths.append(token)
                token = ""
        else:
            token += ch
    if token:
        paths.append(token)
    return paths


def enable_file_drop(widget, on_paths, single=True):
    """Zamienia widget w cel przeciągania plików/folderów z Eksploratora.
    on_paths dostaje listę ścieżek (jednoelementową, jeśli single=True)."""
    widget.drop_target_register(DND_FILES)

    def handler(event):
        paths = parse_dnd_files(event.data)
        if paths:
            on_paths(paths[:1] if single else paths)

    widget.dnd_bind("<<Drop>>", handler)


def browse_save(entry, defaultextension="", filetypes=None, initialfile=""):
    path = filedialog.asksaveasfilename(
        defaultextension=defaultextension,
        filetypes=filetypes or [("Wszystkie pliki", "*.*")],
        initialfile=initialfile,
        initialdir=get_default_save_dir(),
    )
    if path:
        entry.delete(0, "end")
        entry.insert(0, path)
        set_last_output_dir(os.path.dirname(path))


def browse_dir(entry):
    path = filedialog.askdirectory(initialdir=get_default_save_dir())
    if path:
        entry.delete(0, "end")
        entry.insert(0, path)
        set_last_output_dir(path)


def labeled_row(parent, row, label_text):
    ctk.CTkLabel(parent, text=label_text).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=6)


# ---------------------------------------------------------- FileListBox ---
class FileListBox(ctk.CTkFrame):
    """Lista wielu plików (i opcjonalnie folderów) z dodawaniem/usuwaniem/kolejnością."""

    def __init__(self, master, filetypes=None, allow_folders=False, height=6):
        super().__init__(master, fg_color="transparent")
        self.filetypes = filetypes or [("Wszystkie pliki", "*.*")]
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        list_frame = ctk.CTkFrame(self)
        list_frame.grid(row=0, column=0, sticky="nsew")
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        self.listbox = tk.Listbox(
            list_frame, height=height, activestyle="none",
            bg="#2b2b2b", fg="white", selectbackground="#1f6aa5",
            highlightthickness=0, borderwidth=0, selectmode="extended",
        )
        self.listbox.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        enable_file_drop(self.listbox, self._insert_paths, single=False)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=1, column=0, sticky="w", pady=(6, 0))
        ctk.CTkButton(btns, text="+ Dodaj pliki", width=110, command=self._add_files).pack(side="left", padx=(0, 6))
        if allow_folders:
            ctk.CTkButton(btns, text="+ Dodaj folder", width=110, command=self._add_folder).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text="↑", width=32, command=self._move_up).pack(side="left", padx=(0, 2))
        ctk.CTkButton(btns, text="↓", width=32, command=self._move_down).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text="Usuń zaznaczone", width=130, fg_color="gray30",
                      command=self._remove_selected).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text="Wyczyść", width=90, fg_color="gray30",
                      command=self._clear).pack(side="left")

        ctk.CTkLabel(self, text="💡 możesz też przeciągnąć pliki (lub foldery) z Eksploratora bezpośrednio na listę",
                     text_color="gray60", font=ctk.CTkFont(size=11)).grid(row=2, column=0, sticky="w", pady=(4, 0))

    def _insert_paths(self, paths):
        for p in paths:
            self.listbox.insert("end", p)

    def _add_files(self):
        self._insert_paths(filedialog.askopenfilenames(filetypes=self.filetypes))

    def _add_folder(self):
        path = filedialog.askdirectory()
        if path:
            self._insert_paths([path])

    def _remove_selected(self):
        for i in reversed(self.listbox.curselection()):
            self.listbox.delete(i)

    def _clear(self):
        self.listbox.delete(0, "end")

    def _move_up(self):
        for i in list(self.listbox.curselection()):
            if i == 0:
                continue
            text = self.listbox.get(i)
            self.listbox.delete(i)
            self.listbox.insert(i - 1, text)
            self.listbox.selection_set(i - 1)

    def _move_down(self):
        for i in reversed(list(self.listbox.curselection())):
            if i == self.listbox.size() - 1:
                continue
            text = self.listbox.get(i)
            self.listbox.delete(i)
            self.listbox.insert(i + 1, text)
            self.listbox.selection_set(i + 1)

    def get_paths(self):
        return list(self.listbox.get(0, "end"))


# ------------------------------------------------------------------ VideoPlayer
class VideoPlayer:
    """Cienka otoczka na python-vlc: odtwarzanie/pauza/seek osadzone w widgecie
    Tkinter (surface_widget). Jeden silnik dla audio i wideo (VLC pokazuje po
    prostu czarną powierzchnię, gdy plik ma tylko dźwięk)."""

    def __init__(self, surface_widget):
        self._instance = vlc.Instance("--quiet", "--no-video-title-show")
        self._player = self._instance.media_player_new()
        if sys.platform == "win32":
            self._player.set_hwnd(surface_widget.winfo_id())
        elif sys.platform == "darwin":
            self._player.set_nsobject(surface_widget.winfo_id())
        else:
            self._player.set_xwindow(surface_widget.winfo_id())

    def load(self, path):
        self._player.set_media(self._instance.media_new(path))

    def play(self):
        self._player.play()

    def pause(self):
        self._player.set_pause(1)

    def stop(self):
        self._player.stop()

    def is_playing(self):
        return bool(self._player.is_playing())

    def get_time(self):
        """Aktualna pozycja odtwarzania w sekundach, albo None jeśli nieznana."""
        t = self._player.get_time()
        return t / 1000.0 if t is not None and t >= 0 else None

    def set_time(self, seconds):
        self._player.set_time(int(max(0.0, seconds) * 1000))

    def get_length(self):
        length = self._player.get_length()
        return length / 1000.0 if length and length > 0 else None

    def release(self):
        try:
            self._player.stop()
        except Exception:
            pass
        try:
            self._player.release()
            self._instance.release()
        except Exception:
            pass


# ------------------------------------------------------------ WaveformSelector
class WaveformSelector(ctk.CTkFrame):
    """Wizualny wybór zakresu przycięcia na przebiegu fali dźwiękowej (jak w
    programach do montażu - DaVinci itp.). Przeciągnij lewy/prawy uchwyt, żeby
    zmienić start/koniec, albo środek zaznaczenia, żeby przesunąć cały zakres
    bez zmiany jego długości. on_change(start, end) wywoływane na żywo w trakcie
    przeciągania (sekundy, float).

    interactive=False robi z tego widgetu tylko podgląd (bez uchwytów/przeciągania)
    - używane do miniaturowych przebiegów fali poszczególnych ścieżek w mikserze,
    gdzie sam zakres przycięcia jest wspólny i ustawiany na głównym przebiegu."""

    HANDLE_HIT_PX = 8
    MIN_SPAN = 0.05
    SNAP_HIT_PX = 10

    def __init__(self, master, height=90, on_change=None, on_seek=None, on_seek_end=None, interactive=True):
        super().__init__(master, fg_color="transparent")
        self.on_change = on_change
        self.on_seek = on_seek
        self.on_seek_end = on_seek_end
        self.interactive = interactive
        self.duration = 0.0
        self.start = 0.0
        self.end = 0.0
        self.peaks = []
        self.playhead = None
        self._playhead_item = None
        self._playhead_handle = None
        self._drag_mode = None
        self._drag_offset = 0.0
        self._resize_job = None
        self._last_size = (0, 0)

        self.canvas = tk.Canvas(self, height=height, bg="#1a1a1a", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<Configure>", self._on_configure)
        if interactive:
            self.canvas.bind("<Button-1>", self._on_press)
            self.canvas.bind("<B1-Motion>", self._on_drag)
            self.canvas.bind("<ButtonRelease-1>", self._on_release)

    def set_waveform(self, peaks, duration):
        self.peaks = peaks
        self.duration = max(duration, 0.001)
        self.start = 0.0
        self.end = self.duration
        self._redraw()

    def set_selection(self, start, end):
        if not self.duration:
            return
        start = max(0.0, min(start, self.duration))
        end = max(0.0, min(end, self.duration))
        if end < start:
            start, end = end, start
        self.start, self.end = start, end
        self._redraw()

    def set_playhead(self, seconds):
        """Przesuwa tylko linię (i uchwyt) pozycji odtwarzania (tanie, bez
        pełnego przerysowania) - do wywoływania często (co ~100ms) podczas
        odtwarzania, oraz na żywo podczas przeciągania samego uchwytu."""
        self.playhead = seconds
        if self._playhead_item is None or not self.duration:
            self._redraw()
            return
        x = self._time_to_x(seconds)
        self.canvas.coords(self._playhead_item, x, 0, x, self.canvas.winfo_height())
        if self._playhead_handle is not None:
            self.canvas.coords(self._playhead_handle, x - 6, 0, x + 6, 0, x, 10)

    def clear(self, message="wybierz plik, żeby zobaczyć przebieg fali"):
        self.peaks = []
        self.duration = 0.0
        self.start = 0.0
        self.end = 0.0
        self.playhead = None
        self._placeholder_message = message
        self._redraw()

    # ----------------------------------------------------------- resize --
    def _on_configure(self, event):
        """Przerysowanie na <Configure> jest kosztowne (usuwa i odtwarza
        wszystkie słupki), a podczas ręcznego przeciągania krawędzi okna
        zdarzenie to potrafi lecieć dziesiątki razy na sekundę - bez debounce'a
        to właśnie ono odpowiadało za odczuwalne lagi przy resize (zwłaszcza
        z kilkoma przebiegami fali naraz w mikserze). Przerysowujemy dopiero
        gdy rozmiar się faktycznie ustabilizuje."""
        size = (event.width, event.height)
        if size == self._last_size:
            return
        self._last_size = size
        if self._resize_job is not None:
            self.canvas.after_cancel(self._resize_job)
        self._resize_job = self.canvas.after(60, self._do_resize_redraw)

    def _do_resize_redraw(self):
        self._resize_job = None
        if self.canvas.winfo_exists():
            self._redraw()

    # -------------------------------------------------------------- draw --
    def _x_to_time(self, x):
        w = max(1, self.canvas.winfo_width())
        return max(0.0, min(self.duration, (x / w) * self.duration))

    def _time_to_x(self, t):
        w = max(1, self.canvas.winfo_width())
        return (t / self.duration) * w if self.duration else 0

    def _redraw(self):
        self.canvas.delete("all")
        self._playhead_item = None
        self._playhead_handle = None
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w <= 1 or h <= 1:
            return

        if not self.peaks:
            msg = getattr(self, "_placeholder_message", "brak podglądu ścieżki dźwiękowej")
            self.canvas.create_text(w / 2, h / 2, text=msg, fill="gray50", font=("Segoe UI", 10))
            return

        mid = h / 2
        n = len(self.peaks)
        bar_w = w / n
        x0, x1 = self._time_to_x(self.start), self._time_to_x(self.end)

        if self.interactive:
            self.canvas.create_rectangle(x0, 0, x1, h, fill="#2d5578", outline="")

        for i, peak in enumerate(self.peaks):
            x = i * bar_w
            bar_h = max(1.0, peak * (h / 2 - 4))
            in_selection = x0 <= x <= x1
            color = "#7fb8e8" if (self.interactive and in_selection) else "#4a4a4a"
            self.canvas.create_line(x, mid - bar_h, x, mid + bar_h, fill=color, width=max(1, bar_w * 0.8))

        if self.interactive:
            for x in (x0, x1):
                self.canvas.create_line(x, 0, x, h, fill="#ffffff", width=2)
                self.canvas.create_polygon(x - 6, 0, x + 6, 0, x, 10, fill="#ffffff")

        if self.playhead is not None:
            xp = self._time_to_x(self.playhead)
            self._playhead_item = self.canvas.create_line(xp, 0, xp, h, fill="#ffcc00", width=2)
            if self.interactive:
                self._playhead_handle = self.canvas.create_polygon(
                    xp - 6, 0, xp + 6, 0, xp, 10, fill="#ffcc00")

    # ---------------------------------------------------------- dragging --
    def _on_press(self, event):
        if not self.duration:
            return
        if self.playhead is not None:
            xp = self._time_to_x(self.playhead)
            if abs(event.x - xp) <= self.HANDLE_HIT_PX:
                self._drag_mode = "playhead"
                self._seek_to(self._x_to_time(event.x))
                return
        x0, x1 = self._time_to_x(self.start), self._time_to_x(self.end)
        if abs(event.x - x0) <= self.HANDLE_HIT_PX:
            self._drag_mode = "start"
        elif abs(event.x - x1) <= self.HANDLE_HIT_PX:
            self._drag_mode = "end"
        elif x0 < event.x < x1:
            self._drag_mode = "range"
            self._drag_offset = self._x_to_time(event.x) - self.start
        else:
            self._drag_mode = "start" if abs(event.x - x0) < abs(event.x - x1) else "end"
            self._on_drag(event)

    def _seek_to(self, t):
        """Przesuwa uchwyt odtwarzania na żywo w trakcie przeciągania i zgłasza
        nową pozycję na zewnątrz (on_seek) - to on_seek odpowiada za faktyczne
        przewinięcie odtwarzacza, żeby dało się dokładnie namierzyć klatkę/moment
        cięcia."""
        t = max(0.0, min(self.duration, t))
        self.set_playhead(t)
        if self.on_seek:
            self.on_seek(t)

    def _on_drag(self, event):
        if self._drag_mode is None or not self.duration:
            return
        t = self._x_to_time(event.x)
        if self._drag_mode == "playhead":
            self._seek_to(t)
            return
        if self.playhead is not None and self._drag_mode in ("start", "end"):
            snap_x = self._time_to_x(self.playhead)
            if abs(event.x - snap_x) <= self.SNAP_HIT_PX:
                t = self.playhead
        if self._drag_mode == "start":
            self.start = max(0.0, min(t, self.end - self.MIN_SPAN))
        elif self._drag_mode == "end":
            self.end = min(self.duration, max(t, self.start + self.MIN_SPAN))
        elif self._drag_mode == "range":
            span = self.end - self.start
            new_start = max(0.0, min(self.duration - span, t - self._drag_offset))
            self.start, self.end = new_start, new_start + span
        self._redraw()
        if self.on_change:
            self.on_change(self.start, self.end)

    def _on_release(self, _event):
        if self._drag_mode == "playhead" and self.on_seek_end:
            self.on_seek_end()
        self._drag_mode = None


# ------------------------------------------------------------ SegmentedStack
class SegmentedStack(ctk.CTkFrame):
    """Przełącznik pod-operacji w obrębie jednej kategorii (np. Trim / To-GIF / ...).

    Podstrony są budowane leniwie (dopiero przy pierwszym wejściu) i chowane przez
    grid_remove() zamiast samego tkraise() - inaczej wszystkie podstrony wszystkich
    kategorii (dziesiątki widgetów każda) uczestniczyłyby w przeliczaniu layoutu
    przy każdym ręcznym zmienianiu rozmiaru okna, co odczuwalnie laguje."""

    def __init__(self, master, pages):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._builders = pages
        self.frames = {}

        names = list(pages.keys())
        self.seg = ctk.CTkSegmentedButton(self, values=names, command=self._switch)
        self.seg.set(names[0])
        self.seg.grid(row=0, column=0, sticky="w", pady=(0, 14))

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.grid(row=1, column=0, sticky="nsew")
        self.container.grid_columnconfigure(0, weight=1)
        self.container.grid_rowconfigure(0, weight=1)

        self._switch(names[0])

    def _switch(self, name):
        if name not in self.frames:
            frame = self._builders[name](self.container)
            self.frames[name] = frame
        for other_name, other_frame in self.frames.items():
            if other_name != name:
                other_frame.grid_remove()
        self.frames[name].grid(row=0, column=0, sticky="nsew")


# ==================================================================== APP ==
class App(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)
        self.title("local_converter")
        self.geometry("920x680")
        self.minsize(820, 600)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)  # treść zakładki dostaje całą wolną przestrzeń
        self.grid_rowconfigure(1, weight=0)  # rozwijany log - domyślnie zwinięty (brak wysokości)
        self.grid_rowconfigure(2, weight=0)  # smukły pasek statusu - zawsze widoczny

        self._video_players = []  # do zwolnienia zasobów VLC przy zamykaniu okna
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_sidebar()
        self._build_content()
        self._build_status_bar()

        self.show_page("Konwersja")

    def register_video_player(self, player):
        self._video_players.append(player)

    def _on_close(self):
        for player in self._video_players:
            player.release()
        self.destroy()

    # ------------------------------------------------------------- sidebar
    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=190, corner_radius=0)
        sidebar.grid(row=0, column=0, rowspan=3, sticky="nsw")
        sidebar.grid_propagate(False)

        ctk.CTkLabel(sidebar, text="local_converter", font=ctk.CTkFont(size=18, weight="bold")).pack(
            padx=16, pady=(20, 4), anchor="w"
        )
        ctk.CTkLabel(sidebar, text="wszystko lokalnie, offline", text_color="gray60",
                     font=ctk.CTkFont(size=11)).pack(padx=16, pady=(0, 20), anchor="w")

        pages = ["Konwersja", "Obrazy", "Audio / Wideo", "Dokumenty (PDF)", "Archiwa", "Pobierz z linku"]
        self.sidebar_buttons = {}
        for name in pages:
            btn = ctk.CTkButton(sidebar, text=name, anchor="w", fg_color="transparent",
                                 command=lambda n=name: self.show_page(n))
            btn.pack(fill="x", padx=10, pady=4)
            self.sidebar_buttons[name] = btn

    # ------------------------------------------------------------- content
    def _build_content(self):
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=20, pady=(20, 8))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        # Kategorie budowane leniwie (dopiero przy pierwszym wejściu), a nieaktywne
        # chowane przez grid_remove() - patrz komentarz w SegmentedStack.
        self._page_builders = {
            "Konwersja": build_convert_page,
            "Obrazy": build_images_page,
            "Audio / Wideo": build_media_page,
            "Dokumenty (PDF)": build_documents_page,
            "Archiwa": build_archives_page,
            "Pobierz z linku": build_download_page,
        }
        self.pages = {}

    def show_page(self, name):
        if name not in self.pages:
            frame = self._page_builders[name](self.content, self)
            self.pages[name] = frame
        for other_name, other_frame in self.pages.items():
            if other_name != name:
                other_frame.grid_remove()
        self.pages[name].grid(row=0, column=0, sticky="nsew")
        for btn_name, btn in self.sidebar_buttons.items():
            btn.configure(fg_color=("gray75", "gray25") if btn_name == name else "transparent")

    # ------------------------------------------------------------ status --
    _DOT_IDLE = "gray50"
    _DOT_BUSY = "#3b8ed0"
    _DOT_OK = "#2fa572"
    _DOT_ERROR = "#e04f4f"

    def _build_status_bar(self):
        # Rozwijany log - domyślnie zwinięty (grid_remove), więc nie zajmuje
        # miejsca dopóki ktoś go nie otworzy strzałką na pasku statusu. Ma
        # stałą, niewielką wysokość (nie rozciąga się z oknem) - to tu trafiają
        # wszystkie wpisy, pasek statusu pokazuje tylko ostatni.
        self.log_drawer = ctk.CTkFrame(self)
        self.log_drawer.grid(row=1, column=1, sticky="ew", padx=20, pady=(0, 6))
        self.log_drawer.grid_columnconfigure(0, weight=1)
        self.log_box = ctk.CTkTextbox(self.log_drawer, state="disabled", height=140,
                                       font=ctk.CTkFont(family="Consolas", size=11))
        self.log_box.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        self.log_drawer.grid_remove()
        self._log_visible = False

        # Smukły pasek statusu - stała wysokość, zawsze widoczny w wolnym
        # miejscu na dole okna zamiast wielkiego terminala.
        bar = ctk.CTkFrame(self, height=36, corner_radius=8)
        bar.grid(row=2, column=1, sticky="ew", padx=20, pady=(0, 16))
        bar.grid_propagate(False)
        bar.grid_columnconfigure(1, weight=1)

        self.status_dot = ctk.CTkLabel(bar, text="●", text_color=self._DOT_IDLE,
                                        font=ctk.CTkFont(size=13), width=14)
        self.status_dot.grid(row=0, column=0, padx=(12, 6), pady=4)

        self.status_label = ctk.CTkLabel(bar, text="Gotowy.", anchor="w")
        self.status_label.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=4)

        self.progress = ctk.CTkProgressBar(bar, mode="indeterminate", width=130, height=6)
        self.progress.grid(row=0, column=2, padx=(0, 10), pady=4)

        self.log_toggle_btn = ctk.CTkButton(bar, text="Log  ▸", width=64, height=24,
                                             fg_color="gray30", command=self._toggle_log)
        self.log_toggle_btn.grid(row=0, column=3, padx=(0, 8), pady=4)

        self.log("Gotowy.")

    def _toggle_log(self):
        self._log_visible = not self._log_visible
        if self._log_visible:
            self.log_drawer.grid()
            self.log_toggle_btn.configure(text="Log  ▾")
        else:
            self.log_drawer.grid_remove()
            self.log_toggle_btn.configure(text="Log  ▸")

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{ts}] {msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        self.status_label.configure(text=msg)

    # ------------------------------------------------------------- runner
    def run_async(self, fn, trigger_button=None, on_success=None, busy_text="Przetwarzanie...",
                  silent_errors=False):
        if trigger_button:
            trigger_button.configure(state="disabled")
        self.status_dot.configure(text_color=self._DOT_BUSY)
        self.progress.start()
        self.log(busy_text)

        def worker():
            try:
                result = fn()
            except Exception as e:
                # Python usuwa zmienną złapanego wyjątku (tu 'e') zaraz po wyjściu
                # z bloku except - lambda poniżej jest wywoływana PÓŹNIEJ (dopiero
                # gdy self.after(0, ...) faktycznie ją odpali w pętli Tkintera), więc
                # bez podania e=e jako domyślnego argumentu (wiążącego wartość TERAZ,
                # a nie przy wywołaniu) leciał tu NameError - a przez to _finish()
                # nigdy się nie wykonywało: przycisk zostawał zablokowany na stałe,
                # a błąd nigdy nie trafiał na ekran (dokładnie "program się wiesza"
                # zgłoszone dla złego linku, ale dotyczyło to KAŻDEGO błędu w całej
                # aplikacji, nie tylko pobierania).
                self.after(0, lambda e=e: self._finish(trigger_button, error=e, silent_errors=silent_errors))
            else:
                self.after(0, lambda: self._finish(trigger_button, result=result, on_success=on_success))

        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, trigger_button, result=None, error=None, on_success=None, silent_errors=False):
        self.progress.stop()
        if trigger_button:
            trigger_button.configure(state="normal")
        if error:
            self.status_dot.configure(text_color=self._DOT_ERROR)
            self.log(f"❌ Błąd: {error}")
            if not silent_errors:
                messagebox.showerror("Błąd", str(error))
        else:
            self.status_dot.configure(text_color=self._DOT_OK)
            self.log("✅ Gotowe.")
            if on_success:
                on_success(result)


# =========================================================== Konwersja ====
def build_convert_page(parent, app):
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    frame.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(frame, text="Konwersja ogólna (format rozpoznawany po rozszerzeniu)",
                 font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
    ctk.CTkLabel(frame, text="Obrazy, audio/wideo, PDF↔DOCX, CSV/JSON/XLSX/YAML - jedna komenda.",
                 text_color="gray60").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 16))

    labeled_row(frame, 2, "Plik wejściowy:")
    in_entry = ctk.CTkEntry(frame, placeholder_text="wybierz plik lub przeciągnij go tutaj...")
    in_entry.grid(row=2, column=1, sticky="ew", padx=6, pady=6)

    labeled_row(frame, 3, "Format wyjściowy:")
    format_menu = ctk.CTkOptionMenu(frame, values=["- wybierz plik wejściowy -"], width=160,
                                     command=lambda choice: on_format_selected(choice))
    format_menu.set("- wybierz plik wejściowy -")
    format_menu.configure(state="disabled")
    format_menu.grid(row=3, column=1, sticky="w", padx=6, pady=6)

    labeled_row(frame, 4, "Plik wyjściowy:")
    out_entry = ctk.CTkEntry(frame, placeholder_text="nazwa uzupełni się sama po wyborze formatu wyżej")
    out_entry.grid(row=4, column=1, sticky="ew", padx=6, pady=6)
    ctk.CTkButton(frame, text="Zapisz jako...", width=110,
                  command=lambda: browse_save(out_entry)).grid(row=4, column=2, pady=6)

    labeled_row(frame, 5, "Jakość (JPG/WEBP):")
    quality_val = ctk.CTkLabel(frame, text="90")
    quality_slider = ctk.CTkSlider(frame, from_=1, to=100, number_of_steps=99,
                                    command=lambda v: quality_val.configure(text=str(int(v))))
    quality_slider.set(90)
    quality_slider.grid(row=5, column=1, sticky="ew", padx=6, pady=6)
    quality_val.grid(row=5, column=2, sticky="w")

    # Etykiety rozwijanego menu ("PNG") <-> realne rozszerzenia (".png") - CTkOptionMenu
    # operuje na czytelnych dla człowieka napisach, więc trzymamy mapowanie osobno
    # zamiast wymuszać na do_convert() rozpoznawanie etykiet.
    ext_by_label = {}

    def apply_format(input_path, ext):
        if not input_path:
            return
        out_entry.delete(0, "end")
        out_entry.insert(0, suggest_output(input_path, "_wynik", ext))

    def on_format_selected(choice):
        ext = ext_by_label.get(choice)
        if ext:
            apply_format(in_entry.get().strip(), ext)

    def refresh_format_options(path):
        options = output_format_options(path)
        ext_by_label.clear()
        if not options:
            format_menu.configure(values=["(brak obsługiwanej konwersji dla tego pliku)"], state="disabled")
            format_menu.set("(brak obsługiwanej konwersji dla tego pliku)")
            return
        labels = [ext.lstrip(".").upper() for ext in options]
        ext_by_label.update(zip(labels, options))
        format_menu.configure(values=labels, state="normal")
        format_menu.set(labels[0])
        apply_format(path, options[0])

    def on_input_selected(path):
        in_entry.delete(0, "end")
        in_entry.insert(0, path)
        refresh_format_options(path)

    def on_browse_input():
        path = filedialog.askopenfilename(filetypes=[("Wszystkie pliki", "*.*")])
        if path:
            on_input_selected(path)

    ctk.CTkButton(frame, text="Przeglądaj...", width=110,
                  command=on_browse_input).grid(row=2, column=2, pady=6)
    enable_file_drop(in_entry, lambda paths: on_input_selected(paths[0]))

    def on_convert():
        input_path, raw_output = in_entry.get().strip(), out_entry.get().strip()
        if not input_path or not raw_output:
            messagebox.showwarning("Brakuje danych", "Podaj plik wejściowy i wyjściowy.")
            return
        output_path = resolve_output_path(raw_output)
        quality = int(quality_slider.get())
        app.log(f"Konwersja {input_path} -> {output_path}")
        app.run_async(lambda: do_convert(input_path, output_path, quality=quality),
                      trigger_button=convert_btn,
                      on_success=lambda _: app.log(f"Zapisano: {output_path}"),
                      busy_text="Konwertuję...")

    convert_btn = ctk.CTkButton(frame, text="Konwertuj", command=on_convert)
    convert_btn.grid(row=6, column=0, sticky="w", pady=(16, 0))

    return frame


# ============================================================== Obrazy ====
def build_images_page(parent, app):
    def build_resize(p):
        f = ctk.CTkFrame(p, fg_color="transparent")
        f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(f, text="Zmień rozmiar obrazu (proporcje zachowane, jeśli podasz tylko jeden wymiar)",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        labeled_row(f, 1, "Plik wejściowy:")
        in_e = ctk.CTkEntry(f, placeholder_text="wybierz plik lub przeciągnij go tutaj...")
        in_e.grid(row=1, column=1, sticky="ew", padx=6, pady=6)

        def on_input_selected(path):
            in_e.delete(0, "end")
            in_e.insert(0, path)
            out_e.delete(0, "end")
            out_e.insert(0, suggest_output(path, "_resized"))

        def on_browse():
            path = filedialog.askopenfilename(
                filetypes=[("Obrazy", "*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tiff *.ico")])
            if path:
                on_input_selected(path)

        ctk.CTkButton(f, text="Przeglądaj...", width=110, command=on_browse).grid(row=1, column=2, pady=6)
        enable_file_drop(in_e, lambda paths: on_input_selected(paths[0]))

        labeled_row(f, 2, "Szerokość (px):")
        w_e = ctk.CTkEntry(f, placeholder_text="np. 1280")
        w_e.grid(row=2, column=1, sticky="ew", padx=6, pady=6)
        labeled_row(f, 3, "Wysokość (px):")
        h_e = ctk.CTkEntry(f, placeholder_text="zostaw puste, by zachować proporcje")
        h_e.grid(row=3, column=1, sticky="ew", padx=6, pady=6)

        labeled_row(f, 4, "Plik wyjściowy:")
        out_e = ctk.CTkEntry(f)
        out_e.grid(row=4, column=1, sticky="ew", padx=6, pady=6)
        ctk.CTkButton(f, text="Zapisz jako...", width=110, command=lambda: browse_save(out_e)).grid(row=4, column=2, pady=6)

        def on_run():
            if not in_e.get().strip() or not out_e.get().strip():
                messagebox.showwarning("Brakuje danych", "Podaj plik wejściowy i wyjściowy.")
                return
            width = int(w_e.get()) if w_e.get().strip() else None
            height = int(h_e.get()) if h_e.get().strip() else None
            if not width and not height:
                messagebox.showwarning("Brakuje danych", "Podaj szerokość lub wysokość.")
                return
            output_path = resolve_output_path(out_e.get().strip())
            app.run_async(lambda: images.resize(in_e.get().strip(), output_path, width=width, height=height),
                          trigger_button=btn, on_success=lambda _: app.log(f"Zapisano: {output_path}"),
                          busy_text="Zmieniam rozmiar...")

        btn = ctk.CTkButton(f, text="Zmień rozmiar", command=on_run)
        btn.grid(row=5, column=0, sticky="w", pady=(14, 0))
        return f

    def build_exif(p):
        f = ctk.CTkFrame(p, fg_color="transparent")
        f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(f, text="Usuń metadane EXIF (GPS, model telefonu, data) przed wysłaniem zdjęcia",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        labeled_row(f, 1, "Plik wejściowy:")
        in_e = ctk.CTkEntry(f, placeholder_text="wybierz plik lub przeciągnij go tutaj...")
        in_e.grid(row=1, column=1, sticky="ew", padx=6, pady=6)

        def on_input_selected(path):
            in_e.delete(0, "end")
            in_e.insert(0, path)
            out_e.delete(0, "end")
            out_e.insert(0, suggest_output(path, "_clean"))

        def on_browse():
            path = filedialog.askopenfilename(filetypes=[("Obrazy", "*.jpg *.jpeg *.png *.webp *.bmp *.tiff")])
            if path:
                on_input_selected(path)

        ctk.CTkButton(f, text="Przeglądaj...", width=110, command=on_browse).grid(row=1, column=2, pady=6)
        enable_file_drop(in_e, lambda paths: on_input_selected(paths[0]))

        labeled_row(f, 2, "Plik wyjściowy:")
        out_e = ctk.CTkEntry(f)
        out_e.grid(row=2, column=1, sticky="ew", padx=6, pady=6)
        ctk.CTkButton(f, text="Zapisz jako...", width=110, command=lambda: browse_save(out_e)).grid(row=2, column=2, pady=6)

        def on_run():
            if not in_e.get().strip() or not out_e.get().strip():
                messagebox.showwarning("Brakuje danych", "Podaj plik wejściowy i wyjściowy.")
                return
            output_path = resolve_output_path(out_e.get().strip())
            app.run_async(lambda: images.strip_exif(in_e.get().strip(), output_path),
                          trigger_button=btn, on_success=lambda _: app.log(f"Zapisano: {output_path}"),
                          busy_text="Usuwam metadane...")

        btn = ctk.CTkButton(f, text="Usuń EXIF", command=on_run)
        btn.grid(row=3, column=0, sticky="w", pady=(14, 0))
        return f

    outer = ctk.CTkFrame(parent, fg_color="transparent")
    outer.grid_columnconfigure(0, weight=1)
    outer.grid_rowconfigure(0, weight=1)
    SegmentedStack(outer, {"Zmień rozmiar": build_resize, "Usuń EXIF": build_exif}).grid(row=0, column=0, sticky="nsew")
    return outer


# ======================================================== Audio / Wideo ===
def build_media_page(parent, app):
    def build_trim(p):
        outer = ctk.CTkScrollableFrame(p, fg_color="transparent")
        outer.grid_columnconfigure(0, weight=1)
        f = outer

        state = {"path": None, "duration": 0.0, "tracks": [], "preview_temp": None,
                 "mixer_touched": False}
        track_rows = []
        _card_row = [0]

        def next_card_row():
            r = _card_row[0]
            _card_row[0] += 1
            return r

        def card(title):
            """Karta grupująca powiązane kontrolki (zamiast jednej długiej,
            płaskiej listy sekcji na przezroczystym tle - stąd wcześniej
            wrażenie bałaganu na tej zakładce). Zwraca wewnętrzny frame
            z własną, niezależną numeracją wierszy (0, 1, 2, ...)."""
            wrap = ctk.CTkFrame(f, fg_color=("gray90", "gray17"), corner_radius=10)
            wrap.grid(row=next_card_row(), column=0, sticky="ew", pady=(0, 14))
            wrap.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(wrap, text=title, font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=("gray15", "gray90")).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 6))
            inner = ctk.CTkFrame(wrap, fg_color="transparent")
            inner.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))
            inner.grid_columnconfigure(1, weight=1)
            return inner

        ctk.CTkLabel(f, text="✂ Przytnij fragment audio/wideo (MP3, MP4, WAV, MOV, ...)",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(row=next_card_row(), column=0, sticky="w", pady=(0, 2))
        duration_label = ctk.CTkLabel(f, text="Długość pliku: -", text_color="gray60")
        duration_label.grid(row=next_card_row(), column=0, sticky="w", pady=(0, 12))

        # ================================================================ Plik
        c_source = card("📂 Plik źródłowy")
        labeled_row(c_source, 0, "Plik wejściowy:")
        in_e = ctk.CTkEntry(c_source, placeholder_text="wybierz plik lub przeciągnij go tutaj...")
        in_e.grid(row=0, column=1, sticky="ew", padx=6, pady=6)
        browse_btn = ctk.CTkButton(c_source, text="Przeglądaj...", width=110)
        browse_btn.grid(row=0, column=2, pady=6)
        preview_ext_btn = ctk.CTkButton(c_source, text="Otwórz w domyślnym odtwarzaczu systemu",
                                         fg_color="gray30")
        preview_ext_btn.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))

        # ============================================================ Podgląd
        c_preview = card("🎬 Podgląd i odtwarzanie")

        video_surface = tk.Frame(c_preview, bg="black", height=260)
        video_surface.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        video_surface.grid_propagate(False)
        video_surface.grid_remove()
        video_surface.update_idletasks()

        try:
            player = VideoPlayer(video_surface)
            app.register_video_player(player)
        except Exception as e:
            player = None
            app.log(f"⚠ Podgląd/odtwarzanie niedostępne ({e}). Zainstaluj VLC Media Player, "
                     f"żeby móc odtwarzać pliki w tej zakładce.")

        controls = ctk.CTkFrame(c_preview, fg_color="transparent")
        controls.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        controls.grid_columnconfigure(2, weight=1)

        play_btn = ctk.CTkButton(controls, text="▶ Odtwórz", width=110)
        play_btn.grid(row=0, column=0, padx=(0, 6))
        stop_btn = ctk.CTkButton(controls, text="⏹ Stop", width=70, fg_color="gray30")
        stop_btn.grid(row=0, column=1, padx=(0, 10))
        seek_slider = ctk.CTkSlider(controls, from_=0, to=1)
        seek_slider.set(0)
        seek_slider.grid(row=0, column=2, sticky="ew", padx=(0, 10))
        time_label = ctk.CTkLabel(controls, text="00:00:00 / 00:00:00", width=170)
        time_label.grid(row=0, column=3)

        mark_row = ctk.CTkFrame(c_preview, fg_color="transparent")
        mark_row.grid(row=2, column=0, columnspan=3, sticky="w")
        mark_start_btn = ctk.CTkButton(mark_row, text="⏮ Zaznacz początek tutaj", width=180, fg_color="gray30")
        mark_start_btn.pack(side="left", padx=(0, 8))
        mark_end_btn = ctk.CTkButton(mark_row, text="Zaznacz koniec tutaj ⏭", width=180, fg_color="gray30")
        mark_end_btn.pack(side="left")

        if player is None:
            play_btn.configure(state="disabled")
            stop_btn.configure(state="disabled")
            seek_slider.configure(state="disabled")
            mark_start_btn.configure(state="disabled")
            mark_end_btn.configure(state="disabled")

        # ======================================================== Zakres cięcia
        c_range = card("〰 Zakres przycięcia")

        waveform = WaveformSelector(c_range, height=90, on_change=lambda s, e: set_time_fields(s, e))
        waveform.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        ctk.CTkLabel(c_range, text="przeciągnij uchwyty (brzegi) albo całe zaznaczenie, żeby ustawić zakres - "
                             "uchwyty przyciągają się do suwaka odtwarzania, gdy są blisko niego",
                     text_color="gray60", font=ctk.CTkFont(size=11)).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 10))

        labeled_row(c_range, 2, "Początek (HH:MM:SS):")
        start_e = ctk.CTkEntry(c_range, placeholder_text="00:00:00")
        start_e.insert(0, "00:00:00")
        start_e.grid(row=2, column=1, sticky="ew", padx=6, pady=6)

        labeled_row(c_range, 3, "Koniec (HH:MM:SS):")
        end_e = ctk.CTkEntry(c_range, placeholder_text="00:00:30")
        end_e.grid(row=3, column=1, sticky="ew", padx=6, pady=6)

        def set_time_fields(start_sec, end_sec):
            start_e.delete(0, "end")
            start_e.insert(0, format_time_precise(start_sec))
            end_e.delete(0, "end")
            end_e.insert(0, format_time_precise(end_sec))

        def on_time_field_edited(_event=None):
            try:
                s = parse_time_to_seconds(start_e.get())
                e = parse_time_to_seconds(end_e.get())
            except ValueError:
                return
            waveform.set_selection(s, e)

        for entry in (start_e, end_e):
            entry.bind("<Return>", on_time_field_edited)
            entry.bind("<FocusOut>", on_time_field_edited)

        # =========================================================== Mikser
        # Bez własnej karty na stałe - build_mixer dodaje nagłówek tylko gdy
        # plik ma więcej niż jedną ścieżkę audio, więc przy zwykłym pliku
        # ten frame jest po prostu niewidoczny (wysokość 0), zamiast pokazywać
        # pustą kartę.
        # height=1: bez tego CTkFrame domyślnie rezerwuje 200px wysokości nawet
        # bez żadnej zawartości (widoczne jako pusta dziura w layoucie, dopóki
        # nie wczyta się plik z >1 ścieżką audio i build_mixer() go nie wypełni).
        mixer_container = ctk.CTkFrame(f, fg_color="transparent", height=1)
        mixer_container.grid(row=next_card_row(), column=0, sticky="ew", pady=(0, 4))
        mixer_container.grid_columnconfigure(0, weight=1)

        # =========================================================== Zapis
        c_save = card("💾 Zapis wyniku")
        labeled_row(c_save, 0, "Plik wyjściowy:")
        out_e = ctk.CTkEntry(c_save)
        out_e.grid(row=0, column=1, sticky="ew", padx=6, pady=6)
        ctk.CTkButton(c_save, text="Zapisz jako...", width=110, command=lambda: browse_save(out_e)).grid(row=0, column=2, pady=6)

        trim_btn = ctk.CTkButton(c_save, text="✂ Wytnij fragment")
        trim_btn.grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 8))

        ctk.CTkLabel(
            c_save, justify="left", text_color="gray60", font=ctk.CTkFont(size=11),
            text="Bez zmian w mikserze cięcie jest bezstratne i błyskawiczne (bez przekodowania),\n"
                 "ale przy wideo start fragmentu może się przesunąć o ułamek sekundy do najbliższej\n"
                 "klatki kluczowej. Jeśli dostosujesz głośność/wyciszenie ścieżek, dźwięk zostanie\n"
                 "przekodowany na nowo (żeby zapisać zmiksowany wynik) - trwa to dłużej.",
        ).grid(row=2, column=0, columnspan=3, sticky="w")

        # ------------------------------------------------------- odtwarzanie --
        def cleanup_preview_temp():
            old = state["preview_temp"]
            state["preview_temp"] = None
            if old:
                try:
                    os.remove(old)
                except OSError:
                    pass

        def toggle_play_pause():
            if player is None or not state["path"]:
                return
            if player.is_playing():
                player.pause()
                play_btn.configure(text="▶ Odtwórz")
            else:
                player.play()
                play_btn.configure(text="⏸ Pauza")

        def stop_playback():
            if player is None:
                return
            player.stop()
            play_btn.configure(text="▶ Odtwórz")
            seek_slider.set(0)
            waveform.set_playhead(0.0)

        def on_seek(value):
            if player is None or not state["duration"]:
                return
            player.set_time(float(value))
            waveform.set_playhead(float(value))

        def on_waveform_seek(t):
            # Przeciąganie żółtego uchwytu na przebiegu fali - przewija podgląd
            # na żywo do danego momentu, żeby łatwiej było trafić dokładny punkt cięcia.
            _seeking[0] = True
            if player is None or not state["duration"]:
                return
            player.set_time(t)
            seek_slider.set(t)
            time_label.configure(text=f"{format_hhmmss(t)} / {format_hhmmss(state['duration'])}")

        def on_waveform_seek_end():
            _seeking[0] = False

        def mark_start_here():
            if player is None or not state["duration"]:
                return
            t = player.get_time()
            if t is None:
                return
            new_end = waveform.end if t < waveform.end else min(state["duration"], t + WaveformSelector.MIN_SPAN)
            waveform.set_selection(t, new_end)
            set_time_fields(waveform.start, waveform.end)

        def mark_end_here():
            if player is None or not state["duration"]:
                return
            t = player.get_time()
            if t is None:
                return
            new_start = waveform.start if t > waveform.start else max(0.0, t - WaveformSelector.MIN_SPAN)
            waveform.set_selection(new_start, t)
            set_time_fields(waveform.start, waveform.end)

        play_btn.configure(command=toggle_play_pause)
        stop_btn.configure(command=stop_playback)
        seek_slider.configure(command=on_seek)
        mark_start_btn.configure(command=mark_start_here)
        mark_end_btn.configure(command=mark_end_here)
        waveform.on_seek = on_waveform_seek
        waveform.on_seek_end = on_waveform_seek_end

        # Podczas ręcznego przeciągania suwaka odtwarzania poll_tick nie powinien
        # nadpisywać jego pozycji na podstawie player.get_time() (który zwykle nieco
        # spóźnia się za żądanym seekiem) - inaczej suwak "wyrywa się" spod kursora.
        _seeking = [False]
        seek_slider.bind("<Button-1>", lambda _e: _seeking.__setitem__(0, True))
        seek_slider.bind("<ButtonRelease-1>", lambda _e: _seeking.__setitem__(0, False))

        def poll_tick():
            if player is not None:
                t = player.get_time()
                if t is not None:
                    if not _seeking[0]:
                        seek_slider.set(t)
                        waveform.set_playhead(t)
                    time_label.configure(text=f"{format_hhmmss(t)} / {format_hhmmss(state['duration'])}")
                    if not player.is_playing() and state["duration"] and t >= state["duration"] - 0.3:
                        play_btn.configure(text="▶ Odtwórz")
            f.after(150, poll_tick)

        poll_tick()

        # ------------------------------------------------------------ mikser --
        def clear_mixer():
            for child in mixer_container.winfo_children():
                child.destroy()
            track_rows.clear()

        def gather_gains():
            return [0.0 if row["mute_var"].get() else row["volume_slider"].get() / 100.0
                    for row in track_rows]

        def reset_mixer():
            for row in track_rows:
                row["mute_var"].set(False)
                row["volume_slider"].set(100)
                row["pct_label"].configure(text="100%")
            state["mixer_touched"] = False
            schedule_regenerate(force_original=True)

        _regen_job = [None]

        def schedule_regenerate(force_original=False):
            if _regen_job[0]:
                f.after_cancel(_regen_job[0])
                _regen_job[0] = None
            if force_original:
                revert_to_original()
                return
            state["mixer_touched"] = True
            _regen_job[0] = f.after(600, regenerate_preview)

        def revert_to_original():
            if player is None or not state["path"]:
                return
            was_playing = player.is_playing()
            pos = player.get_time() or 0.0
            player.load(state["path"])
            player.play()
            player.set_time(pos)
            if not was_playing:
                player.pause()
            cleanup_preview_temp()

        def regenerate_preview():
            if player is None or not state["path"] or not track_rows:
                return
            path = state["path"]
            gains = gather_gains()
            out_ext = ".mp4" if ext_of(path) in media.VIDEO_EXTS else ".m4a"
            fd, tmp_path = tempfile.mkstemp(suffix=out_ext, prefix="local_converter_preview_")
            os.close(fd)

            def do():
                media.build_mixed_preview(path, gains, tmp_path)
                return tmp_path

            def on_ready(new_path):
                if state["path"] != path:
                    try:
                        os.remove(new_path)
                    except OSError:
                        pass
                    return
                was_playing = player.is_playing()
                pos = player.get_time() or 0.0
                old = state["preview_temp"]
                player.load(new_path)
                player.play()
                player.set_time(pos)
                if not was_playing:
                    player.pause()
                state["preview_temp"] = new_path
                if old:
                    try:
                        os.remove(old)
                    except OSError:
                        pass

            app.run_async(do, on_success=on_ready, busy_text="Przeliczam podgląd miksu ścieżek...",
                          silent_errors=True)

        def build_mixer(path, tracks, duration):
            clear_mixer()
            if len(tracks) <= 1:
                return

            header = ctk.CTkFrame(mixer_container, fg_color="transparent")
            header.grid(row=0, column=0, sticky="ew", pady=(4, 8))
            ctk.CTkLabel(header, text=f"🎚 Ścieżki audio ({len(tracks)}) - dostosuj głośność/wyciszenie",
                         font=ctk.CTkFont(weight="bold")).pack(side="left")
            ctk.CTkButton(header, text="↺ Reset miksu", width=110, fg_color="gray30",
                          command=reset_mixer).pack(side="left", padx=(12, 0))

            for row_i, track in enumerate(tracks, start=1):
                row_frame = ctk.CTkFrame(mixer_container, fg_color=("gray85", "gray20"))
                row_frame.grid(row=row_i, column=0, sticky="ew", pady=3)
                row_frame.grid_columnconfigure(4, weight=1)

                ctk.CTkLabel(row_frame, text=track["label"], width=120, anchor="w").grid(
                    row=0, column=0, padx=(10, 6), pady=8, sticky="w")

                mute_var = tk.BooleanVar(value=False)
                ctk.CTkCheckBox(row_frame, text="Wycisz", variable=mute_var, width=20,
                                command=schedule_regenerate).grid(row=0, column=1, padx=6, pady=8)

                pct_label = ctk.CTkLabel(row_frame, text="100%", width=45)

                def on_volume_change(v, lbl=pct_label):
                    lbl.configure(text=f"{int(float(v))}%")
                    schedule_regenerate()

                vol_slider = ctk.CTkSlider(row_frame, from_=0, to=200, number_of_steps=200,
                                            command=on_volume_change, width=140)
                vol_slider.set(100)
                vol_slider.grid(row=0, column=2, padx=6, pady=8)
                pct_label.grid(row=0, column=3, padx=(0, 6))

                mini_wave = WaveformSelector(row_frame, height=44, interactive=False)
                mini_wave.grid(row=0, column=4, sticky="ew", padx=(6, 10), pady=8)

                track_rows.append({"index": track["index"], "mute_var": mute_var,
                                    "volume_slider": vol_slider, "pct_label": pct_label,
                                    "waveform": mini_wave})

                def load_track_wave(t_index=track["index"], mw=mini_wave):
                    app.run_async(lambda: media.get_waveform_peaks(path, track_index=t_index),
                                  on_success=lambda peaks: mw.set_waveform(peaks, duration),
                                  busy_text=f"Wczytuję ścieżkę {t_index + 1}...", silent_errors=True)

                load_track_wave()

        # -------------------------------------------------------- wczytanie --
        def on_input_selected(path):
            in_e.delete(0, "end")
            in_e.insert(0, path)
            out_e.delete(0, "end")
            out_e.insert(0, suggest_output(path, "_przyciete"))
            duration_label.configure(text="Długość pliku: wczytywanie...")
            waveform.clear("wczytywanie przebiegu fali...")
            clear_mixer()
            cleanup_preview_temp()
            state["path"] = path
            state["mixer_touched"] = False

            is_video = ext_of(path) in media.VIDEO_EXTS
            if is_video and player is not None:
                video_surface.grid()
            else:
                video_surface.grid_remove()

            if player is not None:
                player.stop()
                player.load(path)
                play_btn.configure(text="▶ Odtwórz")

            def on_duration(seconds):
                state["duration"] = seconds
                duration_label.configure(text=f"Długość pliku: {format_hhmmss(seconds)}")
                set_time_fields(0.0, seconds)
                seek_slider.configure(from_=0, to=seconds)
                seek_slider.set(0)
                load_waveform(path, seconds)
                load_tracks(path, seconds)

            app.run_async(lambda: media.get_duration(path), on_success=on_duration,
                          busy_text="Odczytuję długość pliku (ffprobe)...")

        def load_waveform(path, duration):
            def on_peaks(peaks):
                waveform.set_waveform(peaks, duration)

            app.run_async(lambda: media.get_waveform_peaks(path), on_success=on_peaks,
                          busy_text="Generuję podgląd ścieżki dźwiękowej...", silent_errors=True)

        def load_tracks(path, duration):
            def on_tracks(tracks):
                state["tracks"] = tracks
                build_mixer(path, tracks, duration)

            app.run_async(lambda: media.list_audio_tracks(path), on_success=on_tracks,
                          busy_text="Sprawdzam ścieżki audio...", silent_errors=True)

        def on_browse_input():
            exts = sorted(media.AUDIO_EXTS | media.VIDEO_EXTS)
            filetypes = [("Audio/Wideo", " ".join(f"*{e}" for e in exts)), ("Wszystkie pliki", "*.*")]
            path = filedialog.askopenfilename(filetypes=filetypes)
            if path:
                on_input_selected(path)

        browse_btn.configure(command=on_browse_input)
        enable_file_drop(in_e, lambda paths: on_input_selected(paths[0]))

        def on_preview_external():
            path = in_e.get().strip()
            if not path:
                messagebox.showwarning("Brak pliku", "Najpierw wybierz plik wejściowy.")
                return
            open_with_default_app(path)

        preview_ext_btn.configure(command=on_preview_external)

        # ------------------------------------------------------------- cięcie --
        def on_trim():
            input_path, raw_output = in_e.get().strip(), out_e.get().strip()
            start, end = start_e.get().strip(), end_e.get().strip()
            if not input_path or not raw_output or not start or not end:
                messagebox.showwarning("Brakuje danych", "Uzupełnij plik wejściowy, wyjściowy oraz start/koniec.")
                return
            output_path = resolve_output_path(raw_output)

            if state["mixer_touched"] and track_rows:
                gains = gather_gains()
                app.log(f"Przycinanie z miksem ścieżek {input_path} [{start} -> {end}] -> {output_path}")
                app.run_async(lambda: media.build_mixed_preview(input_path, gains, output_path, start=start, end=end),
                              trigger_button=trim_btn,
                              on_success=lambda _: app.log(f"Zapisano: {output_path}"),
                              busy_text="Przycinam i miksuję ścieżki (ffmpeg)...")
            else:
                app.log(f"Przycinanie {input_path} [{start} -> {end}] -> {output_path}")
                app.run_async(lambda: media.trim(input_path, output_path, start, end),
                              trigger_button=trim_btn,
                              on_success=lambda _: app.log(f"Zapisano: {output_path}"),
                              busy_text="Przycinam plik (ffmpeg)...")

        trim_btn.configure(command=on_trim)
        return f

    def build_gif(p):
        f = ctk.CTkFrame(p, fg_color="transparent")
        f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(f, text="Wideo → animowany GIF", font=ctk.CTkFont(weight="bold"))\
            .grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        labeled_row(f, 1, "Plik wideo:")
        in_e = ctk.CTkEntry(f, placeholder_text="wybierz plik lub przeciągnij go tutaj...")
        in_e.grid(row=1, column=1, sticky="ew", padx=6, pady=6)

        def on_input_selected(path):
            in_e.delete(0, "end")
            in_e.insert(0, path)
            out_e.delete(0, "end")
            out_e.insert(0, suggest_output(path, "", ".gif"))

        def on_browse():
            path = filedialog.askopenfilename(filetypes=[("Wideo", "*.mp4 *.avi *.mov *.webm *.mkv")])
            if path:
                on_input_selected(path)

        ctk.CTkButton(f, text="Przeglądaj...", width=110, command=on_browse).grid(row=1, column=2, pady=6)
        enable_file_drop(in_e, lambda paths: on_input_selected(paths[0]))

        labeled_row(f, 2, "FPS:")
        fps_e = ctk.CTkEntry(f)
        fps_e.insert(0, "10")
        fps_e.grid(row=2, column=1, sticky="ew", padx=6, pady=6)

        labeled_row(f, 3, "Szerokość (px):")
        width_e = ctk.CTkEntry(f)
        width_e.insert(0, "480")
        width_e.grid(row=3, column=1, sticky="ew", padx=6, pady=6)

        labeled_row(f, 4, "Plik wyjściowy (.gif):")
        out_e = ctk.CTkEntry(f)
        out_e.grid(row=4, column=1, sticky="ew", padx=6, pady=6)
        ctk.CTkButton(f, text="Zapisz jako...", width=110,
                      command=lambda: browse_save(out_e, ".gif", [("GIF", "*.gif")])).grid(row=4, column=2, pady=6)

        def on_run():
            if not in_e.get().strip() or not out_e.get().strip():
                messagebox.showwarning("Brakuje danych", "Podaj plik wejściowy i wyjściowy.")
                return
            output_path = resolve_output_path(out_e.get().strip())
            app.run_async(lambda: media.to_gif(in_e.get().strip(), output_path,
                                                fps=int(fps_e.get() or 10), width=int(width_e.get() or 480)),
                          trigger_button=btn, on_success=lambda _: app.log(f"Zapisano: {output_path}"),
                          busy_text="Generuję GIF...")

        btn = ctk.CTkButton(f, text="Konwertuj na GIF", command=on_run)
        btn.grid(row=5, column=0, sticky="w", pady=(14, 0))
        return f

    def build_normalize(p):
        f = ctk.CTkFrame(p, fg_color="transparent")
        f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(f, text="Wyrównaj głośność nagrania (EBU R128 loudnorm)", font=ctk.CTkFont(weight="bold"))\
            .grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        labeled_row(f, 1, "Plik audio:")
        in_e = ctk.CTkEntry(f, placeholder_text="wybierz plik lub przeciągnij go tutaj...")
        in_e.grid(row=1, column=1, sticky="ew", padx=6, pady=6)

        def on_input_selected(path):
            in_e.delete(0, "end")
            in_e.insert(0, path)
            out_e.delete(0, "end")
            out_e.insert(0, suggest_output(path, "_norm"))

        def on_browse():
            path = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3 *.wav *.flac *.ogg *.m4a *.aac")])
            if path:
                on_input_selected(path)

        ctk.CTkButton(f, text="Przeglądaj...", width=110, command=on_browse).grid(row=1, column=2, pady=6)
        enable_file_drop(in_e, lambda paths: on_input_selected(paths[0]))

        labeled_row(f, 2, "Plik wyjściowy:")
        out_e = ctk.CTkEntry(f)
        out_e.grid(row=2, column=1, sticky="ew", padx=6, pady=6)
        ctk.CTkButton(f, text="Zapisz jako...", width=110, command=lambda: browse_save(out_e)).grid(row=2, column=2, pady=6)

        def on_run():
            if not in_e.get().strip() or not out_e.get().strip():
                messagebox.showwarning("Brakuje danych", "Podaj plik wejściowy i wyjściowy.")
                return
            output_path = resolve_output_path(out_e.get().strip())
            app.run_async(lambda: media.normalize_audio(in_e.get().strip(), output_path),
                          trigger_button=btn, on_success=lambda _: app.log(f"Zapisano: {output_path}"),
                          busy_text="Wyrównuję głośność...")

        btn = ctk.CTkButton(f, text="Wyrównaj głośność", command=on_run)
        btn.grid(row=3, column=0, sticky="w", pady=(14, 0))
        return f

    def build_compress(p):
        f = ctk.CTkFrame(p, fg_color="transparent")
        f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(f, text="Kompresuj wideo (mniejszy plik)", font=ctk.CTkFont(weight="bold"))\
            .grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        labeled_row(f, 1, "Plik wideo:")
        in_e = ctk.CTkEntry(f, placeholder_text="wybierz plik lub przeciągnij go tutaj...")
        in_e.grid(row=1, column=1, sticky="ew", padx=6, pady=6)

        def on_input_selected(path):
            in_e.delete(0, "end")
            in_e.insert(0, path)
            out_e.delete(0, "end")
            out_e.insert(0, suggest_output(path, "_compressed"))

        def on_browse():
            path = filedialog.askopenfilename(filetypes=[("Wideo", "*.mp4 *.avi *.mov *.webm *.mkv")])
            if path:
                on_input_selected(path)

        ctk.CTkButton(f, text="Przeglądaj...", width=110, command=on_browse).grid(row=1, column=2, pady=6)
        enable_file_drop(in_e, lambda paths: on_input_selected(paths[0]))

        labeled_row(f, 2, "CRF (18-28, niżej = lepsza jakość):")
        crf_val = ctk.CTkLabel(f, text="28")
        crf_slider = ctk.CTkSlider(f, from_=15, to=35, number_of_steps=20,
                                    command=lambda v: crf_val.configure(text=str(int(v))))
        crf_slider.set(28)
        crf_slider.grid(row=2, column=1, sticky="ew", padx=6, pady=6)
        crf_val.grid(row=2, column=2, sticky="w")

        labeled_row(f, 3, "Plik wyjściowy:")
        out_e = ctk.CTkEntry(f)
        out_e.grid(row=3, column=1, sticky="ew", padx=6, pady=6)
        ctk.CTkButton(f, text="Zapisz jako...", width=110, command=lambda: browse_save(out_e)).grid(row=3, column=2, pady=6)

        def on_run():
            if not in_e.get().strip() or not out_e.get().strip():
                messagebox.showwarning("Brakuje danych", "Podaj plik wejściowy i wyjściowy.")
                return
            output_path = resolve_output_path(out_e.get().strip())
            app.run_async(lambda: media.compress_video(in_e.get().strip(), output_path, crf=int(crf_slider.get())),
                          trigger_button=btn, on_success=lambda _: app.log(f"Zapisano: {output_path}"),
                          busy_text="Kompresuję wideo...")

        btn = ctk.CTkButton(f, text="Kompresuj", command=on_run)
        btn.grid(row=4, column=0, sticky="w", pady=(14, 0))
        return f

    outer = ctk.CTkFrame(parent, fg_color="transparent")
    outer.grid_columnconfigure(0, weight=1)
    outer.grid_rowconfigure(0, weight=1)
    SegmentedStack(outer, {
        "Przytnij (Trim)": build_trim,
        "Wideo → GIF": build_gif,
        "Wyrównaj głośność": build_normalize,
        "Kompresuj wideo": build_compress,
    }).grid(row=0, column=0, sticky="nsew")
    return outer


# ===================================================== Dokumenty (PDF) ====
def build_documents_page(parent, app):
    def build_merge(p):
        f = ctk.CTkFrame(p, fg_color="transparent")
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(f, text="Połącz kilka PDF-ów w jeden (kolejność jak na liście)",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 10))
        flb = FileListBox(f, filetypes=[("PDF", "*.pdf")])
        flb.grid(row=1, column=0, sticky="nsew")

        out_row = ctk.CTkFrame(f, fg_color="transparent")
        out_row.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        out_row.grid_columnconfigure(0, weight=1)
        out_e = ctk.CTkEntry(out_row, placeholder_text="polaczony.pdf")
        out_e.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(out_row, text="Zapisz jako...", width=110,
                      command=lambda: browse_save(out_e, ".pdf", [("PDF", "*.pdf")])).grid(row=0, column=1, padx=(6, 0))

        def on_run():
            inputs, raw_output = flb.get_paths(), out_e.get().strip()
            if len(inputs) < 2 or not raw_output:
                messagebox.showwarning("Brakuje danych", "Dodaj min. 2 pliki PDF i podaj plik wyjściowy.")
                return
            output = resolve_output_path(raw_output)
            app.run_async(lambda: documents.merge_pdf(output, inputs), trigger_button=btn,
                          on_success=lambda _: app.log(f"Zapisano: {output}"),
                          busy_text=f"Łączę {len(inputs)} plików PDF...")

        btn = ctk.CTkButton(f, text="Połącz PDF-y", command=on_run)
        btn.grid(row=3, column=0, sticky="w", pady=10)
        return f

    def build_split(p):
        f = ctk.CTkFrame(p, fg_color="transparent")
        f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(f, text="Rozdziel PDF na pojedyncze strony", font=ctk.CTkFont(weight="bold"))\
            .grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        labeled_row(f, 1, "Plik PDF:")
        in_e = ctk.CTkEntry(f, placeholder_text="wybierz plik lub przeciągnij go tutaj...")
        in_e.grid(row=1, column=1, sticky="ew", padx=6, pady=6)
        ctk.CTkButton(f, text="Przeglądaj...", width=110,
                      command=lambda: browse_open(in_e, [("PDF", "*.pdf")])).grid(row=1, column=2, pady=6)
        enable_file_drop(in_e, lambda paths: (in_e.delete(0, "end"), in_e.insert(0, paths[0])))

        labeled_row(f, 2, "Folder wyjściowy:")
        out_e = ctk.CTkEntry(f)
        out_e.grid(row=2, column=1, sticky="ew", padx=6, pady=6)
        ctk.CTkButton(f, text="Wybierz folder...", width=110, command=lambda: browse_dir(out_e)).grid(row=2, column=2, pady=6)

        def on_run():
            if not in_e.get().strip() or not out_e.get().strip():
                messagebox.showwarning("Brakuje danych", "Podaj plik PDF i folder wyjściowy.")
                return
            output_dir = resolve_output_path(out_e.get().strip())
            def do():
                return documents.split_pdf(in_e.get().strip(), output_dir)
            app.run_async(do, trigger_button=btn,
                          on_success=lambda paths: app.log(f"Zapisano {len(paths)} stron -> {output_dir}"),
                          busy_text="Rozdzielam PDF...")

        btn = ctk.CTkButton(f, text="Rozdziel na strony", command=on_run)
        btn.grid(row=3, column=0, sticky="w", pady=(14, 0))
        return f

    def build_rotate(p):
        f = ctk.CTkFrame(p, fg_color="transparent")
        f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(f, text="Obróć strony PDF", font=ctk.CTkFont(weight="bold"))\
            .grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        labeled_row(f, 1, "Plik PDF:")
        in_e = ctk.CTkEntry(f, placeholder_text="wybierz plik lub przeciągnij go tutaj...")
        in_e.grid(row=1, column=1, sticky="ew", padx=6, pady=6)

        def on_input_selected(path):
            in_e.delete(0, "end")
            in_e.insert(0, path)
            out_e.delete(0, "end")
            out_e.insert(0, suggest_output(path, "_rotated"))

        def on_browse():
            path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
            if path:
                on_input_selected(path)

        ctk.CTkButton(f, text="Przeglądaj...", width=110, command=on_browse).grid(row=1, column=2, pady=6)
        enable_file_drop(in_e, lambda paths: on_input_selected(paths[0]))

        labeled_row(f, 2, "Stopnie:")
        degrees_menu = ctk.CTkOptionMenu(f, values=["90", "180", "270"])
        degrees_menu.set("90")
        degrees_menu.grid(row=2, column=1, sticky="w", padx=6, pady=6)

        labeled_row(f, 3, "Plik wyjściowy:")
        out_e = ctk.CTkEntry(f)
        out_e.grid(row=3, column=1, sticky="ew", padx=6, pady=6)
        ctk.CTkButton(f, text="Zapisz jako...", width=110,
                      command=lambda: browse_save(out_e, ".pdf", [("PDF", "*.pdf")])).grid(row=3, column=2, pady=6)

        def on_run():
            if not in_e.get().strip() or not out_e.get().strip():
                messagebox.showwarning("Brakuje danych", "Podaj plik wejściowy i wyjściowy.")
                return
            output_path = resolve_output_path(out_e.get().strip())
            app.run_async(lambda: documents.rotate_pdf(in_e.get().strip(), output_path,
                                                        degrees=int(degrees_menu.get())),
                          trigger_button=btn, on_success=lambda _: app.log(f"Zapisano: {output_path}"),
                          busy_text="Obracam strony...")

        btn = ctk.CTkButton(f, text="Obróć", command=on_run)
        btn.grid(row=4, column=0, sticky="w", pady=(14, 0))
        return f

    def build_img_to_pdf(p):
        f = ctk.CTkFrame(p, fg_color="transparent")
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(f, text="Połącz obrazy w jeden PDF (kolejność jak na liście)",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 10))
        flb = FileListBox(f, filetypes=[("Obrazy", "*.jpg *.jpeg *.png *.webp *.bmp *.tiff")])
        flb.grid(row=1, column=0, sticky="nsew")

        out_row = ctk.CTkFrame(f, fg_color="transparent")
        out_row.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        out_row.grid_columnconfigure(0, weight=1)
        out_e = ctk.CTkEntry(out_row, placeholder_text="album.pdf")
        out_e.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(out_row, text="Zapisz jako...", width=110,
                      command=lambda: browse_save(out_e, ".pdf", [("PDF", "*.pdf")])).grid(row=0, column=1, padx=(6, 0))

        def on_run():
            inputs, raw_output = flb.get_paths(), out_e.get().strip()
            if not inputs or not raw_output:
                messagebox.showwarning("Brakuje danych", "Dodaj co najmniej jeden obraz i podaj plik wyjściowy.")
                return
            output = resolve_output_path(raw_output)
            app.run_async(lambda: documents.images_to_pdf(output, inputs), trigger_button=btn,
                          on_success=lambda _: app.log(f"Zapisano: {output}"),
                          busy_text=f"Tworzę PDF z {len(inputs)} obrazów...")

        btn = ctk.CTkButton(f, text="Utwórz PDF", command=on_run)
        btn.grid(row=3, column=0, sticky="w", pady=10)
        return f

    def build_ocr(p):
        f = ctk.CTkFrame(p, fg_color="transparent")
        f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(f, text="OCR - wyciągnij tekst ze skanu PDF (wymaga Tesseract + Poppler)",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        labeled_row(f, 1, "Plik PDF:")
        in_e = ctk.CTkEntry(f, placeholder_text="wybierz plik lub przeciągnij go tutaj...")
        in_e.grid(row=1, column=1, sticky="ew", padx=6, pady=6)

        def on_input_selected(path):
            in_e.delete(0, "end")
            in_e.insert(0, path)
            out_e.delete(0, "end")
            out_e.insert(0, suggest_output(path, "", ".txt"))

        def on_browse():
            path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
            if path:
                on_input_selected(path)

        ctk.CTkButton(f, text="Przeglądaj...", width=110, command=on_browse).grid(row=1, column=2, pady=6)
        enable_file_drop(in_e, lambda paths: on_input_selected(paths[0]))

        labeled_row(f, 2, "Język (tesseract):")
        lang_e = ctk.CTkEntry(f)
        lang_e.insert(0, "pol+eng")
        lang_e.grid(row=2, column=1, sticky="ew", padx=6, pady=6)

        labeled_row(f, 3, "Plik wyjściowy (.txt):")
        out_e = ctk.CTkEntry(f)
        out_e.grid(row=3, column=1, sticky="ew", padx=6, pady=6)
        ctk.CTkButton(f, text="Zapisz jako...", width=110,
                      command=lambda: browse_save(out_e, ".txt", [("Tekst", "*.txt")])).grid(row=3, column=2, pady=6)

        def on_run():
            if not in_e.get().strip() or not out_e.get().strip():
                messagebox.showwarning("Brakuje danych", "Podaj plik wejściowy i wyjściowy.")
                return
            output_path = resolve_output_path(out_e.get().strip())
            app.run_async(lambda: documents.ocr_pdf_to_text(in_e.get().strip(), output_path,
                                                              lang=lang_e.get().strip() or "pol+eng"),
                          trigger_button=btn, on_success=lambda _: app.log(f"Zapisano: {output_path}"),
                          busy_text="Rozpoznaję tekst (OCR)...")

        btn = ctk.CTkButton(f, text="Rozpoznaj tekst", command=on_run)
        btn.grid(row=4, column=0, sticky="w", pady=(14, 0))
        return f

    outer = ctk.CTkFrame(parent, fg_color="transparent")
    outer.grid_columnconfigure(0, weight=1)
    outer.grid_rowconfigure(0, weight=1)
    SegmentedStack(outer, {
        "Połącz PDF": build_merge,
        "Rozdziel PDF": build_split,
        "Obróć PDF": build_rotate,
        "Obrazy → PDF": build_img_to_pdf,
        "OCR": build_ocr,
    }).grid(row=0, column=0, sticky="nsew")
    return outer


# ============================================================ Archiwa =====
def build_archives_page(parent, app):
    def build_pack(p):
        f = ctk.CTkFrame(p, fg_color="transparent")
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(f, text="Spakuj pliki/foldery do ZIP lub TAR.GZ", font=ctk.CTkFont(weight="bold"))\
            .grid(row=0, column=0, sticky="w", pady=(0, 10))
        flb = FileListBox(f, allow_folders=True)
        flb.grid(row=1, column=0, sticky="nsew")

        out_row = ctk.CTkFrame(f, fg_color="transparent")
        out_row.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        out_row.grid_columnconfigure(0, weight=1)
        out_e = ctk.CTkEntry(out_row, placeholder_text="archiwum.zip lub archiwum.tar.gz")
        out_e.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(out_row, text="Zapisz jako...", width=110,
                      command=lambda: browse_save(
                          out_e, filetypes=[("ZIP", "*.zip"), ("TAR.GZ", "*.tar.gz *.tgz")])
                      ).grid(row=0, column=1, padx=(6, 0))

        def on_run():
            inputs, raw_output = flb.get_paths(), out_e.get().strip()
            if not inputs or not raw_output:
                messagebox.showwarning("Brakuje danych", "Dodaj pliki/foldery i podaj nazwę archiwum.")
                return
            output = resolve_output_path(raw_output)

            def do():
                if output.endswith(".zip"):
                    archives.pack_zip(output, inputs)
                else:
                    archives.pack_tar(output, inputs, gz=output.endswith((".gz", ".tgz")))

            app.run_async(do, trigger_button=btn, on_success=lambda _: app.log(f"Zapisano: {output}"),
                          busy_text=f"Pakuję {len(inputs)} pozycji...")

        btn = ctk.CTkButton(f, text="Spakuj", command=on_run)
        btn.grid(row=3, column=0, sticky="w", pady=10)
        return f

    def build_unpack(p):
        f = ctk.CTkFrame(p, fg_color="transparent")
        f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(f, text="Rozpakuj ZIP lub TAR.GZ", font=ctk.CTkFont(weight="bold"))\
            .grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        labeled_row(f, 1, "Plik archiwum:")
        in_e = ctk.CTkEntry(f, placeholder_text="wybierz plik lub przeciągnij go tutaj...")
        in_e.grid(row=1, column=1, sticky="ew", padx=6, pady=6)
        ctk.CTkButton(f, text="Przeglądaj...", width=110,
                      command=lambda: browse_open(in_e, [("Archiwa", "*.zip *.tar.gz *.tgz *.tar")])
                      ).grid(row=1, column=2, pady=6)
        enable_file_drop(in_e, lambda paths: (in_e.delete(0, "end"), in_e.insert(0, paths[0])))

        labeled_row(f, 2, "Folder wyjściowy:")
        out_e = ctk.CTkEntry(f)
        out_e.grid(row=2, column=1, sticky="ew", padx=6, pady=6)
        ctk.CTkButton(f, text="Wybierz folder...", width=110, command=lambda: browse_dir(out_e)).grid(row=2, column=2, pady=6)

        def on_run():
            input_path, raw_output_dir = in_e.get().strip(), out_e.get().strip()
            if not input_path or not raw_output_dir:
                messagebox.showwarning("Brakuje danych", "Podaj plik archiwum i folder wyjściowy.")
                return
            output_dir = resolve_output_path(raw_output_dir)

            def do():
                if input_path.endswith(".zip"):
                    archives.unpack_zip(input_path, output_dir)
                else:
                    archives.unpack_tar(input_path, output_dir)

            app.run_async(do, trigger_button=btn, on_success=lambda _: app.log(f"Rozpakowano -> {output_dir}"),
                          busy_text="Rozpakowuję...")

        btn = ctk.CTkButton(f, text="Rozpakuj", command=on_run)
        btn.grid(row=3, column=0, sticky="w", pady=(14, 0))
        return f

    outer = ctk.CTkFrame(parent, fg_color="transparent")
    outer.grid_columnconfigure(0, weight=1)
    outer.grid_rowconfigure(0, weight=1)
    SegmentedStack(outer, {"Spakuj": build_pack, "Rozpakuj": build_unpack}).grid(row=0, column=0, sticky="nsew")
    return outer


# ======================================================= Pobierz z linku ===
def build_download_page(parent, app):
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    frame.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(frame, text="Pobierz film z linku (YouTube, Facebook i inne wspierane przez yt-dlp)",
                 font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
    ctk.CTkLabel(frame, text="Pobieranie z tych serwisów łamie ich regulaminy nawet do użytku prywatnego -\n"
                             "to Twoja decyzja, czy i co pobierasz.",
                 text_color="gray60", font=ctk.CTkFont(size=11), justify="left").grid(
        row=1, column=0, columnspan=3, sticky="w", pady=(0, 16))

    labeled_row(frame, 2, "Link:")
    url_e = ctk.CTkEntry(frame, placeholder_text="wklej link do filmu (YouTube, Facebook, ...)")
    url_e.grid(row=2, column=1, sticky="ew", padx=6, pady=6)
    check_btn = ctk.CTkButton(frame, text="Sprawdź", width=110)
    check_btn.grid(row=2, column=2, pady=6)

    info_label = ctk.CTkLabel(frame, text="", text_color="gray60", justify="left", anchor="w")
    info_label.grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 12))

    labeled_row(frame, 4, "Jakość:")
    quality_menu = ctk.CTkOptionMenu(frame, values=download_mod.QUALITY_LABELS, width=180)
    quality_menu.set(download_mod.QUALITY_LABELS[0])
    quality_menu.grid(row=4, column=1, sticky="w", padx=6, pady=6)

    browser_labels = [download_mod.BROWSER_LABELS[b] for b in download_mod.BROWSERS]
    label_to_browser = {v: k for k, v in download_mod.BROWSER_LABELS.items()}

    cookies_var = tk.BooleanVar(value=False)
    cookies_row = ctk.CTkFrame(frame, fg_color="transparent")
    cookies_row.grid(row=5, column=0, columnspan=3, sticky="w", pady=(0, 6))
    browser_menu = ctk.CTkOptionMenu(cookies_row, values=browser_labels, width=110, state="disabled")
    browser_menu.set(browser_labels[0])

    def on_cookies_toggle():
        browser_menu.configure(state="normal" if cookies_var.get() else "disabled")

    ctk.CTkCheckBox(cookies_row, text="Użyj ciasteczek z przeglądarki (część filmów z Facebooka tego wymaga)",
                     variable=cookies_var, command=on_cookies_toggle).pack(side="left")
    browser_menu.pack(side="left", padx=(10, 0))

    ctk.CTkLabel(frame, text="Chrome/Edge/Opera/Opera GX/Brave blokują odczyt ciasteczek, gdy przeglądarka "
                             "jest otwarta - zamknij ją przed pobieraniem (Firefox tego nie wymaga).",
                 text_color="gray60", font=ctk.CTkFont(size=11)).grid(
        row=6, column=0, columnspan=3, sticky="w", pady=(0, 10))

    labeled_row(frame, 7, "Plik wyjściowy:")
    out_e = ctk.CTkEntry(frame, placeholder_text="nazwa uzupełni się po sprawdzeniu linku")
    out_e.grid(row=7, column=1, sticky="ew", padx=6, pady=6)
    ctk.CTkButton(frame, text="Zapisz jako...", width=110, command=lambda: browse_save(out_e)).grid(row=7, column=2, pady=6)

    state = {"last_title": None}

    def current_cookies_browser():
        return label_to_browser.get(browser_menu.get()) if cookies_var.get() else None

    def output_ext():
        return ".mp3" if quality_menu.get() == download_mod.AUDIO_ONLY_LABEL else ".mp4"

    def fill_output_name(title):
        out_e.delete(0, "end")
        out_e.insert(0, os.path.join(get_default_save_dir(), sanitize_filename(title) + output_ext()))

    def on_quality_change(_choice):
        # Podmienia tylko rozszerzenie na zgodne z nowym wyborem, zachowując nazwę -
        # dotyczy tylko nazwy już uzupełnionej wcześniej (po Sprawdź), żeby nie
        # nadpisywać czegoś, co użytkownik sam wpisał/wybrał ręcznie.
        if state["last_title"] and out_e.get().strip():
            base, _old_ext = os.path.splitext(out_e.get().strip())
            out_e.delete(0, "end")
            out_e.insert(0, base + output_ext())

    quality_menu.configure(command=on_quality_change)

    def on_check():
        url = url_e.get().strip()
        if not url:
            messagebox.showwarning("Brak linku", "Wklej link do filmu.")
            return
        cookies_browser = current_cookies_browser()

        def on_ready(info):
            title = info["title"]
            duration = info["duration"]
            dur_text = format_hhmmss(duration) if duration else "nieznana (transmisja na żywo?)"
            uploader_part = f" — {info['uploader']}" if info.get("uploader") else ""
            info_label.configure(text=f"„{title}”{uploader_part} • długość: {dur_text}", text_color="gray80")
            state["last_title"] = title
            if not out_e.get().strip():
                fill_output_name(title)

        app.run_async(lambda: download_mod.get_info(url, cookies_browser=cookies_browser),
                      trigger_button=check_btn, on_success=on_ready, busy_text="Sprawdzam link...")

    check_btn.configure(command=on_check)
    url_e.bind("<Return>", lambda _e: on_check())

    def make_progress_hook():
        # yt-dlp wywołuje ten hook z wątku roboczego (patrz run_async) - stąd
        # aktualizacja etykiety statusu tylko przez app.after(0, ...), tak samo
        # jak _finish() robi to dla wyniku całej operacji. Bez tego samo pobieranie
        # działa (jak wyżej zdiagnozowane - problem był w player_client, nie w
        # braku postępu), ale przy większym/wolniejszym pobieraniu wygląda jak
        # zawieszone, skoro pasek postępu jest tylko animowaną kreską bez %.
        last_shown = [""]

        def hook(d):
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded = d.get("downloaded_bytes") or 0
                if total:
                    text = f"Pobieram... {downloaded / total * 100:.0f}%"
                else:
                    text = f"Pobieram... {downloaded / 1_048_576:.1f} MB"
                speed = d.get("speed")
                if speed:
                    text += f" ({speed / 1_048_576:.1f} MB/s)"
            elif status == "finished":
                text = "Przetwarzam (łączę wideo+audio / konwertuję)..."
            else:
                return
            if text != last_shown[0]:
                last_shown[0] = text
                app.after(0, lambda t=text: app.status_label.configure(text=t))

        return hook

    def on_download():
        url, raw_output = url_e.get().strip(), out_e.get().strip()
        if not url or not raw_output:
            messagebox.showwarning("Brakuje danych", "Podaj link i plik wyjściowy (albo najpierw kliknij Sprawdź).")
            return
        output_path = resolve_output_path(raw_output)
        quality_label = quality_menu.get()
        cookies_browser = current_cookies_browser()

        def on_ready(result):
            final_path, height, was_blocked = result
            if was_blocked and height:
                app.log(f"⚠ YouTube zablokował pobieranie w wyższej jakości i ograniczył ten "
                        f"film do {height}p mimo wyboru {quality_label} (zwykle dotyczy mocno "
                        f"chronionych/oficjalnych teledysków).")
            app.log(f"Zapisano: {final_path}")

        app.log(f"Pobieram {url} -> {output_path}")
        app.run_async(
            lambda: download_mod.download(url, output_path, quality_label=quality_label,
                                           cookies_browser=cookies_browser,
                                           progress_hook=make_progress_hook()),
            trigger_button=download_btn,
            on_success=on_ready,
            busy_text="Pobieram (może to chwilę potrwać, w zależności od długości i jakości)...")

    download_btn = ctk.CTkButton(frame, text="⬇ Pobierz", command=on_download)
    download_btn.grid(row=8, column=0, sticky="w", pady=(16, 0))

    return frame


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
