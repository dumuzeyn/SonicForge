from __future__ import annotations

import re
from collections import Counter

from .models import AudioAnalysis, VisualDNA, VisualPlan
from .utils import clamp, scale


POSITIVE_CUES = ("joy", "happy", "love", "sun", "summer", "счаст", "рад", "люб", "солн", "лето")
NEGATIVE_CUES = ("sad", "death", "lost", "pain", "hell", "груст", "смерт", "потер", "боль", "ад")
INTENSE_CUES = ("fire", "battle", "rage", "storm", "огонь", "бой", "ярост", "гроза")
CALM_CUES = ("sleep", "calm", "quiet", "sea", "сон", "тихо", "спокой", "море")


def build_visual_dna(
    analysis: AudioAnalysis,
    metadata_text: str = "",
    lyrics: str = "",
    mood_override: str = "auto",
) -> VisualDNA:
    brightness = clamp(
        scale(analysis.spectral_centroid_hz, 500.0, 4_800.0) * 0.68
        + analysis.high_energy * 0.32
    )
    warmth = clamp(
        analysis.bass_energy * 0.45
        + analysis.mid_energy * 0.30
        + (1.0 - brightness) * 0.25
    )
    roughness = clamp(
        analysis.spectral_flatness * 0.28
        + analysis.spectral_flux * 0.25
        + analysis.zero_crossing_rate * 0.17
        + analysis.attack_strength * 0.30
    )
    dissonance = clamp(
        analysis.harmonic_complexity * 0.38
        + analysis.spectral_flatness * 0.26
        + analysis.chord_change_rate * 0.21
        + (1.0 - analysis.key_strength) * 0.15
    )
    absolute_energy = clamp(scale(analysis.rms_dbfs, -42.0, -9.0))
    tempo_energy = clamp(scale(analysis.tempo, 55.0, 185.0)) * analysis.tempo_confidence
    arousal = clamp(
        absolute_energy * 0.27
        + analysis.rhythmic_density * 0.20
        + tempo_energy * 0.13
        + analysis.attack_strength * 0.18
        + analysis.spectral_flux * 0.12
        + analysis.section_contrast * 0.10
    )
    tension = clamp(
        dissonance * 0.32
        + roughness * 0.25
        + analysis.section_contrast * 0.18
        + analysis.attack_strength * 0.15
        + analysis.largest_transition * 0.10
    )
    audio_valence = clamp(
        0.50
        + (0.13 if analysis.mode == "major" else -0.10 if analysis.mode == "minor" else 0.0)
        + warmth * 0.18
        + brightness * 0.08
        - dissonance * 0.17
        - tension * 0.12
    )
    metadata_valence, metadata_arousal, metadata_confidence = _metadata_emotion(
        f"{metadata_text} {lyrics[:4000]}"
    )
    semantic_weight = min(0.18, metadata_confidence * 0.18)
    valence = clamp(audio_valence * (1.0 - semantic_weight) + metadata_valence * semantic_weight)
    arousal = clamp(arousal * (1.0 - semantic_weight) + metadata_arousal * semantic_weight)
    if mood_override not in ("", "auto", None):
        valence, arousal, tension = _apply_mood_override(valence, arousal, tension, mood_override)

    dynamic_complexity = clamp(
        analysis.relative_dynamic_range * 0.32
        + analysis.section_contrast * 0.31
        + analysis.largest_transition * 0.19
        + min(1.0, analysis.section_count / 7.0) * 0.18
    )
    aggressiveness = clamp(arousal * 0.34 + tension * 0.29 + roughness * 0.22 + analysis.attack_strength * 0.15)
    relaxation = clamp(1.0 - (arousal * 0.44 + tension * 0.34 + roughness * 0.22))
    acousticness = clamp(
        analysis.harmonic_ratio * 0.38
        + (1.0 - analysis.spectral_flatness) * 0.24
        + (1.0 - analysis.beat_regularity) * 0.14
        + (1.0 - analysis.high_energy) * 0.12
        + analysis.crest_factor_db / 24.0 * 0.12
    )
    electronicness = clamp(
        analysis.beat_regularity * 0.28
        + analysis.spectral_flatness * 0.24
        + analysis.high_energy * 0.18
        + analysis.rhythmic_density * 0.18
        + analysis.percussive_ratio * 0.12
    )
    vocal_probability = clamp(
        analysis.mid_energy * 0.44
        + analysis.harmonic_ratio * 0.28
        + (1.0 - analysis.spectral_flatness) * 0.18
        - analysis.bass_energy * 0.10
    )

    return VisualDNA(
        tempo=analysis.tempo,
        tempo_confidence=analysis.tempo_confidence,
        valence=valence,
        arousal=arousal,
        tension=tension,
        aggressiveness=aggressiveness,
        relaxation=relaxation,
        brightness=brightness,
        darkness=clamp(1.0 - brightness * 0.72 - valence * 0.18 + tension * 0.15),
        warmth=warmth,
        roughness=roughness,
        dissonance=dissonance,
        spectral_flatness=analysis.spectral_flatness,
        bass_mass=clamp(analysis.bass_energy * 1.35),
        rhythmic_density=analysis.rhythmic_density,
        rhythmic_regularity=analysis.beat_regularity,
        dynamic_complexity=dynamic_complexity,
        harmonic_complexity=analysis.harmonic_complexity,
        chord_change_rate=analysis.chord_change_rate,
        acousticness=acousticness,
        electronicness=electronicness,
        vocal_probability=vocal_probability,
        key=analysis.key,
        mode=analysis.mode,
        key_strength=analysis.key_strength,
        section_count=analysis.section_count,
        section_contrast=analysis.section_contrast,
        attack_strength=analysis.attack_strength,
        spectral_flux=analysis.spectral_flux,
        spectral_centroid=clamp(scale(analysis.spectral_centroid_hz, 350.0, 6_000.0)),
        spectral_rolloff=clamp(scale(analysis.spectral_rolloff_hz, 1_200.0, 10_000.0)),
        spectral_contrast=analysis.spectral_contrast,
        zero_crossing_rate=analysis.zero_crossing_rate,
        absolute_loudness=absolute_energy,
        crest_factor=clamp(scale(analysis.crest_factor_db, 3.0, 22.0)),
        original_dynamic_range=clamp(scale(analysis.dynamic_range_db, 2.0, 30.0)),
        energy_curve=analysis.energy_curve,
        peak_position=analysis.peak_position,
        largest_transition=analysis.largest_transition,
        climax_position=analysis.climax_position,
        intro_energy=analysis.intro_energy,
        ending_energy=analysis.ending_energy,
        fingerprint=analysis.fingerprint,
        activity_curve=analysis.activity_curve,
    )


