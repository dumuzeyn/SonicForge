from pathlib import Path
import shutil
import tempfile
import threading
import time
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch, PropertyMock

from audio_editor import AudioSource
from music_polisher_gui import SonicForgeApp
from ui.widgets import RoundedButton
from test_audio_editor import make_tone


class EditorUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = SonicForgeApp()

    @classmethod
    def tearDownClass(cls):
        cls.app._close()

    def setUp(self):
        from audio_editor import Timeline
        self.editor = self.app.view.editor
        self.editor.stop()
        self.editor.project = Timeline()
        self.editor.selected = None
        self.editor.cursor = 0
        self.editor.range = None
        self.editor._range_clip_id = None
        self.editor._cursor_selection = None
        self.editor._drag = None
        self.editor._drag_preview = None
        self.editor.fit()
        self.editor.lane.set(1)
        self.app.view.show_tab("editor")
        self.app.update()

    def test_editor_is_default_on_launch_and_does_not_load_models(self):
        self.assertEqual(self.app.view.active_tab, "editor")
        self.assertIsNone(self.app._lyrics_service)
        self.assertIsNone(self.app.worker)

    def test_tool_shortcuts_work_in_russian_layout_and_show_in_stem_menu(self):
        def key(code, symbol, state=4):
            return SimpleNamespace(widget=self.editor.canvas, keycode=code, keysym=symbol, state=state)
        clip = self.editor.project.add(AudioSource('song.wav', 10))
        self.editor.selected = clip.id
        self.editor.cursor = 4
        self.assertEqual(self.editor._shortcut(key(75, 'Cyrillic_el')), 'break')
        self.assertEqual(len(self.editor.project.clips), 2)
        self.editor._shortcut(key(90, 'Cyrillic_ya'))
        self.assertEqual(len(self.editor.project.clips), 1)
        self.editor._shortcut(key(90, 'Cyrillic_ya', 5))
        self.assertEqual(len(self.editor.project.clips), 2)
        with patch.object(self.editor, 'separate_stems') as separate:
            self.editor._shortcut(key(86, 'Cyrillic_em', 5))
            self.editor._shortcut(key(66, 'Cyrillic_i', 5))
        self.assertEqual([call.args for call in separate.call_args_list], [('two',), ('four',)])
        self.assertEqual(self.editor.stems_menu.entrycget(0, 'accelerator'), 'Ctrl+Shift+V')

    def test_tool_shortcuts_never_intercept_fields_other_tabs_modals_or_altgr(self):
        entry = self.app.view.source_entry
        modal = tk.Toplevel(self.app)
        try:
            with patch.object(self.editor, 'separate_stems') as separate:
                for widget, state in ((entry, 5), (self.editor.canvas, 13), (modal, 5)):
                    event = SimpleNamespace(widget=widget, state=state, keycode=86, keysym='V')
                    self.assertIsNone(self.editor._shortcut(event))
                self.app.view.show_tab('metadata')
                event = SimpleNamespace(widget=self.editor.canvas, state=5, keycode=86, keysym='V')
                self.assertIsNone(self.editor._shortcut(event))
            separate.assert_not_called()
        finally:
            modal.destroy()

    def test_canvas_key_event_invokes_action_once_and_busy_escape_cancels(self):
        self.editor.canvas.focus_force()
        self.app.update()
        with patch.object(self.editor, 'choose_audio') as choose:
            self.editor.canvas.event_generate('<KeyPress>', keycode=73, state=4)
            self.app.update()
            choose.assert_called_once()
        with patch.object(type(self.editor), 'is_busy', new_callable=PropertyMock) as busy:
            busy.return_value = True
            with patch.object(self.editor, 'separate_stems') as separate:
                self.editor._shortcut(SimpleNamespace(widget=self.editor.canvas, state=5, keycode=86, keysym='V'))
                separate.assert_not_called()
            self.editor._shortcut(SimpleNamespace(widget=self.editor.canvas, state=0, keycode=27, keysym='Escape'))
            self.assertTrue(self.editor.cancel.is_set())
        self.editor.cancel.clear()

    def test_real_undo_redo_events_work_from_canvas_buttons_and_numeric_inspector(self):
        clip = self.editor.project.add(AudioSource('song.wav', 10))
        self.editor.selected = clip.id
        self.editor.project.update(clip.id, end=8)
        self.editor.refresh()
        for focus in (self.editor.canvas, self.editor.undo_button, self.editor.inspector_controls[0]):
            focus.focus_force()
            self.app.update()
            focus.event_generate('<KeyPress>', keycode=90, state=4)
            self.app.update()
            self.assertEqual(self.editor.project.get(clip.id).end, 10)
            focus.event_generate('<KeyPress>', keycode=89, state=4)
            self.app.update()
            self.assertEqual(self.editor.project.get(clip.id).end, 8)
            focus.event_generate('<KeyPress>', keycode=90, state=4)
            self.app.update()
            focus.event_generate('<KeyPress>', keycode=90, state=5)
            self.app.update()
            self.assertEqual(self.editor.project.get(clip.id).end, 8)
        self.editor.canvas.focus_force()
        self.app.update()
        with patch.object(self.editor, 'edit') as edit:
            self.editor.canvas.event_generate('<KeyPress>', keycode=75, state=4)
            self.app.update()
            self.editor.canvas.event_generate('<KeyPress>', keycode=68, state=4)
            self.app.update()
        self.assertEqual([call.args for call in edit.call_args_list], [('split',), ('duplicate',)])

    def test_rounded_buttons_keyboard_disabled_and_text_layout(self):
        calls = []
        wrapper = tk.Frame(self.app)
        button = RoundedButton(wrapper, text="Проверка", command=lambda: calls.append(True))
        button.pack()
        try:
            wrapper.place(x=0, y=0)
            self.app.update()
            button.invoke()
            button.configure(state="disabled")
            button.invoke()
            self.assertEqual(calls, [True])
            button.configure(text="Long English button", state="normal")
            self.app.update_idletasks()
            self.assertGreaterEqual(button.winfo_width(), button.font.measure(button.cget("text")) + 24)
        finally:
            wrapper.destroy()

    def test_trim_split_volume_and_undo_through_editor_commands(self):
        source = AudioSource("song.wav", 10, (.1,) * 200)
        clip = self.editor.project.add(source)
        self.editor.selected = clip.id
        self.editor.refresh()
        self.editor.fields["start"].set("1,5")
        self.editor.fields["end"].set("8")
        self.editor.fields["gain"].set("-6")
        self.editor.apply()
        self.assertEqual(self.editor.project.get(clip.id).start, 1.5)
        self.assertEqual(self.editor.project.get(clip.id).gain, -6)
        self.editor.cursor = 3
        self.editor.edit("split")
        self.assertEqual(len(self.editor.project.clips), 2)
        self.editor.history(False)
        self.assertEqual(len(self.editor.project.clips), 1)

    def _wait_for_editor(self):
        deadline = time.monotonic() + 10
        while self.editor.is_busy:
            self.app.update()
            time.sleep(.005)
            if time.monotonic() > deadline:
                self.fail(self.editor.status.get())

    def test_range_cut_removes_selection_joins_and_keeps_position_one_undo(self):
        source = AudioSource("song.wav", 10)
        clip = self.editor.project.add(source, position=3)
        self.editor.selected = clip.id
        self.editor.range = (4, 7)
        self.editor._range_clip_id = clip.id
        with patch('ui.editor.remove_audio_selection', return_value=AudioSource('edited.wav', 6.96)) as cut:
            self.editor.edit("trim")
            self._wait_for_editor()
        cut.assert_called_once_with(source, clip, 4, 7, self.editor.cancel)
        edited = self.editor.project.get(clip.id)
        self.assertEqual((edited.start, edited.end, edited.position), (0, 6.96, 3))
        self.assertEqual(edited.source, 'edited.wav')
        self.editor.history(False)
        self.assertEqual(self.editor.project.get(clip.id), clip)
        self.editor.history(True)
        self.assertEqual(self.editor.project.get(clip.id), edited)

    def test_mute_undo_and_export_are_not_batch_processing(self):
        source = AudioSource("song.wav", 10)
        clip = self.editor.project.add(source)
        self.editor.selected = clip.id
        with patch.object(self.app, "_run_process") as process:
            self.editor.project.toggle_mute(0)
            self.editor.history(False)
            self.editor.edit("duplicate")
        process.assert_not_called()
        self.assertFalse(self.editor.project.muted)

    def _event(self, at, lane=0, state=0):
        return SimpleNamespace(x=85 + at * self.editor._scale() - self.editor.canvas.canvasx(0),
                               y=35 + lane * 76 + 20 - self.editor.canvas.canvasy(0), state=state)

    def test_exact_selection_is_clip_relative_and_does_not_edit_audio(self):
        clip = self.editor.project.add(AudioSource('song.wav', 30), position=20)
        self.editor.selected = clip.id
        self.editor.refresh()
        self.editor.selection_fields['start'].set('1,234')
        self.editor.selection_fields['end'].set('2.345')
        self.editor.set_selection()
        a, b = self.editor._trim_range()
        self.assertAlmostEqual(a, 21.234)
        self.assertAlmostEqual(b, 22.345)
        self.assertEqual(self.editor.project.get(clip.id), clip)
        self.assertIn('1.111', self.editor.selection_length.get())
        self.editor.zoom_selection()
        self.app.update_idletasks()
        self.assertGreater(self.editor.zoom, 1)
        rect = self.editor.canvas.find_withtag('selection-range')[0]
        self.assertEqual(self.editor.canvas.coords(rect)[1::2], [38, 100])
        self.editor.fit()

    def test_cursor_selection_two_clicks_keeps_button_size_and_clip_intact(self):
        clip = self.editor.project.add(AudioSource('song.wav', 10), position=3)
        self.editor.selected = clip.id
        self.editor.cursor = 4.234
        self.editor.refresh()
        self.app.update_idletasks()
        button = self.editor.cursor_selection_button
        before = (button.winfo_width(), button.winfo_height())
        button.invoke()
        self.app.update_idletasks()
        self.assertEqual(button.cget('text'), self.editor.tr('finish_range'))
        self.assertEqual((button.winfo_width(), button.winfo_height()), before)
        self.editor.cursor = 6.345
        self.editor._update_cursor_selection()
        self.assertEqual(self.editor.trim_button.cget('state'), 'disabled')
        self.editor.edit('trim')
        self.assertEqual(self.editor.project.get(clip.id), clip)
        button.invoke()
        self.app.update_idletasks()
        self.assertEqual(button.cget('text'), self.editor.tr('begin_range'))
        self.assertEqual((button.winfo_width(), button.winfo_height()), before)
        self.assertEqual(self.editor._trim_range(), (4.234, 6.345))
        self.assertEqual(self.editor.trim_button.cget('state'), 'normal')
        self.assertEqual(self.editor.project.get(clip.id), clip)

    def test_cursor_selection_follows_playback_and_finishes_without_stopping(self):
        clip = self.editor.project.add(AudioSource('song.wav', 10))
        self.editor.selected = clip.id
        self.editor.refresh()
        self.editor._playing = True
        self.editor._play_origin = 2
        self.editor._play_started = 100
        with patch('ui.editor.time.monotonic', return_value=100.234):
            self.editor.toggle_cursor_selection()
        with patch('ui.editor.time.monotonic', return_value=101.345):
            self.editor._tick()
        self.assertAlmostEqual(self.editor.range[1], 3.345)
        with patch('ui.editor.time.monotonic', return_value=101.456):
            self.editor.toggle_cursor_selection()
        self.assertTrue(self.editor._playing)
        self.assertAlmostEqual(self.editor._trim_range()[0], 2.234)
        self.assertAlmostEqual(self.editor._trim_range()[1], 3.456)
        self.editor.stop()

    def test_cursor_selection_manual_movement_escape_and_language_size(self):
        clip = self.editor.project.add(AudioSource('song.wav', 10))
        self.editor.selected = clip.id
        self.editor.cursor = 2
        self.editor.changed()
        self.app.update()
        self.editor.toggle_cursor_selection()
        self.editor._press(self._event(4))
        self.editor._motion(self._event(5))
        self.editor._release(self._event(5))
        self.editor.toggle_cursor_selection()
        self.assertEqual(self.editor._trim_range(), (2, 5))
        self.assertEqual(self.editor.project.get(clip.id), clip)
        for language in ('en', 'ru'):
            if self.app.language != language:
                self.app.toggle_language()
            self.app.update_idletasks()
            width = self.editor.cursor_selection_button.winfo_width()
            self.editor.toggle_cursor_selection()
            self.app.update_idletasks()
            self.assertEqual(self.editor.cursor_selection_button.winfo_width(), width)
            self.editor._shortcut(SimpleNamespace(widget=self.editor.canvas, keycode=27, keysym='Escape', state=0))
            self.assertIsNone(self.editor._cursor_selection)
            self.assertIsNone(self.editor.range)
            self.editor.cancel.clear()
        self.editor.cursor = 20
        self.editor.toggle_cursor_selection()
        self.assertIsNone(self.editor._cursor_selection)

    def test_entire_clip_moves_live_during_drag_and_commits_one_undo(self):
        clip = self.editor.project.add(AudioSource('song.wav', 10, (.1,) * 200))
        self.editor.selected = clip.id
        self.editor.changed()
        self.app.update()
        self.editor._press(self._event(1))
        cursor = self.editor.cursor
        undo_count = len(self.editor.project._undo)
        self.editor._motion(self._event(3))
        self.app.update_idletasks()
        self.assertEqual(self.editor.project.get(clip.id), clip)
        self.assertEqual(self.editor.cursor, cursor)
        self.assertEqual(len(self.editor.project._undo), undo_count)
        rect = self.editor.canvas.find_withtag('clip:' + clip.id)[0]
        self.assertAlmostEqual(self.editor.canvas.coords(rect)[0], 85 + 2 * self.editor._scale())
        self.editor._release(self._event(3))
        self.assertAlmostEqual(self.editor.project.get(clip.id).position, 2)
        self.assertEqual(len(self.editor.project._undo), undo_count + 1)
        self.assertIsNone(self.editor._drag_preview)

    def test_dragging_red_cursor_does_not_move_underlying_clip(self):
        clip = self.editor.project.add(AudioSource('song.wav', 10))
        self.editor.selected = clip.id
        self.editor.cursor = 2
        self.editor.changed()
        self.app.update()
        self.editor._press(self._event(2))
        self.editor._motion(self._event(5))
        self.editor._release(self._event(5))
        self.assertAlmostEqual(self.editor.cursor, 5)
        self.assertEqual(self.editor.project.get(clip.id), clip)

    def test_preview_uses_exact_cursor_and_tick_advances_red_line(self):
        self.editor.project.add(AudioSource('song.wav', 30))
        self.editor.cursor = 12.345
        self.editor.refresh()
        with patch('ui.editor.render', return_value=Path('preview.wav')) as renderer, patch.object(self.editor, '_play') as play:
            self.editor.preview()
            self._wait_for_editor()
        self.assertAlmostEqual(renderer.call_args.kwargs['start'], 12.345)
        self.assertAlmostEqual(play.call_args.args[1], 12.345)
        self.editor._playing = True
        self.editor._play_origin = 12.345
        self.editor._play_started = 100
        with patch('ui.editor.time.monotonic', return_value=102.5):
            self.editor._tick()
        self.assertAlmostEqual(self.editor.cursor, 14.845)
        red_line = self.editor.canvas.find_withtag('cursor')[0]
        self.assertAlmostEqual(self.editor.canvas.coords(red_line)[0], 85 + self.editor.cursor * self.editor._scale())
        self.editor.stop()
        self.editor.cursor = 30
        with patch.object(self.editor, '_task') as task:
            self.editor.preview()
        task.assert_not_called()

    def test_invalid_selection_does_not_replace_confirmed_range(self):
        clip = self.editor.project.add(AudioSource('song.wav', 10))
        self.editor.selected = clip.id
        self.editor.refresh()
        self.editor.selection_fields['start'].set('2')
        self.editor.selection_fields['end'].set('3')
        self.editor.set_selection()
        before = self.editor.range
        for start, end in (('nan', '3'), ('-1', '3'), ('3', '2'), ('1', '11'), ('2', '2.001')):
            self.editor.selection_fields['start'].set(start)
            self.editor.selection_fields['end'].set(end)
            self.editor.set_selection()
            self.assertEqual(self.editor.range, before)
        self.editor.selected = None
        self.editor.refresh()
        self.assertTrue(all(str(w.cget('state')) == 'disabled' for w in self.editor.inspector_controls + self.editor.selection_controls))

    def test_inspector_groups_apply_all_audio_and_placement_parameters(self):
        clip = self.editor.project.add(AudioSource('song.wav', 20))
        self.editor.selected = clip.id
        self.editor.refresh()
        self.assertEqual(len(self.editor.inspector_groups), 3)
        for key, value in {'start': '1.234', 'end': '12.345', 'position': '2.345',
                           'gain': '-3.5', 'fade_in': '0.123', 'fade_out': '0.234'}.items():
            self.editor.fields[key].set(value)
        self.editor.lane.set(3)
        self.editor.apply()
        changed = self.editor.project.get(clip.id)
        self.assertEqual((changed.start, changed.end, changed.position, changed.gain, changed.fade_in, changed.fade_out, changed.lane),
                         (1.234, 12.345, 2.345, -3.5, .123, .234, 2))
        self.editor.history(False)
        self.assertEqual(self.editor.project.get(clip.id), clip)

    def test_open_with_arguments_import_unicode_audio_into_editor_without_processing(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / 'Песня с пробелами.MP3'
            second = Path(folder) / 'another.wav'
            first.touch()
            second.touch()
            self.app.view.show_tab('metadata')
            with patch.object(self.editor, 'import_files') as importer, patch.object(self.app, '_run_process') as process:
                self.app.open_audio_arguments(['--bad', folder, str(first), str(first), str(second), str(first.with_suffix('.txt'))])
            importer.assert_called_once_with([str(first.resolve()), str(second.resolve())])
            process.assert_not_called()
            self.assertEqual(self.app.view.active_tab, 'editor')
            self.assertEqual(self.app.source_var.get(), str(first.resolve()))
            self.assertEqual(Path(self.app.output_var.get()), first.parent / 'SonicForgeProgect')

    def test_plain_drag_never_sets_trim_range_or_changes_source_bounds(self):
        clip = self.editor.project.add(AudioSource('song.wav', 10))
        self.editor.selected = clip.id
        self.editor.changed()
        self.app.update()
        self.editor._press(self._event(1))
        self.editor._motion(self._event(3))
        self.editor._release(self._event(3))
        moved = self.editor.project.get(clip.id)
        self.assertEqual((moved.start, moved.end), (0, 10))
        self.assertAlmostEqual(moved.position, 2)
        self.assertIsNone(self.editor.range)
        self.assertEqual(self.editor.trim_button.cget('state'), 'disabled')
        self.editor.edit('trim')
        self.assertEqual(self.editor.project.get(clip.id), moved)

    def test_explicit_shift_range_enables_trim_and_stale_range_is_rejected(self):
        clip = self.editor.project.add(AudioSource('song.wav', 10))
        self.editor.changed()
        self.app.update()
        self.editor._press(self._event(2, state=1))
        self.editor._motion(self._event(5, state=1))
        self.assertEqual(self.editor.trim_button.cget('state'), 'disabled')
        self.editor._release(self._event(5, state=1))
        self.assertEqual(self.editor.trim_button.cget('state'), 'normal')
        bounds = self.editor._trim_range()
        duration = clip.duration - (bounds[1] - bounds[0]) - .04
        with patch('ui.editor.remove_audio_selection', return_value=AudioSource('edited.wav', duration)):
            self.editor.trim_button.invoke()
            self._wait_for_editor()
        trimmed = self.editor.project.get(clip.id)
        self.assertEqual(trimmed.start, 0)
        self.assertAlmostEqual(trimmed.duration, duration)
        self.assertEqual(trimmed.position, clip.position)
        self.editor.range = (2, 4)
        self.editor._range_clip_id = 'different-clip'
        self.editor.edit('trim')
        self.assertEqual(self.editor.project.get(clip.id), trimmed)

    def test_removing_entire_selection_deletes_clip_without_processing_source(self):
        clip = self.editor.project.add(AudioSource('song.wav', 10), position=3)
        self.editor.selected = clip.id
        self.editor.range = (0, 20)
        self.editor._range_clip_id = clip.id
        with patch('ui.editor.remove_audio_selection') as cut:
            self.editor.edit('trim')
        cut.assert_not_called()
        self.assertEqual(self.editor.project.clips, [])
        self.editor.history(False)
        self.assertEqual(self.editor.project.clips, [clip])

    def test_explanations_are_in_help_not_permanently_on_working_pages(self):
        from ui.editor import TEXT
        texts = []
        def walk(widget):
            try:
                texts.append(str(widget.cget('text')))
            except tk.TclError:
                pass
            for child in widget.winfo_children():
                walk(child)
        walk(self.app.view)
        self.assertNotIn(TEXT[self.app.language]['intro'], texts)
        self.assertNotIn(TEXT[self.app.language]['hint'], texts)
        self.assertNotIn(self.app.t('help_hint'), texts)
        self.assertNotIn(self.app.t('audio_scope'), texts)
        guide, parameters = self.app.view._help_content('editor')
        self.assertTrue(any('40' in body for _, body in parameters))

    def test_drag_on_empty_space_does_not_move_previous_selection(self):
        clip = self.editor.project.add(AudioSource('song.wav', 2))
        self.editor.selected = clip.id
        self.editor.changed()
        self.app.update()
        self.editor._press(self._event(6))
        self.editor._motion(self._event(8))
        self.editor._release(self._event(8))
        self.assertEqual(self.editor.project.get(clip.id), clip)
        self.assertIsNone(self.editor.selected)

    def test_vertical_drag_creates_new_lane_and_can_be_undone(self):
        clip = self.editor.project.add(AudioSource('song.wav', 10))
        self.editor.changed()
        self.app.update()
        self.editor._press(self._event(1))
        self.editor._motion(self._event(1, lane=1))
        self.editor._release(self._event(1, lane=1))
        self.assertEqual(self.editor.project.get(clip.id).lane, 1)
        self.editor.history(False)
        self.assertEqual(self.editor.project.get(clip.id).lane, 0)

    def test_native_file_drop_accepts_unicode_names_and_new_lane(self):
        self.assertTrue(self.app.TkdndVersion)
        self.assertTrue(self.editor.canvas.dnd_bind('<<Drop>>'))
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ('песня {1}.wav', 'second song.wav')]
            for path in paths:
                make_tone(path)
            event = SimpleNamespace(data=self.editor.tk.call('list', *(str(p) for p in paths)),
                x_root=self.editor.canvas.winfo_rootx() + 85 + 3 * self.editor._scale() - self.editor.canvas.canvasx(0),
                y_root=self.editor.canvas.winfo_rooty() + 150)
            with patch.object(self.editor, 'import_files') as imported:
                self.assertEqual(self.editor._drop_files(event), 'copy')
                actual_paths = imported.call_args.args[0]
                self.assertEqual(tuple(actual_paths), tuple(str(p) for p in paths))
                self.assertEqual(imported.call_args.kwargs['lane'], 1)
                self.assertAlmostEqual(imported.call_args.kwargs['position'], 3, delta=1 / self.editor._scale() + 1e-6)
            event.data = self.editor.tk.call('list', directory)
            with patch.object(self.editor, 'import_files') as imported:
                self.assertEqual(self.editor._drop_files(event), 'refuse_drop')
                imported.assert_not_called()

    def test_stem_replacement_is_separate_lanes_and_one_undo_step(self):
        clip = self.editor.project.add(AudioSource('song.wav', 10), position=3)
        self.editor.selected = clip.id
        before = list(self.editor.project.clips)
        self.editor.events.put(('stems', ([AudioSource(name + '.wav', 10) for name in ('vocals', 'drums', 'bass', 'other')], clip)))
        self.editor._poll()
        self.assertEqual(len(self.editor.project.clips), 4)
        self.assertEqual({c.position for c in self.editor.project.clips}, {3})
        self.assertEqual(len({c.lane for c in self.editor.project.clips}), 4)
        self.editor.history(False)
        self.assertEqual(self.editor.project.clips, before)
        self.editor.history(True)
        self.assertEqual(len(self.editor.project.clips), 4)

    def test_many_lanes_have_no_fixed_limit_and_draw_only_visible_rows(self):
        self.editor.project.add(AudioSource('song.wav', 10), lane=1999)
        self.editor.changed()
        self.app.update()
        self.assertEqual(self.editor._lane_count(), 2000)
        self.assertEqual(self.editor._drop_lane(35 + 2001 * 76), 2000)
        self.assertLess(len(self.editor.canvas.find_all()), 200)
        self.editor._scroll_y('moveto', 1)
        self.app.update()
        self.assertTrue(any(self.editor.tr('new_lane') == self.editor.canvas.itemcget(item, 'text')
                            for item in self.editor.canvas.find_all() if self.editor.canvas.type(item) == 'text'))

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
    def test_import_runs_in_background_without_blocking_navigation(self):
        from audio_editor import read_waveform
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "song.wav"
            make_tone(path)
            release = threading.Event()
            def decode(*args, **kwargs):
                self.assertIsNot(threading.current_thread(), threading.main_thread())
                if not release.wait(10):
                    raise TimeoutError('UI did not release background decoder')
                return read_waveform(*args, **kwargs)
            with patch('ui.editor.read_waveform', side_effect=decode):
                self.editor.import_files([str(path)])
                deadline = time.monotonic() + 15
                ticks = 0
                try:
                    while self.editor.is_busy or not self.editor.project.clips:
                        self.app.view.show_tab("metadata")
                        self.app.view.show_tab("editor")
                        self.app.update()
                        time.sleep(.005)
                        ticks += 1
                        if ticks >= 3:
                            release.set()
                        if time.monotonic() > deadline:
                            self.fail(self.editor.status.get())
                finally:
                    release.set()
            self.assertGreater(ticks, 1)
            self.assertTrue(self.editor.project.clips)
            self.assertIsNone(self.app.worker)

    def test_default_import_puts_each_song_on_a_new_lane_at_zero(self):
        self.editor.project.add(AudioSource('existing.wav', 10), lane=0)
        self.editor.lane.set(1)
        sources = [AudioSource('first.wav', 8), AudioSource('second.wav', 6)]
        with patch('ui.editor.read_waveform', side_effect=sources):
            with tempfile.TemporaryDirectory() as directory:
                paths = [Path(directory) / name for name in ('first.wav', 'second.wav')]
                for path in paths:
                    path.touch()
                with patch.object(self.editor, '_task', side_effect=lambda operation, work:
                                       self.editor.events.put((operation, work()))):
                    self.editor.import_files(paths)
                self.editor._poll()
        self.assertEqual([(c.lane, c.position) for c in self.editor.project.clips],
                         [(0, 0), (1, 0), (2, 0)])

    def test_explicit_drop_lane_keeps_requested_time_and_sequential_files(self):
        sources = [AudioSource('first.wav', 8), AudioSource('second.wav', 6)]
        with patch('ui.editor.read_waveform', side_effect=sources):
            with tempfile.TemporaryDirectory() as directory:
                paths = [Path(directory) / name for name in ('first.wav', 'second.wav')]
                for path in paths:
                    path.touch()
                with patch.object(self.editor, '_task', side_effect=lambda operation, work:
                                       self.editor.events.put((operation, work()))):
                    self.editor.import_files(paths, lane=3, position=5)
                self.editor._poll()
        self.assertEqual([(c.lane, c.position) for c in self.editor.project.clips], [(3, 5), (3, 13)])
