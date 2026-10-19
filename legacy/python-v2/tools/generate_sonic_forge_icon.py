from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
UZYRO_ROOT = Path.home() / "Documents" / "PhotoRedactor"
ASSETS = ROOT / "assets"
SIZE = 1024
SCALE = 2

sys.path.insert(0, str(UZYRO_ROOT))
from uzyro.document import Document  # noqa: E402
from uzyro.layer import Layer  # noqa: E402


def fit_reference(points):
    return [
        (
            round(x / 287 * SIZE * SCALE),
            round(y / 286 * SIZE * SCALE),
        )
        for x, y in points
    ]


def reference_cubic(start, control_a, control_b, end, steps=16):
    points = []
    for index in range(1, steps + 1):
        t = index / steps
        inverse = 1.0 - t
        points.append(
            (
                inverse**3 * start[0]
                + 3 * inverse**2 * t * control_a[0]
                + 3 * inverse * t**2 * control_b[0]
                + t**3 * end[0],
                inverse**3 * start[1]
                + 3 * inverse**2 * t * control_a[1]
                + 3 * inverse * t**2 * control_b[1]
                + t**3 * end[1],
            )
        )
    return fit_reference(points)


def draw_mask(points):
    mask = Image.new("L", (SIZE * SCALE, SIZE * SCALE), 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    return mask


def layer_from_mask(name, mask, layer_type, path_points):
    height = SIZE * SCALE
    pixels = np.zeros((height, height, 4), dtype=np.uint8)
    alpha = np.asarray(mask, dtype=np.uint8)
    blend = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    for channel, (top, bottom) in enumerate(zip((20, 23, 30), (27, 30, 37))):
        values = top * (1.0 - blend) + bottom * blend
        pixels[:, :, channel] = np.repeat(values, height, axis=1).astype(np.uint8)
    pixels[:, :, 3] = alpha
    layer = Layer(name, pixels)
    layer.shape_data = {
        "type": layer_type,
        "points": [[x / SCALE, y / SCALE] for x, y in path_points],
        "fill": "#17191F",
    }
    return layer


def build_document():
    canvas_size = SIZE * SCALE
    transparent = np.zeros((canvas_size, canvas_size, 4), dtype=np.uint8)
    background = Image.new(
        "RGBA",
        (canvas_size, canvas_size),
        (249, 249, 251, 255),
    )

    s_outline = fit_reference([(162, 64), (71, 64)])
    s_outline += reference_cubic((71, 64), (48, 65), (33, 82), (33, 108))
    s_outline += reference_cubic((33, 108), (33, 128), (45, 137), (65, 143))
    s_outline += fit_reference([(99, 153)])
    s_outline += reference_cubic((99, 153), (106, 155), (110, 160), (109, 166))
    s_outline += reference_cubic((109, 166), (108, 171), (103, 174), (93, 174))
    s_outline += fit_reference([(16, 174)])
    s_outline += reference_cubic((16, 174), (11, 174), (12, 184), (15, 190))
    s_outline += reference_cubic((15, 190), (19, 198), (28, 201), (40, 201))
    s_outline += fit_reference([(97, 201)])
    s_outline += reference_cubic((97, 201), (115, 199), (126, 186), (131, 170))
    s_outline += reference_cubic((131, 170), (136, 152), (128, 137), (116, 128))
    s_outline += fit_reference([(65, 113)])
    s_outline += reference_cubic((65, 113), (61, 112), (59, 107), (59, 102))
    s_outline += reference_cubic((59, 102), (59, 95), (65, 90), (75, 90))
    s_outline += fit_reference([(150, 90)])
    s_outline += reference_cubic((150, 90), (154, 90), (156, 86), (158, 81))
    s_outline += fit_reference([(164, 67)])

    f_top = fit_reference([(189, 64), (276, 64)])
    f_top += reference_cubic((276, 64), (280, 64), (279, 67), (277, 72), 6)
    f_top += fit_reference([(269, 86)])
    f_top += reference_cubic((269, 86), (267, 89), (263, 91), (258, 91), 6)
    f_top += fit_reference([(171, 90), (181, 69)])
    f_top += reference_cubic((181, 69), (183, 66), (186, 64), (189, 64), 6)

    f_body = fit_reference([(177, 131), (254, 131)])
    f_body += reference_cubic((254, 131), (257, 131), (259, 133), (257, 137), 6)
    f_body += fit_reference([(249, 151)])
    f_body += reference_cubic((249, 151), (246, 156), (243, 158), (237, 158), 8)
    f_body += fit_reference([(195, 158)])
    f_body += reference_cubic((195, 158), (188, 158), (184, 162), (182, 168), 8)
    f_body += fit_reference([(174, 198)])
    f_body += reference_cubic((174, 198), (172, 207), (168, 214), (162, 219), 8)
    f_body += fit_reference([(134, 240), (133, 238), (153, 170), (158, 151)])
    f_body += reference_cubic((158, 151), (162, 138), (168, 131), (177, 131), 10)

    document = Document(
        canvas_size,
        canvas_size,
        dpi=300,
        background=(0, 0, 0, 0),
        layers=[
            Layer("Transparent base", transparent.copy()),
            Layer("Light icon background", np.asarray(background, dtype=np.uint8).copy()),
            layer_from_mask("S", draw_mask(s_outline), "bezier_path", s_outline),
            layer_from_mask("F top bar", draw_mask(f_top), "polygon", f_top),
            layer_from_mask("F body", draw_mask(f_body), "polygon", f_body),
        ],
        active_layer=4,
    )
    document.metadata.update(
        {
            "title": "Sonic Forge SF mark",
            "authoring_app": "UZYRO",
            "waveform": "removed",
            "reference_style": "silhouette traced from the supplied SF icon",
            "border": "none",
        }
    )
    return document


def export_assets():
    ASSETS.mkdir(parents=True, exist_ok=True)
    document = build_document()
    project_path = ASSETS / "SonicForgeIcon.prdx"
    png_path = ASSETS / "sonic_forge_mark.png"
    ico_path = ASSETS / "sonic_forge_mark.ico"
    document.save_project(project_path)
    rendered = Image.fromarray(document.composite(False), "RGBA")
    rendered = rendered.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    rendered.save(png_path, optimize=True)
    rendered.save(
        ico_path,
        format="ICO",
        sizes=[
            (16, 16),
            (20, 20),
            (24, 24),
            (32, 32),
            (40, 40),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256),
        ],
    )
    return project_path, png_path, ico_path


if __name__ == "__main__":
    for output in export_assets():
        print(output)