def create_song_description(dna: VisualDNA, language: str = "en", lyrics: str = "") -> str:
    lyric_cue = _lyric_cue(lyrics)
    if language == "ru":
        mood = _choice(dna.valence, ("мрачная", "сдержанная", "светлая"), (0.38, 0.64))
        force = _choice(dna.arousal, ("спокойная", "подвижная", "энергичная"), (0.36, 0.68))
        texture = _choice(dna.roughness, ("мягким", "выразительным", "шероховатым"), (0.35, 0.67))
        rhythm = _choice(dna.rhythmic_density, ("редким", "ровным", "плотным"), (0.34, 0.67))
        structure = _structure_phrase_ru(dna)
        sound_description = (
            f"{mood.capitalize()} {force} композиция с {texture} тембром, {rhythm} ритмическим движением "
            f"и { _choice(dna.tension, ('низким', 'умеренным', 'высоким'), (0.35, 0.68)) } напряжением. "
            f"{structure} Бас формирует { _choice(dna.bass_mass, ('лёгкую', 'заметную', 'массивную'), (0.34, 0.68)) } "
            "визуальную массу, а атаки и спектральные изменения определяют резкость движения."
        )
        return (f"Образ из текста песни — «{lyric_cue}». " if lyric_cue else "") + sound_description
    mood = _choice(dna.valence, ("dark", "restrained", "luminous"), (0.38, 0.64))
    force = _choice(dna.arousal, ("calm", "mobile", "energetic"), (0.36, 0.68))
    texture = _choice(dna.roughness, ("soft", "defined", "rough"), (0.35, 0.67))
    rhythm = _choice(dna.rhythmic_density, ("sparse", "steady", "dense"), (0.34, 0.67))
    sound_description = (
        f"A {mood}, {force} composition with a {texture} timbre, {rhythm} rhythmic motion, and "
        f"{_choice(dna.tension, ('low', 'moderate', 'high'), (0.35, 0.68))} tension. "
        f"{_structure_phrase_en(dna)} Bass supplies {_choice(dna.bass_mass, ('light', 'present', 'massive'), (0.34, 0.68))} "
        "visual weight while attacks and spectral changes shape the sharpness of motion."
    )
    return (f"Lyric image: “{lyric_cue}”. " if lyric_cue else "") + sound_description


def _lyric_cue(lyrics: str) -> str:
    lines = []
    for raw in (lyrics or "").splitlines():
        line = re.sub(r"^(?:\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\])+", "", raw).strip()
        line = re.sub(r"\s+", " ", line).strip(" -–—.,:;!?\"'«»")
        if 3 <= len(line.split()) <= 18:
            lines.append(line)
    if not lines:
        return ""
    counts = Counter(line.casefold() for line in lines)
    selected = max(enumerate(lines), key=lambda item: (
        counts[item[1].casefold()], min(len(item[1].split()), 8), -item[0]
    ))[1]
    return selected if len(selected) <= 100 else selected[:100].rsplit(" ", 1)[0]


