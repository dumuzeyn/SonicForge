"""Modern Windows folder picker. Run it on its own STA worker thread."""

import ctypes
import uuid
from pathlib import Path


class _GUID(ctypes.Structure):
    _fields_ = [("data1", ctypes.c_uint32), ("data2", ctypes.c_uint16),
                ("data3", ctypes.c_uint16), ("data4", ctypes.c_ubyte * 8)]

    @classmethod
    def from_text(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


class WindowsFolderDialog:
    def __init__(self):
        self.dialog = ctypes.c_void_p()
        self.initialized = False
        self.ole32 = ctypes.WinDLL("ole32")
        self.shell32 = ctypes.WinDLL("shell32")
        self.ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.ole32.CoInitializeEx.restype = ctypes.c_long
        self.ole32.CoCreateInstance.argtypes = [
            ctypes.POINTER(_GUID), ctypes.c_void_p, ctypes.c_uint32,
            ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p),
        ]
        self.ole32.CoCreateInstance.restype = ctypes.c_long
        self.ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        self.shell32.SHCreateItemFromParsingName.argtypes = [
            ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(_GUID),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self.shell32.SHCreateItemFromParsingName.restype = ctypes.c_long

    @staticmethod
    def _check(result):
        if result < 0:
            raise OSError(f"Windows folder picker: 0x{result & 0xFFFFFFFF:08X}")

    @staticmethod
    def _call(pointer, slot, types=(), arguments=()):
        vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        method = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(vtable[slot])
        return method(pointer, *arguments)

    def __enter__(self):
        self._check(self.ole32.CoInitializeEx(None, 0x2 | 0x4))
        self.initialized = True
        try:
            clsid = _GUID.from_text("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")
            iid = _GUID.from_text("D57C7288-D4AD-4768-BE02-9D969532D960")
            self._check(self.ole32.CoCreateInstance(
                ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(self.dialog),
            ))
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def configure(self, title, initial_directory):
        # IFileDialog slots: GetOptions=10, SetOptions=9, SetTitle=17.
        options = ctypes.c_uint32()
        self._check(self._call(self.dialog, 10, (ctypes.POINTER(ctypes.c_uint32),), (ctypes.byref(options),)))
        # PICKFOLDERS | FORCEFILESYSTEM | NOCHANGEDIR | DONTADDTORECENT.
        self._check(self._call(self.dialog, 9, (ctypes.c_uint32,), (options.value | 0x20 | 0x40 | 0x8 | 0x02000000,)))
        self._check(self._call(self.dialog, 17, (ctypes.c_wchar_p,), (title,)))
        folder = ctypes.c_void_p()
        iid = _GUID.from_text("43826D1E-E718-42EE-BC55-A1E261C37BFE")
        result = self.shell32.SHCreateItemFromParsingName(
            str(Path(initial_directory)), None, ctypes.byref(iid), ctypes.byref(folder),
        )
        if result >= 0 and folder:
            try:
                self._check(self._call(self.dialog, 11, (ctypes.c_void_p,), (folder,)))
            finally:
                self._call(folder, 2)

    def show(self, owner):
        user32 = ctypes.WinDLL("user32")
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        user32.GetAncestor.restype = ctypes.c_void_p
        owner = user32.GetAncestor(owner, 2) or owner
        result = self._call(self.dialog, 3, (ctypes.c_void_p,), (owner,))
        if result & 0xFFFFFFFF == 0x800704C7:  # User cancelled.
            return ""
        self._check(result)
        selected = ctypes.c_void_p()
        self._check(self._call(self.dialog, 20, (ctypes.POINTER(ctypes.c_void_p),), (ctypes.byref(selected),)))
        name = ctypes.c_void_p()
        try:
            self._check(self._call(selected, 5, (ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)), (0x80058000, ctypes.byref(name))))
            return ctypes.wstring_at(name)
        finally:
            if name:
                self.ole32.CoTaskMemFree(name)
            self._call(selected, 2)

    def __exit__(self, *_):
        if self.dialog:
            self._call(self.dialog, 2)
            self.dialog = ctypes.c_void_p()
        if self.initialized:
            self.ole32.CoUninitialize()
            self.initialized = False


def choose_windows_folder(owner, title, initial_directory):
    with WindowsFolderDialog() as dialog:
        dialog.configure(title, initial_directory)
        return dialog.show(owner)
