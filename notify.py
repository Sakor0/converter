"""
notify.py - Powiadomienie systemowe (dymek w zasobniku / toast w Centrum
akcji) po zakończeniu dłuższej operacji (pobieranie, partia plików, OCR) -
żeby wynik był widoczny nawet gdy okno aplikacji jest zminimalizowane albo
w tle. Czysty ctypes wołający Shell_NotifyIcon (bez dodatkowej zależności
pip/pywin32, więc nic dodatkowego nie trzeba dokładać do build_release.py) -
na Windows 10/11 taki dymek jest automatycznie pokazywany jako zwykły toast.

Poza Windows to zwyczajny no-op (funkcja notify() nic nie robi) - reszta
programu (CLI, konwertery) działa wieloplatformowo i nie powinna nagle
wymagać Windows tylko z powodu powiadomień.
"""

import os
import sys
import threading

_ENABLED = sys.platform == "win32"

if _ENABLED:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _shell32 = ctypes.windll.shell32
    _kernel32 = ctypes.windll.kernel32

    _NIM_ADD, _NIM_MODIFY, _NIM_DELETE = 0x00000000, 0x00000001, 0x00000002
    _NIF_MESSAGE, _NIF_ICON, _NIF_TIP, _NIF_INFO = 0x01, 0x02, 0x04, 0x10
    _NIIF_INFO = 0x00000001
    _WM_USER = 0x0400
    _IDI_APPLICATION = 32512
    _IMAGE_ICON = 1
    _LR_LOADFROMFILE = 0x00000010
    _LR_DEFAULTSIZE = 0x00000040

    class _NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon", wintypes.HICON),
            ("szTip", wintypes.WCHAR * 128),
            ("dwState", wintypes.DWORD),
            ("dwStateMask", wintypes.DWORD),
            ("szInfo", wintypes.WCHAR * 256),
            ("uTimeout", wintypes.UINT),
            ("szInfoTitle", wintypes.WCHAR * 64),
            ("dwInfoFlags", wintypes.DWORD),
            ("guidItem", ctypes.c_byte * 16),
            ("hBalloonIcon", wintypes.HICON),
        ]

    _WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT,
                                   wintypes.WPARAM, wintypes.LPARAM)

    class _WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", _WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    # Jawne argtypes/restype dla każdego wywołania - bez tego ctypes zgaduje
    # marshalling na podstawie typów pythonowych, a uchwyty (HWND/HINSTANCE/...)
    # to 64-bitowe wskaźniki, które jako "goły" python int potrafią przepełnić
    # domyślnie zakładane 32-bitowe c_int (OverflowError przy CreateWindowExW).
    _kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    _kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    _user32.RegisterClassW.restype = wintypes.ATOM
    _user32.RegisterClassW.argtypes = [ctypes.POINTER(_WNDCLASSW)]
    _user32.CreateWindowExW.restype = wintypes.HWND
    _user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    _user32.DefWindowProcW.restype = ctypes.c_long
    _user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.LoadIconW.restype = wintypes.HICON
    _user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
    _user32.LoadImageW.restype = wintypes.HICON
    _user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    _shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    _shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(_NOTIFYICONDATAW)]

    _state = {"hwnd": None, "wndproc": None}
    _state_lock = threading.Lock()

    def _icon_path():
        if getattr(sys, "frozen", False):
            base = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, "assets", "icon.ico")

    def _load_icon():
        handle = _user32.LoadImageW(None, _icon_path(), _IMAGE_ICON, 0, 0,
                                     _LR_LOADFROMFILE | _LR_DEFAULTSIZE)
        if handle:
            return handle
        # Brak/zły plik ikony (np. inny układ folderów w spakowanej wersji) -
        # ogólna systemowa ikona zamiast całkiem rezygnować z powiadomienia.
        return _user32.LoadIconW(None, ctypes.cast(_IDI_APPLICATION, wintypes.LPCWSTR))

    def _get_hwnd():
        """Niewidoczne okno-wiadomość wymagane jako 'właściciel' ikony
        powiadomień (Shell_NotifyIcon go wymaga) - tworzone raz na cały czas
        działania programu, samo nigdy się nie pokazuje na ekranie."""
        with _state_lock:
            if _state["hwnd"] is not None:
                return _state["hwnd"]
            # Referencja do wndproc musi przeżyć tę funkcję - inaczej GC
            # zbiera callback, a Windows w końcu wywoła zwolniony wskaźnik.
            wndproc = _WNDPROC(lambda hwnd, msg, wp, lp: _user32.DefWindowProcW(hwnd, msg, wp, lp))
            hinst = _kernel32.GetModuleHandleW(None)
            wc = _WNDCLASSW()
            wc.lpfnWndProc = wndproc
            wc.hInstance = hinst
            wc.lpszClassName = "local_converter_notify"
            _user32.RegisterClassW(ctypes.byref(wc))
            hwnd = _user32.CreateWindowExW(0, wc.lpszClassName, "local_converter", 0,
                                            0, 0, 0, 0, None, None, hinst, None)
            _state["hwnd"] = hwnd
            _state["wndproc"] = wndproc
            return hwnd

    def _show(title, message):
        hwnd = _get_hwnd()
        nid = _NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = 1
        nid.uFlags = _NIF_MESSAGE | _NIF_ICON | _NIF_TIP
        nid.uCallbackMessage = _WM_USER + 20
        nid.hIcon = _load_icon()
        nid.szTip = "local_converter"
        _shell32.Shell_NotifyIconW(_NIM_ADD, ctypes.byref(nid))

        # Dwa oddzielne wywołania (NIM_ADD z samą ikoną, potem NIM_MODIFY z
        # dymkiem) zamiast jednego - to sprawdzony wzorzec z przykładów
        # Win32; próba spakowania NIF_INFO już do NIM_ADD bywa niestabilna
        # na części wersji Windows.
        nid.uFlags = _NIF_INFO
        nid.szInfo = message[:255]
        nid.szInfoTitle = title[:63]
        nid.dwInfoFlags = _NIIF_INFO
        _shell32.Shell_NotifyIconW(_NIM_MODIFY, ctypes.byref(nid))

        def cleanup():
            try:
                _shell32.Shell_NotifyIconW(_NIM_DELETE, ctypes.byref(nid))
            except Exception:
                pass

        # Usunięcie ikony od razu po dodaniu potrafi ubiec wyświetlenie
        # dymka - stąd sprzątanie kilka sekund później, w osobnym wątku.
        threading.Timer(8.0, cleanup).start()


def notify(title, message):
    """Pokazuje powiadomienie systemowe (no-op poza Windows). Nigdy nie
    rzuca wyjątku - to dodatek do właściwej operacji, nie jej część, więc
    awaria powiadomienia (stary Windows, wyłączone powiadomienia, Focus
    Assist) nie może przerwać/oznaczyć błędem samej konwersji/pobierania."""
    if not _ENABLED:
        return
    try:
        _show(title, message)
    except Exception:
        pass
