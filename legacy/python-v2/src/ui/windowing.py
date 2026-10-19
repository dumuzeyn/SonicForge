from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes


def centered_outer_position(work_area, outer_size):
    left, top, right, bottom = work_area
    width, height = outer_size
    return (
        round(left + ((right - left) - width) / 2),
        round(top + ((bottom - top) - height) / 2),
    )


def _geometry(width, height, x, y):
    x_part = f"+{x}" if x >= 0 else f"-{abs(x)}"
    y_part = f"+{y}" if y >= 0 else f"-{abs(y)}"
    return f"{width}x{height}{x_part}{y_part}"


def _window_handle(root):
    user32 = ctypes.windll.user32
    user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    user32.GetAncestor.restype = wintypes.HWND
    return user32.GetAncestor(root.winfo_id(), 2)


def set_native_window_icon(window, icon_path):
    """Set both shell icon sizes on the current Windows wrapper, including remaps."""
    if sys.platform != "win32":
        return
    user32 = ctypes.windll.user32
    user32.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.LoadImageW.argtypes = (wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                 ctypes.c_int, ctypes.c_int, wintypes.UINT)
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.DestroyIcon.argtypes = (wintypes.HICON,)
    if not hasattr(window, '_sonic_native_icons'):
        # Real ICO frames keep small title/taskbar icons crisp. Keep HICONs alive
        # for as long as the window uses them; never destroy a Tk-owned handle.
        handles = []
        for size_kind, metric in ((0, 49), (1, 11)):  # SMALLICON / ICON
            size = user32.GetSystemMetrics(metric)
            icon = user32.LoadImageW(None, str(icon_path), 1, size, size, 0x0010)
            if icon:
                handles.append((size_kind, icon))
        window._sonic_native_icons = handles

        def apply(event=None):
            if event is not None and event.widget is not window:
                return
            hwnd = _window_handle(window)
            for size_kind, icon in window._sonic_native_icons:
                user32.SendMessageW(hwnd, 0x0080, size_kind, icon)  # WM_SETICON

        def release(event):
            if event.widget is window:
                for _, icon in window._sonic_native_icons:
                    user32.DestroyIcon(icon)
                window._sonic_native_icons = []

        window._sonic_apply_native_icons = apply
        window.bind('<Map>', apply, add='+')
        window.bind('<Destroy>', release, add='+')
    window._sonic_apply_native_icons()


def _primary_work_area(root):
    if sys.platform != "win32":
        return (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())

    class MonitorInfo(ctypes.Structure):
        _fields_ = (
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        )

    user32 = ctypes.windll.user32
    user32.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = (wintypes.HMONITOR, ctypes.POINTER(MonitorInfo))
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    monitor = user32.MonitorFromWindow(_window_handle(root), 1)
    info = MonitorInfo(cbSize=ctypes.sizeof(MonitorInfo))
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        raise ctypes.WinError()
    return (info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom)


def _outer_bounds(root):
    if sys.platform != "win32":
        return (
            root.winfo_rootx(),
            root.winfo_rooty(),
            root.winfo_rootx() + root.winfo_width(),
            root.winfo_rooty() + root.winfo_height(),
        )
    user32 = ctypes.windll.user32
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    user32.GetWindowRect.restype = wintypes.BOOL
    rect = wintypes.RECT()
    if not user32.GetWindowRect(_window_handle(root), ctypes.byref(rect)):
        raise ctypes.WinError()
    return (rect.left, rect.top, rect.right, rect.bottom)


def show_centered(root, client_width, client_height, parent=None):
    previous_fade = getattr(root, '_sonic_fade_after', None)
    if previous_fade is not None:
        root.after_cancel(previous_fade)
        root._sonic_fade_after = None
    root.attributes("-alpha", 0.0)
    root.geometry(_geometry(client_width, client_height, 0, 0))
    root.deiconify()
    root.update_idletasks()

    work_area = _primary_work_area(parent or root)
    for _ in range(3):
        outer = _outer_bounds(root)
        outer_size = (outer[2] - outer[0], outer[3] - outer[1])
        target_x, target_y = centered_outer_position(work_area, outer_size)
        delta_x, delta_y = target_x - outer[0], target_y - outer[1]
        if abs(delta_x) <= 1 and abs(delta_y) <= 1:
            break
        root.geometry(
            _geometry(
                client_width,
                client_height,
                root.winfo_x() + delta_x,
                root.winfo_y() + delta_y,
            )
        )
        root.update_idletasks()

    outer = _outer_bounds(root)
    window_center = ((outer[0] + outer[2]) / 2, (outer[1] + outer[3]) / 2)
    work_center = (
        (work_area[0] + work_area[2]) / 2,
        (work_area[1] + work_area[3]) / 2,
    )
    result = {
        "client_size": (root.winfo_width(), root.winfo_height()),
        "outer_bounds": outer,
        "work_area": work_area,
        "window_center": window_center,
        "work_area_center": work_center,
        "center_delta": (
            window_center[0] - work_center[0],
            window_center[1] - work_center[1],
        ),
    }
    # A short non-blocking fade makes dialogs feel connected to the action
    # that opened them without delaying keyboard or mouse input.
    started = time.perf_counter()
    def fade():
        try:
            elapsed = min(1.0, (time.perf_counter() - started) / .14)
            root.attributes("-alpha", 1 - (1 - elapsed) ** 3)
            if elapsed < 1:
                root._sonic_fade_after = root.after(16, fade)
            else:
                root._sonic_fade_after = None
        except Exception:
            pass

    def cancel_fade(event):
        if event.widget is not root:
            return
        after_id = getattr(root, "_sonic_fade_after", None)
        if after_id is not None:
            try:
                root.after_cancel(after_id)
            except Exception:
                pass
            root._sonic_fade_after = None

    root.bind("<Destroy>", cancel_fade, add="+")
    fade()
    return result
