import ast
import ctypes
from ctypes import wintypes
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from music_polisher_gui import SonicForgeApp
from ui.theme import COLORS
from ui.windowing import _window_handle


def native_icon_pixels(icon):
    class IconInfo(ctypes.Structure):
        _fields_ = [('fIcon', wintypes.BOOL), ('xHotspot', wintypes.DWORD),
                    ('yHotspot', wintypes.DWORD), ('hbmMask', wintypes.HBITMAP),
                    ('hbmColor', wintypes.HBITMAP)]

    class Bitmap(ctypes.Structure):
        _fields_ = [('bmType', wintypes.LONG), ('bmWidth', wintypes.LONG),
                    ('bmHeight', wintypes.LONG), ('bmWidthBytes', wintypes.LONG),
                    ('bmPlanes', wintypes.WORD), ('bmBitsPixel', wintypes.WORD),
                    ('bmBits', ctypes.c_void_p)]

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    user32.GetIconInfo.argtypes = (wintypes.HICON, ctypes.POINTER(IconInfo))
    gdi32.GetObjectW.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p)
    gdi32.GetBitmapBits.argtypes = (wintypes.HBITMAP, wintypes.LONG, ctypes.c_void_p)
    gdi32.DeleteObject.argtypes = (wintypes.HANDLE,)
    info, bitmap = IconInfo(), Bitmap()
    if not user32.GetIconInfo(icon, ctypes.byref(info)):
        raise ctypes.WinError()
    try:
        gdi32.GetObjectW(info.hbmColor, ctypes.sizeof(bitmap), ctypes.byref(bitmap))
        buffer = ctypes.create_string_buffer(bitmap.bmWidthBytes * bitmap.bmHeight)
        gdi32.GetBitmapBits(info.hbmColor, len(buffer), buffer)
        return bitmap.bmWidth, bitmap.bmHeight, buffer.raw
    finally:
        gdi32.DeleteObject(info.hbmColor)
        gdi32.DeleteObject(info.hbmMask)


class NavigationRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = SonicForgeApp()
        cls.app.update()

    @classmethod
    def tearDownClass(cls):
        cls.app._close()

    def test_strip_has_no_colored_top_padding_or_colored_empty_tail(self):
        self.app.update()
        view = self.app.view
        view.show_tab('editor')
        self.app.update_idletasks()
        self.assertEqual(view.tab_bar.winfo_rooty(), view.winfo_rooty())
        self.assertEqual(view.tab_buttons['editor'].winfo_rooty(), view.tab_bar.winfo_rooty())
        self.assertEqual(ttk.Style(self.app).lookup('TabBar.TFrame', 'background'), COLORS['bg'])
        for button in view.tab_buttons.values():
            self.assertEqual(int(button.grid_info()['pady']), 0)

    def test_switch_does_not_change_any_page_geometry_or_redraw_the_editor(self):
        view = self.app.view
        self.app.update()
        widgets = [*view.tab_pages.values(), view.editor_context, view.batch_context,
                   view.editor_header, view.paths_frame, view.editor.canvas]
        bounds = {widget: widget.winfo_geometry() for widget in widgets}
        project = view.editor.project
        with patch.object(view.editor, 'draw', wraps=view.editor.draw) as draw, \
                patch.object(self.app, 'update_idletasks') as idle:
            for name in ('audio', 'editor', 'metadata', 'editor', 'settings', 'editor') * 5:
                view.show_tab(name)
                self.app.update()
                self.assertEqual(bounds, {widget: widget.winfo_geometry() for widget in widgets})
                self.assertIs(view.editor.project, project)
                self.assertIsNone(view.editor._draw_after)
                self.assertEqual(view.active_tab, name)
            draw.assert_not_called()
            idle.assert_not_called()

    def test_selected_tab_is_a_noop_and_children_are_not_recreated(self):
        view = self.app.view
        def children(widget):
            return tuple((child, children(child)) for child in sorted(widget.winfo_children(), key=str))
        view.show_tab('editor')
        before = children(view)
        with patch.object(view.tab_pages['editor'], 'tkraise') as raise_page:
            view.show_tab('editor')
            raise_page.assert_not_called()
        for name in ('audio', 'editor', 'metadata', 'editor', 'settings', 'editor'):
            view.show_tab(name)
        self.assertEqual(before, children(view))

    def test_main_window_and_dialog_have_explicit_current_icons(self):
        self.app.show_advanced_audio()
        try:
            self.app.update()
            user32 = ctypes.windll.user32
            user32.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
            user32.SendMessageW.restype = ctypes.c_ssize_t
            user32.LoadImageW.argtypes = (wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                         ctypes.c_int, ctypes.c_int, wintypes.UINT)
            user32.LoadImageW.restype = wintypes.HANDLE
            user32.DestroyIcon.argtypes = (wintypes.HICON,)
            for window in (self.app, self.app.advanced_dialog):
                for size_kind in (0, 1):  # WM_GETICON / small and large shell icons
                    icon = user32.SendMessageW(_window_handle(window), 0x007F, size_kind, 0)
                    self.assertTrue(icon)
                    width, height, pixels = native_icon_pixels(icon)
                    expected = user32.LoadImageW(None, str(self.app.window_icon_path), 1, width, height, 0x0010)
                    self.assertTrue(expected)
                    try:
                        self.assertEqual((width, height, pixels), native_icon_pixels(expected))
                    finally:
                        user32.DestroyIcon(expected)
        finally:
            self.app.advanced_dialog.close()

    def test_sound_selection_is_not_confused_with_keyboard_focus(self):
        self.app.show_advanced_audio()
        dialog = self.app.advanced_dialog
        try:
            notebook = dialog.notebook
            notebook.select(dialog.effects_tab)
            notebook.focus_set()
            self.app.update_idletasks()
            self.assertEqual(notebook.select(), str(dialog.effects_tab))
            style = ttk.Style(self.app)
            for states in (('selected',), ('selected', 'focus'), ('selected', 'active')):
                self.assertEqual(style.lookup('TNotebook.Tab', 'background', states), COLORS['accent'])
                self.assertEqual(style.lookup('TNotebook.Tab', 'foreground', states), COLORS['white'])
            self.assertEqual(style.lookup('TNotebook.Tab', 'background', ('focus',)), COLORS['button'])
            self.assertNotIn('Notebook.focus', repr(style.layout('TNotebook.Tab')))
            self.assertEqual(tuple(style.lookup('TNotebook.Tab', 'expand', ('selected',))), (0, 0, 0, 0))
            for states in ((), ('selected',)):
                self.assertEqual(tuple(int(str(value)) for value in style.lookup('TNotebook.Tab', 'padding', states)), (16, 9))
        finally:
            dialog.close()


class StartupPackagingTests(unittest.TestCase):
    def test_splash_uses_the_same_brand_artwork_as_the_application(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / 'packaging/SonicForge.spec').read_text(encoding='utf-8'))
        analysis = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == 'a' for target in node.targets))
        hooks = next(keyword.value for keyword in analysis.keywords if keyword.arg == 'runtime_hooks')
        self.assertIn('scripts/splash_runtime.py', ast.unparse(hooks))
        self.assertNotIn('OptionalSplash', ast.unparse(tree))


if __name__ == '__main__':
    unittest.main()
