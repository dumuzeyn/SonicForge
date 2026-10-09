"""Music-conditioned lettering, rendered into the cover's pixels.

Correspondences are soft design priors, not psychological diagnoses. See
docs/music-lettering.md for research, calibration and vocal-estimate limits.
Only Pillow/numpy and the already bundled variable fonts are required.
"""
from __future__ import annotations

import colorsys
import math
import unicodedata
from dataclasses import asdict, dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


VERSION = "music-lettering-v3"


def unit(value):
    value = float(value)
    return max(0., min(1., value)) if math.isfinite(value) else .5


def ramp(value, low, high):
    return unit((float(value) - low) / (high - low))


@dataclass(frozen=True)
class LetteringDesign:
    angularity: float
    mass: float
    openness: float
    weight: float
    width: float
    slant: float
    tracking: float
    scale: float
    line_contrast: float
    hue: float
    saturation: float
    family: str
    preferred_placement: str
    terminal_extension: float
    vocal_influence: float

    def to_dict(self):
        return asdict(self)


def design_from_music(dna):
    """Continuous, interpretable controls. Genre and title never enter this map."""
    def v(name, default=.5):
        return unit(getattr(dna, name, default))

    edge = unit(.38 * ramp(v("roughness"), .12, .43)
                + .25 * v("brightness") + .22 * v("attack_strength")
                + .15 * ramp(v("spectral_flux"), .03, .30))
    drive = ramp(v("arousal"), .24, .72)
    mass = unit(.32 * drive + .28 * v("bass_mass") * (.25 + .75 * edge)
                + .26 * v("absolute_loudness") * (1 - v("crest_factor"))
                + .14 * v("attack_strength"))
    # The measured mixtures occupy a narrower range than theoretical extrema.
    # Calibrate continuously; bass-heavy piano alone must not become heavy type.
    mass = ramp(mass + .20 * edge, .36, .69)
    openness = unit(v("relaxation") * .55 + (1 - edge) * .25 + v("crest_factor") * .20)
    # Mid-band/harmonic evidence in a mix cannot identify a singer reliably.
    # Use the existing weak vocal proxy only as a bounded expressive prior.
    voice = min(.15, v("vocal_probability") * v("acousticness") * .20)
    expressive_voice = voice * (v("original_dynamic_range") - edge)
    vocal_softness = voice * (1 - edge) * (1 - drive)
    weight = max(300., min(850., 280 + mass * 650 + edge * 140 - openness * 70 - 80 * vocal_softness))
    width = .85 + .26 * openness - .14 * edge - .14 * v("rhythmic_density") + .08 * v("bass_mass")
    slant = .14 * edge * drive * (.35 + .65 * (1 - v("rhythmic_regularity"))) + expressive_voice * .20
    tracking = .004 + .065 * openness - .035 * v("rhythmic_density") + .03 * vocal_softness
    dynamic = v("dynamic_complexity") * .5 + v("original_dynamic_range") * .5
    if edge > .45 and v("brightness") > .46:
        family, preferred = "geometric", "top"
    elif edge > .43:
        family, preferred = "condensed", "left"
    elif v("acousticness") > .70 and v("original_dynamic_range") > .18:
        family, preferred = "serif", "right"
    else:
        family, preferred = "humanist", "bottom"
    valence, tension = v("valence"), v("tension")
    hue = (225 * (1 - valence) + 32 * valence - 45 * tension * edge) / 360
    return LetteringDesign(
        angularity=edge, mass=mass, openness=openness, weight=weight, width=width,
        slant=slant, tracking=max(.006, tracking), scale=.095 + .065 * mass + .018 * dynamic,
        line_contrast=.06 + .25 * dynamic, hue=hue % 1,
        saturation=.10 + .52 * drive + .15 * edge, family=family,
        preferred_placement=preferred, terminal_extension=.06 * (1 - edge) * dynamic,
        vocal_influence=voice,
    )


def clusters(text):
    """Keep Cyrillic combining accents with their base, never track through them."""
    result = []
    for char in unicodedata.normalize("NFC", text):
        if unicodedata.combining(char) and result:
            result[-1] += char
        else:
            result.append(char)
    return result


