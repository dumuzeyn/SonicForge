import tkinter as tk
import os
import shutil
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from tkinter import ttk
from unittest.mock import patch

from PIL import Image

import music_polisher_gui
from lyrics_engine import LyricsResult, LyricsService, TranscriptSegment
from lyrics_engine.providers import MockLyricsProvider
from ui.widgets import ModernScale, RoundedButton, SquareCheckbutton


class GuiAcceptanceTests(unittest.TestCase):
    def test_audio_processing_requires_explicit_selection(self):
        self.assertFalse(self.app.process_audio_var.get())
        self.app.process_audio_var.set(False)
        try:
            with patch.object(self.app, '_run_process') as run:
                self.app.run_selected_steps()
            self.assertNotIn('audio', run.call_args.args[0])
            self.app.process_audio_var.set(True)
            with patch.object(self.app, '_run_process') as run:
                self.app.run_selected_steps()
            self.assertIn('audio', run.call_args.args[0])
        finally:
            self.app.process_audio_var.set(False)

    def test_lyrics_failure_displays_full_filename_and_reason(self):
        filename = 'Полное название песни ' * 7 + '.mp3'
        error = 'RecognitionMemoryError: available RAM: 128 MB'
        self.app.view.update_lyrics_execution('failed', dict(index=2, total=165, file=filename, error=error))
        status = self.app.view.lyrics_execution_status.get()
        self.assertIn(filename, status)
        self.assertIn(error, status)
        self.app.toggle_language()
        self.assertIn(filename, self.app.view.lyrics_execution_status.get())
        self.assertIn(error, self.app.view.lyrics_execution_status.get())
        self.app.view.reset_lyrics_execution(True)

    def _send_control_key(self, widget, letter):
        if os.name == "nt":
            widget.event_generate("<Control-KeyPress>", keycode=ord(letter.upper()), state=4)
        else:
            widget.event_generate(f"<Control-KeyPress-{letter}>")
        self.app.update()

    def test_path_entries_select_all_and_copy_with_real_key_events(self):
        for name in ("source", "output"):
            variable = getattr(self.app, f"{name}_var")
            entry = getattr(self.app.view, f"{name}_entry")
            original = variable.get()
            try:
                path = "C:/TestMusic/Проверка test.mp3"
                variable.set(path)
                entry.selection_clear()
                entry.focus_force()
                self.app.update()
                self._send_control_key(entry, "a")
                self.assertTrue(entry.selection_present(), name)
                self.assertEqual(entry.index("sel.first"), 0)
                self.assertEqual(entry.index("sel.last"), len(path))
                self._send_control_key(entry, "c")
                self.assertEqual(self.app.clipboard_get(), path)
                self.assertEqual(variable.get(), path)
            finally:
                variable.set(original)

    def test_foreign_transcription_is_displayed_as_sound_not_english_language(self):
        self.app._apply_lyrics_result(LyricsResult(
            text="gamarjoba megobaro", language="ka", language_confidence=.423,
            transcription_alphabet="en", quality="medium",
        ))
        self.assertEqual(self.app.view.get_lyrics_text(), "gamarjoba megobaro")
        self.assertIn("английскими буквами", self.app.lyrics_status_var.get())
        self.assertIn("не перевод", self.app.lyrics_status_var.get())
        self.app.toggle_language()
        self.assertIn("English letters", self.app.lyrics_status_var.get())

    def test_uncertain_language_has_a_visible_message(self):
        self.app._apply_lyrics_result(LyricsResult(text="", review_reason="language", quality="low"))
        self.assertIn("не определён", self.app.lyrics_status_var.get())
        self.app.toggle_language()
        self.assertIn("could not be identified", self.app.lyrics_status_var.get())

    def test_lyrics_verification_has_a_visible_localized_status(self):
        self.app._lyrics_results.put(("progress", "verifying"))
        self.app._lyrics_results.put(("done", None))
        self.app._poll_lyrics()
        self.assertEqual(self.app.lyrics_status_var.get(), self.app.t("lyrics_status_verifying"))
        self.app.toggle_language()
        self.assertEqual(self.app.lyrics_status_var.get(), "Rechecking uncertain words...")

    def test_lyrics_select_all_works_with_latin_and_russian_key_symbols(self):
        editor = self.app.view.lyrics_editor
        text = "В комнате темно\nВетер за окном"
        self.app.view.set_lyrics_text(text)
        for keysym in ("a", "A", "Cyrillic_ef", "Cyrillic_EF"):
            with self.subTest(keysym=keysym):
                editor.tag_remove(tk.SEL, "1.0", tk.END)
                result = self.app._lyrics_editor_shortcut(SimpleNamespace(
                    widget=editor, keysym=keysym, keycode=65, state=4,
                ))
                self.assertEqual(result, "break")
                self.assertEqual(editor.get(tk.SEL_FIRST, tk.SEL_LAST), text)

    def test_lyrics_control_a_binding_runs_before_text_class(self):
        editor = self.app.view.lyrics_editor
        self.app.view.show_tab("lyrics")
        self.app.view.set_lyrics_text("Первая строка\nВторая строка")
        # Finish native page mapping before requesting keyboard focus. A focus
        # event from a previously closed dialog must not overtake this request.
        self.app.update()
        editor.focus_force()
        self.app.update()
        if os.name == "nt":
            # Tk cannot synthesize Latin keysyms in a Russian Windows layout.
            editor.event_generate("<Control-KeyPress>", keycode=65, state=4)
        else:
            editor.event_generate("<Control-KeyPress-a>")
        self.app.update()
        self.assertEqual(editor.get(tk.SEL_FIRST, tk.SEL_LAST), self.app.view.get_lyrics_text())
        self.assertIn(self.app._editing_bindtag, editor.bindtags())
        self.assertLess(editor.bindtags().index(self.app._editing_bindtag),
                        editor.bindtags().index(editor.winfo_class()))

    def test_entry_shortcuts_run_before_class_and_support_russian_layout(self):
        entry = self.app.view.source_entry
        original = self.app.source_var.get()
        text = "C:/TestMusic/Пример.mp3"
        try:
            self.app.source_var.set(text)
            self.assertLess(entry.bindtags().index(self.app._editing_bindtag),
                            entry.bindtags().index(entry.winfo_class()))
            for keysym, keycode in (("a", 65), ("Cyrillic_ef", 65)):
                entry.selection_clear()
                self.assertEqual(self.app._editor_shortcut(SimpleNamespace(
                    widget=entry, keysym=keysym, keycode=keycode, state=4,
                )), "break")
                self.assertEqual(entry.index("sel.last") - entry.index("sel.first"), len(text))
                self.assertEqual(self.app._editor_shortcut(SimpleNamespace(
                    widget=entry, keysym="Cyrillic_es", keycode=67, state=4,
                )), "break")
                self.assertEqual(self.app.clipboard_get(), text)
        finally:
            self.app.source_var.set(original)

    def test_new_dialog_entries_get_shortcuts_and_altgr_is_not_intercepted(self):
        dialog = tk.Toplevel(self.app)
        try:
            entry = ttk.Entry(dialog)
            entry.pack()
            self.app.update()
            self.assertIn(self.app._editing_bindtag, entry.bindtags())
            self.assertIsNone(self.app._editor_shortcut(SimpleNamespace(
                widget=entry, keysym="a", keycode=65, state=4 | 0x20000,
            )))
        finally:
            dialog.destroy()

    def test_processing_has_separate_lyrics_section_and_real_status(self):
        view = self.app.view
        view.reset_lyrics_execution(True)
        try:
            self.assertEqual(view.lyrics_execution_frame.cget("text"), "Обработка текста песни")
            self.app.log_queue.put(("__LYRICS_BATCH_PROGRESS__", "loading_model",
                                    dict(file="test.mp3", index=1, total=2)))
            self.app._drain_log_queue()
            self.assertIn("загрузка модели", view.lyrics_execution_status.get())
            self.assertIn("1/2", view.lyrics_execution_status.get())
            view.update_lyrics_execution("transcribing", dict(file="test.mp3", index=1, total=2,
                                                               audio_end=30, duration=120))
            self.assertEqual(view.lyrics_execution_progress.cget("value"), 25)
            view.update_lyrics_execution("completed", dict(total=2, saved=1, preserved=0, uncertain=1, failed=0))
            self.assertEqual(view.lyrics_execution_progress.cget("value"), 200)
            self.assertIn("требуют проверки: 1", view.lyrics_execution_status.get())
            self.app.toggle_language()
            self.assertEqual(view.lyrics_execution_frame.cget("text"), "Lyrics processing")
            self.assertIn("need review: 1", view.lyrics_execution_status.get())
            view.finish_lyrics_execution("run_finished")
            self.assertEqual(view.lyrics_execution_stage, "completed")
        finally:
            view.reset_lyrics_execution(True)

    def test_lyrics_execution_reports_stop_and_unselected_stage(self):
        view = self.app.view
        view.reset_lyrics_execution(False)
        view.finish_lyrics_execution("run_stopped")
        self.assertEqual(view.lyrics_execution_status.get(), "Этап не выбран")
        view.reset_lyrics_execution(True)
        view.finish_lyrics_execution("run_stopped")
        self.assertIn("остановлена", view.lyrics_execution_status.get())
        view.reset_lyrics_execution(True)

    @classmethod
    def setUpClass(cls):
        cls.preferences_directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.preferences_directory.cleanup)
        cls.preference_path = Path(cls.preferences_directory.name) / 'custom_cover.json'
        cls.preferences_patch = patch('cover_preferences.preference_path', return_value=cls.preference_path)
        cls.preferences_patch.start()
        cls.addClassCleanup(cls.preferences_patch.stop)
        cls.app = music_polisher_gui.SonicForgeApp()
        # Process native Map/Configure events before checking mapped widgets.
        cls.app.update()
        from .clipboard_guard import ClipboardGuard
        cls.clipboard_guard = ClipboardGuard(cls.app)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.clipboard_guard.restore()
        finally:
            cls.app.destroy()

    def test_lyrics_copy_shortcut_menu_and_button_never_use_path_selection(self):
        editor = self.app.view.lyrics_editor
        original_text = self.app.view.get_lyrics_text()
        source = self.app.source_var.get()
        text = "Первая строка песни\nВторая строка песни"
        try:
            self.app.view.show_tab('lyrics')
            self.app.view.set_lyrics_text(text)
            self.app.source_var.set('C:/TestMusic/Проверка test.mp3')
            self.app.view.source_entry.selection_range(0, tk.END)
            for busy in (False, True):
                self.app.view.set_lyrics_busy(busy)
                editor.tag_remove(tk.SEL, '1.0', tk.END)
                editor.focus_force()
                self.app.update()
                self.app.clipboard_clear()
                self.app.clipboard_append('C:/TestMusic/Проверка test.mp3')
                self._send_control_key(editor, 'c')
                self.assertEqual(self.app.clipboard_get(), text)
                self.assertEqual(self.clipboard_guard.unicode_text().replace('\r\n', '\n'), text)
                editor.tag_add(tk.SEL, '2.0', '2.end')
                self._send_control_key(editor, 'c')
                self.assertEqual(self.app.clipboard_get(), 'Вторая строка песни')
                # Invoke the actual popup commands; opening must retain selection.
                with patch.object(self.app.view.lyrics_menu, 'tk_popup') as popup:
                    editor.event_generate('<Button-3>', x=15, y=15, rootx=200, rooty=200)
                    self.app.update()
                    popup.assert_called_once()
                self.app.view.lyrics_menu.invoke(0)
                self.assertEqual(self.app.clipboard_get(), 'Вторая строка песни')
                self.app.view.lyrics_menu.invoke(1)
                self.assertEqual(self.app.clipboard_get(), text)
                self.app.view.copy_lyrics_button.invoke()
                self.assertEqual(self.app.clipboard_get(), text)
                self.app.view.lyrics_menu.invoke(2)
                self.assertEqual(editor.get(tk.SEL_FIRST, tk.SEL_LAST), text)
            self.app.toggle_language()
            self.assertEqual(self.app.view.lyrics_menu.entrycget(1, 'label'), 'Copy lyrics')
            self.assertEqual(self.app.view.copy_lyrics_button.cget('text'), 'Copy lyrics')
        finally:
            self.app.view.set_lyrics_busy(False)
            self.app.view.set_lyrics_text(original_text)
            self.app.source_var.set(source)

    def setUp(self):
        if self.app.language != "ru":
            self.app.toggle_language()
        self.app.clear_log()
        self.app.write_log(self.app.t("log_ready") + "\n")
        self.app._set_lyrics_status("lyrics_status_empty")
        self.app.view.show_tab("metadata")
        self.app.update_idletasks()

    def test_window_is_compact_and_pages_do_not_force_resize(self):
        widths = []
        geometry = self.app.geometry()
        for name, page in self.app.view.tab_pages.items():
            self.app.view.show_tab(name)
            self.app.update_idletasks()
            widths.append(page.winfo_reqwidth())
            self.assertEqual(self.app.geometry(), geometry)
        self.assertLessEqual(max(widths), 900)
        width, height = map(int, geometry.split("+")[0].split("x"))
        self.assertLessEqual(width, 1100)
        self.assertLessEqual(height, 850)

    def test_log_is_read_only_but_copyable(self):
        self.app.clear_log()
        self.app.write_log("first line\nsecond line\n")
        self.assertEqual(self.app.view.log.cget("state"), tk.DISABLED)
        self.app.select_all_log()
        self.app.copy_log_selection()
        self.assertEqual(self.app.clipboard_get(), "first line\nsecond line\n")
        self.app.copy_log()
        self.assertEqual(self.app.clipboard_get(), "first line\nsecond line\n")

    def test_classic_sections_keep_natural_widths_and_share_one_strip(self):
        tab_bar = next(iter(self.app.view.tab_buttons.values())).master
        count = len(self.app.view.tab_buttons)
        weights = [tab_bar.grid_columnconfigure(i)["weight"] for i in range(count)]
        uniforms = [tab_bar.grid_columnconfigure(i)["uniform"] for i in range(count)]
        self.assertEqual(weights, [0] * count)
        self.assertFalse(any(uniforms))
        self.assertEqual(tab_bar.grid_columnconfigure(count)["weight"], 1)

    def test_settings_language_selector_translates_ui_without_losing_edits(self):
        view = self.app.view
        previous_title = self.app.title_var.get()
        previous_lyrics = view.get_lyrics_text()
        project = view.editor.project
        try:
            self.app.title_var.set('My unchanged title')
            view.set_lyrics_text('Сохранённая строка песни')
            view.show_tab('settings')
            self.app.update_idletasks()
            view.interface_language_var.set('English')
            view.interface_language_combo.event_generate('<<ComboboxSelected>>')
            self.app.update_idletasks()
            self.assertEqual(self.app.language, 'en')
            self.assertEqual(view.active_tab, 'settings')
            self.assertEqual(view.tab_buttons['settings'].cget('text'), 'Settings')
            self.assertEqual(view.tab_buttons['help'].cget('text'), 'Help')
            self.assertEqual(self.app.title_var.get(), 'My unchanged title')
            self.assertEqual(view.get_lyrics_text(), 'Сохранённая строка песни')
            self.assertIs(view.editor.project, project)
            view.interface_language_var.set('Русский')
            view.interface_language_combo.event_generate('<<ComboboxSelected>>')
            self.assertEqual(self.app.language, 'ru')
        finally:
            if self.app.language != 'ru':
                self.app.toggle_language()
            self.app.title_var.set(previous_title)
            view.set_lyrics_text(previous_lyrics)

    def test_help_section_is_inline_and_keeps_its_context_and_navigation(self):
        view = self.app.view
        view.show_tab('audio')
        windows = set(self.app.winfo_children())
        view.tab_buttons['help'].invoke()
        self.app.update_idletasks()
        self.assertEqual(view.active_tab, 'help')
        self.assertEqual(view.help_panel.page, 'audio')
        self.assertGreater(len(view.help_panel.cards), 3)
        self.assertEqual(set(self.app.winfo_children()), windows)
        view.help_panel.buttons['lyrics'].invoke()
        self.assertEqual(view.help_panel.page, 'lyrics')
        self.assertEqual(view.active_tab, 'help')

    def test_editor_is_first_and_not_a_processing_stage(self):
        self.assertEqual(next(iter(self.app.view.tab_buttons)), "editor")
        self.assertFalse(hasattr(self.app, "process_editor_var"))
        self.assertFalse(hasattr(self.app.view, "header_icon"))
        self.app.view.show_tab("editor")
        self.app.update_idletasks()
        top = self.app.view.tab_buttons["editor"].winfo_rooty()
        self.assertIs(self.app.view._current_layer, self.app.view.page_layers['editor'])
        self.app.view.show_tab("audio")
        self.app.update_idletasks()
        self.assertIs(self.app.view._current_layer, self.app.view.page_layers['audio'])
        self.assertTrue(self.app.view.paths_frame.winfo_ismapped())
        self.assertEqual(self.app.view.tab_buttons["editor"].winfo_rooty(), top)

    def test_advanced_values_are_not_reset_when_collecting_audio_options(self):
        variables = (self.app.bass_gain_var, self.app.integrated_lufs_var, self.app.stereo_width_var)
        before = [var.get() for var in variables]
        try:
            for variable, value in zip(variables, (7, -17, 1.4)):
                variable.set(value)
            values = self.app._audio_processing_values()
            self.assertEqual((values['bass_gain'], values['integrated_lufs'], values['stereo_width']), (7, -17, 1.4))
            self.app.update_idletasks()
            self.assertIn("-17.0 LUFS", self.app.view.audio_summary.get())
            self.assertIn("+7.00 dB", self.app.view.audio_summary.get())
        finally:
            for var, value in zip(variables, before):
                var.set(value)

    def test_audio_dialog_is_reused_after_close(self):
        self.app.show_advanced_audio()
        dialog = self.app.advanced_dialog
        dialog.close()
        self.assertTrue(dialog.winfo_exists())
        self.assertEqual(dialog.state(), "withdrawn")
        self.app.show_advanced_audio()
        self.assertIs(self.app.advanced_dialog, dialog)
        dialog.close()

    def test_editor_and_sound_help_have_explanations(self):
        for page in ("editor", "audio", "metadata", "cover", "lyrics", "processing"):
            self.app.view.show_help(page)
            window = self.app.view._help_window
            self.assertGreater(len(' '.join(label.cget('text') for label in window.labels)), 150)
            self.assertGreater(len(window.cards), 3)
            window.close()

    def test_slider_redraw_reuses_canvas_items(self):
        slider = next(w for w in _descendants(self.app.view.tab_pages["audio"]) if isinstance(w, ModernScale))
        items = slider.find_all()
        for _ in range(30):
            slider._redraw()
        self.assertEqual(items, slider.find_all())

    def test_audio_page_uses_stable_custom_sliders_and_neutral_defaults(self):
        self.app.view.show_tab("audio")
        self.app.update_idletasks()
        sliders = [widget for widget in _descendants(self.app.view.tab_pages["audio"]) if isinstance(widget, ModernScale)]
        self.assertEqual(len(sliders), 5)
        self.assertEqual(self.app.final_gain_var.get(), 1.0)
        self.assertFalse(self.app.highpass_enabled_var.get())
        self.assertFalse(self.app.lowpass_enabled_var.get())
        self.assertEqual(self.app.audio_option_key("sample_rate"), "source")
        self.assertEqual(self.app.audio_option_key("channels"), "source")

    def test_language_switch_updates_status_log_and_open_dialogs(self):
        self.assertTrue(self.app.lyrics_status_var.get().startswith("Текст ещё"))
        self.app.show_advanced_audio()
        self.app.toggle_language()
        self.app.update_idletasks()
        self.assertTrue(self.app.lyrics_status_var.get().startswith("No lyrics"))
        self.assertEqual(self.app.view.log.get("1.0", "end-1c"), "Ready.\n")
        self.assertEqual(self.app.advanced_dialog.title(), self.app.t("advanced_title"))
        self.app.advanced_dialog.destroy()
        self.app.advanced_dialog = None

        self.app.show_additional_metadata()
        self.app.toggle_language()
        self.app.update_idletasks()
        self.assertEqual(
            self.app.metadata_dialog.title(),
            self.app.t("additional_metadata_title"),
        )
        self.app.metadata_dialog.destroy()
        self.app.metadata_dialog = None

    def test_detected_language_and_quality_relocalize(self):
        self.app._apply_lyrics_result(
            LyricsResult(
                text="Test lyrics here",
                language="en",
                language_confidence=0.91,
                quality="high",
            )
        )
        self.assertIn("Английский", self.app.lyrics_status_var.get())
        self.assertIn("высокое", self.app.lyrics_status_var.get())
        self.app.toggle_language()
        self.assertIn("English", self.app.lyrics_status_var.get())
        self.assertIn("high", self.app.lyrics_status_var.get())

    def test_no_visible_primary_text_is_clipped_in_ru_or_en(self):
        failures = []
        for language in ("ru", "en"):
            if self.app.language != language:
                self.app.toggle_language()
            for page_name, page in self.app.view.tab_pages.items():
                self.app.view.show_tab(page_name)
                self.app.update_idletasks()
                for widget in _descendants(page):
                    if not widget.winfo_ismapped() or not isinstance(
                        widget,
                        (tk.Label, tk.Button, ttk.Label, ttk.Button, ttk.Menubutton, RoundedButton, SquareCheckbutton),
                    ):
                        continue
                    text = widget.cget("text") if "text" in widget.keys() else ""
                    if text and widget.winfo_width() + 2 < widget.winfo_reqwidth():
                        failures.append(
                            (language, page_name, text, widget.winfo_width(), widget.winfo_reqwidth())
                        )
        self.assertEqual(failures, [])

    def test_six_cover_styles_relocalize(self):
        self.assertEqual(len(self.app.cover_choice_values("style")), 6)
        self.assertNotIn("disabled", self.app.view.cover_style_combo.state())
        self.app.cover_style_var.set("Классический узор · современные цвета")
        self.assertEqual(self.app._process_kwargs()["cover_style"], "legacy_current_colors")
        self.app.toggle_language()
        self.assertEqual(self.app.cover_choice("style", self.app.cover_style_var.get()),
                         "legacy_current_colors")

    def test_cover_page_has_only_a_real_preview_action(self):
        self.app.view.show_tab("cover")
        self.app.update_idletasks()
        self.assertEqual(self.app.view.cover_preview_button.cget("text"), "Предпросмотр обложки")
        self.assertFalse(hasattr(self.app.view, "cover_variant_button"))
        self.assertFalse(hasattr(self.app.view, "cover_detail_combo"))
        self.assertFalse(hasattr(self.app.view, "cover_title_mode_combo"))
        self.assertFalse(hasattr(self.app.view, "description_generate_button"))

    def test_custom_style_apply_cancel_and_relocalization(self):
        from ui.dialogs import CustomCoverDialog
        initial = dict(self.app.custom_cover_settings)
        initial_style = self.app.cover_style_var.get()
        try:
            dialog = CustomCoverDialog(self.app)
            dialog.variables["detail"].set(77)
            dialog.close()
            self.assertEqual(self.app.custom_cover_settings, initial)
            dialog = CustomCoverDialog(self.app)
            dialog.pattern.set(self.app.t("custom_pattern_legacy"))
            dialog.colors[0] = "#123456"
            dialog.variables["softness"].set(35)
            dialog.apply()
            self.assertEqual(self.app.custom_cover_settings["pattern"], "legacy")
            self.assertEqual(self.app.custom_cover_settings["colors"][0], "#123456")
            self.assertEqual(self.app._process_kwargs()["custom_cover_settings"]["softness"], 35)
            self.assertEqual(self.app.cover_choice("style", self.app.cover_style_var.get()), "custom")
            self.app.toggle_language()
            self.assertEqual(self.app.cover_style_var.get(), "Custom style")
            dialog = CustomCoverDialog(self.app)
            self.assertEqual(dialog.title(), "Custom cover style")
            dialog.reset()
            self.assertEqual(dialog.variables["softness"].get(), 0)
            dialog.close()
            with patch("music2picture.make_cover") as render:
                self.app._cover_preview_worker("song.wav", "preview.png", 384, 38, "", "title",
                                              "auto", "custom", False, dict(self.app.custom_cover_settings))
            self.assertEqual(render.call_args.kwargs["custom_cover_settings"]["pattern"], "legacy")
        finally:
            if self.app.language != "ru":
                self.app.toggle_language()
            self.app.custom_cover_settings = initial
            self.app.cover_style_var.set(initial_style)
            self.app._cover_preview_ready.clear()

    def test_custom_style_is_restored_after_restart_and_cancel_never_saves(self):
        from ui.dialogs import CustomCoverDialog
        from cover_preferences import load_custom_cover_settings
        initial, initial_style = dict(self.app.custom_cover_settings), self.app.cover_style_var.get()
        dialog = CustomCoverDialog(self.app)
        restarted = None
        try:
            dialog.colors = ['#ff0000', '#00ff00', '#0000ff']
            dialog.positions = [.08, .35, .9]
            dialog.pattern.set(self.app.t('custom_pattern_legacy'))
            for key, value in dict(detail=83, contrast=128, saturation=74, softness=16).items():
                dialog.variables[key].set(value)
            dialog.apply()
            expected = dict(self.app.custom_cover_settings)
            self.assertEqual(load_custom_cover_settings(), expected)
            restarted = music_polisher_gui.SonicForgeApp()
            self.assertEqual(restarted.custom_cover_settings, expected)
            self.assertEqual(restarted.cover_choice('style', restarted.cover_style_var.get()), 'custom')
            dialog = CustomCoverDialog(restarted)
            self.assertEqual(dialog.positions, [.08, .35, .9])
            dialog.reset()
            dialog.close()
            self.assertEqual(load_custom_cover_settings(), expected)
            self.assertEqual(restarted.custom_cover_settings, expected)
        finally:
            if dialog.winfo_exists():
                dialog.close()
            if restarted is not None:
                restarted._close()
            self.app.custom_cover_settings = initial
            self.app.cover_style_var.set(initial_style)

    def test_custom_style_save_error_retains_previous_settings_and_open_dialog(self):
        from ui.dialogs import CustomCoverDialog
        initial, style = dict(self.app.custom_cover_settings), self.app.cover_style_var.get()
        dialog = CustomCoverDialog(self.app)
        try:
            dialog.variables['detail'].set(83)
            with patch('music_polisher_gui.save_custom_cover_settings', side_effect=OSError('Disk full')), \
                 patch('music_polisher_gui.messagebox.showerror') as error:
                dialog.apply()
            error.assert_called_once()
            self.assertTrue(dialog.winfo_exists())
            self.assertEqual(self.app.custom_cover_settings, initial)
            self.assertEqual(self.app.cover_style_var.get(), style)
        finally:
            dialog.close()

    def test_palette_has_no_count_limit_and_can_reorder_edit_remove(self):
        from ui.dialogs import CustomCoverDialog
        from music2picture_v2.custom_style import CustomCoverSettings
        initial = dict(self.app.custom_cover_settings)
        initial_style = self.app.cover_style_var.get()
        dialog = CustomCoverDialog(self.app)
        try:
            self.app.update()
            self.assertGreater(dialog.palette_list.winfo_width(), 250)
            dialog.colors = [f"#{index:06x}" for index in range(1024)]
            dialog._refresh_palette(1023)
            self.assertEqual(dialog.palette_list.size(), 1024)
            self.assertIn("1024", dialog.palette_count.cget("text"))
            with patch("ui.dialogs.colorchooser.askcolor", return_value=((255, 0, 0), "#ff0000")):
                dialog.add_color()
            self.assertEqual(dialog.colors[-1], "#ff0000")
            self.assertEqual(dialog.palette_list.size(), 1025)
            dialog.move_color(-1)
            self.assertEqual(dialog.colors[-2], "#ff0000")
            with patch("ui.dialogs.colorchooser.askcolor", return_value=((0, 255, 0), "#00ff00")):
                dialog.edit_color()
            self.assertEqual(dialog.colors[-2], "#00ff00")
            dialog.remove_color()
            self.assertEqual(len(dialog.colors), 1024)
            dialog.apply()
            self.assertEqual(len(self.app._process_kwargs()["custom_cover_settings"]["colors"]), 1024)
            self.assertEqual(len(CustomCoverSettings.parse(self.app.custom_cover_settings).colors), 1024)
            dialog = CustomCoverDialog(self.app)
            self.assertEqual(dialog.palette_list.size(), 1024)
            dialog.colors = ["#001122"]
            dialog._refresh_palette()
            dialog.remove_color()
            self.assertEqual(dialog.colors, ["#001122"])
            with patch("ui.dialogs.colorchooser.askcolor", return_value=(None, None)):
                dialog.add_color()
            self.assertEqual(dialog.colors, ["#001122"])
        finally:
            if dialog.winfo_exists():
                dialog.close()
            self.app.custom_cover_settings = initial
            self.app.cover_style_var.set(initial_style)

    def test_palette_drag_reorders_stops_clamps_and_persists(self):
        from ui.dialogs import CustomCoverDialog
        from types import SimpleNamespace
        initial = dict(self.app.custom_cover_settings)
        initial_style = self.app.cover_style_var.get()
        dialog = CustomCoverDialog(self.app)
        try:
            self.app.update()
            dialog.colors = ["#ff0000", "#00ff00", "#0000ff"]
            dialog.positions = [0, .4, 1]
            dialog._refresh_palette(1)
            x = round(dialog._palette_x(.4))
            dialog.gradient.event_generate("<Button-1>", x=x, y=38)
            dialog.gradient.event_generate("<B1-Motion>", x=round(dialog._palette_x(.7)), y=38)
            self.app.update()
            dialog.gradient.event_generate("<ButtonRelease-1>", x=round(dialog._palette_x(.7)), y=38)
            self.app.update()
            self.assertAlmostEqual(dialog.positions[1], .7, delta=.002)
            self.assertEqual(dialog.colors[1], "#00ff00")
            self.assertEqual(self.app.custom_cover_settings, initial)
            saved_positions = list(dialog.positions)
            dialog.add_color("#abcdef")
            self.assertEqual(dialog.positions[:-1], saved_positions)
            dialog.remove_color()
            dialog._refresh_palette(1)
            # Drag across the endpoint, maintaining the moved color's identity.
            dialog._start_palette_drag(SimpleNamespace(x=dialog._palette_x(.7)))
            dialog._drag_palette_color(SimpleNamespace(x=dialog.gradient.winfo_width() + 100))
            dialog._end_palette_drag(SimpleNamespace(x=dialog.gradient.winfo_width() + 100))
            self.assertEqual(dialog.colors, ["#ff0000", "#0000ff", "#00ff00"])
            self.assertEqual(dialog.positions[-1], 1)
            dialog._start_palette_drag(SimpleNamespace(x=dialog._palette_x(1)))
            dialog._end_palette_drag(SimpleNamespace(x=-100))
            self.assertEqual(dialog.colors, ["#ff0000", "#00ff00", "#0000ff"])
            self.assertEqual(dialog.positions, [0, 0, 1])
            dialog._nudge_palette_color(1, SimpleNamespace(state=1))
            self.assertEqual(dialog.positions[1], .001)
            expected = list(dialog.positions)
            dialog.apply()
            self.assertEqual(self.app._process_kwargs()["custom_cover_settings"]["positions"], expected)
            dialog = CustomCoverDialog(self.app)
            self.assertEqual(dialog.positions, expected)
            self.assertIsNotNone(dialog._gradient_image)
            dialog._start_palette_drag(SimpleNamespace(x=dialog._palette_x(.001)))
            dialog._drag_palette_color(SimpleNamespace(x=dialog._palette_x(.6)))
            dialog.close()  # Also cancel a pending idle redraw safely.
            self.assertEqual(self.app.custom_cover_settings["positions"], expected)
        finally:
            if dialog.winfo_exists():
                dialog.close()
            self.app.custom_cover_settings = initial
            self.app.cover_style_var.set(initial_style)

    def test_new_palette_colors_keep_automatic_spacing_until_customized(self):
        from ui.dialogs import CustomCoverDialog
        dialog = CustomCoverDialog(self.app)
        try:
            dialog.colors = ["#ff0000", "#00ff00"]
            dialog.positions = [0, 1]
            dialog._refresh_palette()
            dialog.add_color("#0000ff")
            self.assertEqual(dialog.positions, [0, .5, 1])
            dialog._nudge_palette_color(-1, SimpleNamespace(state=0))
            positions = list(dialog.positions)
            dialog.add_color("#ffffff")
            self.assertEqual(dialog.positions, positions + [1])
        finally:
            dialog.close()

    def test_custom_cover_switches_off_generation_controls_and_reaches_processing(self):
        previous = self.app.custom_cover_path_var.get()
        try:
            self.app.custom_cover_path_var.set("C:/Music/my-cover.png")
            self.app.view.update_cover_source()
            self.assertIn("disabled", self.app.view.cover_style_combo.state())
            self.assertIn("disabled", self.app.view.cover_style_settings_button.state())
            self.assertIn("my-cover.png", self.app.view.cover_custom_status.cget("text"))
            self.assertEqual(self.app._process_kwargs()["custom_cover_path"], "C:/Music/my-cover.png")
            self.app.toggle_language()
            self.assertIn("Custom image", self.app.view.cover_custom_status.cget("text"))
            self.app.toggle_language()
        finally:
            self.app.custom_cover_path_var.set(previous)
            self.app.view.update_cover_source()

    def test_double_click_selects_a_unicode_lyrics_word_with_apostrophe(self):
        editor = self.app.view.lyrics_editor
        self.app.view.set_lyrics_text("Привет l'amour мир")
        self.app.view.show_tab("lyrics")
        self.app.update_idletasks()
        box = editor.bbox("1.10")
        self.assertIsNotNone(box)
        event = SimpleNamespace(x=box[0] + 1, y=box[1] + 1)
        self.assertEqual(self.app.view._select_lyrics_word(event), "break")
        self.assertEqual(editor.get(tk.SEL_FIRST, tk.SEL_LAST), "l'amour")

    def test_mp3_format_explicitly_embeds_lyrics_and_other_audio_offers_sidecars(self):
        old_source = self.app.source_var.get()
        try:
            self.app.source_var.set("C:/Music/song.mp3")
            self.assertEqual(self.app.lyrics_format_key(), "uslt")
            self.assertIn("USLT", self.app.lyrics_format_var.get())
            self.assertEqual(len(self.app.view.lyrics_format.cget("values")), 1)
            self.app.toggle_language()
            self.assertEqual(self.app.lyrics_format_key(), "uslt")
            self.assertIn("In song", self.app.lyrics_format_var.get())
            self.app.source_var.set("C:/Music/song.wav")
            self.assertEqual(self.app.lyrics_format_key(), "txt")
            self.assertEqual(len(self.app.view.lyrics_format.cget("values")), 2)
        finally:
            self.app.source_var.set(old_source)

    def test_recognized_lines_display_independently_of_log_queue(self):
        self.app.view.set_lyrics_text("")
        self.app.view.set_lyrics_busy(True)
        self.app._lyrics_results.put(("line", TranscriptSegment(1, 3, "Русская строка песни")))
        self.app._lyrics_results.put(("done", None))
        self.app._poll_lyrics()
        self.assertEqual(self.app.view.get_lyrics_text(), "Русская строка песни")
        self.assertNotIn("[00:", self.app.view.get_lyrics_text())

    def test_preview_never_reads_the_image_before_rendering_finishes(self):
        previous_worker = self.app.worker
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "unfinished.png"
            target.touch()
            self.app._pending_preview_path = target
            self.app._cover_preview_displayed = False
            self.app._cover_preview_ready.clear()
            self.app.worker = SimpleNamespace(is_alive=lambda: True)
            try:
                with patch.object(self.app.view, "show_cover_preview") as show:
                    self.app._poll_cover_preview()
                    show.assert_not_called()
            finally:
                self.app.after_cancel(self.app._preview_after_id)
                self.app._preview_after_id = None
                self.app._pending_preview_path = None
                self.app.worker = previous_worker

    def test_embedding_error_does_not_hide_recognized_text(self):
        result = LyricsResult(text="Русская строка песни", language="ru", language_confidence=0.89,
                              segments=(TranscriptSegment(1, 3, "Русская строка песни", 0.9),))
        previous_service = self.app._lyrics_service
        previous_source = self.app.source_var.get()
        try:
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "song.mp3"
                source.touch()
                self.app.source_var.set(str(source))
                self.app._lyrics_service = LyricsService(provider=MockLyricsProvider(result))
                with patch("music_polisher_gui.save_lyrics", side_effect=PermissionError("locked file")), \
                     patch("music_polisher_gui.messagebox.showwarning") as warning:
                    self.app.recognize_lyrics()
                    self.app.worker.join(5)
                    self.assertFalse(self.app.worker.is_alive())
                    self.app.after_cancel(self.app._lyrics_after_id)
                    self.app._poll_lyrics()
                self.assertEqual(self.app.view.get_lyrics_text(), result.text)
                self.assertEqual(self.app.lyrics_result.language, "ru")
                warning.assert_called_once()
                self.assertFalse(source.with_suffix(".lrc").exists())
        finally:
            self.app._lyrics_service = previous_service
            self.app.source_var.set(previous_source)

    def test_file_selection_sets_sibling_output_without_audio_analysis(self):
        source = Path("C:/Music/Album/song.mp3")
        old_source, old_output = self.app.source_var.get(), self.app.output_var.get()
        try:
            with patch("music_polisher_gui.filedialog.askopenfilename", return_value=str(source)), \
                 patch.object(self.app, "analyze_audio_settings") as analyze:
                self.app.choose_source_file()
            analyze.assert_not_called()
            self.assertEqual(Path(self.app.output_var.get()), source.parent / "SonicForgeProgect")
            self.assertEqual(self.app.source_var.get(), str(source))
            self.assertIsNone(self.app.audio_analysis_data)
        finally:
            self.app.source_var.set(old_source)
            self.app.output_var.set(old_output)

    @unittest.skipUnless(os.name == "nt", "Windows folder picker")
    def test_folder_picker_keeps_tk_responsive_and_output_outside_source(self):
        source = Path("C:/Music/Album")
        release = threading.Event()
        entered = threading.Event()
        old_source, old_output = self.app.source_var.get(), self.app.output_var.get()
        callback_ran = []
        worker_threads = []

        def pick(*args):
            worker_threads.append(threading.get_ident())
            entered.set()
            release.wait(5)
            return str(source)

        try:
            with patch("music_polisher_gui.choose_windows_folder", side_effect=pick):
                start = time.monotonic()
                self.app.choose_source_folder()
                self.assertLess(time.monotonic() - start, 0.5)
                self.assertTrue(entered.wait(2))
                self.app.after(0, lambda: callback_ran.append(True))
                self.app.update()
                self.assertEqual(callback_ran, [True])
                self.assertNotEqual(worker_threads[0], threading.get_ident())
                release.set()
                self.app._folder_picker_thread.join(2)
                self.app.after_cancel(self.app._folder_picker_after_id)
                self.app._poll_folder_picker()
            self.assertEqual(Path(self.app.output_var.get()), source.parent / "SonicForgeProgect")
            self.assertFalse(self.app._folder_picker_open)
        finally:
            release.set()
            self.app.source_var.set(old_source)
            self.app.output_var.set(old_output)

    def test_cancelled_folder_picker_preserves_paths(self):
        previous = (self.app.source_var.get(), self.app.output_var.get())
        self.app._folder_picker_open = True
        self.app._folder_picker_results.put(("source", "", ""))
        self.app._poll_folder_picker()
        self.assertEqual((self.app.source_var.get(), self.app.output_var.get()), previous)
        self.assertFalse(self.app._folder_picker_open)

    def test_preview_button_renders_quick_image_and_displays_it(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "song.wav"
            with wave.open(str(source), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(8000)
                audio.writeframes(b"\0\0" * 8000)
            self.app.source_var.set(str(source))
            self.app.cover_size_var.set(512)
            self.app.seed_var.set("4")
            rendered = []

            def render(_source, target, **kwargs):
                rendered.append((Path(target), kwargs))
                Path(target).parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (kwargs["size"], kwargs["size"]), "#27559c").save(target)

            with patch("music2picture.make_cover", side_effect=render):
                self.app.preview_cover()
                self.app.worker.join(timeout=5)
            self.app._poll_cover_preview()
            self.assertEqual(len(rendered), 1)
            self.assertEqual(rendered[0][1]["size"], 384)
            self.assertTrue(rendered[0][1]["preview"])
            self.assertIs(rendered[0][1]["use_lyrics_for_cover"], False)
            self.assertEqual(rendered[0][1]["lyrics_text"], "")
            self.assertTrue(self.app.last_cover_path.is_file())
            self.assertTrue(self.app.view.cover_preview_image.cget("image"))
            self.assertEqual(self.app.view._cover_preview_photo.width(), 220)
            self.app.source_var.set("")

    def test_cover_lyrics_switch_reaches_preview_and_processing(self):
        self.assertFalse(hasattr(self.app, 'use_lyrics_for_cover_var'))
        self.assertFalse(hasattr(self.app.view, 'use_lyrics_check'))
        try:
            kwargs = self.app._process_kwargs()
            self.assertIs(kwargs["use_lyrics_for_cover"], False)
            self.assertEqual(kwargs["cover_lyrics_text"], "")
            with patch("music2picture.make_cover") as render:
                self.app._cover_preview_worker("test.wav", "test.png", 128, 0,
                                              "Editor test text", "none", "auto", "current", False)
            self.assertIs(render.call_args.kwargs["use_lyrics_for_cover"], False)
        finally:
            self.app._cover_preview_ready.clear()

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required for cover rendering")
    def test_real_preview_appears_without_log_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "song.wav"
            with wave.open(str(source), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(8000)
                audio.writeframes(b"\0\0" * 8000)
            self.app.source_var.set(str(source))
            self.app.cover_style_var.set("Современный рисунок")
            self.app.seed_var.set("0")
            self.app.last_cover_path = None
            with patch.dict(os.environ, {"LOCALAPPDATA": directory}):
                self.app.preview_cover()
                deadline = time.monotonic() + 15
                while self.app.last_cover_path is None and time.monotonic() < deadline:
                    self.app.update()
                    time.sleep(0.05)
            self.assertIsNotNone(
                self.app.last_cover_path,
                f"worker_alive={self.app.worker.is_alive()}, "
                f"error={self.app._cover_preview_error}, "
                f"pending={self.app._pending_preview_path}, "
                f"exists={self.app._pending_preview_path.is_file() if self.app._pending_preview_path else None}",
            )
            self.assertTrue(self.app.view.cover_preview_image.cget("image"))
            self.app.worker.join(timeout=5)
            self.app._poll_cover_preview()
            self.app.source_var.set("")


def _descendants(widget):
    children = list(widget.winfo_children())
    for child in children:
        yield child
        yield from _descendants(child)


if __name__ == "__main__":
    unittest.main()
