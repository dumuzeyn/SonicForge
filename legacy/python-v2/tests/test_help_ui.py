import tkinter as tk
import unittest

from music_polisher_gui import SonicForgeApp
from ui.widgets import ToolTip
from ui.windowing import _outer_bounds, _primary_work_area


class HelpUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = SonicForgeApp()
        cls.app.update()

    @classmethod
    def tearDownClass(cls):
        cls.app._close()

    def assertCentered(self, window):
        self.app.update()
        left, top, right, bottom = _primary_work_area(self.app)
        x1, y1, x2, y2 = _outer_bounds(window)
        self.assertLessEqual(abs((x1 + x2 - left - right) / 2), 2)
        self.assertLessEqual(abs((y1 + y2 - top - bottom) / 2), 2)

    def test_tips_open_only_on_right_click_toggle_and_do_not_invoke_control(self):
        from ui.widgets import RoundedButton
        calls = []
        control = RoundedButton(self.app, text='Tip target', command=lambda: calls.append(True))
        control.place(x=20, y=20)
        tooltip = ToolTip(control, lambda: 'Explanation', delay=1)
        try:
            self.app.update()
            control.event_generate('<Enter>')
            control.event_generate('<FocusIn>')
            self.app.update()
            self.assertIsNone(tooltip.window)
            self.assertIsNone(tooltip.after_id)
            control.event_generate('<ButtonPress-3>', x=5, y=5)
            self.app.update()
            self.assertIsNotNone(tooltip.window)
            self.assertEqual(calls, [])
            control.event_generate('<ButtonPress-3>', x=5, y=5)
            self.app.update()
            self.assertIsNone(tooltip.window)
            self.assertEqual(calls, [])
        finally:
            tooltip._hide()
            control.destroy()

    def test_help_and_settings_use_the_same_icon_asset_as_main_window(self):
        from unittest.mock import patch
        with patch.object(self.app, 'set_window_icon', wraps=self.app.set_window_icon) as icon:
            self.app.view.show_help()
            help_window = self.app.view._help_window
            help_window.close()
            self.app.show_advanced_audio()
            self.app.advanced_dialog.close()
            self.app.show_additional_metadata()
            self.app.metadata_dialog.close()
        self.assertIn(help_window, [call.args[0] for call in icon.call_args_list])
        self.assertIn(self.app.advanced_dialog, [call.args[0] for call in icon.call_args_list])
        self.assertIn(self.app.metadata_dialog, [call.args[0] for call in icon.call_args_list])

    def test_help_is_centered_has_cards_and_navigation_does_not_change_app(self):
        self.app.view.show_tab('editor')
        self.app.view.show_help('audio')
        window = self.app.view._help_window
        try:
            self.assertCentered(window)
            self.assertGreater(len(window.cards), 5)
            window.buttons['lyrics'].invoke()
            self.assertEqual(window.page, 'lyrics')
            self.assertEqual(self.app.view.active_tab, 'editor')
            self.assertGreater(len(window.labels), 3)
            self.assertCentered(window)
        finally:
            window.close()

    def test_parameter_cards_use_meaningful_icons_instead_of_bullets(self):
        self.app.view.show_help('audio')
        window = self.app.view._help_window
        try:
            texts = [
                child.cget('text')
                for card in window.cards
                for child in card.winfo_children()
                if isinstance(child, tk.Label)
            ]
            self.assertNotIn('•', texts)
            self.assertTrue(any(icon in texts for icon in ('♪', '⚙', '▶', '⌕')))
        finally:
            window.close()

    def test_advanced_and_metadata_center_on_first_open_and_reopen(self):
        for show, attribute in ((self.app.show_advanced_audio, 'advanced_dialog'),
                                (self.app.show_additional_metadata, 'metadata_dialog')):
            show()
            window = getattr(self.app, attribute)
            self.assertCentered(window)
            window.geometry('+0+0')
            window.close()
            show()
            self.assertIs(window, getattr(self.app, attribute))
            self.assertCentered(window)
            window.close()

    def test_help_restores_advanced_dialog_modal_grab(self):
        self.app.show_advanced_audio()
        self.app.view.show_help('audio')
        window = self.app.view._help_window
        self.assertIs(self.app.grab_current(), window)
        window.close()
        self.assertIs(self.app.grab_current(), self.app.advanced_dialog)
        self.app.advanced_dialog.close()

    def test_tooltip_card_has_title_description_and_keyboard_hint(self):
        tip = ToolTip(self.app.view.source_entry, lambda: 'Не меняет оригинальный файл.', title_provider=lambda: 'Источник')
        try:
            tip._show()
            self.app.update_idletasks()
            labels = tip.window.winfo_children()[0].winfo_children()
            captions = [w.cget('text') for w in labels if isinstance(w, tk.Label)]
            self.assertIn('Источник', captions)
            self.assertIn('Не меняет оригинальный файл.', captions)
            self.assertTrue(any('F1' in text for text in captions))
        finally:
            tip._hide()
