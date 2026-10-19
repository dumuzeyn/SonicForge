from tkinter import ttk


APP_BACKGROUND = "#F6F5FA"

COLORS = {
    "bg": APP_BACKGROUND,
    "surface": "#FFFFFF",
    "surface_alt": "#F1EFF8",
    "elevated": "#EBE6F8",
    "field": "#FCFBFF",
    "text": "#17191D",
    "secondary": "#525A6C",
    "disabled": "#989DA5",
    "border": "#DED9EA",
    "border_active": "#ACA0C9",
    "accent": "#6250BE",
    "accent_hover": "#7563CC",
    "accent_pressed": "#493B94",
    "timeline": "#F5F4FB",
    "button": "#F0ECFC",
    "button_hover": "#E5DEFA",
    "button_pressed": "#DCD3F5",
    "button_text": "#443578",
    "button_disabled": "#F3F1F8",
    "danger_surface": "#F8ECEF",
    "danger_surface_hover": "#F1DCE2",
    "danger_surface_pressed": "#E9CBD4",
    "danger": "#A94F56",
    "danger_hover": "#8F4047",
    "log": "#FCFBFF",
    "white": "#FFFFFF",
}
TRACK_COLORS = ("#DBD4FF", "#C9E8EB", "#F4DEC4", "#D7E7CE")

SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 18, "xl": 24}
SIZES = {
    "control_height": 32,
    "button_width": 11,
    "language_width": 12,
    "primary_width": 18,
    "check_size": 16,
    "header_height": 70,
    "tab_height": 36,
    "tooltip_width": 380,
    "window_width_reserve": 6,
    "window_height_reserve": 4,
    "startup_width": 1000,
}
FONTS = {
    "body": ("Segoe UI", 10),
    "label": ("Segoe UI", 10),
    "section": ("Segoe UI Semibold", 11),
    "title": ("Segoe UI Semibold", 15),
    "small": ("Segoe UI", 10),
    "mono": ("Cascadia Mono", 9),
    "button": ("Segoe UI Semibold", 10),
}


