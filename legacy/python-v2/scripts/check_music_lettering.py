"""Reproduce a before/after audit on five local recordings; never alter audio.

Before requires a snapshot of typography.py from before this change, supplied
with --baseline. This prevents a comparison with an invented old renderer.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image, ImageChops, ImageDraw, ImageFont
import music2picture
import music_metadata
from cover_engine.titles import clean_artist, resolve_title
from music2picture_v2 import DEFAULT_PIPELINE


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--music-root", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "validation" / "music_lettering")
    parser.add_argument("--tracks", nargs="+", default=["Fallen Down", "Another Love", "Animal I Have Become", "Android Dubstep", "Я тебе не верю"])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("baseline_lettering", args.baseline.resolve())
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    old = baseline.TypographyEngine()
    records, previews = [], []
    files = sorted(args.music_root.rglob("*.mp3"))
    for index, name in enumerate(args.tracks, 1):
        matches = [p for p in files if p.stem == name]
        if not matches:
            raise FileNotFoundError(name)
        path = min(matches, key=lambda p: (len(p.parts), str(p)))
        print(f"[{index}/{len(args.tracks)}] {path.name}", flush=True)
        tags = music_metadata.read_all_metadata(path)
        metadata = {k: v for k, v in tags.items() if "lyrics" not in str(k).lower()}
        bundle = DEFAULT_PIPELINE.analyse(path, metadata=metadata)
        stem = f"{index:02d}"
        bare_path, after_path = args.output / f"{stem}_artwork.png", args.output / f"{stem}_after.png"
        # Both pictures use the public export entry point and exactly the same
        # song, seed, artwork, resolution and lyric setting.
        music2picture.make_cover(path, bare_path, size=1000, seed=7, preview=True, text_mode="none")
        music2picture.make_cover(path, after_path, size=1000, seed=7, preview=True, text_mode="title_artist")
        bare = Image.open(bare_path).convert("RGB")
        title = tags.get("title") or music2picture.clean_stem(path)
        artist = tags.get("artist", "")
        resolved = resolve_title(title, "stylized")
        before = old.compose(bare, resolved.selected, clean_artist(artist), profile=SimpleNamespace(
            typography_style="artistic title", typography_locked=True, text_position="center"),
            title_treatment=resolved, show_artist=True, language=bundle.language, placement_override="center")
        before.save(args.output / f"{stem}_before.png")
        layout = {}
        # The bare public export now contains the song's focal symbol. Recover
        # its deterministic bounds so inspection protects the same area.
        _, symbol_layout = music2picture._add_cover_symbol(bare, bundle.visual_dna, title)
        check = music2picture._add_cover_text(bare, title, artist, text_mode="title_artist", language=bundle.language,
                                            visual_dna=bundle.visual_dna, layout_out=layout, symbol_layout=symbol_layout)
        after = Image.open(after_path).convert("RGB")
        assert ImageChops.difference(check, after).getbbox() is None, "Export differs from inspected typography"
        assert layout["contrast_ratio"] >= 4.5, layout
        assert layout["ink_bounds"] == ImageChops.difference(bare, after).getbbox() or layout["adaptive_veil"]
        records.append({"track": str(path), "title": title, "artist": artist,
                        "audio": bundle.analysis.to_dict(), "dna": bundle.visual_dna.to_dict(),
                        "before": old.last_layout, "after": layout,
                        "export_matches_inspected_pixels": True})
        previews.append((name, before, after))
        print(json.dumps({"family": layout["design"]["family"], "weight": round(layout["design"]["weight"]),
                          "placement": layout["placement"], "contrast": layout["contrast_ratio"]}), flush=True)
    (args.output / "measurements.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    tile, label, padding = 300, 50, 18
    row_height = tile + label + 54
    sheet = Image.new("RGB", (padding + len(previews)*(tile+padding), 2*row_height+padding), "#111827")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(str(ROOT / "assets/fonts/NotoSans-Variable.ttf"), 19)
    draw.text((padding, 10), "ДО — фиксированный центр и вес 560", font=font, fill="#e2e8f0")
    draw.text((padding, row_height+10), "ПОСЛЕ — форма и композиция из аудио", font=font, fill="#e2e8f0")
    for index, (name, before, after) in enumerate(previews):
        x = padding + index*(tile+padding)
        for row, image in enumerate((before, after)):
            y = 48 + row*row_height
            sheet.paste(image.resize((tile, tile), Image.Resampling.LANCZOS), (x, y))
            draw.text((x, y+tile+9), name, font=font, fill="#e2e8f0")
    sheet.save(args.output / "before_after.png")
    print(args.output / "before_after.png", flush=True)


if __name__ == "__main__":
    main()
