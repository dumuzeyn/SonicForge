import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat


FONT_ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2])) / "assets" / "fonts"
NOTO_SANS = str(FONT_ROOT / "NotoSans-Variable.ttf")
NOTO_SERIF = str(FONT_ROOT / "NotoSerif-Variable.ttf")
OSWALD = str(FONT_ROOT / "Oswald-Variable.ttf")
UNBOUNDED = str(FONT_ROOT / "Unbounded-Variable.ttf")

FONT_CANDIDATES = (
    NOTO_SANS,
    "C:/Windows/Fonts/bahnschrift.ttf",
    "C:/Windows/Fonts/seguisb.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
)
ARTISTIC_FONT_CANDIDATES = (
    NOTO_SANS, UNBOUNDED, OSWALD,
    "C:/Windows/Fonts/bahnschrift.ttf",
    "C:/Windows/Fonts/ARIALNB.TTF",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/ariblk.ttf",
)
SERIF_FONT_CANDIDATES = (
    NOTO_SERIF,
    "C:/Windows/Fonts/georgiab.ttf",
    "C:/Windows/Fonts/georgia.ttf",
    "C:/Windows/Fonts/cambriab.ttf",
    "C:/Windows/Fonts/timesbd.ttf",
)

PLACEMENTS = ("top", "bottom", "left", "right", "center")
STYLE_SCALE = {
    "cinematic title": .064,
    "compact title": .058,
    "editorial title": .068,
    "expressive title": .064,
    "artistic title": .150,
    "minimal clean": .060,
    "cinematic": .078,
    "dark dramatic": .080,
    "dreamy": .066,
    "electronic neon": .069,
    "indie editorial": .067,
    "elegant serif": .070,
    "bold modern": .078,
    "editorial": .070,
    "brutalist": .084,
    "elegant": .070,
    "minimal": .058,
    "condensed": .080,
    "wide tracking": .061,
    "retro": .073,
    "futuristic": .071,
    "industrial": .080,
    "dark": .079,
    "intimate": .066,
    "electronic": .071,
    "experimental": .076,
    "serif editorial": .070,
    "geometric sans": .074,
}
STYLE_TRACKING = {
    "minimal clean": .105,
    "cinematic": .045,
    "dark dramatic": .012,
    "dreamy": .080,
    "electronic neon": .070,
    "indie editorial": .035,
    "elegant serif": .025,
    "bold modern": .010,
    "artistic title": .018,
    "editorial": .032,
    "brutalist": .006,
    "elegant": .030,
    "minimal": .110,
    "condensed": .018,
    "wide tracking": .145,
    "retro": .045,
    "futuristic": .095,
    "industrial": .012,
    "dark": .018,
    "intimate": .052,
    "electronic": .082,
    "experimental": .050,
    "serif editorial": .028,
    "geometric sans": .038,
}


