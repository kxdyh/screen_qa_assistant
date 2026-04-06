from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication


WM_HOTKEY = 0x0312
WM_NCDESTROY = 0x0082
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
ERROR_HOTKEY_ALREADY_REGISTERED = 1409
ERROR_INVALID_WINDOW_HANDLE = 1400
ERROR_CLASS_ALREADY_EXISTS = 1410

USER32 = ctypes.windll.user32
KERNEL32 = ctypes.windll.kernel32
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

USER32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
USER32.DefWindowProcW.restype = LRESULT
USER32.DestroyWindow.argtypes = [wintypes.HWND]
USER32.DestroyWindow.restype = wintypes.BOOL
USER32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
USER32.RegisterHotKey.restype = wintypes.BOOL
USER32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
USER32.UnregisterHotKey.restype = wintypes.BOOL
KERNEL32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
KERNEL32.GetModuleHandleW.restype = wintypes.HINSTANCE


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt_x", wintypes.LONG),
        ("pt_y", wintypes.LONG),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.c_uint),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", ctypes.c_void_p),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


USER32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
USER32.RegisterClassW.restype = wintypes.ATOM
USER32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    ctypes.c_void_p,
]
USER32.CreateWindowExW.restype = wintypes.HWND


def parse_hotkey(sequence: str) -> tuple[int, int]:
    parts = [part.strip().upper() for part in sequence.split("+") if part.strip()]
    if len(parts) < 2:
        raise ValueError("快捷键至少需要一个修饰键和一个主键")

    modifiers = 0
    for modifier in parts[:-1]:
        if modifier == "CTRL":
            modifiers |= MOD_CONTROL
        elif modifier == "SHIFT":
            modifiers |= MOD_SHIFT
        elif modifier == "ALT":
            modifiers |= MOD_ALT
        elif modifier in {"WIN", "META"}:
            modifiers |= MOD_WIN
        else:
            raise ValueError(f"不支持的修饰键：{modifier}")

    key_part = parts[-1]
    if len(key_part) == 1 and key_part.isalnum():
        return modifiers, ord(key_part)
    if key_part.startswith("F") and key_part[1:].isdigit():
        index = int(key_part[1:])
        if 1 <= index <= 24:
            return modifiers, 0x6F + index

    special = {
        "SPACE": 0x20,
        "TAB": 0x09,
        "ENTER": 0x0D,
        "ESC": 0x1B,
        "ESCAPE": 0x1B,
        "PRINTSCREEN": 0x2C,
        "UP": 0x26,
        "DOWN": 0x28,
        "LEFT": 0x25,
        "RIGHT": 0x27,
        "HOME": 0x24,
        "END": 0x23,
        "PAGEUP": 0x21,
        "PAGEDOWN": 0x22,
        "INSERT": 0x2D,
        "DELETE": 0x2E,
    }
    if key_part in special:
        return modifiers, special[key_part]
    raise ValueError(f"不支持的主键：{key_part}")


def _hotkey_error_message(error_code: int) -> str:
    if error_code == ERROR_HOTKEY_ALREADY_REGISTERED:
        return "这个快捷键已经被其他程序占用了，请换一个组合键。"
    if error_code == ERROR_INVALID_WINDOW_HANDLE:
        return "快捷键注册失败：窗口句柄无效。"
    return f"全局快捷键注册失败，错误码 {error_code}。"


def probe_hotkey_registration(
    sequence: str,
    *,
    user32=USER32,
    error_getter: Callable[[], int] = ctypes.GetLastError,
) -> tuple[bool, str | None]:
    try:
        modifiers, key_code = parse_hotkey(sequence)
    except ValueError as exc:
        return False, str(exc)

    probe_id = 0x5A11
    if user32.RegisterHotKey(None, probe_id, modifiers, key_code):
        user32.UnregisterHotKey(None, probe_id)
        return True, None
    return False, _hotkey_error_message(error_getter())


