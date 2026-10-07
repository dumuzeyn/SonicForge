"""Early Windows splash with real per-pixel alpha, without Tk or a color key."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys
import threading


_splash = None


def premultiply_bgra(data):
    result = bytearray(data)
    for offset in range(0, len(result), 4):
        alpha = result[offset + 3]
        for channel in range(3):
            result[offset + channel] = (result[offset + channel] * alpha + 127) // 255
    return bytes(result)


class BitmapHeader(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('width', wintypes.LONG), ('height', wintypes.LONG),
                ('planes', wintypes.WORD), ('bits', wintypes.WORD), ('compression', wintypes.DWORD),
                ('image_size', wintypes.DWORD), ('xppm', wintypes.LONG), ('yppm', wintypes.LONG),
                ('used', wintypes.DWORD), ('important', wintypes.DWORD)]


class IconInfo(ctypes.Structure):
    _fields_ = [('is_icon', wintypes.BOOL), ('x', wintypes.DWORD), ('y', wintypes.DWORD),
                ('mask', wintypes.HBITMAP), ('color', wintypes.HBITMAP)]


class BlendFunction(ctypes.Structure):
    _fields_ = [('operation', wintypes.BYTE), ('flags', wintypes.BYTE),
                ('alpha', wintypes.BYTE), ('format', wintypes.BYTE)]


class Size(ctypes.Structure):
    _fields_ = [('cx', wintypes.LONG), ('cy', wintypes.LONG)]


class TransparentSplash:
    def __init__(self, icon_path):
        self.icon_path = icon_path
        self.hwnd = None
        self.error = None
        self.ready = threading.Event()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, name='SonicForgeSplash', daemon=True)

    def start(self):
        self.thread.start()
        self.ready.wait(.4)

    def close(self):
        self.stopped.set()
        if self.hwnd:
            user32 = ctypes.windll.user32
            user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
            user32.PostMessageW(self.hwnd, 0x0010, 0, 0)
        self.thread.join(.3)

    def _run(self):
        user32, gdi32, kernel32 = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.kernel32
        wndproc_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                         wintypes.WPARAM, wintypes.LPARAM)

        class WindowClass(ctypes.Structure):
            _fields_ = [('style', wintypes.UINT), ('proc', wndproc_type), ('class_extra', ctypes.c_int),
                        ('window_extra', ctypes.c_int), ('instance', wintypes.HINSTANCE),
                        ('icon', wintypes.HICON), ('cursor', wintypes.HANDLE), ('background', wintypes.HBRUSH),
                        ('menu', wintypes.LPCWSTR), ('name', wintypes.LPCWSTR)]

        kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.RegisterClassW.argtypes = (ctypes.POINTER(WindowClass),)
        user32.CreateWindowExW.argtypes = (wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                         ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                         wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p)
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.DestroyWindow.argtypes = (wintypes.HWND,)
        user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
        user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
        user32.DispatchMessageW.restype = ctypes.c_ssize_t
        user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
        user32.UnregisterClassW.argtypes = (wintypes.LPCWSTR, wintypes.HINSTANCE)
        user32.LoadImageW.argtypes = (wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                     ctypes.c_int, ctypes.c_int, wintypes.UINT)
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.GetIconInfo.argtypes = (wintypes.HICON, ctypes.POINTER(IconInfo))
        user32.DestroyIcon.argtypes = (wintypes.HICON,)
        user32.SystemParametersInfoW.argtypes = (wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT)
        gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
        gdi32.CreateCompatibleDC.restype = wintypes.HDC
        gdi32.CreateDIBSection.argtypes = (wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                         ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD)
        gdi32.CreateDIBSection.restype = wintypes.HBITMAP
        gdi32.GetDIBits.argtypes = (wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                                   ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT)
        gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HANDLE)
        gdi32.SelectObject.restype = wintypes.HANDLE
        gdi32.DeleteObject.argtypes = (wintypes.HANDLE,)
        gdi32.DeleteDC.argtypes = (wintypes.HDC,)
        user32.UpdateLayeredWindow.argtypes = (wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                             ctypes.POINTER(Size), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                             wintypes.COLORREF, ctypes.POINTER(BlendFunction), wintypes.DWORD)
        user32.UpdateLayeredWindow.restype = wintypes.BOOL

        @wndproc_type
        def wndproc(hwnd, message, wparam, lparam):
            if message == 0x0010:  # WM_CLOSE
                user32.DestroyWindow(hwnd)
                return 0
            if message == 0x0002:  # WM_DESTROY
                self.hwnd = None
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, message, wparam, lparam)

        instance = kernel32.GetModuleHandleW(None)
        class_name = 'SonicForgeTransparentSplash'
        window_class = WindowClass(instance=instance, proc=wndproc, name=class_name)
        dc, bitmap, previous, icon, registered = None, None, None, None, False
        info = IconInfo()
        try:
            width = height = 256
            dc = gdi32.CreateCompatibleDC(None)
            icon = user32.LoadImageW(None, str(self.icon_path), 1, width, height, 0x0010)
            if not icon or not user32.GetIconInfo(icon, ctypes.byref(info)):
                raise ctypes.WinError()
            header = BitmapHeader(size=ctypes.sizeof(BitmapHeader), width=width, height=-height,
                                  planes=1, bits=32)
            source = ctypes.create_string_buffer(width * height * 4)
            if not gdi32.GetDIBits(dc, info.color, 0, height, source, ctypes.byref(header), 0):
                raise ctypes.WinError()
            self.pixels = premultiply_bgra(source.raw)
            pixel_address = ctypes.c_void_p()
            bitmap = gdi32.CreateDIBSection(dc, ctypes.byref(header), 0, ctypes.byref(pixel_address), None, 0)
            if not bitmap:
                raise ctypes.WinError()
            ctypes.memmove(pixel_address, self.pixels, len(self.pixels))
            previous = gdi32.SelectObject(dc, bitmap)
            registered = bool(user32.RegisterClassW(ctypes.byref(window_class)))
            if not registered:
                raise ctypes.WinError()
            # Layered + tool window + topmost + no activation + click-through.
            self.hwnd = user32.CreateWindowExW(0x080800A8, class_name, 'SonicForge — Loading',
                                             0x80000000, 0, 0, width, height, None, None, instance, None)
            if not self.hwnd:
                raise ctypes.WinError()
            area = wintypes.RECT()
            user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0)
            position = wintypes.POINT((area.left + area.right - width) // 2,
                                      (area.top + area.bottom - height) // 2)
            size, origin, blend = Size(width, height), wintypes.POINT(0, 0), BlendFunction(0, 0, 255, 1)
            if not user32.UpdateLayeredWindow(self.hwnd, None, ctypes.byref(position), ctypes.byref(size),
                                            dc, ctypes.byref(origin), 0, ctypes.byref(blend), 2):
                raise ctypes.WinError()
            if self.stopped.is_set():
                return
            user32.ShowWindow(self.hwnd, 4)
            self.ready.set()
            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        except Exception as error:
            self.error = error  # Splash failure must not prevent app startup.
        finally:
            self.ready.set()
            if self.hwnd:
                user32.DestroyWindow(self.hwnd)
                self.hwnd = None
            if registered:
                user32.UnregisterClassW(class_name, instance)
            if previous:
                gdi32.SelectObject(dc, previous)
            for handle in (bitmap, info.color, info.mask):
                if handle:
                    gdi32.DeleteObject(handle)
            if icon:
                user32.DestroyIcon(icon)
            if dc:
                gdi32.DeleteDC(dc)


def show_splash():
    global _splash
    if sys.argv[1:2] == ['--lyrics-worker']:
        return
    if sys.platform != 'win32' or _splash is not None:
        return
    local_data = os.environ.get('LOCALAPPDATA')
    if local_data and (Path(local_data) / 'SonicForge' / 'hide_splash.flag').exists():
        return
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    icon_path = root / 'assets' / 'sonic_forge_mark.ico'
    if icon_path.is_file():
        _splash = TransparentSplash(icon_path)
        _splash.start()


def close_splash():
    global _splash
    if _splash is not None:
        _splash.close()
        _splash = None