def positions(text, font, tracking):
    """Native pair kerning, plus controlled tracking; used by both fit and draw."""
    items = clusters(text)
    x, output = 0., []
    for index, item in enumerate(items):
        output.append((item, x))
        advance = font.getlength(item)
        if index + 1 < len(items):
            following = items[index + 1]
            advance += font.getlength(item + following) - font.getlength(item) - font.getlength(following)
            advance += tracking
        x += advance
    return output, x


def variable_font(engine, text, size, design, source_font=None):
    from .typography import NOTO_SANS, NOTO_SERIF, OSWALD, UNBOUNDED

    families = {"humanist": NOTO_SANS, "serif": NOTO_SERIF,
                "condensed": OSWALD, "geometric": UNBOUNDED}
    if source_font is not None and hasattr(source_font,'font_variant'):
        # Coverage was checked on the nominal font. Reuse that face instead of
        # rasterizing every supported character again at the sampling scale.
        font = source_font.font_variant(size=size)
    else:
        font = engine._font(size, (families[design.family], NOTO_SANS), text)
    try:
        values = []
        for axis in font.get_variation_axes():
            name = axis["name"].decode("utf-8", "replace").lower()
            value = design.weight if name == "weight" else 100 * design.width if name == "width" else axis["default"]
            values.append(max(axis["minimum"], min(axis["maximum"], value)))
        font.set_variation_by_axes(values)
    except (AttributeError, OSError, ValueError):
        pass
    return font