def create_visual_brief(dna: VisualDNA, plan: VisualPlan) -> str:
    mood = ", ".join((
        _choice(dna.valence, ("somber", "ambiguous", "uplifting"), (0.38, 0.64)),
        _choice(dna.arousal, ("calm", "active", "forceful"), (0.36, 0.68)),
        _choice(dna.tension, ("open", "tense", "pressurized"), (0.34, 0.68)),
    ))
    return (
        f"Mood: {mood}.\n"
        f"Composition: {plan.geometry}; visual weight {plan.visual_weight:.2f}; symmetry {plan.symmetry:.2f}; "
        f"density {plan.density:.2f}; focal position {plan.focal_position[0]:.2f}, {plan.focal_position[1]:.2f}.\n"
        f"Palette: {', '.join(plan.palette)}; temperature {plan.palette_temperature:.2f}; "
        f"saturation {plan.saturation:.2f}; luminance {plan.luminance:.2f}; contrast {plan.contrast:.2f}.\n"
        f"Texture: roughness {plan.texture_roughness:.2f}; granularity {plan.granularity:.2f}; "
        f"edge sharpness {plan.edge_sharpness:.2f}.\n"
        f"Lighting: {plan.lighting}.\n"
        f"Motion: flow {plan.flow:.2f}; directionality {plan.directionality:.2f}; repetition {plan.repetition:.2f}; "
        f"fragmentation {plan.fragmentation:.2f}; dispersion {plan.dispersion:.2f}."
    )


def detect_language(text: str) -> str:
    cyrillic = len(re.findall(r"[А-Яа-яЁё]", text or ""))
    latin = len(re.findall(r"[A-Za-z]", text or ""))
    if cyrillic and latin:
        return "mixed"
    if cyrillic:
        return "ru"
    return "en"


def _metadata_emotion(text: str) -> tuple[float, float, float]:
    normalized = re.sub(r"\s+", " ", (text or "").lower())
    positive = sum(cue in normalized for cue in POSITIVE_CUES)
    negative = sum(cue in normalized for cue in NEGATIVE_CUES)
    intense = sum(cue in normalized for cue in INTENSE_CUES)
    calm = sum(cue in normalized for cue in CALM_CUES)
    total = positive + negative + intense + calm
    if total == 0:
        return 0.5, 0.5, 0.0
    valence = clamp(0.5 + (positive - negative) * 0.16)
    arousal = clamp(0.5 + (intense - calm) * 0.16)
    return valence, arousal, clamp(total / 5.0)


def _apply_mood_override(valence, arousal, tension, mood):
    targets = {
        "calm": (0.58, 0.22, 0.20),
        "melancholic": (0.24, 0.34, 0.48),
        "energetic": (0.68, 0.82, 0.52),
        "intense": (0.35, 0.88, 0.84),
        "romantic": (0.72, 0.46, 0.35),
    }
    target = targets.get(str(mood).lower())
    if not target:
        return valence, arousal, tension
    return tuple(clamp(original * 0.72 + desired * 0.28) for original, desired in zip((valence, arousal, tension), target))


def _choice(value: float, labels: tuple[str, str, str], thresholds: tuple[float, float]) -> str:
    return labels[0] if value < thresholds[0] else labels[1] if value < thresholds[1] else labels[2]


def _structure_phrase_ru(dna: VisualDNA) -> str:
    if dna.intro_energy + 0.18 < max(dna.ending_energy, dna.arousal):
        return "Развитие начинается сдержанно и постепенно усиливается к поздней кульминации."
    if dna.intro_energy > dna.ending_energy + 0.18:
        return "Композиция открывается сильнее и постепенно рассеивает энергию к финалу."
    if dna.section_contrast > 0.58:
        return "Структура строится на заметных контрастах между спокойными и насыщенными участками."
    return "Энергетическая линия развивается последовательно, без резких потерь музыкального характера."


def _structure_phrase_en(dna: VisualDNA) -> str:
    if dna.intro_energy + 0.18 < max(dna.ending_energy, dna.arousal):
        return "It begins with restraint and builds toward a later climax."
    if dna.intro_energy > dna.ending_energy + 0.18:
        return "It opens strongly and gradually releases energy toward the ending."
    if dna.section_contrast > 0.58:
        return "Its structure alternates clearly between restrained and saturated sections."
    return "Its energy develops consistently without erasing the track's dynamic identity."