def configure_styles(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        ".",
        background=COLORS["bg"],
        foreground=COLORS["text"],
        fieldbackground=COLORS["field"],
        bordercolor=COLORS["border"],
        lightcolor=COLORS["border"],
        darkcolor=COLORS["border"],
        font=FONTS["body"],
    )
    style.configure("TFrame", background=COLORS["bg"])
    style.configure("Surface.TFrame", background=COLORS["surface"])
    style.configure("Elevated.TFrame", background=COLORS["elevated"])
    style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"])
    style.configure("Surface.TLabel", background=COLORS["surface"], foreground=COLORS["text"])
    style.configure(
        "Secondary.TLabel",
        background=COLORS["bg"],
        foreground=COLORS["secondary"],
        font=FONTS["small"],
    )
    style.configure(
        "SurfaceSecondary.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["secondary"],
        font=FONTS["small"],
    )
    style.configure("Title.TLabel", font=FONTS["title"], background=COLORS["surface"])
    style.configure("Section.TLabel", font=FONTS["section"])
    style.configure(
        "Surface.TLabelframe",
        background=COLORS["surface"],
        bordercolor=COLORS["border"],
        borderwidth=1,
        relief="solid",
    )
    style.configure(
        "Surface.TLabelframe.Label",
        background=COLORS["surface"],
        foreground=COLORS["text"],
        font=FONTS["section"],
    )

    style.configure(
        "TButton",
        background=COLORS["button"],
        foreground=COLORS["button_text"],
        bordercolor=COLORS["border"],
        borderwidth=1,
        focusthickness=1,
        focuscolor=COLORS["accent"],
        padding=(12, 7),
        relief="flat",
        font=FONTS["button"],
    )
    style.map(
        "TButton",
        background=[("pressed", COLORS["button_pressed"]), ("active", COLORS["button_hover"])],
        bordercolor=[("focus", COLORS["accent"]), ("active", COLORS["border_active"])],
        foreground=[("disabled", COLORS["disabled"])],
    )
    style.configure("Editor.TButton", background=COLORS["button"], foreground=COLORS["button_text"],
                    bordercolor=COLORS["border"], padding=(12, 7), font=FONTS["button"])
    style.map("Editor.TButton", background=[("pressed", COLORS["button_pressed"]), ("active", COLORS["button_hover"])],
              foreground=[("disabled", COLORS["disabled"])])
    style.configure(
        "TMenubutton",
        background=COLORS["button"],
        foreground=COLORS["button_text"],
        bordercolor=COLORS["border"],
        borderwidth=1,
        padding=(12, 7),
        arrowcolor=COLORS["secondary"],
        font=FONTS["button"],
    )
    style.map(
        "TMenubutton",
        background=[("pressed", COLORS["button_pressed"]), ("active", COLORS["button_hover"])],
        bordercolor=[("focus", COLORS["accent"]), ("active", COLORS["border_active"])],
    )
    style.configure(
        "Primary.TButton",
        background=COLORS["accent"],
        foreground=COLORS["white"],
        bordercolor=COLORS["accent"],
        font=("Segoe UI Semibold", 10),
        padding=(14, 7),
    )
    style.map(
        "Primary.TButton",
        background=[("pressed", COLORS["accent_pressed"]), ("active", COLORS["accent_hover"])],
        bordercolor=[("pressed", COLORS["accent_pressed"]), ("active", COLORS["accent_hover"])],
        foreground=[("disabled", "#D2D4D8")],
    )
    style.configure("Danger.TButton", background=COLORS["danger_surface"], foreground=COLORS["danger"])
    style.map(
        "Danger.TButton",
        background=[("pressed", COLORS["danger_surface_pressed"]), ("active", COLORS["danger_surface_hover"])],
        bordercolor=[("focus", COLORS["danger"]), ("active", COLORS["danger_hover"])],
    )

    for name in ("TEntry", "TSpinbox", "TCombobox"):
        style.configure(
            name,
            fieldbackground=COLORS["field"],
            foreground=COLORS["text"],
            insertcolor=COLORS["text"],
            bordercolor=COLORS["border"],
            arrowcolor=COLORS["secondary"],
            borderwidth=1,
            padding=(8, 6),
        )
        style.map(
            name,
            bordercolor=[("focus", COLORS["accent"]), ("disabled", COLORS["border"])],
            fieldbackground=[("disabled", COLORS["surface_alt"]), ("readonly", COLORS["field"])],
            foreground=[("disabled", COLORS["disabled"]), ("readonly", COLORS["text"])],
        )
    style.map(
        "TCombobox",
        selectbackground=[("readonly", COLORS["field"])],
        selectforeground=[("readonly", COLORS["text"])],
    )
    style.configure(
        "Thin.Horizontal.TProgressbar",
        background=COLORS["accent"],
        troughcolor=COLORS["surface_alt"],
        bordercolor=COLORS["surface_alt"],
        lightcolor=COLORS["accent"],
        darkcolor=COLORS["accent"],
        thickness=6,
    )
    style.configure(
        "Vertical.TScrollbar",
        background=COLORS["elevated"],
        troughcolor=COLORS["log"],
        bordercolor=COLORS["border"],
        arrowcolor=COLORS["secondary"],
    )
    style.configure("TSeparator", background=COLORS["border"])
    style.configure("TabBar.TFrame", background=COLORS["bg"])
    style.configure("TNotebook", background=COLORS["bg"], borderwidth=0, tabmargins=(0, 0, 0, 8))
    style.configure("TNotebook.Tab", background=COLORS["button"], foreground=COLORS["button_text"],
                    padding=(16, 9), font=FONTS["button"], borderwidth=0)
    # Clam's focus element adds the dotted rectangle and its selected expansion
    # makes the inactive tab appear raised. Selection alone determines the fill.
    style.layout("TNotebook.Tab", [("Notebook.tab", {"sticky": "nswe", "children": [
        ("Notebook.padding", {"side": "top", "sticky": "nswe", "children": [
            ("Notebook.label", {"side": "top", "sticky": ""})]})]})])
    style.map("TNotebook.Tab", background=[("selected", COLORS["accent"]), ("active", COLORS["button_hover"])],
              foreground=[("selected", COLORS["white"]), ("active", COLORS["button_text"])],
              padding=[("selected", (16, 9)), ("!selected", (16, 9))],
              expand=[("selected", (0, 0, 0, 0))],
              lightcolor=[("selected", COLORS["accent"]), ("!selected", COLORS["button"])],
              darkcolor=[("selected", COLORS["accent"]), ("!selected", COLORS["button"])],
              bordercolor=[("selected", COLORS["accent"]), ("!selected", COLORS["button"])])
    style.configure(
        "Tab.TButton",
        background=COLORS["accent"],
        foreground=COLORS["white"],
        bordercolor=COLORS["accent"],
        borderwidth=0,
        padding=(12, 8),
        font=FONTS["body"],
    )
    style.map(
        "Tab.TButton",
        background=[("pressed", COLORS["accent_pressed"]), ("active", COLORS["accent_hover"])],
        foreground=[("active", COLORS["white"])],
    )
    style.configure(
        "Selected.Tab.TButton",
        background=COLORS["surface"],
        foreground=COLORS["button_text"],
        bordercolor=COLORS["surface"],
        borderwidth=0,
        padding=(12, 8),
        font=("Segoe UI Semibold", 10),
    )
    style.map(
        "Selected.Tab.TButton",
        background=[("pressed", COLORS["surface"]), ("active", COLORS["surface"])],
        foreground=[("disabled", COLORS["disabled"])],
    )
    return style
