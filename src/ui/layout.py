import tkinter as tk
import re
import webbrowser
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
from app_identity import GITHUB_REPOSITORY_URL, AUTHOR_SUPPORT_URL

from .theme import COLORS, FONTS, SPACING, SIZES
from .widgets import ModernScale, RibbonTab, RoundedButton, RoundedMenuButton, SquareCheckbutton, ThemedMenu, ToolTip
from .editor import AudioEditor
from .help_content import PAGES
from .help_dialog import HelpDialog, HelpPanel


class SonicForgeView(ttk.Frame):
    METADATA_FIELDS = (
        ("title", "title_var", "tip_title"),
        ("artist", "artist_var", None),
        ("album", "album_var", None),
        ("album_artist", "album_artist_var", None),
        ("composer", "composer_var", None),
        ("date", "date_var", None),
        ("track", "track_var", None),
        ("genre", "genre_var", "tip_genre"),
        ("comment", "comment_var", None),
    )

    def __init__(self, parent, app, header_image):
        super().__init__(parent, padding=(SPACING["lg"], 0, SPACING["lg"], SPACING["md"]))
        self.app = app
        self.header_image = header_image
        self.localized = []
        self.cover_controls = []
        self.cover_generation_controls = []
        self.lyrics_controls = []
        self.tooltips = []
        self._summary_after = None
        self._help_window = None
        self.busy = False
        self.active_tab = "editor"
        self.tab_buttons = {}
        self.tab_pages = {}
        self.bind("<Destroy>", self._cancel_tab_transition, add="+")
        self._build()

    def _cancel_tab_transition(self, event=None):
        if event is not None and event.widget is not self:
            return
        for attribute in ("_summary_after",):
            after_id = getattr(self, attribute, None)
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
                except tk.TclError:
                    pass
                setattr(self, attribute, None)

    def _localize(self, widget, key):
        widget.configure(text=self.app.t(key))
        self.localized.append((widget, key))
        aliases = {"use_lyrics_for_cover_short": "use_lyrics_for_cover", "processing_start": "run",
                   "processing_stop": "stop", "show_splash": "show_splash"}
        tip_key = "tip_" + aliases.get(key, key)
        if self.app.t(tip_key) != tip_key:
            self._tip(widget, tip_key)
        return widget

    def _tip(self, widget, key):
        widget.help_key = key
        if not hasattr(widget, "_sonic_tip"):
            def title():
                value = self.app.t(widget.help_key.removeprefix('tip_'))
                if value == widget.help_key.removeprefix('tip_'):
                    try:
                        value = widget.cget('text')
                    except tk.TclError:
                        value = 'Подсказка' if self.app.language == 'ru' else 'Tip'
                return value
            widget._sonic_tip = ToolTip(widget, lambda: self.app.t(widget.help_key), title_provider=title)
            self.tooltips.append(widget._sonic_tip)
        return widget

    def _section(self, parent, key, row, column, **grid_options):
        frame = ttk.Labelframe(
            parent,
            text=self.app.t(key),
            style="Surface.TLabelframe",
            padding=SPACING["sm"],
        )
        self.localized.append((frame, key))
        frame.grid(row=row, column=column, **grid_options)
        return frame

    def _build(self):
        self.pack(fill=tk.BOTH, expand=True)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        self._build_tabs()

    def _build_paths(self, parent):
        frame = self._section(parent, "paths", 0, 0, sticky="nsew")
        frame.configure(padding=(SPACING['sm'], SPACING['xs']))
        self.paths_frame = frame
        frame.columnconfigure(1, weight=1)
        self._path_row(frame, 0, "source", self.app.source_var, "tip_source", True)
        self._path_row(frame, 1, "output", self.app.output_var, "tip_output", False)

    def _path_row(self, parent, row, key, variable, tip_key, source):
        label = self._localize(ttk.Label(parent, style="Surface.TLabel"), key)
        label.grid(row=row, column=0, sticky="w", padx=(0, SPACING["md"]), pady=SPACING["xs"])
        entry = ttk.Entry(parent, textvariable=variable)
        setattr(self, f"{key}_entry", entry)
        entry.grid(row=row, column=1, sticky="ew", pady=SPACING["xs"])
        self._tip(label, tip_key)
        self._tip(entry, tip_key)
        buttons = ttk.Frame(parent, style="Surface.TFrame")
        buttons.grid(row=row, column=2, sticky="e", padx=(SPACING["sm"], 0))
        if source:
            file_button = self._localize(
                RoundedButton(buttons, width=SIZES["button_width"], command=self.app.choose_source_file),
                "choose_file",
            )
            folder_button = self._localize(
                RoundedButton(buttons, width=SIZES["button_width"], command=self.app.choose_source_folder),
                "choose_folder",
            )
            file_button.grid(row=0, column=0, padx=(0, SPACING["sm"]))
            folder_button.grid(row=0, column=1)
        else:
            choose_button = self._localize(
                RoundedButton(buttons, width=SIZES["button_width"], command=self.app.choose_output_folder),
                "choose",
            )
            choose_button.grid(row=0, column=1)

    def _build_tabs(self):
        tabs = ttk.Frame(self)
        tabs.grid(row=3, column=0, sticky="nsew")
        tabs.columnconfigure(0, weight=1)
        tabs.rowconfigure(1, weight=1)

        tab_bar = ttk.Frame(tabs, style="TabBar.TFrame", height=SIZES["tab_height"])
        tab_bar.grid(row=0, column=0, sticky="ew")
        tab_bar.grid_propagate(False)
        tab_bar.rowconfigure(0, weight=1)
        self.tab_bar = tab_bar
        for column, (name, key) in enumerate(
            (
                ("editor", "tab_editor"),
                ("metadata", "tab_metadata"),
                ("audio", "tab_audio"),
                ("cover", "tab_cover"),
                ("lyrics", "tab_lyrics"),
                ("processing", "tab_processing"),
                ("help", "tab_help"),
                ("settings", "tab_settings"),
            )
        ):
            button = self._localize(
                RibbonTab(
                    tab_bar,
                    style="Tab.TButton",
                    command=lambda selected=name: self.show_tab(selected),
                ),
                key,
            )
            button.grid(row=0, column=column, sticky="nsew")
            self.tab_buttons[name] = button
        tab_bar.columnconfigure(len(self.tab_buttons), weight=1)

        # Independent, persistent layouts. Switching changes stacking order,
        # never the shared header height or the geometry of eight widget trees.
        layers = {}
        for name in ('editor', 'batch', 'help', 'settings'):
            layer = ttk.Frame(tabs, style="Surface.TFrame")
            layer.grid(row=1, column=0, sticky="nsew")
            layer.columnconfigure(0, weight=1)
            layer.rowconfigure(1 if name in ('editor', 'batch') else 0, weight=1)
            layers[name] = layer
        self.page_layers = {name: layers[name if name in layers else 'batch']
                            for name in self.tab_buttons}
        self._current_layer = None
        self.editor_context = ttk.Frame(layers['editor'], style="Surface.TFrame", padding=SPACING['md'])
        self.editor_context.grid(row=0, column=0, sticky='ew')
        self.editor_context.columnconfigure(0, weight=1)
        self.batch_context = ttk.Frame(layers['batch'], style="Surface.TFrame", padding=SPACING['md'])
        self.batch_context.grid(row=0, column=0, sticky='ew')
        self.batch_context.columnconfigure(0, weight=1)
        self.context_holder = self.editor_context
        self._build_paths(self.batch_context)
        self.editor_header = ttk.Frame(self.editor_context, style="Surface.TFrame")
        self.editor_header.grid(row=0, column=0, sticky="nsew")
        page_holder = ttk.Frame(layers['batch'], style="Surface.TFrame")
        page_holder.grid(row=1, column=0, sticky="nsew")
        page_holder.columnconfigure(0, weight=1)
        page_holder.rowconfigure(0, weight=1)
        for name in self.tab_buttons:
            parent = page_holder if name not in layers else layers[name]
            page = ttk.Frame(parent, style="Surface.TFrame", padding=SPACING["md"])
            page.grid(row=1 if name == 'editor' else 0, column=0, sticky="nsew")
            page.columnconfigure(0, weight=1)
            page.rowconfigure(0, weight=1)
            self.tab_pages[name] = page

        self.editor = AudioEditor(self.tab_pages["editor"], self.app, header_parent=self.editor_header)
        self.editor.grid(row=0, column=0, sticky="nsew")
        self._build_metadata(self.tab_pages["metadata"])
        self._build_audio(self.tab_pages["audio"])
        self._build_cover(self.tab_pages["cover"])
        self._build_lyrics(self.tab_pages["lyrics"])
        processing_page = self.tab_pages["processing"]
        processing_page.rowconfigure(0, weight=0)
        processing_page.rowconfigure(1, weight=1)
        self._build_processing(processing_page)
        self._build_log(processing_page)
        self._build_settings(self.tab_pages["settings"])
        self.help_panel = HelpPanel(self.tab_pages["help"], self.app, self._help_content)
        self.help_panel.grid(row=0, column=0, sticky="nsew")
        self.show_tab(self.active_tab)

    def _reserve_context_height(self):
        for holder, header in ((self.editor_context, self.editor_header),
                               (self.batch_context, self.paths_frame)):
            holder.rowconfigure(0, minsize=header.winfo_reqheight())

    def show_tab(self, name):
        if name not in self.tab_pages:
            return
        if name == self.active_tab and self._current_layer is not None:
            return
        previous = self.active_tab
        self.active_tab = name
        self.context_holder = self.editor_context if name == 'editor' else self.batch_context
        if previous in self.tab_buttons and previous != name:
            self.tab_buttons[previous].configure(style="Tab.TButton")
        self.tab_buttons[name].configure(style="Selected.Tab.TButton")
        if name == "help":
            topic = previous if previous in PAGES else self.help_panel.page
            self.help_panel.ensure_page(topic)
        self.tab_pages[name].tkraise()
        layer = self.page_layers[name]
        if layer is not self._current_layer:
            layer.tkraise()
            self._current_layer = layer

    def _build_settings(self, parent):
        frame = self._section(parent, "settings_title", 0, 0, sticky="nsew")
        frame.configure(padding=SPACING["lg"])
        frame.columnconfigure(1, weight=1)
        self._localize(ttk.Label(frame, style="SurfaceSecondary.TLabel"), "settings_description").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, SPACING["lg"]))
        label = self._localize(ttk.Label(frame, style="Surface.TLabel"), "interface_language")
        label.grid(row=1, column=0, sticky="w", padx=(0, SPACING["lg"]))
        self.interface_language_var = tk.StringVar(master=self, value="Русский" if self.app.language == "ru" else "English")
        self.interface_language_combo = ttk.Combobox(frame, textvariable=self.interface_language_var,
                                                   values=("Русский", "English"), state="readonly", width=20)
        self.interface_language_combo.grid(row=1, column=1, sticky="w")
        self.interface_language_combo.bind("<<ComboboxSelected>>", self._change_interface_language)
        self._tip(label, "tip_interface_language")
        self._tip(self.interface_language_combo, "tip_interface_language")
        self._localize(ttk.Label(frame, style="SurfaceSecondary.TLabel", wraplength=650, justify="left"),
                       "interface_language_hint").grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 20))
        self.splash_check = self._localize(
            SquareCheckbutton(frame, self.app.show_splash_var, command=self.app.update_splash_preference),
            "show_splash")
        self.splash_check.grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Separator(frame).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(24, 16))
        self._localize(ttk.Label(frame, style="Surface.TLabel", font=FONTS['section']),
                       'settings_about').grid(row=5, column=0, columnspan=2, sticky='w', pady=(0, 12))
        self.settings_link_buttons = {}
        self.settings_link_descriptions = {}
        for row, key, address, description in ((6, 'project_repository', GITHUB_REPOSITORY_URL, 'project_repository_description'),
                                               (7, 'author_support', AUTHOR_SUPPORT_URL, 'donation_notice')):
            link_row = ttk.Frame(frame, style='Surface.TFrame')
            link_row.grid(row=row, column=0, columnspan=2, sticky='ew', pady=(0, 10))
            link_row.columnconfigure(1, weight=1)
            button = self._localize(RoundedButton(link_row, width=22, command=lambda url=address: self._open_project_link(url)), key)
            button.grid(row=0, column=0, sticky='nw', padx=(0, 16))
            label = self._localize(
                ttk.Label(link_row, style='SurfaceSecondary.TLabel', wraplength=540, justify='left'),
                description)
            label.grid(row=0, column=1, sticky='w')
            self.settings_link_buttons[key] = button
            self.settings_link_descriptions[key] = label
        self.donation_notice = self.settings_link_descriptions['author_support']

    def _open_project_link(self, address):
        if address not in (GITHUB_REPOSITORY_URL, AUTHOR_SUPPORT_URL):
            return False
        try:
            opened = webbrowser.open_new_tab(address)
        except (webbrowser.Error, OSError):
            opened = False
        if not opened:
            messagebox.showerror(self.app.app_name(), self.app.t('link_open_failed'), parent=self.app)
        return opened

    def _change_interface_language(self, _event=None):
        language = {"Русский": "ru", "English": "en"}.get(self.interface_language_var.get())
        if language is not None and language != self.app.language:
            self.app.toggle_language()

    def _build_metadata(self, parent):
        frame = self._section(parent, "metadata", 0, 0, sticky="nsew")
        frame.configure(padding=(SPACING["sm"], SPACING["xs"]))
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        for index, (key, var_name, tip_key) in enumerate(self.METADATA_FIELDS):
            if key == "comment":
                column, pair_row, span = 0, 4, 2
            else:
                column, pair_row, span = index % 2, index // 2, 1
            base_row = pair_row * 2
            label = self._localize(ttk.Label(frame, style="SurfaceSecondary.TLabel"), key)
            label.grid(
                row=base_row,
                column=column,
                columnspan=span,
                sticky="w",
                padx=(0 if column == 0 else SPACING["sm"], SPACING["sm"] if column == 0 else 0),
            )
            entry = ttk.Entry(frame, textvariable=getattr(self.app, var_name))
            entry.grid(
                row=base_row + 1,
                column=column,
                columnspan=span,
                sticky="ew",
                padx=(0 if column == 0 else SPACING["sm"], SPACING["sm"] if column == 0 else 0),
                pady=(1, 2),
            )
            self._tip(label, tip_key or f"tip_{key}")
            self._tip(entry, tip_key or f"tip_{key}")
        checks = ttk.Frame(frame, style="Surface.TFrame")
        checks.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(SPACING["xs"], 0))
        self.overwrite_genre_check = self._localize(
            SquareCheckbutton(checks, self.app.overwrite_genre_var, fixed_width=230), "overwrite_genre"
        )
        self.overwrite_genre_check.pack(side=tk.LEFT, padx=(0, SPACING["lg"]))
        self._tip(self.overwrite_genre_check, "tip_overwrite_genre")
        self.overwrite_all_check = self._localize(
            SquareCheckbutton(checks, self.app.overwrite_all_metadata_var, fixed_width=230), "overwrite_all_metadata"
        )
        self.overwrite_all_check.pack(side=tk.LEFT)
        self._tip(self.overwrite_all_check, "tip_overwrite_all_metadata")
        self.metadata_actions = self._localize(
            RoundedMenuButton(checks, width=SIZES["button_width"]), "metadata_actions"
        )
        self.metadata_actions.pack(side=tk.RIGHT)
        self.metadata_menu = ThemedMenu(self.metadata_actions, tearoff=False)
        self.metadata_actions.configure(menu=self.metadata_menu)
        self._rebuild_metadata_menu()

    def _build_audio(self, parent):
        frame = self._section(parent, "audio", 0, 0, sticky="nsew")
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)

        profile_label = self._localize(ttk.Label(frame, style="SurfaceSecondary.TLabel"), "audio_profile")
        profile_label.grid(row=0, column=0, sticky="w", padx=(0, SPACING["sm"]))
        self.audio_profile_combo = ttk.Combobox(
            frame,
            textvariable=self.app.audio_profile_var,
            values=self.app.audio_profile_values(),
            state="readonly",
        )
        self.audio_profile_combo.grid(row=0, column=1, columnspan=2, sticky="ew")
        self.audio_profile_combo.bind("<<ComboboxSelected>>", lambda _event: self.app.audio_profile_changed())
        self._tip(profile_label, "tip_audio_profile")
        self._tip(self.audio_profile_combo, "tip_audio_profile")
        advanced = self._localize(
            RoundedButton(frame, command=self.app.show_advanced_audio), "advanced_audio"
        )
        advanced.grid(row=0, column=3, sticky="e", padx=(SPACING["md"], 0))

        intensity_label = self._localize(ttk.Label(frame, style="SurfaceSecondary.TLabel"), "audio_intensity")
        intensity_label.grid(row=1, column=0, sticky="w", pady=(SPACING["md"], 0))
        intensity = ModernScale(
            frame, from_=0, to=100, variable=self.app.audio_intensity_var,
            command=lambda value: self.app._apply_audio_macros(),
        )
        intensity.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(SPACING["md"], 0))
        self.intensity_value = tk.StringVar()
        intensity_label.configure(textvariable=self.intensity_value)
        self._tip(intensity_label, "tip_audio_intensity")
        self._tip(intensity, "tip_audio_intensity")

        macros = ttk.Frame(frame, style="Surface.TFrame")
        macros.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(SPACING["md"], 0))
        macros.columnconfigure(1, weight=1)
        macros.columnconfigure(4, weight=1)
        macro_fields = (
            ("audio_loudness", self.app.loudness_macro_var, "audio_quieter", "audio_louder"),
            ("audio_character", self.app.character_macro_var, "audio_softer", "audio_brighter"),
            ("audio_bass_macro", self.app.bass_macro_var, "audio_less", "audio_more"),
            ("audio_space", self.app.space_macro_var, "audio_narrower", "audio_wider"),
        )
        for index, (key, variable, left_key, right_key) in enumerate(macro_fields):
            column = 0 if index % 2 == 0 else 3
            row = (index // 2) * 2
            label = self._localize(ttk.Label(macros, style="Surface.TLabel"), key)
            label.grid(row=row, column=column, columnspan=2, sticky="w", pady=(0, 2))
            scale = ModernScale(
                macros,
                from_=-100,
                to=100,
                variable=variable,
                command=self.app.audio_macro_changed,
                height=38,
                show_value=True,
                value_formatter=lambda value: f"{value:+.0f}%",
            )
            scale.grid(row=row + 1, column=column + 1, sticky="ew", padx=SPACING["xs"])
            self._tip(scale, f"tip_{key}")
            left = self._localize(ttk.Label(macros, style="SurfaceSecondary.TLabel"), left_key)
            right = self._localize(ttk.Label(macros, style="SurfaceSecondary.TLabel"), right_key)
            left.grid(row=row + 1, column=column, sticky="w")
            right.grid(row=row + 1, column=column + 2, sticky="e", padx=(SPACING["xs"], SPACING["md"] if column == 0 else 0))

        checks = ttk.Frame(frame, style="Surface.TFrame")
        checks.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(SPACING["md"], 0))
        self.auto_denoise_check = self._localize(
            SquareCheckbutton(
                checks,
                self.app.auto_denoise_var,
                command=self.app.auto_denoise_changed,
                fixed_width=260,
            ),
            "audio_auto_denoise",
        )
        self.auto_denoise_check.pack(side=tk.LEFT)
        self.limiter_check = self._localize(
            SquareCheckbutton(checks, self.app.limiter_var, fixed_width=210), "audio_peak_protection"
        )
        self.limiter_check.pack(side=tk.LEFT, padx=(SPACING["md"], 0))

        actions = ttk.Frame(frame, style="Surface.TFrame")
        actions.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(SPACING["md"], 0))
        for column in range(3):
            actions.columnconfigure(column, weight=1, uniform="audio_actions")
        self.audio_analyze_button = self._localize(
            RoundedButton(actions, text="", command=self.app.analyze_audio_settings), "audio_analyze"
        )
        self.audio_apply_button = self._localize(
            RoundedButton(actions, text="", command=self.app.apply_audio_recommendation),
            "audio_apply_recommendation",
        )
        self.audio_preview_button = self._localize(
            RoundedButton(actions, text="", command=self.app.create_audio_preview, primary=True), "audio_preview"
        )
        self.audio_original_button = self._localize(
            RoundedButton(actions, text="", command=lambda: self.app.play_audio_preview(False)), "audio_original"
        )
        self.audio_processed_button = self._localize(
            RoundedButton(actions, text="", command=lambda: self.app.play_audio_preview(True)), "audio_processed"
        )
        self.audio_stop_button = self._localize(
            RoundedButton(actions, text="", command=self.app.stop_audio_preview), "audio_stop"
        )
        for column, button in enumerate(
            (self.audio_analyze_button, self.audio_apply_button, self.audio_preview_button)
        ):
            button.grid(row=0, column=column, sticky="ew", padx=(0, SPACING["sm"] if column < 2 else 0))
        for column, button in enumerate(
            (self.audio_original_button, self.audio_processed_button, self.audio_stop_button)
        ):
            button.grid(row=1, column=column, sticky="ew", padx=(0, SPACING["sm"] if column < 2 else 0), pady=(SPACING["xs"], 0))
        for button in (self.audio_apply_button, self.audio_original_button, self.audio_processed_button, self.audio_stop_button):
            button.configure(state="disabled")

        analysis = ttk.Label(
            frame, textvariable=self.app.audio_analysis_var, style="SurfaceSecondary.TLabel",
            wraplength=760, justify=tk.LEFT,
        )
        analysis.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(SPACING["md"], 0))
        warning = ttk.Label(
            frame, textvariable=self.app.audio_warning_var, style="SurfaceSecondary.TLabel",
            foreground=COLORS["danger"], wraplength=760, justify=tk.LEFT,
        )
        warning.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(SPACING["xs"], 0))
        summary = self._section(frame, "audio_changes", 4, 0, columnspan=4, sticky="ew", pady=(10, 0))
        self.audio_summary = tk.StringVar()
        ttk.Label(summary, textvariable=self.audio_summary, style="Surface.TLabel", wraplength=780,
                  justify=tk.LEFT, font=FONTS["body"]).pack(fill=tk.X)
        self.audio_detail = tk.StringVar()
        ttk.Label(summary, textvariable=self.audio_detail, style="SurfaceSecondary.TLabel", wraplength=780,
                  justify=tk.LEFT).pack(fill=tk.X, pady=(5, 0))
        for name in ("integrated_lufs", "true_peak", "lra", "final_gain", "bass_gain", "mid_gain", "treble_gain",
                     "stereo_width", "compressor", "compressor_ratio", "compressor_threshold", "compressor_attack",
                     "compressor_release", "compressor_makeup", "denoise_mode", "denoise_strength", "limiter",
                     "highpass_enabled", "lowpass_enabled", "highpass_hz", "lowpass_hz", "pitch_semitones",
                     "playback_speed", "reverb_mix", "fade_in", "fade_out", "audio_intensity", "sample_rate", "channels", "mp3_quality"):
            getattr(self.app, name + "_var").trace_add("write", lambda *_: self.schedule_audio_summary())
        self.schedule_audio_summary()

    def schedule_audio_summary(self):
        if self._summary_after is None:
            self._summary_after = self.after_idle(self._update_audio_summary)

    def _update_audio_summary(self):
        self._summary_after = None
        app = self.app
        try:
            number = lambda name: float(getattr(app, name + "_var").get())
            self.intensity_value.set(app.t("audio_intensity_value").format(value=number("audio_intensity")))
            self.audio_summary.set(app.t("audio_summary").format(
                lufs=number("integrated_lufs"), bass=number("bass_gain"), treble=number("treble_gain"),
                width=number("stereo_width"), peak=number("true_peak"), mid=number("mid_gain"), gain=number("final_gain")))
            ru = app.language == "ru"
            values = []
            if app.auto_denoise_var.get():
                values.append("Автоочистка шума" if ru else "Automatic noise cleanup")
            elif app.denoise_var.get():
                values.append(f"{app.t('denoise')}: {number('denoise_strength'):g} dB")
            if app.limiter_var.get():
                values.append("Защита от перегрузки" if ru else "Peak protection")
            if app.compressor_var.get():
                values.append(
                    f"{app.t('compressor')}: {number('compressor_threshold'):g} dB / "
                    f"{number('compressor_ratio'):g}:1"
                )
            if number("lra") != 11:
                values.append(f"{app.t('lra')}: {number('lra'):g}")
            for enabled, name, label in (("highpass_enabled", "highpass_hz", "Срез снизу" if ru else "Low cut"),
                                         ("lowpass_enabled", "lowpass_hz", "Срез сверху" if ru else "High cut")):
                if getattr(app, enabled + "_var").get():
                    values.append(f"{label}: {number(name):g} Hz")
            for name in ("pitch_semitones", "playback_speed", "reverb_mix", "fade_in", "fade_out"):
                value = number(name)
                if value != (1 if name == "playback_speed" else 0):
                    values.append(f"{app.t(name)}: {value:g}")
            self.audio_detail.set(" • ".join(values) or (
                "Дополнительные эффекты выключены" if ru else "Additional effects are off"
            ))
        except (ValueError, tk.TclError):
            self.audio_detail.set("Введите числовое значение." if app.language == "ru" else "Enter a numeric value.")

    def show_help(self, page_name=None):
        page = page_name or self.active_tab
        if page == "help":
            page = self.help_panel.page
        if self._help_window and self._help_window.winfo_exists():
            self._help_window.close()
        focus = self.app.focus_get()
        key = getattr(focus, "help_key", None)
        self._help_window = HelpDialog(self.app, page, self._help_content, self.app.t(key) if key else None)

    def _help_content(self, page):
        parameters = []
        if page == "editor":
            from .editor import TEXT
            for key, value in TEXT[self.app.language].items():
                if key.endswith("_tip") or key == "preview":
                    title = TEXT[self.app.language].get(key[:-4], key)
                    if key == "preview":
                        title = TEXT[self.app.language]["play"]
                    parameters.append((title, value))
        else:
            seen = set()
            def explain(widget):
                key = getattr(widget, "help_key", None)
                if key and key not in seen:
                    seen.add(key)
                    label_key = key.removeprefix("tip_")
                    label = self.app.t(label_key)
                    if label == label_key:
                        try:
                            label = widget.cget("text") or label
                        except tk.TclError:
                            pass
                    parameters.append((label, self.app.t(key)))
                for child in widget.winfo_children():
                    explain(child)
            explain(self.tab_pages[page])
            if page != "settings":
                explain(self.paths_frame)
            if page == "audio":
                for key in ("integrated_lufs", "true_peak", "lra", "final_gain", "bass_gain", "mid_gain", "treble_gain",
                            "stereo_width", "highpass_hz", "lowpass_hz", "denoise_strength", "compressor_threshold",
                            "compressor_ratio", "compressor_attack", "compressor_release", "compressor_makeup",
                            "pitch_semitones", "playback_speed", "reverb_mix", "fade_in", "fade_out",
                            "sample_rate", "channel_layout", "mp3_quality"):
                    if "tip_" + key not in seen:
                        parameters.append((self.app.t(key), self.app.t("tip_" + key)))
        return PAGES[page][0 if self.app.language == "ru" else 1], parameters

    def _build_cover(self, parent):
        header = ttk.Frame(parent, style="Surface.TFrame")
        self._localize(ttk.Label(header, style="Surface.TLabel", font=FONTS["section"]), "cover").pack(side=tk.LEFT, padx=(0, SPACING["lg"]))
        self.no_change_cover_check = self._localize(
            SquareCheckbutton(header, self.app.no_change_cover_var, command=self.update_dependencies, fixed_width=190),
            "no_change_cover",
        )
        self.no_change_cover_check.pack(side=tk.LEFT)
        self._tip(self.no_change_cover_check, "tip_no_change_cover")
        frame = ttk.Labelframe(parent, labelwidget=header, style="Surface.TLabelframe", padding=SPACING["sm"])
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=0)
        frame.rowconfigure(0, weight=1)

        controls = ttk.Frame(frame, style="Surface.TFrame")
        controls.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["lg"]))
        controls.columnconfigure(1, weight=1)
        style_label = self._localize(
            ttk.Label(controls, style="SurfaceSecondary.TLabel"), "cover_style"
        )
        style_label.grid(row=0, column=0, sticky="w", padx=(0, SPACING["sm"]), pady=SPACING["xs"])
        self.cover_style_combo = ttk.Combobox(
            controls, textvariable=self.app.cover_style_var,
            values=self.app.cover_choice_values("style"), state="readonly",
        )
        self.cover_style_combo.grid(row=0, column=1, sticky="ew", pady=SPACING["xs"])
        self.cover_controls.extend((style_label, self.cover_style_combo))
        self.cover_generation_controls.extend((style_label, self.cover_style_combo))
        self._tip(style_label, "tip_cover_style")
        self._tip(self.cover_style_combo, "tip_cover_style")

        fields = (
            ("seed", self.app.seed_var, None, "tip_seed"),
            ("cover_size", self.app.cover_size_var, "size", "tip_cover_size"),
        )
        for row, (key, variable, values, tip_key) in enumerate(fields, start=1):
            label = self._localize(ttk.Label(controls, style="SurfaceSecondary.TLabel"), key)
            label.grid(row=row, column=0, sticky="w", padx=(0, SPACING["sm"]), pady=SPACING["xs"])
            if isinstance(values, tuple):
                control = ttk.Combobox(controls, textvariable=variable, values=values, state="readonly")
            elif values == "size":
                control = ttk.Spinbox(controls, textvariable=variable, from_=512, to=2048, increment=256)
            else:
                control = ttk.Entry(controls, textvariable=variable)
            control.grid(row=row, column=1, sticky="ew", pady=SPACING["xs"])
            self.cover_controls.extend((label, control))
            if key == "seed":
                self.cover_generation_controls.extend((label, control))
            self._tip(label, tip_key)
            self._tip(control, tip_key)

        options = ttk.Frame(controls, style="Surface.TFrame")
        options.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(SPACING["sm"], 0))
        self.use_lyrics_check = self._localize(
            SquareCheckbutton(options, self.app.use_lyrics_for_cover_var, fixed_width=175),
            "use_lyrics_for_cover_short",
        )
        self.cover_title_check = self._localize(
            SquareCheckbutton(options, self.app.cover_title_var, fixed_width=145),
            "cover_show_title",
        )
        self.cover_artist_check = self._localize(
            SquareCheckbutton(options, self.app.cover_artist_var, fixed_width=145),
            "cover_show_artist",
        )
        self.use_lyrics_check.grid(row=0, column=0, sticky="w", padx=(0, SPACING["md"]))
        self.cover_title_check.grid(row=0, column=1, sticky="w")
        self.cover_artist_check.grid(row=1, column=0, sticky="w", pady=(SPACING["xs"], 0))
        self.embed_cover_check = self._localize(
            SquareCheckbutton(options, self.app.embed_cover_var, fixed_width=145), "embed_cover_short"
        )
        self.embed_cover_check.grid(row=1, column=1, sticky="w", pady=(SPACING["xs"], 0))
        self.cover_controls.extend(
            (self.use_lyrics_check, self.cover_title_check, self.cover_artist_check, self.embed_cover_check)
        )
        self.cover_generation_controls.extend(
            (self.use_lyrics_check, self.cover_title_check, self.cover_artist_check)
        )
        self._tip(self.use_lyrics_check, "tip_use_lyrics_for_cover")

        preview = ttk.Frame(frame, style="Surface.TFrame")
        preview.grid(row=0, column=1, sticky="n")
        preview_box = tk.Frame(
            preview,
            width=220,
            height=220,
            bg=COLORS["field"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
        )
        preview_box.pack_propagate(False)
        preview_box.pack()
        self.cover_preview_image = self._localize(
            tk.Label(
                preview_box,
                bg=COLORS["field"],
                fg=COLORS["secondary"],
                anchor="center",
                justify=tk.CENTER,
                wraplength=190,
                font=FONTS["small"],
            ),
            "cover_preview_empty",
        )
        self.cover_preview_image.pack(fill=tk.BOTH, expand=True)
        preview_actions = ttk.Frame(preview, style="Surface.TFrame")
        preview_actions.pack(fill=tk.X, pady=(SPACING["sm"], 0))
        self.cover_preview_button = self._localize(
            RoundedButton(preview_actions, style="Primary.TButton", command=self.app.preview_cover),
            "cover_preview",
        )
        self.cover_preview_button.pack(fill=tk.X)
        self.cover_controls.append(self.cover_preview_button)
        self.cover_custom_status = ttk.Label(
            preview,
            style="SurfaceSecondary.TLabel",
            justify=tk.CENTER,
            anchor="center",
            wraplength=220,
        )
        self.cover_custom_status.pack(fill=tk.X, pady=(SPACING["sm"], SPACING["xs"]))
        self.cover_custom_button = self._localize(
            RoundedButton(preview, command=self.app.choose_custom_cover), "cover_choose_custom"
        )
        self.cover_custom_button.pack(fill=tk.X)
        self.cover_generated_button = self._localize(
            RoundedButton(preview, command=self.app.clear_custom_cover), "cover_use_generated"
        )
        self.cover_generated_button.pack(fill=tk.X)
        self.cover_controls.extend((self.cover_custom_button, self.cover_generated_button))
        self._tip(self.cover_custom_button, "tip_cover_choose_custom")
        self.update_cover_source()

    def _build_lyrics(self, parent):
        frame = self._section(parent, "lyrics_workspace", 0, 0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(4, weight=1)

        toolbar = ttk.Frame(frame, style="Surface.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, SPACING["sm"]))
        self.load_lyrics_button = self._localize(
            RoundedButton(toolbar, command=self.app.load_existing_lyrics), "lyrics_load"
        )
        self.recognize_lyrics_button = self._localize(
            RoundedButton(toolbar, style="Primary.TButton", command=self.app.recognize_lyrics),
            "lyrics_recognize",
        )
        self.save_lyrics_button = self._localize(
            RoundedButton(toolbar, command=self.app.save_lyrics_file), "lyrics_save"
        )
        self.load_lyrics_button.pack(side=tk.LEFT, padx=(0, SPACING["sm"]))
        self.recognize_lyrics_button.pack(side=tk.LEFT, padx=(0, SPACING["sm"]))
        self.save_lyrics_button.pack(side=tk.LEFT)

        options = ttk.Frame(frame, style="Surface.TFrame")
        options.grid(row=1, column=0, sticky="ew", pady=(0, SPACING["sm"]))
        format_label = self._localize(
            ttk.Label(options, style="SurfaceSecondary.TLabel"), "lyrics_format"
        )
        format_label.pack(side=tk.LEFT, padx=(0, SPACING["sm"]))
        self.lyrics_format = ttk.Combobox(
            options,
            textvariable=self.app.lyrics_format_var,
            values=self.app.lyrics_format_values(),
            state="readonly",
            width=25,
        )
        self.lyrics_format.pack(side=tk.LEFT)
        language_label = self._localize(
            ttk.Label(options, style="SurfaceSecondary.TLabel"), "lyrics_language"
        )
        language_label.pack(side=tk.LEFT, padx=(SPACING["md"], SPACING["sm"]))
        self.lyrics_language = ttk.Combobox(
            options,
            textvariable=self.app.lyrics_language_var,
            values=self.app.lyrics_language_values(),
            state="readonly",
            width=24,
        )
        self.lyrics_language.pack(side=tk.LEFT)
        extra_options = ttk.Frame(frame, style="Surface.TFrame")
        extra_options.grid(row=2, column=0, sticky="ew", pady=(0, SPACING["sm"]))
        self.overwrite_lyrics_check = self._localize(
            SquareCheckbutton(extra_options, self.app.overwrite_lyrics_var, fixed_width=170),
            "overwrite_lyrics",
        )
        self.overwrite_lyrics_check.pack(side=tk.LEFT, padx=(0, SPACING["sm"]))
        self.use_lyrics_check = self._localize(
            SquareCheckbutton(
                extra_options,
                self.app.use_lyrics_for_cover_var,
                fixed_width=175,
            ),
            "use_lyrics_for_cover_short",
        )
        self.use_lyrics_check.pack(side=tk.LEFT)
        self._tip(self.load_lyrics_button, "tip_lyrics_load")
        self._tip(self.save_lyrics_button, "tip_lyrics_save")
        self._tip(self.recognize_lyrics_button, "tip_lyrics_recognize")
        self._tip(self.lyrics_format, "tip_lyrics_format")
        self._tip(self.lyrics_language, "tip_lyrics_language")
        self._tip(self.use_lyrics_check, "tip_use_lyrics_for_cover")

        status = ttk.Label(
            frame,
            textvariable=self.app.lyrics_status_var,
            style="SurfaceSecondary.TLabel",
            anchor="w",
        )
        status.grid(row=3, column=0, sticky="ew", pady=(0, SPACING["sm"]))

        editor_wrap = tk.Frame(
            frame,
            bg=COLORS["field"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
        )
        editor_wrap.grid(row=4, column=0, sticky="nsew")
        editor_wrap.columnconfigure(0, weight=1)
        editor_wrap.rowconfigure(0, weight=1)
        self.lyrics_editor = tk.Text(
            editor_wrap,
            height=11,
            wrap="word",
            undo=True,
            bg=COLORS["field"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            selectbackground=COLORS["accent"],
            selectforeground=COLORS["white"],
            inactiveselectbackground=COLORS["accent_hover"],
            exportselection=False,
            selectborderwidth=0,
            insertwidth=2,
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=10,
            font=FONTS["body"],
        )
        scrollbar = ttk.Scrollbar(editor_wrap, orient="vertical", command=self.lyrics_editor.yview)
        self.lyrics_editor.configure(yscrollcommand=scrollbar.set)
        self.lyrics_editor.grid(row=0, column=0, sticky="nsew")
        self.lyrics_editor.bind("<Double-Button-1>", self._select_lyrics_word)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.lyrics_controls = [
            self.load_lyrics_button,
            self.recognize_lyrics_button,
            self.save_lyrics_button,
            self.lyrics_format,
            self.lyrics_language,
            self.overwrite_lyrics_check,
        ]

    def _select_lyrics_word(self, event):
        """Select a whole Unicode lyric word, including apostrophe compounds."""
        widget = self.lyrics_editor
        index = widget.index(f"@{event.x},{event.y}")
        try:
            offset = int(widget.count("1.0", index, "chars")[0])
        except (tk.TclError, TypeError):
            return None
        text = widget.get("1.0", "end-1c")
        for match in re.finditer(r"[^\W_]+(?:['’‑-][^\W_]+)*", text, re.UNICODE):
            if match.start() <= offset <= match.end():
                widget.tag_remove(tk.SEL, "1.0", tk.END)
                widget.tag_add(tk.SEL, f"1.0+{match.start()}c", f"1.0+{match.end()}c")
                widget.mark_set(tk.INSERT, f"1.0+{match.end()}c")
                widget.see(tk.INSERT)
                return "break"
        return None

    def _build_processing(self, parent):
        frame = self._section(parent, "processing", 0, 0, sticky="ew", pady=(0, SPACING["md"]))
        frame.columnconfigure(1, weight=1)
        stages = ttk.Frame(frame, style="Surface.TFrame")
        stages.grid(row=0, column=0, columnspan=3, sticky="w")
        stage_label = self._localize(ttk.Label(stages, style="SurfaceSecondary.TLabel"), "stages")
        stage_label.pack(side=tk.LEFT, padx=(0, SPACING["md"]))
        for key, variable in (
            ("stage_audio", self.app.process_audio_var),
            ("stage_metadata", self.app.process_metadata_var),
            ("stage_lyrics", self.app.process_lyrics_var),
            ("stage_cover", self.app.process_cover_var),
        ):
            check = self._localize(
                SquareCheckbutton(stages, variable, fixed_width=105), key
            )
            check.pack(side=tk.LEFT, padx=(0, SPACING["md"]))
            self._tip(check, "tip_" + key)
        actions = ttk.Frame(frame, style="Surface.TFrame")
        actions.grid(row=1, column=2, sticky="e", pady=(SPACING["sm"], 0))
        self.run_button = self._localize(
            RoundedButton(
                actions,
                style="Primary.TButton",
                width=SIZES["primary_width"],
                command=self.app.run_selected_steps,
            ),
            "run",
        )
        self.run_button.pack(side=tk.LEFT, padx=(0, SPACING["sm"]))
        self.stop_button = self._localize(
            RoundedButton(
                actions,
                style="Danger.TButton",
                width=SIZES["button_width"],
                command=self.app.stop_processing,
                state=tk.DISABLED,
            ),
            "stop",
        )
        self.stop_button.pack(side=tk.LEFT)
        self._tip(self.run_button, "tip_run")
        self._tip(self.stop_button, "tip_stop")
        self.progress = ttk.Progressbar(frame, mode="indeterminate", style="Thin.Horizontal.TProgressbar")
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(0, SPACING["lg"]), pady=(SPACING["sm"], 0))
        self.lyrics_execution_frame = self._section(frame, "lyrics_execution", 2, 0, columnspan=3,
                                                    sticky="ew", pady=(SPACING["sm"], 0))
        self.lyrics_execution_frame.columnconfigure(0, weight=1)
        self.lyrics_execution_status = tk.StringVar()
        ttk.Label(self.lyrics_execution_frame, textvariable=self.lyrics_execution_status,
                  style="SurfaceSecondary.TLabel", wraplength=650).grid(row=0, column=0, sticky="ew")
        self.lyrics_execution_progress = ttk.Progressbar(
            self.lyrics_execution_frame, mode="determinate", style="Thin.Horizontal.TProgressbar")
        self.lyrics_execution_progress.grid(row=1, column=0, sticky="ew", pady=(SPACING["xs"], 0))
        self.reset_lyrics_execution(self.app.process_lyrics_var.get())

    def reset_lyrics_execution(self, enabled):
        self.lyrics_execution_stage = "waiting" if enabled else "disabled"
        self.lyrics_execution_data = {}
        self.lyrics_execution_progress.stop()
        self.lyrics_execution_progress.configure(mode="determinate", maximum=100, value=0)
        self._refresh_lyrics_execution()

    def update_lyrics_execution(self, stage, data):
        self.lyrics_execution_stage = stage
        self.lyrics_execution_data = dict(data)
        total = max(1, int(data.get("total", 1)))
        index = int(data.get("index", 1))
        self.lyrics_execution_progress.stop()
        self.lyrics_execution_progress.configure(mode="determinate", maximum=total * 100)
        if stage == "completed":
            self.lyrics_execution_progress.configure(value=total * 100)
        elif stage in {"saved", "preserved", "uncertain", "failed"}:
            self.lyrics_execution_progress.configure(value=index * 100)
        elif data.get("duration") and data.get("audio_end") is not None:
            fraction = max(0.0, min(.99, data["audio_end"] / data["duration"]))
            self.lyrics_execution_progress.configure(value=(index - 1 + fraction) * 100)
        elif stage not in {"started", "cancelled"}:
            self.lyrics_execution_progress.configure(mode="indeterminate")
            self.lyrics_execution_progress.start(15)
        self._refresh_lyrics_execution()

    def finish_lyrics_execution(self, outcome):
        if self.lyrics_execution_stage in {"disabled", "completed"}:
            return
        self.lyrics_execution_progress.stop()
        self.lyrics_execution_stage = "cancelled" if outcome == "run_stopped" else "error"
        self._refresh_lyrics_execution()

    def _refresh_lyrics_execution(self):
        stage = self.lyrics_execution_stage
        keys = {"started": "waiting", "file_started": "preparing"}
        key = "lyrics_batch_" + keys.get(stage, stage)
        values = dict(total=0, index=0, file="", saved=0, preserved=0, uncertain=0, failed=0)
        values.update(self.lyrics_execution_data)
        filename = values.get("file", "")
        values["file"] = filename if len(filename) <= 48 else filename[:45] + "..."
        self.lyrics_execution_status.set(self.app.t(key).format(**values))

    def _build_log(self, parent):
        frame = self._section(parent, "log", 1, 0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        actions = ttk.Frame(frame, style="Surface.TFrame")
        actions.grid(row=0, column=0, sticky="e", pady=(0, SPACING["sm"]))
        self.copy_log_button = self._localize(
            RoundedButton(actions, command=self.app.copy_log), "copy_log"
        )
        self.clear_log_button = self._localize(
            RoundedButton(actions, command=self.app.clear_log), "clear_log"
        )
        self.copy_log_button.pack(side=tk.LEFT, padx=(0, SPACING["sm"]))
        self.clear_log_button.pack(side=tk.LEFT)
        log_wrap = tk.Frame(
            frame,
            bg=COLORS["log"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
        )
        log_wrap.grid(row=1, column=0, sticky="nsew")
        log_wrap.columnconfigure(0, weight=1)
        log_wrap.rowconfigure(0, weight=1)
        self.log = tk.Text(
            log_wrap,
            height=6,
            wrap="word",
            undo=True,
            bg=COLORS["log"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            selectbackground=COLORS["accent_pressed"],
            selectforeground=COLORS["white"],
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=10,
            font=FONTS["mono"],
            state=tk.DISABLED,
        )
        scrollbar = ttk.Scrollbar(log_wrap, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_menu = ThemedMenu(self.log, tearoff=False)
        self.log_menu.add_command(label=self.app.t("copy"), command=self.app.copy_log_selection)
        self.log_menu.add_command(label=self.app.t("select_all"), command=self.app.select_all_log)
        self.log.bind("<Button-3>", self._show_log_menu)

    def update_dependencies(self):
        cover_enabled = not self.app.no_change_cover_var.get()
        state = "normal" if cover_enabled else "disabled"
        for control in self.cover_controls:
            if isinstance(control, SquareCheckbutton):
                control.configure(state=state)
            elif isinstance(control, ttk.Label):
                control.configure(foreground=COLORS["secondary"] if cover_enabled else COLORS["disabled"])
            elif isinstance(control, ttk.Combobox):
                control.configure(state="readonly" if cover_enabled else "disabled")
            else:
                control.configure(state=state)
        self.update_cover_source()
        self.update_engine_dependencies()

    def update_cover_source(self):
        if not hasattr(self, "cover_custom_status"):
            return
        custom = self.app.custom_cover_path_var.get().strip()
        if custom:
            from pathlib import Path

            self.cover_custom_status.configure(
                text=self.app.t("cover_custom_selected").format(name=Path(custom).name)
            )
            self.cover_custom_button.pack_forget()
            if not self.cover_generated_button.winfo_manager():
                self.cover_generated_button.pack(fill=tk.X)
        else:
            self.cover_custom_status.configure(text=self.app.t("cover_custom_empty"))
            self.cover_generated_button.pack_forget()
            if not self.cover_custom_button.winfo_manager():
                self.cover_custom_button.pack(fill=tk.X)
        source_controls_state = (
            "normal" if not self.busy and not self.app.no_change_cover_var.get() else "disabled"
        )
        self.cover_custom_button.configure(state=source_controls_state)
        self.cover_generated_button.configure(state=source_controls_state)
        generated = not custom and not self.app.no_change_cover_var.get() and not self.busy
        for control in self.cover_generation_controls:
            if isinstance(control, SquareCheckbutton):
                control.configure(state="normal" if generated else "disabled")
            elif isinstance(control, ttk.Label):
                control.configure(foreground=COLORS["secondary"] if generated else COLORS["disabled"])
            elif isinstance(control, ttk.Combobox):
                control.configure(state="readonly" if generated else "disabled")
            else:
                control.configure(state="normal" if generated else "disabled")

    def apply_language(self):
        for widget, key in self.localized:
            widget.configure(text=self.app.t(key))
        self._rebuild_metadata_menu()
        self.update_dependencies()
        self.cover_style_combo.configure(values=self.app.cover_choice_values("style"))
        self.update_cover_source()
        self.lyrics_language.configure(values=self.app.lyrics_language_values())
        self.audio_profile_combo.configure(values=self.app.audio_profile_values())
        self.log_menu.entryconfigure(0, label=self.app.t("copy"))
        self.log_menu.entryconfigure(1, label=self.app.t("select_all"))
        self._refresh_lyrics_execution()
        self.editor.apply_language()
        self.interface_language_var.set("Русский" if self.app.language == "ru" else "English")
        self.help_panel.refresh_language()
        if self.busy:
            self.run_button.configure(text=self.app.t("processing_busy"))

    def get_lyrics_text(self):
        return self.lyrics_editor.get("1.0", tk.END).strip()

    def set_lyrics_text(self, text):
        state = self.lyrics_editor.cget("state")
        self.lyrics_editor.configure(state=tk.NORMAL)
        self.lyrics_editor.delete("1.0", tk.END)
        self.lyrics_editor.insert("1.0", text)
        self.lyrics_editor.configure(state=state)

    def append_lyrics_line(self, text):
        state = self.lyrics_editor.cget("state")
        self.lyrics_editor.configure(state=tk.NORMAL)
        if self.lyrics_editor.get("1.0", "end-1c"):
            self.lyrics_editor.insert(tk.END, "\n")
        self.lyrics_editor.insert(tk.END, text)
        self.lyrics_editor.see(tk.END)
        self.lyrics_editor.configure(state=state)

    def set_lyrics_busy(self, busy):
        self.lyrics_editor.configure(state=tk.DISABLED if busy else tk.NORMAL)
        state = tk.DISABLED if busy else tk.NORMAL
        self.load_lyrics_button.configure(state=state)
        self.recognize_lyrics_button.configure(state=state)
        self.save_lyrics_button.configure(state=state)
        self.lyrics_format.configure(state="disabled" if busy else "readonly")
        self.lyrics_language.configure(state="disabled" if busy else "readonly")
        self.overwrite_lyrics_check.configure(state=state)

    def reset_cover_preview(self):
        self._cover_preview_photo = None
        self.cover_preview_image.configure(image="", text=self.app.t("cover_preview_empty"))

    def show_cover_preview(self, path):
        with Image.open(path) as source:
            try:
                source.draft("RGB", (440, 440))
            except (AttributeError, OSError):
                pass
            source.thumbnail((220, 220), Image.Resampling.LANCZOS)
            image = source.convert("RGB")
        self._cover_preview_photo = ImageTk.PhotoImage(image)
        self.cover_preview_image.configure(image=self._cover_preview_photo, text="")

    def set_cover_preview_busy(self, busy):
        state = tk.DISABLED if busy else tk.NORMAL
        self.cover_preview_button.configure(state=state)
        self.cover_custom_button.configure(state=state)
        self.cover_generated_button.configure(state=state)
        if busy:
            self._cover_preview_photo = None
            self.cover_preview_image.configure(image="", text=self.app.t("cover_preview_working"))
        elif not busy and self.cover_preview_image.cget("text") == self.app.t("cover_preview_working"):
            self.cover_preview_image.configure(text=self.app.t("cover_preview_empty"))
        self.update_cover_source()

    def set_audio_preview_ready(self, ready):
        state = tk.NORMAL if ready else tk.DISABLED
        self.audio_original_button.configure(state=state)
        self.audio_processed_button.configure(state=state)
        self.audio_stop_button.configure(state=state)

    def set_audio_recommendation_ready(self, ready):
        self.audio_apply_button.configure(state=tk.NORMAL if ready else tk.DISABLED)

    def set_audio_task_busy(self, busy):
        state = tk.DISABLED if busy else tk.NORMAL
        self.audio_analyze_button.configure(state=state)
        self.audio_preview_button.configure(state=state)

    def update_engine_dependencies(self):
        self.cover_preview_button.configure(state=tk.DISABLED if self.busy else tk.NORMAL)
        self.cover_style_combo.configure(
            state="readonly" if not self.busy and not self.app.no_change_cover_var.get()
            and not self.app.custom_cover_path_var.get().strip()
            else "disabled"
        )
        self.update_cover_source()

    def _show_log_menu(self, event):
        self.log.focus_set()
        try:
            self.log_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.log_menu.grab_release()

    def _rebuild_metadata_menu(self):
        self.metadata_menu.delete(0, tk.END)
        self.metadata_menu.add_command(
            label=self.app.t("read_metadata"), command=self.app.load_metadata
        )
        self.metadata_menu.add_command(
            label=self.app.t("additional_metadata"),
            command=self.app.show_additional_metadata,
        )
        self.metadata_menu.add_separator()
        self.metadata_menu.add_command(
            label=self.app.t("clear_metadata"), command=self.app.clear_metadata
        )

    def set_busy(self, busy):
        self.busy = busy
        self.run_button.configure(
            state=tk.DISABLED if busy else tk.NORMAL,
            text=self.app.t("processing_busy") if busy else self.app.t("run"),
        )
        state = tk.DISABLED if busy else tk.NORMAL
        self.update_engine_dependencies()
        self.stop_button.configure(state=tk.NORMAL if busy else tk.DISABLED)
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()