def line_mask(engine, text, size, design, accent=False):
    # Transform a local oversampled glyph strip, not an enlarged cover. This
    # preserves fractional kerning and smooth diagonal stems after shearing.
    nominal_size = size
    sample_scale = 3
    layout_font = variable_font(engine, text, nominal_size, design)
    size *= sample_scale
    font = variable_font(engine, text, size, design, source_font=layout_font)
    tracking = size * design.tracking
    items, advance = positions(text, font, tracking)
    bounds = font.getbbox(text)
    pad = max(6 * sample_scale, round(size * .14))
    mask = Image.new("L", (max(1, math.ceil(advance + pad * 2 + size * .25)),
                           max(1, bounds[3] - bounds[1] + pad * 2)), 0)
    draw = ImageDraw.Draw(mask)
    for item, x in items:
        draw.text((pad + x, pad - bounds[1]), item, font=font, fill=255)
    # Extend a single suitable crossbar/terminal on the emphatic line. The
    # extension is bounded by tracking and does not touch another character.
    extension = 0
    if accent and design.terminal_extension > .008 and nominal_size >= 35:
        for item, x in items:
            if item in "TТFГ":
                box = font.getbbox(item)
                length = min(size * design.terminal_extension, tracking * .65)
                yy = pad - bounds[1] + box[1] + max(sample_scale, size * .025)
                xx = pad + x + box[2] - sample_scale
                draw.line((xx - 2 * sample_scale, yy, xx + length, yy), fill=255,
                          width=max(sample_scale, round(size * design.weight / 19000)))
                extension = round(length / sample_scale, 2)
                break
    # Mild contour rounding on soft titles, capped below one output pixel.
    # No displacement maps, jitter, per-character rotation or destroyed counters.
    if design.angularity < .36 and nominal_size >= 35:
        mask = mask.filter(ImageFilter.GaussianBlur(sample_scale * .30 * (1 - design.angularity)))
    # A bounded affine proportion/slant change affects every glyph consistently.
    # Noto width axis already adjusts outlines; this extra optical ratio also
    # works for the two families without a width axis.
    optical_width = .97 + (design.width - 1) * .42
    mask = mask.resize((max(1, round(mask.width * optical_width)), mask.height), Image.Resampling.LANCZOS)
    shift = abs(design.slant) * mask.height
    if shift > .2 * sample_scale:
        mask = mask.transform((mask.width + math.ceil(shift), mask.height), Image.Transform.AFFINE,
                              (1, design.slant, -shift if design.slant > 0 else 0, 0, 1, 0),
                              Image.Resampling.BICUBIC)
    # Keep a sample-grid-aligned border so reduction does not clip edge coverage.
    bbox = mask.getbbox()
    if not bbox:
        return Image.new("L", (1, 1)), layout_font, extension
    bbox = (math.floor(bbox[0]/sample_scale)*sample_scale,
            math.floor(bbox[1]/sample_scale)*sample_scale,
            math.ceil(bbox[2]/sample_scale)*sample_scale,
            math.ceil(bbox[3]/sample_scale)*sample_scale)
    mask = mask.crop(bbox)
    mask = mask.resize((mask.width//sample_scale, mask.height//sample_scale), Image.Resampling.LANCZOS)
    bbox = mask.getbbox()
    return mask.crop(bbox) if bbox else Image.new("L", (1, 1)), layout_font, extension


def line_options(text):
    words = text.split()
    yield (text,)
    for count in (2, 3, 4):
        if len(words) < count:
            continue
        # Balanced word boundaries, never drop words or cut short words apart.
        lines, current, remaining = [], [], sum(len(w) + 1 for w in words)
        for index, word in enumerate(words):
            current.append(word)
            slots = count - len(lines)
            if slots > 1 and len(words) - index - 1 >= slots - 1 and sum(len(w) + 1 for w in current) >= remaining / slots:
                line = " ".join(current)
                lines.append(line)
                remaining -= len(line) + 1
                current = []
        if current:
            lines.append(" ".join(current))
        if len(lines) == count:
            yield tuple(lines)


def fit_title(engine, title, design, width, height, canvas_size):
    best = None
    # Search actual transformed masks, including descenders/accents. Binary
    # search bounds the cost for large exports and unusually long titles.
    for lines in line_options(title):
        sizes = range(max(14, round(canvas_size * design.scale)), 9, -2)
        left, right, candidate = 0, len(sizes) - 1, None
        while left <= right:
            middle = (left + right) // 2
            size = sizes[middle]
            emphasis_index = max(range(len(lines)), key=lambda i: len(lines[i]))
            masks, fonts, extensions = [], [], []
            for index, line in enumerate(lines):
                ratio = 1 if len(lines) == 1 or index == emphasis_index else 1 - design.line_contrast
                mask, font, extension = line_mask(engine, line, max(10, round(size * ratio)), design, index == emphasis_index)
                masks.append(mask)
                fonts.append(font)
                extensions.append(extension)
            gap = max(5, round(size * (.16 + .15 * design.openness)))
            total_height = sum(mask.height for mask in masks) + gap * (len(lines) - 1)
            max_width = max(mask.width for mask in masks)
            if max_width <= width and total_height <= height:
                candidate = (size, masks, fonts, extensions, gap)
                right = middle - 1
            else:
                left = middle + 1
        if candidate:
            size, masks, fonts, extensions, gap = candidate
            balance = min(mask.width for mask in masks) / max(mask.width for mask in masks)
            score = size * (1 + .12 * balance) - size * .08 * (len(lines) - 1)
            if best is None or score > best[0]:
                best = (score, lines, masks, fonts, extensions, gap)
    if best is None:
        # Pathological unbroken titles: retain the complete text in a fitted mask.
        mask, font, extension = line_mask(engine, title, max(10, round(canvas_size * .06)), design)
        ratio = min(width / mask.width, height / mask.height)
        mask = mask.resize((max(1, round(mask.width * ratio)), max(1, round(mask.height * ratio))), Image.Resampling.LANCZOS)
        return (title,), [mask], [font], [extension], 5
    return best[1:]


def luminance(rgb):
    rgb = np.asarray(rgb, dtype=float) / 255.
    linear = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    return linear @ np.array([.2126, .7152, .0722])


def ink_for_region(image, box, design, accent):
    pixels = np.asarray(image.crop(box).convert("RGB").resize((48, 48)), dtype=float)
    background = luminance(pixels)
    # Harmonize emotional hue with the artwork; retain a reliable luminance.
    art_hue, art_sat, _ = colorsys.rgb_to_hsv(*(channel / 255 for channel in accent))
    hue = design.hue
    if art_sat > .16:
        delta = ((art_hue - hue + .5) % 1) - .5
        hue = (hue + delta * .70) % 1
    choices = []
    for light in (.94, .08):
        rgb = tuple(round(channel * 255) for channel in colorsys.hls_to_rgb(hue, light, design.saturation))
        level = float(luminance(rgb))
        contrasts = (np.maximum(level, background) + .05) / (np.minimum(level, background) + .05)
        choices.append((float(np.percentile(contrasts, 15)), rgb, level))
    contrast, rgb, level = max(choices)
    return rgb, contrast, (0, 0, 0) if level > .5 else (255, 255, 255)


def select_region(image, width, height, design, subject, protected_boxes=(), placement_override=None,
                  composition_zone=None, composition_alignment=None):
    """Score the actual ink block, not a broad predefined third of the image."""
    size = image.width
    margin = max(8, round(size * .065))
    gray = np.asarray(image.convert("L"))
    edges = np.asarray(image.convert("L").filter(ImageFilter.FIND_EDGES))
    if composition_zone:
        left,top,right,bottom=composition_zone
        alignment=composition_alignment or 'left'
        x=left if alignment=='left' else right-width if alignment=='right' else (left+right-width)//2
        choices=[]
        for y in (top,(top+bottom-height)//2,bottom-height):
            box=(int(x),int(y),int(x+width),int(y+height))
            patch=gray[box[1]:box[3],box[0]:box[2]]
            complexity=float(patch.std()/100+edges[box[1]:box[3],box[0]:box[2]].mean()/70) if patch.size else 10.
            overlap=max((intersection_fraction(box,p) for p in protected_boxes),default=0)
            choices.append((complexity+overlap*100,box,alignment,overlap,complexity))
        return min(choices,key=lambda row:row[0])
    regions = []
    for placement, x in (("top", (size-width)//2), ("bottom", (size-width)//2),
                          ("left", margin), ("right", size-margin-width),
                          ("center", (size-width)//2)):
        if placement_override and placement != placement_override:
            continue
        ys = {"top": (margin,), "bottom": (size-margin-height,),
              "left": (margin, round(size*.36), size-margin-height),
              "right": (margin, round(size*.36), size-margin-height),
              "center": ((size-height)//2,)}[placement]
        for y in ys:
            x, y = max(margin, x), min(max(margin, y), size-margin-height)
            box = (int(x), int(y), int(x+width), int(y+height))
            patch = gray[box[1]:box[3], box[0]:box[2]]
            if patch.size == 0:
                continue
            complexity = float(patch.std() / 100 + edges[box[1]:box[3], box[0]:box[2]].mean() / 70)
            protected = [subject["protected_box"], *protected_boxes]
            overlap = max(intersection_fraction(box, p) for p in protected)
            explicit_overlap = max((intersection_fraction(box, p) for p in protected_boxes), default=0)
            preference = .55 if placement == design.preferred_placement else 0
            score = complexity + overlap * 2.8 + explicit_overlap * 100 - preference
            regions.append((score, box, placement, overlap, complexity))
    return min(regions, key=lambda row: row[0])


def intersection_fraction(a, b):
    return max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1])) / max(1, (a[2]-a[0])*(a[3]-a[1]))


def compose_music_title(engine, image, title, artist, dna, profile=None, show_artist=True,
                        language="unknown", placement_override=None):
    design = design_from_music(dna)
    canvas = image.convert("RGBA")
    size = canvas.width
    title = unicodedata.normalize("NFC", " ".join(title.split()))
    composition_zone=getattr(profile,'composition_zone',None)
    alignment=getattr(profile,'composition_alignment',None)
    # Only local glyph strips are supersampled; the canvas stays at export size.
    fit_width=round(size*.83)
    fit_height=round(size*.34)
    if composition_zone:
        fit_width=composition_zone[2]-composition_zone[0]
        fit_height=composition_zone[3]-composition_zone[1]
        if show_artist and artist.strip():
            fit_height=max(12,round(fit_height*.76))
    lines, masks, fonts, extensions, gap = fit_title(engine, title, design, fit_width, fit_height, size)
    artist_mask = None
    if show_artist and artist.strip():
        artist_design = LetteringDesign(**{**design.to_dict(), "family": "humanist", "weight": 450,
                                           "slant": 0., "tracking": .08, "terminal_extension": 0.})
        artist_mask, _, _ = line_mask(engine, artist.strip(), max(10, round(max(f.size for f in fonts) * .23)), artist_design)
        if artist_mask.width > size*.78:
            ratio = size*.78 / artist_mask.width
            artist_mask = artist_mask.resize((round(artist_mask.width*ratio), max(1, round(artist_mask.height*ratio))), Image.Resampling.LANCZOS)
    height = sum(m.height for m in masks) + gap * (len(masks)-1)
    artist_gap = max(8, round(size*.021))
    if artist_mask is not None:
        height += artist_gap + artist_mask.height
    width = max([m.width for m in masks] + ([artist_mask.width] if artist_mask else []))
    subject = engine._analyze_subject(image, profile)
    if getattr(profile, "candidate_type", "") == "abstract":
        # Abstract artwork has no detected face/object. Protect its estimated
        # focal core, rather than treating all its texture as a single object.
        cx, cy = subject["center"]
        radius = size * .12
        subject["protected_box"] = (cx-radius, cy-radius, cx+radius, cy+radius)
    protected_boxes = tuple(getattr(profile, "protected_boxes", ()) or ())
    if composition_zone:
        available_width=composition_zone[2]-composition_zone[0]
        available_height=composition_zone[3]-composition_zone[1]
        ratio=min(1.,available_width/max(1,width),available_height/max(1,height))
        if ratio<1:
            masks=[m.resize((max(1,round(m.width*ratio)),max(1,round(m.height*ratio))),Image.Resampling.LANCZOS) for m in masks]
            if artist_mask:
                artist_mask=artist_mask.resize((max(1,round(artist_mask.width*ratio)),max(1,round(artist_mask.height*ratio))),Image.Resampling.LANCZOS)
            gap=max(1,round(gap*ratio));artist_gap=max(1,round(artist_gap*ratio))
            height=sum(m.height for m in masks)+gap*(len(masks)-1)+(artist_gap+artist_mask.height if artist_mask else 0)
            width=max([m.width for m in masks]+([artist_mask.width] if artist_mask else []))
    _, box, placement, overlap, complexity = select_region(image, width, height, design, subject, protected_boxes, placement_override,
                                                         composition_zone,alignment)
    # Reduce type before accepting overlap with explicit subject/face bounds.
    for _ in range(4):
        if not protected_boxes or not any(intersection_fraction(box, p) > .005 for p in protected_boxes):
            break
        masks = [m.resize((max(1, round(m.width*.82)), max(1, round(m.height*.82))), Image.Resampling.LANCZOS) for m in masks]
        if artist_mask:
            artist_mask = artist_mask.resize((max(1, round(artist_mask.width*.82)), max(1, round(artist_mask.height*.82))), Image.Resampling.LANCZOS)
        height = sum(m.height for m in masks) + gap*(len(masks)-1) + (artist_gap + artist_mask.height if artist_mask else 0)
        width = max([m.width for m in masks] + ([artist_mask.width] if artist_mask else []))
        _, box, placement, overlap, complexity = select_region(image, width, height, design, subject, protected_boxes, placement_override,
                                                             composition_zone,alignment)
    accent = engine._artistic_accent(image, box) or (128, 128, 128)
    ink, initial_contrast, backing = ink_for_region(image, box, design, accent)
    mask = Image.new("L", canvas.size, 0)
    y = box[1]
    for line in masks + ([artist_mask] if artist_mask else []):
        x = box[0] if placement == "left" else box[2]-line.width if placement == "right" else box[0]+(width-line.width)//2
        mask.paste(line, (x, y))
        y += line.height + (artist_gap if line is masks[-1] else gap)
    # Test contrast at the glyph pixels themselves and add only the necessary
    # local backing. Report contrast after compositing, using linear sRGB.
    alpha = np.asarray(mask)
    glyphs = alpha > 180
    background = np.asarray(canvas.convert("RGB"))[glyphs]
    ink_level = float(luminance(ink))
    glyph_veil=None
    if composition_zone:
        veil_size=min(768,size)
        diameter=max(3,round(veil_size*.025)|1)
        glyph_veil=mask.resize((veil_size,veil_size),Image.Resampling.LANCZOS)
        glyph_veil=glyph_veil.filter(ImageFilter.MaxFilter(diameter)).filter(ImageFilter.GaussianBlur(max(1,veil_size*.012)))
        glyph_veil=glyph_veil.resize(canvas.size,Image.Resampling.LANCZOS)
        coverage=np.asarray(glyph_veil)[glyphs].astype(float)/255
    else:
        coverage=1.
    opacity = 0.
    for opacity in (0., .16, .30, .44, .58, .72, .84, .98):
        effective=np.asarray(coverage)*opacity
        if effective.ndim:
            effective=effective[:,None]
        levels = luminance(background * (1-effective) + np.array(backing)*effective)
        ratios = (np.maximum(ink_level, levels)+.05)/(np.minimum(ink_level, levels)+.05)
        contrast = float(np.percentile(ratios, 5)) if ratios.size else 1.
        if contrast >= (4.6 if composition_zone else 4.5):
            break
    if opacity:
        if glyph_veil is not None:
            veil=glyph_veil.point(lambda a:round(a*opacity))
        else:
            veil = Image.new("L", canvas.size, 0)
            d = ImageDraw.Draw(veil)
            pad = round(size*.02)
            d.rounded_rectangle((box[0]-pad, box[1]-pad, box[2]+pad, box[3]+pad), radius=pad, fill=round(opacity*255))
            veil = veil.filter(ImageFilter.GaussianBlur(max(2, size*.009)))
        layer = Image.new("RGBA", canvas.size, (*backing, 0))
        layer.putalpha(veil)
        canvas = Image.alpha_composite(canvas, layer)
    layer = Image.new("RGBA", canvas.size, (*ink, 0))
    layer.putalpha(mask)
    # Verify the actual rendered backing, rather than the opacity estimate.
    levels = luminance(np.asarray(canvas.convert("RGB"))[glyphs])
    ratios = (np.maximum(ink_level, levels)+.05)/(np.minimum(ink_level, levels)+.05)
    contrast = float(np.percentile(ratios, 5)) if ratios.size else 1.
    engine.last_layout = {
        "version": VERSION, "style": "music-conditioned lettering", "design": design.to_dict(),
        "edge_sampling": "local-3x-lanczos",
        "placement": placement, "preferred_placement": design.preferred_placement,
        "language": language, "display_lines": lines, "line_count": len(lines),
        "font_size": max(f.size for f in fonts), "font_path": str(getattr(fonts[0], "path", "fallback")),
        "line_font_sizes": tuple(f.size for f in fonts), "letter_spacing": design.tracking*fonts[0].size,
        "safe_area": box, "ink_bounds": mask.getbbox(), "ink_color": ink,
        "contrast_ratio": round(contrast, 3), "initial_contrast_ratio": round(initial_contrast, 3),
        "adaptive_veil": opacity > 0, "veil_opacity": opacity, "decoration": "none",
        "subject_overlap": round(overlap, 4), "subject_box": subject["box"],
        "subject_detection": "image saliency heuristic; explicit protected_boxes supported",
        "composition_zone": composition_zone,
        "round_safe_radius": getattr(profile,'round_safe_radius',None),
        "veil_style": 'glyph-following' if composition_zone else 'local-area',
        "terminal_extensions": extensions, "local_complexity": round(complexity, 3),
        "title_artist_ratio": max(m.height for m in masks)/artist_mask.height if artist_mask else None,
        "vocal_evidence": "weak mixed-audio proxy; bounded influence, no singer classification",
    }
    return Image.alpha_composite(canvas, layer).convert("RGB")
