import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch
from PIL import ImageTk

from music_polisher_gui import SonicForgeApp
from ui.theme import COLORS, FONTS, SPACING, SIZES
from ui.widgets import RibbonTab, RoundedButton, RoundedMenuButton, ThemedMenu


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def button_fill(button):
    raster = ImageTk.getimage(button._raster)
    pixel = raster.getpixel((raster.width // 2, raster.height // 2))
    return '#%02X%02X%02X' % pixel[:3]


class UnifiedDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = SonicForgeApp()

    @classmethod
    def tearDownClass(cls):
        cls.app._close()

    def test_all_app_actions_and_dropdowns_use_shared_components(self):
        self.app.show_advanced_audio()
        self.app.advanced_dialog.close()
        self.app.show_additional_metadata()
        self.app.metadata_dialog.close()
        controls = list(descendants(self.app))
        old = [w for w in controls if isinstance(w, (ttk.Button, ttk.Menubutton))]
        self.assertEqual(old, [])
        self.assertGreater(len([w for w in controls if isinstance(w, RoundedButton)]), 35)
        self.assertIsInstance(self.app.view.metadata_actions, RoundedMenuButton)
        menus = [w for w in controls if isinstance(w, tk.Menu)]
        self.assertGreaterEqual(len(menus), 3)
        self.assertTrue(all(isinstance(w, ThemedMenu) for w in menus))

    def test_compact_startup_keeps_editor_controls_inside_window(self):
        width, height = self.app.startup_geometry['client_size']
        self.assertLessEqual(width, 1100)
        self.assertLessEqual(height, 850)
        self.app.view.show_tab('editor')
        self.app.update()
        editor = self.app.view.editor
        for button in (editor.cursor_selection_button, editor.trim_button, editor.stop_button):
            self.assertGreaterEqual(button.winfo_rootx(), self.app.winfo_rootx())
            self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), self.app.winfo_rootx() + self.app.winfo_width())
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), self.app.winfo_rooty() + self.app.winfo_height())
        self.assertGreaterEqual(editor.canvas.winfo_height(), 100)

    def test_shared_button_font_and_surface_across_pages(self):
        controls = [w for w in descendants(self.app) if isinstance(w, RoundedButton) and not isinstance(w, RibbonTab)]
        for button in controls:
            self.assertEqual(button.font.actual('family'), 'Segoe UI Semibold')
            self.assertIn(button.cget('background'), (COLORS['bg'], COLORS['surface']))
            self.assertEqual(button.cget('height'), str(SIZES['control_height']))

    def test_navigation_selection_and_position_survive_language_switch(self):
        view = self.app.view
        view.show_tab('editor')
        self.app.update()
        top = view.tab_buttons['editor'].winfo_rooty()
        for language in ('ru', 'en'):
            if self.app.language != language:
                self.app.toggle_language()
            for name, button in view.tab_buttons.items():
                view.show_tab(name)
                self.app.update_idletasks()
                self.assertEqual(button.cget('style'), 'Selected.Tab.TButton')
                self.assertEqual(button.winfo_rooty(), top)
                self.assertIsInstance(button, RibbonTab)
                self.assertEqual(button_fill(button), COLORS['surface'])
                self.assertEqual(button.itemcget(button._text, 'fill'), COLORS['button_text'])
        if self.app.language != 'ru':
            self.app.toggle_language()

    def test_dropdown_invokes_existing_menu_and_disabled_does_not_open(self):
        button = self.app.view.metadata_actions
        with patch.object(button.menu, 'tk_popup') as popup, patch.object(button.menu, 'grab_release') as release:
            button.invoke()
            popup.assert_called_once()
            release.assert_called_once()
            button.configure(state='disabled')
            button.invoke()
            self.assertEqual(popup.call_count, 1)
        button.configure(state='normal')
        self.assertIn('▾', button._display_text())

    def test_editor_reclaims_header_space_without_resizing_the_window(self):
        view = self.app.view
        original_geometry = self.app.geometry()
        try:
            for size in (None, (self.app.winfo_width() + 120, self.app.winfo_height() + 80)):
                if size:
                    self.app.geometry(f'{size[0]}x{size[1]}')
                self.app.update()
                for language in ('ru', 'en'):
                    if self.app.language != language:
                        self.app.toggle_language()
                    view.show_tab('editor')
                    self.app.update_idletasks()
                    editor_page = view.tab_pages['editor']
                    expected = (editor_page.winfo_rootx(), editor_page.winfo_rooty(),
                                editor_page.winfo_width(), editor_page.winfo_height())
                    window_size = (self.app.winfo_width(), self.app.winfo_height())
                    other_page_bounds = None
                    for name, page in view.tab_pages.items():
                        view.show_tab(name)
                        self.app.update_idletasks()
                        actual = (page.winfo_rootx(), page.winfo_rooty(),
                                  page.winfo_width(), page.winfo_height())
                        self.assertEqual(actual[0], expected[0])
                        self.assertEqual(actual[2], expected[2])
                        if name == 'editor':
                            self.assertEqual(actual, expected)
                        elif name in ('help', 'settings'):
                            self.assertLess(actual[1], expected[1])
                            self.assertGreater(actual[3], expected[3])
                            self.assertEqual(actual[1] + actual[3], expected[1] + expected[3])
                        else:
                            self.assertGreater(actual[1], expected[1])
                            self.assertLess(actual[3], expected[3])
                            self.assertEqual(actual[1] + actual[3], expected[1] + expected[3])
                            if other_page_bounds is None:
                                other_page_bounds = actual
                            self.assertEqual(actual, other_page_bounds)
                        self.assertEqual((self.app.winfo_width(), self.app.winfo_height()), window_size)
                        self.assertIs(view._current_layer, view.page_layers[name])
                        # Covered layers remain mapped with stable geometry.
                        self.assertTrue(view.editor_header.winfo_ismapped())
                        self.assertTrue(view.paths_frame.winfo_ismapped())
        finally:
            self.app.geometry(original_geometry)
            if self.app.language != 'ru':
                self.app.toggle_language()
            view.show_tab('editor')

    def test_state_and_primary_danger_roles_are_consistent(self):
        button = self.app.view.run_button
        button.configure(state='normal')
        self.assertEqual(button_fill(button), COLORS['accent'])
        button.configure(state='disabled')
        self.assertEqual(button_fill(button), COLORS['button_disabled'])
        self.assertEqual(button.state(), ('disabled',))
        button.state(['!disabled'])
        self.assertEqual(button.state(), ())
        stop = self.app.view.stop_button
        stop.configure(state='normal')
        self.assertEqual(button_fill(stop), COLORS['danger_surface'])
        stop.configure(state='disabled')

    def test_context_has_balanced_margins_and_aligns_with_page_content(self):
        view = self.app.view
        self.app.update()
        for language in ('ru', 'en'):
            if self.app.language != language:
                self.app.toggle_language()
            for name, context in (('editor', view.editor_header), ('metadata', view.paths_frame)):
                view.show_tab(name)
                self.app.update_idletasks()
                holder = view.context_holder
                inset = SPACING['md']
                self.assertEqual(context.winfo_x(), inset)
                self.assertEqual(context.winfo_y(), inset)
                self.assertEqual(holder.winfo_width() - context.winfo_x() - context.winfo_width(), inset)
                self.assertEqual(holder.winfo_height() - context.winfo_y() - context.winfo_height(), inset)
                content = view.editor if name == 'editor' else view.tab_pages[name].winfo_children()[0]
                self.assertEqual(context.winfo_rootx(), content.winfo_rootx())
        if self.app.language != 'ru':
            self.app.toggle_language()

    def test_processing_stage_explanations_have_real_keys(self):
        controls = [w for w in descendants(self.app.view.tab_pages['processing']) if hasattr(w, 'help_key')]
        for widget in controls:
            self.assertNotEqual(self.app.t(widget.help_key), widget.help_key)
