"""Capture only the test-created app windows at native resolution for visual QA."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import statistics
import sys
import time

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from music_polisher_gui import SonicForgeApp
from ui.windowing import _window_handle, _outer_bounds


def capture(window, destination):
    class BitmapHeader(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('width', wintypes.LONG), ('height', wintypes.LONG),
                    ('planes', wintypes.WORD), ('bits', wintypes.WORD), ('compression', wintypes.DWORD),
                    ('image_size', wintypes.DWORD), ('xppm', wintypes.LONG), ('yppm', wintypes.LONG),
                    ('used', wintypes.DWORD), ('important', wintypes.DWORD)]

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    hwnd = _window_handle(window)
    left, top, right, bottom = _outer_bounds(window)
    width, height = right - left, bottom - top
    user32.GetDC.argtypes = (wintypes.HWND,)
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
    user32.PrintWindow.argtypes = (wintypes.HWND, wintypes.HDC, wintypes.UINT)
    gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateDIBSection.argtypes = (wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                     ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD)
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HANDLE)
    gdi32.SelectObject.restype = wintypes.HANDLE
    gdi32.DeleteObject.argtypes = (wintypes.HANDLE,)
    gdi32.DeleteDC.argtypes = (wintypes.HDC,)
    screen_dc = user32.GetDC(hwnd)
    dc = gdi32.CreateCompatibleDC(screen_dc)
    header = BitmapHeader(size=ctypes.sizeof(BitmapHeader), width=width, height=-height, planes=1, bits=32)
    pixels = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(dc, ctypes.byref(header), 0, ctypes.byref(pixels), None, 0)
    previous = gdi32.SelectObject(dc, bitmap)
    try:
        if not user32.PrintWindow(hwnd, dc, 2):
            raise ctypes.WinError()
        data = ctypes.string_at(pixels, width * height * 4)
        Image.frombytes('RGB', (width, height), data, 'raw', 'BGRX').save(destination)
    finally:
        gdi32.SelectObject(dc, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(dc)
        user32.ReleaseDC(hwnd, screen_dc)


def settle(window):
    window.update()
    fade = getattr(window, '_sonic_fade_after', None)
    if fade:
        window.after_cancel(fade)
        window._sonic_fade_after = None
    window.attributes('-alpha', 1)
    window.update()


def main():
    output = Path(__file__).resolve().parents[1] / 'validation'
    output.mkdir(exist_ok=True)
    app = SonicForgeApp()
    try:
        settle(app)
        durations = []
        for _ in range(10):
            for name in ('metadata', 'editor', 'audio', 'editor'):
                start = time.perf_counter()
                app.view.show_tab(name)
                durations.append((time.perf_counter() - start) * 1000)
                app.update()
        capture(app, output / 'navigation-editor-current.png')
        app.view.show_tab('settings')
        settle(app)
        capture(app, output / 'navigation-settings-current.png')
        app.show_advanced_audio()
        dialog = app.advanced_dialog
        dialog.notebook.select(dialog.effects_tab)
        settle(dialog)
        capture(dialog, output / 'navigation-effects-current.png')
        print(f'40 switches: median {statistics.median(durations):.1f} ms; max {max(durations):.1f} ms')
        print(output / 'navigation-editor-current.png')
        print(output / 'navigation-settings-current.png')
        print(output / 'navigation-effects-current.png')
        dialog.close()
    finally:
        app._close()


if __name__ == '__main__':
    main()
