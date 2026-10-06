import tkinter as tk
from tkinter import ttk

from .theme import COLORS, SPACING, SIZES
from .widgets import RoundedButton, SquareCheckbutton, ToolTip
from .windowing import show_centered


class CenteredDialog(tk.Toplevel):
    def show(self):
        self.centering = show_centered(self, *self._dialog_size, parent=self.app)
        self.app.set_window_icon(self)
        self.grab_set()
        self.lift()

    def close(self):
        self._dialog_size = (self.winfo_width(), self.winfo_height())
        self.grab_release()
        self.withdraw()


class AdvancedAudioDialog(CenteredDialog):
    def __init__(self, app):
        super().__init__(app)
        self.withdraw()
        self._dialog_size = (760, 690)
        self.app = app
        self.localized = []
        self.title(app.t("advanced_title"))
        self.configure(bg=COLORS["bg"])
        self.geometry("760x690")
        self.minsize(720, 650)
        self.transient(app)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _event: self.close())
        self.bind("<F1>", lambda _event: self.app.view.show_help("audio"))
        self.show()

    def _text(self, widget, key):
        widget.configure(text=self.app.t(key))
        self.localized.append((widget, key))
        if self.app.t("tip_" + key) != "tip_" + key:
            self._tip(widget, "tip_" + key)
        return widget

    def _tip(self, widget, key):
        widget.help_key = key
        ToolTip(widget, lambda: self.app.t(key))

    def _build(self):
        body = ttk.Frame(self, padding=SPACING["lg"])
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.notebook = ttk.Notebook(body)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.enhancement_page = ttk.Frame(self.notebook)
        self.enhancement_page.columnconfigure(0, weight=1)
        self.enhancement_page.rowconfigure(0, weight=1)
        self.enhancement_canvas = tk.Canvas(
            self.enhancement_page,
            bg=COLORS["bg"],
            highlightthickness=0,
            borderwidth=0,
        )
        enhancement_scrollbar = ttk.Scrollbar(
            self.enhancement_page,
            orient="vertical",
            command=self.enhancement_canvas.yview,
        )
        self.enhancement_canvas.configure(yscrollcommand=enhancement_scrollbar.set)
        self.enhancement_canvas.grid(row=0, column=0, sticky="nsew")
        enhancement_scrollbar.grid(row=0, column=1, sticky="ns")
        self.enhancement_tab = ttk.Frame(self.enhancement_canvas, padding=SPACING["md"])
        self.enhancement_window = self.enhancement_canvas.create_window(
            (0, 0), window=self.enhancement_tab, anchor="nw"
        )
        self.enhancement_tab.bind("<Configure>", self._update_enhancement_scroll_region)
        self.enhancement_canvas.bind("<Configure>", self._resize_enhancement_content)
        self.bind("<MouseWheel>", self._scroll_enhancement)
        self.effects_tab = ttk.Frame(self.notebook, padding=SPACING["md"])
        self.notebook.add(self.enhancement_page, text=self.app.t("enhancement"))
        self.notebook.add(self.effects_tab, text=self.app.t("effects"))
        self._build_enhancement(self.enhancement_tab)
        self._build_effects(self.effects_tab)

        warning = ttk.Label(
            body, textvariable=self.app.audio_warning_var, style="Secondary.TLabel",
            foreground=COLORS["danger"], wraplength=680,
        )
        warning.grid(row=1, column=0, sticky="ew", pady=(SPACING["sm"], 0))
        close = RoundedButton(
            body,
            text=self.app.t("close"),
            width=SIZES["button_width"],
            command=self.close,
        )
        self.localized.append((close, "close"))
        close.grid(row=2, column=0, sticky="e", pady=(SPACING["sm"], 0))

    def _update_enhancement_scroll_region(self, _event=None):
        self.enhancement_canvas.configure(scrollregion=self.enhancement_canvas.bbox("all"))

    def _resize_enhancement_content(self, event):
        self.enhancement_canvas.itemconfigure(self.enhancement_window, width=event.width)

    def _scroll_enhancement(self, event):
        self.enhancement_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _section(self, parent, key, row):
        frame = ttk.Labelframe(parent, text=self.app.t(key), style="Surface.TLabelframe", padding=SPACING["sm"])
        self.localized.append((frame, key))
        frame.grid(row=row, column=0, sticky="ew", pady=(0, SPACING["sm"]))
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        return frame

    def _fields(self, frame, fields, start_row=0, resettable=()):
        for index, (key, var_name, minimum, maximum, step) in enumerate(fields):
            column = index % 2
            row = start_row + (index // 2) * 2
            label = ttk.Label(frame, text=self.app.t(key), style="SurfaceSecondary.TLabel")
            self.localized.append((label, key))
            label.grid(row=row, column=column, sticky="w", padx=(0 if column == 0 else SPACING["sm"], 0))
            spin = ttk.Spinbox(
                frame, textvariable=app_var(self.app, var_name), from_=minimum, to=maximum,
                increment=step, width=14,
            )
            spin.grid(row=row + 1, column=column, sticky="ew", padx=(0 if column == 0 else SPACING["sm"], 0), pady=(2, SPACING["xs"]))
            self._tip(label, f"tip_{key}")
            self._tip(spin, f"tip_{key}")
            if var_name in resettable:
                spin.bind("<Double-Button-1>", lambda _event, variable=app_var(self.app, var_name): variable.set(0))

    def _build_enhancement(self, parent):
        parent.columnconfigure(0, weight=1)
        normalization = self._section(parent, "normalization", 0)
        self._fields(normalization, (
            ("integrated_lufs", "integrated_lufs_var", -30, -5, .5),
            ("true_peak", "true_peak_var", -9, 0, .1),
            ("lra", "lra_var", 1, 20, .5),
            ("final_gain", "final_gain_var", .5, 2, .05),
        ))
        equalizer = self._section(parent, "equalizer", 1)
        self._fields(equalizer, (
            ("bass_gain", "bass_gain_var", -12, 12, .5),
            ("mid_gain", "mid_gain_var", -12, 12, .5),
            ("treble_gain", "treble_gain_var", -12, 12, .5),
            ("stereo_width", "stereo_width_var", 0, 2, .05),
        ), resettable=("bass_gain_var", "mid_gain_var", "treble_gain_var"))
        filters = self._section(parent, "filters", 2)
        low_cut = SquareCheckbutton(filters, self.app.highpass_enabled_var, self.app.t("highpass_enabled"), fixed_width=220)
        high_cut = SquareCheckbutton(filters, self.app.lowpass_enabled_var, self.app.t("lowpass_enabled"), fixed_width=220)
        self.localized.extend(((low_cut, "highpass_enabled"), (high_cut, "lowpass_enabled")))
        low_cut.grid(row=0, column=0, sticky="w")
        high_cut.grid(row=0, column=1, sticky="w", padx=(SPACING["sm"], 0))
        self._tip(low_cut, "tip_highpass_enabled")
        self._tip(high_cut, "tip_lowpass_enabled")
        highpass = ttk.Spinbox(filters, textvariable=self.app.highpass_hz_var, from_=10, to=500, increment=5)
        highpass.grid(row=1, column=0, sticky="ew")
        lowpass = ttk.Spinbox(filters, textvariable=self.app.lowpass_hz_var, from_=4000, to=24000, increment=100)
        lowpass.grid(row=1, column=1, sticky="ew", padx=(SPACING["sm"], 0))
        self._tip(highpass, "tip_highpass_hz")
        self._tip(lowpass, "tip_lowpass_hz")
        dynamics = self._section(parent, "noise_and_dynamics", 3)
        denoise_label = ttk.Label(dynamics, text=self.app.t("denoise_mode"), style="SurfaceSecondary.TLabel")
        self.localized.append((denoise_label, "denoise_mode"))
        denoise_label.grid(row=0, column=0, sticky="w")
        self.denoise_combo = ttk.Combobox(dynamics, textvariable=self.app.denoise_mode_var, values=self.app.audio_option_values("denoise"), state="readonly")
        self.denoise_combo.grid(row=1, column=0, sticky="ew", padx=(0, SPACING["sm"]))
        self.denoise_combo.bind("<<ComboboxSelected>>", lambda _event: self.app.denoise_mode_changed())
        self._tip(denoise_label, "tip_denoise_mode")
        self._tip(self.denoise_combo, "tip_denoise_mode")
        compressor = SquareCheckbutton(dynamics, self.app.compressor_var, self.app.t("compressor"), fixed_width=220)
        self.localized.append((compressor, "compressor"))
        compressor.grid(row=0, column=1, sticky="w")
        self._tip(compressor, "tip_compressor")
        self._fields(dynamics, (
            ("compressor_threshold", "compressor_threshold_var", -60, 0, 1),
            ("compressor_ratio", "compressor_ratio_var", 1, 20, .5),
            ("compressor_attack", "compressor_attack_var", 1, 200, 1),
            ("compressor_release", "compressor_release_var", 20, 2000, 10),
            ("compressor_makeup", "compressor_makeup_var", 0, 18, .5),
        ), start_row=2)
        output = self._section(parent, "audio_output", 4)
        self.output_combos = []
        for column, (key, variable, kind) in enumerate((
            ("sample_rate", self.app.sample_rate_var, "sample_rate"),
            ("channel_layout", self.app.channels_var, "channels"),
        )):
            label = ttk.Label(output, text=self.app.t(key), style="SurfaceSecondary.TLabel")
            self.localized.append((label, key))
            label.grid(row=0, column=column, sticky="w", padx=(0 if column == 0 else SPACING["sm"], 0))
            combo = ttk.Combobox(output, textvariable=variable, values=self.app.audio_option_values(kind), state="readonly")
            combo.grid(row=1, column=column, sticky="ew", padx=(0 if column == 0 else SPACING["sm"], 0))
            self._tip(label, f"tip_{key}")
            self._tip(combo, f"tip_{key}")
            self.output_combos.append((combo, kind))
        quality_label = ttk.Label(output, text=self.app.t("mp3_quality"), style="SurfaceSecondary.TLabel")
        self.localized.append((quality_label, "mp3_quality"))
        quality_label.grid(row=2, column=0, sticky="w", pady=(SPACING["xs"], 0))
        self.quality_combo = ttk.Combobox(output, textvariable=self.app.mp3_quality_var, values=self.app.audio_option_values("quality"), state="readonly")
        self.quality_combo.grid(row=3, column=0, columnspan=2, sticky="ew")
        self._tip(quality_label, "tip_mp3_quality")
        self._tip(self.quality_combo, "tip_mp3_quality")

    def _build_effects(self, parent):
        parent.columnconfigure(0, weight=1)
        effects = self._section(parent, "effects", 0)
        self._fields(effects, (
            ("pitch_semitones", "pitch_semitones_var", -12, 12, .5),
            ("playback_speed", "playback_speed_var", .5, 2, .05),
            ("reverb_mix", "reverb_mix_var", 0, 1, .05),
            ("fade_in", "fade_in_var", 0, 30, .5),
            ("fade_out", "fade_out_var", 0, 30, .5),
        ))

    def apply_language(self):
        self.title(self.app.t("advanced_title"))
        for widget, key in self.localized:
            widget.configure(text=self.app.t(key))
        self.notebook.tab(self.enhancement_page, text=self.app.t("enhancement"))
        self.notebook.tab(self.effects_tab, text=self.app.t("effects"))
        self.denoise_combo.configure(values=self.app.audio_option_values("denoise"))
        for combo, kind in self.output_combos:
            combo.configure(values=self.app.audio_option_values(kind))
        self.quality_combo.configure(values=self.app.audio_option_values("quality"))

    def close(self):
        self.app.refresh_audio_warning()
        super().close()


def app_var(app, name):
    return getattr(app, name)


class AdditionalMetadataDialog(CenteredDialog):
    FIELDS = (
        ("disc", "disc_var"),
        ("publisher", "publisher_var"),
        ("copyright", "copyright_var"),
        ("lyrics", "lyrics_var"),
    )

    def __init__(self, app):
        super().__init__(app)
        self.withdraw()
        self._dialog_size = (680, 330)
        self.app = app
        self.localized = []
        self.title(app.t("additional_metadata_title"))
        self.configure(bg=COLORS["bg"])
        self.geometry("680x330")
        self.resizable(False, False)
        self.transient(app)
        self._build()
        self.bind("<Escape>", lambda _event: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<F1>", lambda _event: self.app.view.show_help("metadata"))
        self.show()

    def _build(self):
        body = ttk.Labelframe(
            self,
            text=self.app.t("additional_metadata_title"),
            style="Surface.TLabelframe",
            padding=SPACING["lg"],
        )
        self.localized.append((body, "additional_metadata_title"))
        body.pack(fill=tk.BOTH, expand=True, padx=SPACING["lg"], pady=SPACING["lg"])
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        for index, (key, var_name) in enumerate(self.FIELDS):
            column = index % 2
            row = (index // 2) * 2
            label = ttk.Label(
                body,
                text=self.app.t(key),
                style="SurfaceSecondary.TLabel",
            )
            self.localized.append((label, key))
            label.grid(
                row=row,
                column=column,
                sticky="w",
                padx=(0 if column == 0 else SPACING["sm"], SPACING["sm"] if column == 0 else 0),
            )
            entry = ttk.Entry(body, textvariable=getattr(self.app, var_name))
            ToolTip(label, lambda k=key: self.app.t("tip_" + k))
            ToolTip(entry, lambda k=key: self.app.t("tip_" + k))
            entry.grid(
                row=row + 1,
                column=column,
                sticky="ew",
                padx=(0 if column == 0 else SPACING["sm"], SPACING["sm"] if column == 0 else 0),
                pady=(SPACING["xs"], SPACING["md"]),
            )
        close = RoundedButton(
            body,
            text=self.app.t("close"),
            width=SIZES["button_width"],
            command=self.close,
        )
        self.localized.append((close, "close"))
        close.grid(row=4, column=0, columnspan=2, sticky="e", pady=(SPACING["sm"], 0))

    def apply_language(self):
        self.title(self.app.t("additional_metadata_title"))
        for widget, key in self.localized:
            widget.configure(text=self.app.t(key))

    def close(self):
        super().close()
