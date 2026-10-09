"""Keep native GUI tests from leaving fixtures in the user's clipboard."""
import ctypes
from ctypes import wintypes
import os
import time


class ClipboardGuard:
    def __init__(self, root):
        self.root = root
        self.formats = []
        self.bitmap = None
        if os.name != 'nt':
            try:
                self.text = root.clipboard_get()
            except Exception:
                self.text = None
            return
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        for name, args, result in (
            ('OpenClipboard', [wintypes.HWND], wintypes.BOOL),
            ('CloseClipboard', [], wintypes.BOOL),
            ('EnumClipboardFormats', [wintypes.UINT], wintypes.UINT),
            ('GetClipboardData', [wintypes.UINT], wintypes.HANDLE),
            ('SetClipboardData', [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE),
            ('EmptyClipboard', [], wintypes.BOOL),
            ('CopyImage', [wintypes.HANDLE, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT], wintypes.HANDLE),
        ):
            function = getattr(self.user, name)
            function.argtypes, function.restype = args, result
        for name, args, result in (
            ('GlobalSize', [wintypes.HANDLE], ctypes.c_size_t),
            ('GlobalLock', [wintypes.HANDLE], ctypes.c_void_p),
            ('GlobalUnlock', [wintypes.HANDLE], wintypes.BOOL),
            ('GlobalAlloc', [wintypes.UINT, ctypes.c_size_t], wintypes.HANDLE),
            ('GlobalFree', [wintypes.HANDLE], wintypes.HANDLE),
        ):
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = args, result
        self._open()
        try:
            format_id = 0
            while True:
                format_id = self.user.EnumClipboardFormats(format_id)
                if not format_id:
                    break
                handle = self.user.GetClipboardData(format_id)
                if format_id == 2:  # CF_BITMAP is a GDI handle, not HGLOBAL.
                    self.bitmap = self.user.CopyImage(handle, 0, 0, 0, 0x2000)
                    continue
                if format_id not in (1, 7, 8, 13, 15, 16, 17) and format_id < 0xc000:
                    continue
                size = self.kernel.GlobalSize(handle)
                pointer = self.kernel.GlobalLock(handle) if size else None
                if pointer:
                    try:
                        self.formats.append((format_id, ctypes.string_at(pointer, size)))
                    finally:
                        self.kernel.GlobalUnlock(handle)
        finally:
            self.user.CloseClipboard()

    def _open(self):
        for _ in range(20):
            if self.user.OpenClipboard(self.root.winfo_id()):
                return
            time.sleep(.025)
        raise OSError('Clipboard is busy; do not run native clipboard tests now.')

    def restore(self):
        if os.name != 'nt':
            self.root.clipboard_clear()
            if self.text is not None:
                self.root.clipboard_append(self.text)
            return
        self._open()
        try:
            self.user.EmptyClipboard()
            for format_id, payload in self.formats:
                handle = self.kernel.GlobalAlloc(0x42, len(payload))
                if not handle:
                    raise MemoryError('Could not restore clipboard data')
                pointer = self.kernel.GlobalLock(handle)
                if not pointer:
                    self.kernel.GlobalFree(handle)
                    raise OSError('Could not lock clipboard data')
                ctypes.memmove(pointer, payload, len(payload))
                self.kernel.GlobalUnlock(handle)
                if not self.user.SetClipboardData(format_id, handle):
                    self.kernel.GlobalFree(handle)
                    raise OSError('Could not restore clipboard format')
            if self.bitmap:
                if not self.user.SetClipboardData(2, self.bitmap):
                    raise OSError('Could not restore clipboard image')
                self.bitmap = None
        finally:
            self.user.CloseClipboard()

    def unicode_text(self):
        """Read CF_UNICODETEXT as a different Windows application would."""
        if os.name != 'nt':
            return self.root.clipboard_get()
        self._open()
        try:
            handle = self.user.GetClipboardData(13)
            pointer = self.kernel.GlobalLock(handle)
            if not pointer:
                raise OSError('No Unicode text in the native clipboard')
            try:
                return ctypes.wstring_at(pointer)
            finally:
                self.kernel.GlobalUnlock(handle)
        finally:
            self.user.CloseClipboard()