class GlobalHotkeyWidget(QObject):
    activated = Signal()
    registration_failed = Signal(str)

    _window_class_name = "ScreenQAAssistantHotkeySink"
    _window_class_registered = False
    _instances: dict[int, "GlobalHotkeyWidget"] = {}
    _wnd_proc_ref: WNDPROC | None = None

    def __init__(self, app: QApplication | None = None) -> None:
        resolved_app = app or QApplication.instance()
        if resolved_app is None:
            raise RuntimeError("GlobalHotkeyWidget 需要在 QApplication 创建后初始化")
        super().__init__(resolved_app)
        self._app = resolved_app
        self._hotkey_id = 1
        self._registered = False
        self._hwnd = self._create_window()
        self._app.aboutToQuit.connect(self.dispose)

    def register_hotkey(self, sequence: str) -> bool:
        self.unregister_hotkey()
        try:
            modifiers, key_code = parse_hotkey(sequence)
        except ValueError as exc:
            self.registration_failed.emit(str(exc))
            return False

        if not USER32.RegisterHotKey(self._hwnd, self._hotkey_id, modifiers, key_code):
            self.registration_failed.emit(_hotkey_error_message(ctypes.GetLastError()))
            return False
        self._registered = True
        return True

    def unregister_hotkey(self) -> None:
        if self._registered:
            USER32.UnregisterHotKey(self._hwnd, self._hotkey_id)
            self._registered = False

    def nativeEventFilter(self, eventType, message):  # type: ignore[override]
        if eventType not in {b"windows_generic_MSG", b"windows_dispatcher_MSG", "windows_generic_MSG", "windows_dispatcher_MSG"}:
            return False, 0
        msg = MSG.from_address(int(message))
        return self._dispatch_native_message(msg.message, int(msg.wParam))

    @property
    def window_handle(self) -> int:
        try:
            return int(self._hwnd)
        except (TypeError, ValueError):
            return 0

    def dispose(self) -> None:
        self.unregister_hotkey()
        if self._hwnd:
            self._instances.pop(int(self._hwnd), None)
            USER32.DestroyWindow(self._hwnd)
            self._hwnd = wintypes.HWND()

    def _dispatch_native_message(self, message_code: int, hotkey_id: int) -> tuple[bool, int]:
        if message_code == WM_HOTKEY and hotkey_id == self._hotkey_id:
            self.activated.emit()
            return True, 0
        return False, 0

    @classmethod
    def _ensure_window_class(cls) -> None:
        if cls._window_class_registered:
            return

        @WNDPROC
        def _wnd_proc(hwnd, message, wparam, lparam):
            instance = cls._instances.get(int(hwnd))
            if instance is not None:
                handled, result = instance._dispatch_native_message(int(message), int(wparam))
                if handled:
                    return result
                if message == WM_NCDESTROY:
                    cls._instances.pop(int(hwnd), None)
            return USER32.DefWindowProcW(hwnd, message, wparam, lparam)

        wnd_class = WNDCLASSW()
        wnd_class.lpfnWndProc = _wnd_proc
        wnd_class.hInstance = KERNEL32.GetModuleHandleW(None)
        wnd_class.lpszClassName = cls._window_class_name

        atom = USER32.RegisterClassW(ctypes.byref(wnd_class))
        if not atom and ctypes.GetLastError() != ERROR_CLASS_ALREADY_EXISTS:
            raise OSError(ctypes.GetLastError(), "注册全局快捷键窗口类失败")

        cls._wnd_proc_ref = _wnd_proc
        cls._window_class_registered = True

    def _create_window(self) -> wintypes.HWND:
        self._ensure_window_class()
        hwnd = USER32.CreateWindowExW(
            0,
            self._window_class_name,
            self._window_class_name,
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            KERNEL32.GetModuleHandleW(None),
            None,
        )
        if not hwnd:
            raise OSError(ctypes.GetLastError(), "创建全局快捷键窗口失败")
        self._instances[int(hwnd)] = self
        return hwnd
