"""Read-only cover regression check and captures of test-created dialog windows."""
import argparse
import hashlib
from pathlib import Path
import sys

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from music2picture import make_cover
from music_polisher_gui import SonicForgeApp, enable_high_dpi
from scripts.check_navigation_rendering import capture, settle
from ui.dialogs import CustomCoverDialog


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    args = parser.parse_args()
    source = args.audio.resolve(strict=True)
    before = digest(source)
    output = ROOT / "validation" / "custom-cover"
    output.mkdir(parents=True, exist_ok=True)
    palette = ["#123b53", "#306982", "#54a4a3", "#85c0b0", "#b9cfac", "#ebd79b",
               "#f4c66a", "#e99354", "#af5972", "#705488", "#484d77", "#142f49"]
    examples = (
        ("fixed-title", "current_legacy_colors", None),
        ("custom-modern", "custom", dict(pattern="modern", colors=palette, detail=70)),
        ("custom-music2picture", "custom", dict(pattern="legacy", colors=palette[::-1], detail=75)),
    )
    sheet = Image.new("RGB", (960, 352), "#f5f4fb")
    draw = ImageDraw.Draw(sheet)
    for index, (name, style, settings) in enumerate(examples):
        target = output / f"{name}.png"
        make_cover(source, target, size=1000, seed=38, text_mode="title", preview=True,
                   style=style, custom_cover_settings=settings)
        with Image.open(target) as image:
            sheet.paste(image.resize((304, 304), Image.Resampling.LANCZOS), (index * 320 + 8, 8))
        draw.text((index * 320 + 8, 320), name, fill="#252036")
    sheet.save(output / "comparison.png")
    assert digest(source) == before, "Source audio changed"
    assert not (output / ".sonicforge").exists(), "Preview wrote a persistent profile"
    enable_high_dpi()
    app = SonicForgeApp()
    app.custom_cover_settings["colors"] = palette
    try:
        for language in ("ru", "en"):
            if app.language != language:
                app.toggle_language()
            app.view.show_tab("cover")
            settle(app)
            dialog = CustomCoverDialog(app)
            settle(dialog)
            capture(dialog, ROOT / "docs" / "images" / f"cover-custom-{language}.png")
            dialog.close()
        capture(app, output / "cover-page-en.png")
    finally:
        app.destroy()  # Only this test-created instance, never a user's open app.
    print(f"Source SHA256 unchanged: {before}")
    print(output / "comparison.png")


if __name__ == "__main__":
    main()