class TypographyEngine:
    def __init__(self):
        self.last_layout = {}

    def compose(
        self, image, title, artist="", profile=None, enabled=True, show_artist=True,
        language="unknown", song_profile=None, title_treatment=None,
        placement_override=None,
    ):
        self.last_layout = {}
        if not enabled or not title.strip():
            return image
        canvas = image.convert("RGBA")
        size = canvas.width
        style = self._contextual_style(image, profile, song_profile)
        preferred = getattr(
            profile, "preferred_text_region", getattr(profile, "text_position", "bottom")
        )
        subject = self._analyze_subject(image, profile)
        treatment_lines = tuple(getattr(title_treatment, "display_lines", ()) or ())
        layout_strategy = self._layout_strategy(profile, style, preferred, treatment_lines)
        placement = placement_override or self._placement_for_strategy(
            image, preferred, style, layout_strategy, subject
        )
        scale_intent = getattr(profile, "title_scale_intent", "supporting large")
        width_ratio = .58 if placement in ("left", "right") else .76
        if scale_intent == "dominant":
            width_ratio += .08
        elif scale_intent == "restrained":
            width_ratio -= .10
        max_width = int(size * min(.86, max(.46, width_ratio)))
        max_height = int(size * (.42 if style == "artistic title" else
                                 .34 if len(treatment_lines) > 1 else .22))
        base_scale = STYLE_SCALE.get(style, .088)
        base_scale *= {
            "dominant": 1.22,
            "large": 1.10,
            "supporting large": 1.0,
            "adaptive multiline": .91,
            "restrained": .78,
        }.get(scale_intent, 1.0)
        display_title = self._display_title(title.strip(), style, language)
        font_candidates = self._font_candidates(style)
        tracking_ratio = STYLE_TRACKING.get(style, .025)
        base_font, lines = self._fit(
            display_title, max_width, max_height, size, base_scale,
            font_candidates=font_candidates,
            preferred_lines=treatment_lines,
            tracking_ratio=tracking_ratio,
        )
        treatment_weights = tuple(getattr(title_treatment, "line_emphasis", ()) or ())
        line_weights = self._line_weights(lines, treatment_lines, treatment_weights)
        line_fonts = []
        line_trackings = []
        for line, weight in zip(lines, line_weights):
            maximum = max(12, int(base_font.size * (.82 + .28 * weight)))
            line_tracking = max(.5, round(maximum * tracking_ratio, 2)) if tracking_ratio > 0 else 0
            line_font = self._fit_single_line(
                line, max_width, maximum, max(10, int(size * .022)),
                font_candidates=font_candidates, tracking=line_tracking,
            )
            line_fonts.append(line_font)
            line_trackings.append(
                max(.5, round(line_font.size * tracking_ratio, 2)) if tracking_ratio > 0 else 0
            )
        draw_probe = ImageDraw.Draw(Image.new("L", (4, 4)))
        largest_font = max(line_fonts, key=lambda item: item.size)
        line_gap = max(4, int(largest_font.size * (.16 if style in {"dreamy", "elegant serif"} else .10)))
        boxes = [
            draw_probe.textbbox((0, 0), line, font=line_font, stroke_width=1)
            for line, line_font in zip(lines, line_fonts)
        ]
        title_height = sum(box[3] - box[1] for box in boxes) + line_gap * max(0, len(lines) - 1)
        artist_text = self._artist_display(artist, style) if show_artist and artist.strip() else ""
        artist_ratio = .24 if scale_intent == "dominant" else .29
        if getattr(profile, "artist_role", "").startswith("prominent"):
            artist_ratio = .36
        artist_tracking = max(1, int(largest_font.size * .055)) if artist_text else 0
        artist_font = self._fit_single_line(
            artist_text,
            max_width,
            max(12, int(largest_font.size * artist_ratio)),
            max(10, int(size * .018)),
            font_candidates=font_candidates,
            tracking=artist_tracking,
        )
        artist_height = int(artist_font.size * 1.55) if artist_text else 0
        block_height = title_height + artist_height
        line_widths = [
            self._text_length(line, line_font, tracking)
            for line, line_font, tracking in zip(lines, line_fonts, line_trackings)
        ]
        artist_width = self._text_length(artist_text, artist_font, artist_tracking) if artist_text else 0
        block_width = max([*line_widths, artist_width, size * .16])
        x, y, anchor = self._origin(placement, size, block_width, block_height)
        block_box = self._block_box(x, y, block_width, block_height, anchor, size)
        fill, stroke, veil, local_context = self._colors(
            image, block_box, force_light=style == "artistic title"
        )
        artistic_accent = self._artistic_accent(image, block_box)
        if artistic_accent:
            tint = .15 if style in {"artistic title", "indie editorial", "electronic neon"} else .06
            fill = tuple(round(fill[index] * (1 - tint) + artistic_accent[index] * tint) for index in range(3)) + (255,)
        decoration = self._decoration_policy(
            style, profile, local_context, layout_strategy
        )

        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        if veil:
            veil_mask = Image.new("L", canvas.size, 0)
            mask_draw = ImageDraw.Draw(veil_mask)
            mask_draw.rounded_rectangle(block_box, radius=int(size * .035), fill=veil[3])
            veil_mask = veil_mask.filter(ImageFilter.GaussianBlur(max(3, int(size * .028))))
            veil_layer = Image.new("RGBA", canvas.size, (*veil[:3], 0))
            veil_layer.putalpha(veil_mask)
            overlay = Image.alpha_composite(overlay, veil_layer)
            draw = ImageDraw.Draw(overlay)
        if artistic_accent and decoration == "glow":
            accent_mask = Image.new("L", canvas.size, 0)
            accent_draw = ImageDraw.Draw(accent_mask)
            accent_y = y
            for line, box, line_font, tracking, line_width in zip(
                lines, boxes, line_fonts, line_trackings, line_widths
            ):
                line_height = box[3] - box[1]
                line_x = self._line_x(x, line_width, anchor, size)
                self._draw_tracked(
                    accent_draw,
                    (line_x, accent_y - box[1]),
                    line,
                    font=line_font,
                    fill=120,
                    tracking=tracking,
                )
                accent_y += line_height + line_gap
            if artist_text:
                artist_width = self._text_length(artist_text, artist_font, artist_tracking)
                artist_x = self._line_x(x, artist_width, anchor, size)
                self._draw_tracked(
                    accent_draw,
                    (artist_x, accent_y + artist_font.size * .25),
                    artist_text,
                    font=artist_font,
                    fill=125,
                    tracking=artist_tracking,
                )
            accent_mask = accent_mask.filter(ImageFilter.GaussianBlur(max(2, int(size * .009))))
            accent_layer = Image.new("RGBA", canvas.size, (*artistic_accent, 0))
            accent_layer.putalpha(accent_mask)
            overlay = Image.alpha_composite(overlay, accent_layer)
            draw = ImageDraw.Draw(overlay)
        if artistic_accent and decoration not in {"none", "glow"}:
            self._draw_style_accent(
                draw, decoration, block_box, y, title_height, artistic_accent, size, anchor
            )
        cursor_y = y
        emphasis_words = tuple(getattr(title_treatment, "emphasis_words", ()) or ())
        emphasis_fill = None
        if artistic_accent and emphasis_words and local_context["accent_contrast"] >= 3.2:
            emphasis_fill = (*artistic_accent, 255)
        stroke_width = 0 if local_context["contrast_ratio"] >= 5.0 else 1
        if style in {"dark dramatic", "bold modern"} and local_context["contrast_ratio"] < 4.2:
            stroke_width = max(1, size // 620)
        for line, box, line_font, tracking, line_width in zip(
            lines, boxes, line_fonts, line_trackings, line_widths
        ):
            line_height = box[3] - box[1]
            line_x = self._line_x(x, line_width, anchor, size)
            self._draw_tracked(
                draw,
                (line_x, cursor_y - box[1]),
                line,
                font=line_font,
                fill=fill,
                stroke_width=stroke_width,
                stroke_fill=stroke,
                tracking=tracking,
                emphasis_words=emphasis_words,
                emphasis_fill=emphasis_fill,
            )
            cursor_y += line_height + line_gap
        if artist_text:
            artist_width = self._text_length(artist_text, artist_font, artist_tracking)
            artist_x = self._line_x(x, artist_width, anchor, size)
            self._draw_tracked(
                draw,
                (artist_x, cursor_y + artist_font.size * .25),
                artist_text,
                font=artist_font,
                fill=(*fill[:3], 225),
                stroke_width=0 if local_context["contrast_ratio"] >= 4.4 else 1,
                stroke_fill=stroke,
                tracking=artist_tracking,
            )
        self.last_layout = {
            "placement": placement,
            "preferred_placement": preferred,
            "style": style,
            "layout_strategy": layout_strategy,
            "language": language,
            "font_size": largest_font.size,
            "line_font_sizes": tuple(font.size for font in line_fonts),
            "font_path": str(getattr(largest_font, "path", "system fallback")),
            "letter_spacing": max(line_trackings, default=0),
            "line_letter_spacing": tuple(line_trackings),
            "line_count": len(lines),
            "display_lines": tuple(lines),
            "safe_area": tuple(round(value, 1) for value in block_box),
            "adaptive_veil": bool(veil),
            "decoration": decoration,
            "background_accent": artistic_accent,
            "local_luminance": round(local_context["luminance"], 2),
            "local_saturation": round(local_context["saturation"], 2),
            "local_complexity": round(local_context["complexity"], 3),
            "contrast_ratio": round(local_context["contrast_ratio"], 2),
            "subject_position": subject["position"],
            "subject_box": tuple(round(value, 1) for value in subject["box"]),
            "subject_overlap": round(self._box_overlap(block_box, subject["protected_box"]), 4),
            "intended_adherence": placement == preferred,
            "title_scale_intent": scale_intent,
            "title_artist_ratio": round(largest_font.size / max(1, artist_font.size), 3) if artist_text else None,
            "title_role": getattr(profile, "title_role", "primary"),
            "artist_role": getattr(profile, "artist_role", "secondary credit"),
            "text_image_relationship": getattr(profile, "text_image_relationship", ""),
            "song_typography_hint": getattr(song_profile, "typography_mood_hint", ""),
            "title_confidence": getattr(title_treatment, "confidence", None),
            "case_strategy": getattr(title_treatment, "case_strategy", "canonical"),
            "emphasis_words": emphasis_words,
        }
        return Image.alpha_composite(canvas, overlay).convert("RGB")

    def compose_candidates(self, image, title, max_candidates=3, **kwargs):
        """Render distinct image-aware placements so final scoring can choose one."""
        profile = kwargs.get("profile")
        preferred = getattr(
            profile, "preferred_text_region", getattr(profile, "text_position", "bottom")
        )
        subject = self._analyze_subject(image, profile)
        safest = self._safe_placement(image, preferred, subject=subject)
        opposite = {
            "left": "right", "right": "left", "top": "bottom",
            "bottom": "top", "center": safest,
        }.get(preferred, safest)
        order = tuple(dict.fromkeys((safest, preferred, opposite, "top", "bottom", "left", "right")))
        rendered = []
        for placement in order[:max(1, int(max_candidates))]:
            cover = self.compose(
                image, title, placement_override=placement, **kwargs
            )
            rendered.append((cover, dict(self.last_layout)))
        return rendered

    @staticmethod
    def _display_title(title, style, language):
        if language == "mixed":
            return title.replace(" x ", " × ").replace(" X ", " × ")
        return title.replace("_", " ")

    @staticmethod
    def _artist_display(artist, style):
        value = artist.strip()
        if style in {"electronic neon", "bold modern", "dark dramatic"}:
            return value.upper()
        return value

    @staticmethod
    def _contextual_style(image, concept, song_profile):
        requested = getattr(concept, "typography_style", "compact title")
        if getattr(concept, "typography_locked", False):
            return requested
        family = getattr(concept, "candidate_type", "")
        narrative = getattr(song_profile, "narrative_mode", "")
        mood = getattr(song_profile, "mood", "")
        rgb = image.convert("RGB")
        hsv = ImageStat.Stat(rgb.convert("HSV"))
        brightness = ImageStat.Stat(rgb.convert("L")).mean[0]
        saturation = hsv.mean[1]
        if family == "minimal":
            return "minimal"
        if narrative == "rhythmic_mechanical" or (saturation > 92 and getattr(song_profile, "energy", 0) > .66):
            return "futuristic" if family == "surreal" else "electronic"
        if narrative in {"aggressive", "epic"} or (brightness < 82 and getattr(song_profile, "drama", 0) > .68):
            return "brutalist" if family == "editorial" else "industrial"
        if narrative in {"dreamlike", "luminous"}:
            return "dreamy" if family in {"surreal", "abstract"} else "elegant"
        if narrative == "intimate" or mood in {"romantic", "melancholic"}:
            return "serif editorial" if family in {"portrait", "symbolic", "cinematic"} else "intimate"
        if family == "editorial":
            return "editorial"
        if family == "portrait":
            return "elegant"
        if family == "symbolic" and getattr(song_profile, "energy", 0) > .62:
            return "geometric sans"
        return requested if requested in STYLE_SCALE else "cinematic"

    @staticmethod
    def _layout_strategy(concept, style, preferred, treatment_lines):
        composition = getattr(concept, "composition", "")
        if style == "artistic title":
            return "centered"
        if style == "minimal clean" and len(treatment_lines) <= 1:
            return "minimal_caption"
        if len(treatment_lines) > 1:
            return "split_lines"
        if preferred in {"left", "right"} or composition in {"editorial_poster", "asymmetrical_scene", "strong_negative_space"}:
            return "corner_anchored"
        if composition in {"surreal_artwork", "double_exposure"} and style == "dreamy":
            return "centered"
        return preferred if preferred in {"top", "bottom"} else "bottom"

    def _placement_for_strategy(self, image, preferred, style, strategy, subject=None):
        if style == "artistic title" or strategy == "centered":
            return self._safe_placement(image, "center", subject=subject)
        if strategy == "minimal_caption":
            return self._safe_placement(
                image, preferred or "bottom", allowed=("bottom", "left", "right"), subject=subject
            )
        if strategy == "corner_anchored":
            corner = preferred if preferred in {"left", "right"} else "left"
            return self._safe_placement(image, corner, allowed=("left", "right"), subject=subject)
        return self._safe_placement(image, preferred, subject=subject)

    @staticmethod
    def _font_candidates(style):
        if style in {"artistic title", "brutalist", "condensed", "futuristic", "industrial", "electronic", "experimental"}:
            return ARTISTIC_FONT_CANDIDATES
        if style in {"elegant serif", "elegant", "intimate", "serif editorial", "retro"}:
            return SERIF_FONT_CANDIDATES + FONT_CANDIDATES
        if style in {"cinematic", "bold modern", "dark dramatic", "electronic neon"}:
            return ARTISTIC_FONT_CANDIDATES
        return FONT_CANDIDATES

    @staticmethod
    def _draw_style_accent(draw, decoration, block_box, y, title_height, accent, size, anchor):
        left, _top, right, _bottom = block_box
        color = (*accent, 205)
        shadow = (8, 10, 14, 135)
        rule_y = int(y + title_height + size * .014)
        if decoration == "editorial_rule":
            width = min((right - left) * .44, size * .28)
            center = (left + right) / 2
            line = (int(center - width / 2), rule_y, int(center + width / 2), rule_y)
            draw.line((line[0], line[1] + 2, line[2], line[3] + 2), fill=shadow, width=max(2, size // 260))
            draw.line(line, fill=color, width=max(2, size // 300))
        elif decoration == "editorial_bar":
            bar_x = int(right - size * .018) if anchor == "ra" else int(left + size * .018)
            draw.line(
                (bar_x, int(y), bar_x, int(y + title_height)),
                fill=color,
                width=max(3, size // 135),
            )
        elif decoration == "impact_bar":
            bar_height = max(3, size // 110)
            draw.rectangle(
                (int(left + size * .02), rule_y, int(right - size * .02), rule_y + bar_height),
                fill=(*accent, 150),
            )

    def _safe_placement(self, image, preferred, allowed=None, subject=None):
        gray = image.convert("L")
        edge = gray.filter(ImageFilter.FIND_EDGES)
        size = image.width
        regions = {
            "top": (int(size*.06), int(size*.05), int(size*.94), int(size*.36)),
            "bottom": (int(size*.06), int(size*.64), int(size*.94), int(size*.95)),
            "left": (int(size*.05), int(size*.10), int(size*.70), int(size*.62)),
            "right": (int(size*.30), int(size*.10), int(size*.95), int(size*.62)),
            "center": (int(size*.12), int(size*.34), int(size*.88), int(size*.66)),
        }
        scores = {}
        for placement, box in regions.items():
            local_gray = gray.crop(box)
            local_edge = edge.crop(box)
            variation = ImageStat.Stat(local_gray).stddev[0]
            edge_level = ImageStat.Stat(local_edge).mean[0]
            score = 100 - variation * .72 - edge_level * 1.15
            if placement == preferred:
                score += 22
            if placement == "center":
                score -= 9
            if subject:
                overlap = self._box_overlap(box, subject["protected_box"])
                score -= overlap * 95
            scores[placement] = score
        return max(allowed or PLACEMENTS, key=lambda value: scores[value])

    @staticmethod
    def _line_weights(lines, treatment_lines, treatment_weights):
        if not treatment_lines or not treatment_weights:
            return tuple(1.0 for _ in lines)
        output = []
        for line in lines:
            tokens = set(re.findall(r"[\wЁё]+", line.lower()))
            candidates = []
            for source, weight in zip(treatment_lines, treatment_weights):
                source_tokens = set(re.findall(r"[\wЁё]+", source.lower()))
                if tokens & source_tokens:
                    candidates.append(float(weight))
            output.append(max(candidates, default=.82))
        return tuple(output)

    @staticmethod
    def _analyze_subject(image, concept=None):
        sample = image.convert("RGB").resize((64, 64), Image.Resampling.LANCZOS)
        gray = sample.convert("L")
        edges = gray.filter(ImageFilter.FIND_EDGES)
        border_pixels = []
        for x in range(64):
            border_pixels.extend((sample.getpixel((x, 0)), sample.getpixel((x, 63))))
        for y in range(1, 63):
            border_pixels.extend((sample.getpixel((0, y)), sample.getpixel((63, y))))
        border = tuple(
            sorted(pixel[channel] for pixel in border_pixels)[len(border_pixels) // 2]
            for channel in range(3)
        )
        values = []
        for y in range(64):
            for x in range(64):
                if x < 3 or x > 60 or y < 3 or y > 60:
                    continue
                red, green, blue = sample.getpixel((x, y))
                distance = ((red-border[0])**2 + (green-border[1])**2 + (blue-border[2])**2) ** .5
                edge = edges.getpixel((x, y))
                center_prior = max(0.0, 1.0 - (((x-31.5)/40)**2 + ((y-31.5)/40)**2))
                values.append((edge * .58 + distance * .36 + center_prior * 12, x, y))
        values.sort(reverse=True)
        selected = values[:max(64, len(values) // 8)]
        total = sum(item[0] for item in selected) or 1.0
        center_x = sum(item[0] * item[1] for item in selected) / total
        center_y = sum(item[0] * item[2] for item in selected) / total
        xs = sorted(item[1] for item in selected)
        ys = sorted(item[2] for item in selected)
        left, right = xs[len(xs)//12], xs[-len(xs)//12 - 1]
        top, bottom = ys[len(ys)//12], ys[-len(ys)//12 - 1]
        scale_x, scale_y = image.width / 64, image.height / 64
        box = (left*scale_x, top*scale_y, (right+1)*scale_x, (bottom+1)*scale_y)
        if center_x < 25:
            position = "left"
        elif center_x > 39:
            position = "right"
        else:
            position = "center"
        protected = box
        if getattr(concept, "candidate_type", "") == "portrait":
            height = box[3] - box[1]
            protected = (box[0], box[1], box[2], box[1] + height * .62)
        return {
            "position": position,
            "center": (center_x*scale_x, center_y*scale_y),
            "box": box,
            "protected_box": protected,
        }

    @staticmethod
    def _box_overlap(left, right):
        x1, y1 = max(left[0], right[0]), max(left[1], right[1])
        x2, y2 = min(left[2], right[2]), min(left[3], right[3])
        intersection = max(0.0, x2-x1) * max(0.0, y2-y1)
        area = max(1.0, (left[2]-left[0]) * (left[3]-left[1]))
        return intersection / area

    @staticmethod
    def _decoration_policy(style, concept, local_context, layout_strategy):
        complexity = local_context["complexity"]
        relationship = getattr(concept, "text_image_relationship", "").lower()
        if style in {"electronic neon", "electronic", "futuristic"} and local_context["luminance"] < 145 and complexity < .72:
            return "glow"
        if style in {"indie editorial", "editorial", "serif editorial"} and "editorial counterweight" in relationship:
            return "editorial_bar" if layout_strategy == "corner_anchored" else "editorial_rule"
        if style in {"bold modern", "dark dramatic", "brutalist", "industrial", "dark"} and getattr(concept, "title_scale_intent", "") == "dominant":
            return "impact_bar"
        return "none"

    @staticmethod
    def _origin(placement, size, width, height):
        if placement == "left":
            return size * .07, size * .12, "la"
        if placement == "right":
            return size * .93, size * .12, "ra"
        if placement == "top":
            return size * .50, size * .065, "ma"
        if placement == "bottom":
            return size * .50, size - height - size * .075, "ma"
        return size * .50, size * .50 - height * .50, "ma"

    @staticmethod
    def _line_x(x, line_width, anchor, size):
        if anchor == "ma":
            return (size - line_width) / 2
        if anchor == "ra":
            return x - line_width
        return x

    @staticmethod
    def _block_box(x, y, width, height, anchor, size):
        padding_x = size * .025
        padding_y = size * .018
        if anchor == "ma":
            left, right = x - width / 2 - padding_x, x + width / 2 + padding_x
        elif anchor == "ra":
            left, right = x - width - padding_x, x + padding_x
        else:
            left, right = x - padding_x, x + width + padding_x
        return (
            max(0, left),
            max(0, y - padding_y),
            min(size, right),
            min(size, y + height + padding_y),
        )

    @staticmethod
    def _colors(image, block_box, force_light=False):
        crop = image.crop(tuple(int(value) for value in block_box)).convert("RGB")
        gray = crop.convert("L")
        stat = ImageStat.Stat(gray)
        mean = stat.mean[0]
        variation = stat.stddev[0]
        hsv = ImageStat.Stat(crop.convert("HSV"))
        saturation = hsv.mean[1]
        edge_level = ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).mean[0]
        complexity = min(1.0, variation / 85 * .58 + edge_level / 42 * .42)
        background_luminance = mean / 255
        light_luminance = 246 / 255
        dark_luminance = 20 / 255
        light_contrast = (light_luminance + .05) / (background_luminance + .05) if light_luminance >= background_luminance else (background_luminance + .05) / (light_luminance + .05)
        dark_contrast = (background_luminance + .05) / (dark_luminance + .05) if background_luminance >= dark_luminance else (dark_luminance + .05) / (background_luminance + .05)
        if force_light:
            fill = (250, 250, 248, 255)
            stroke = (5, 7, 11, 145)
            veil = (5, 7, 12, 42) if complexity > .72 else None
        elif light_contrast >= dark_contrast:
            fill = (246, 246, 242, 255)
            stroke = (8, 10, 14, 210)
            veil = (5, 7, 12, 48) if complexity > .78 else None
        else:
            fill = (18, 20, 24, 255)
            stroke = (255, 255, 255, 210)
            veil = (255, 255, 255, 44) if complexity > .78 else None
        text_luminance = sum(fill[:3]) / (3 * 255)
        contrast_ratio = (max(background_luminance, text_luminance) + .05) / (min(background_luminance, text_luminance) + .05)
        accent = TypographyEngine._artistic_accent(image, block_box)
        accent_luminance = sum(accent or fill[:3]) / (3 * 255)
        accent_contrast = (max(background_luminance, accent_luminance) + .05) / (min(background_luminance, accent_luminance) + .05)
        context = {
            "luminance": mean,
            "saturation": saturation,
            "complexity": complexity,
            "contrast_ratio": contrast_ratio,
            "accent_contrast": accent_contrast,
        }
        return fill, stroke, veil, context

    @staticmethod
    def _artistic_accent(image, block_box):
        crop = image.crop(tuple(int(value) for value in block_box)).convert("RGB").resize((48, 48))
        colors = crop.quantize(colors=10, method=Image.Quantize.MEDIANCUT).convert("RGB").getcolors(48 * 48)
        if not colors:
            return None

        def score(item):
            count, (red, green, blue) = item
            high, low = max(red, green, blue), min(red, green, blue)
            saturation = high - low
            brightness = (red + green + blue) / 3
            usable_light = 1.0 - min(abs(brightness - 145) / 180, .75)
            return saturation * usable_light * (1.0 + count / (48 * 48))

        return max(colors, key=score)[1]

    def _fit(
        self, text, max_width, max_height, canvas_size, base_scale,
        font_candidates=None, preferred_lines=(), tracking_ratio=0.0,
    ):
        words = text.replace("_", " ").split()
        minimum = int(canvas_size * .018)
        maximum = int(canvas_size * base_scale)
        whole_words = set(words)
        for font_size in range(maximum, minimum - 1, -2):
            font = self._font(font_size, font_candidates, text)
            tracking = max(.5, round(font_size * tracking_ratio, 2)) if tracking_ratio > 0 else 0
            layouts = []
            if preferred_lines:
                preferred_layout = []
                for preferred in preferred_lines:
                    preferred_layout.extend(self._wrap(preferred.split(), font, max_width, tracking))
                layouts.append(preferred_layout)
            layouts.append(self._wrap(words, font, max_width, tracking))
            draw = ImageDraw.Draw(Image.new("L", (4, 4)))
            fitting = []
            for preference, lines in enumerate(layouts):
                boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
                height = sum(box[3] - box[1] for box in boxes) + max(0, len(lines)-1) * int(font_size*.11)
                widths = [self._text_length(line, font, tracking) for line in lines]
                # "Im", "Я", "So" etc. are real words, not broken fragments.
                # A suggested editorial break must never force the whole title
                # down to the minimum font size. Try automatic wrapping too.
                fragment = any(len(line.strip()) <= 2 and line.strip() not in whole_words
                               and line.strip() not in {"×", "X", "&"} for line in lines)
                if not lines or len(lines) > 4 or height > max_height or fragment or max(widths) > max_width:
                    continue
                short_orphans = sum(len(line.strip()) <= 2 for line in lines) if len(lines) > 1 else 0
                imbalance = (max(widths) - min(widths)) / max_width
                fitting.append((short_orphans, imbalance + preference * .02, lines))
            if fitting:
                return font, min(fitting, key=lambda item: item[:2])[2]
        font = self._font(minimum, font_candidates, text)
        tracking = max(.5, round(minimum * tracking_ratio, 2)) if tracking_ratio > 0 else 0
        return font, self._wrap(words, font, max_width, tracking)

    def _fit_single_line(self, text, max_width, maximum, minimum, font_candidates=None, tracking=0):
        for size in range(maximum, minimum - 1, -1):
            font = self._font(size, font_candidates, text)
            if self._text_length(text, font, tracking) <= max_width:
                return font
        return self._font(minimum, font_candidates, text)

    def _wrap(self, words, font, max_width, tracking=0):
        expanded = []
        for word in words or [""]:
            if self._text_length(word, font, tracking) <= max_width:
                expanded.append(word)
                continue
            expanded.extend(self._split_word(word, font, max_width, tracking))
        lines = []
        current = ""
        for word in expanded:
            candidate = f"{current} {word}".strip()
            if current and self._text_length(candidate, font, tracking) > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    def _split_word(self, word, font, max_width, tracking=0):
        pieces = []
        current = ""
        for character in word:
            candidate = current + character
            if current and self._text_length(candidate, font, tracking) > max_width:
                pieces.append(current)
                current = character
            else:
                current = candidate
        if current:
            pieces.append(current)
        return pieces

    @staticmethod
    def _text_length(text, font, tracking=0):
        draw = ImageDraw.Draw(Image.new("L", (4, 4)))
        return sum(float(draw.textlength(character, font=font)) for character in text) + max(0, len(text) - 1) * tracking

    @classmethod
    def _draw_tracked(
        cls, draw, position, text, font, fill, tracking=0, stroke_width=0,
        stroke_fill=None, emphasis_words=(), emphasis_fill=None,
    ):
        x, y = position
        emphasis = {str(word).lower().strip(".,:;!?()[]") for word in emphasis_words}
        for token in re_split_words(text):
            token_key = token.lower().strip(".,:;!?()[]")
            token_fill = emphasis_fill if token_key in emphasis and emphasis_fill else fill
            for character in token:
                draw.text(
                    (x, y), character, font=font, fill=token_fill,
                    stroke_width=stroke_width, stroke_fill=stroke_fill,
                )
                x += cls._text_length(character, font) + tracking

    @staticmethod
    def _font(size, candidates=None, text=""):
        for candidate in candidates or FONT_CANDIDATES:
            if Path(candidate).exists():
                font = ImageFont.truetype(candidate, size)
                if TypographyEngine._supports_text(font, text):
                    try:
                        axes = font.get_variation_axes()
                        values = [
                            min(axis["maximum"], max(axis["minimum"], 560))
                            if axis["name"].lower() == b"weight" else axis["default"]
                            for axis in axes
                        ]
                        font.set_variation_by_axes(values)
                    except (AttributeError, OSError, ValueError):
                        pass
                    return font
        return ImageFont.load_default()

    @staticmethod
    def _supports_text(font, text):
        required = set(text or "") | {"Ё", "ё"}
        for character in required:
            if character.isspace():
                continue
            try:
                if font.getmask(character).getbbox() is None:
                    return False
            except (OSError, ValueError):
                return False
        return True


def re_split_words(text):
    return re.findall(r"\s+|[^\s]+", text)
