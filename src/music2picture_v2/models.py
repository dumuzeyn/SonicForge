from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class AudioAnalysis:
    """Measured audio evidence before any semantic or visual mapping."""

    duration: float
    sample_rate: int
    fingerprint: str
    absolute_peak: float
    rms_dbfs: float
    loudness_p10_dbfs: float
    loudness_p50_dbfs: float
    loudness_p90_dbfs: float
    crest_factor_db: float
    dynamic_range_db: float
    relative_dynamic_range: float
    spectral_centroid_hz: float
    spectral_rolloff_hz: float
    spectral_flatness: float
    spectral_contrast: float
    zero_crossing_rate: float
    spectral_flux: float
    onset_strength: float
    onset_density: float
    tempo: float
    tempo_confidence: float
    beat_regularity: float
    rhythmic_density: float
    bass_energy: float
    mid_energy: float
    high_energy: float
    harmonic_ratio: float
    percussive_ratio: float
    harmonic_complexity: float
    chord_change_rate: float
    attack_strength: float
    key: str
    mode: str
    key_strength: float
    section_count: int
    section_contrast: float
    energy_curve: tuple[float, ...]
    peak_position: float
    largest_transition: float
    climax_position: float
    intro_energy: float
    ending_energy: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VisualDNA:
    """Multidimensional musical character used by every downstream artifact."""

    tempo: float
    tempo_confidence: float
    valence: float
    arousal: float
    tension: float
    aggressiveness: float
    relaxation: float
    brightness: float
    darkness: float
    warmth: float
    roughness: float
    dissonance: float
    spectral_flatness: float
    bass_mass: float
    rhythmic_density: float
    rhythmic_regularity: float
    dynamic_complexity: float
    harmonic_complexity: float
    chord_change_rate: float
    acousticness: float
    electronicness: float
    vocal_probability: float
    key: str
    mode: str
    key_strength: float
    section_count: int
    section_contrast: float
    attack_strength: float
    spectral_flux: float
    spectral_centroid: float
    spectral_rolloff: float
    spectral_contrast: float
    zero_crossing_rate: float
    absolute_loudness: float
    crest_factor: float
    original_dynamic_range: float
    energy_curve: tuple[float, ...]
    peak_position: float
    largest_transition: float
    climax_position: float
    intro_energy: float
    ending_energy: float
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VisualPlan:
    """Renderer-neutral visual parameters derived from VisualDNA."""

    primary_hue: float
    secondary_hue: float
    accent_hue: float
    palette_width: float
    palette_temperature: float
    saturation: float
    luminance: float
    contrast: float
    geometry: str
    curvature: float
    angularity: float
    symmetry: float
    density: float
    texture_roughness: float
    edge_sharpness: float
    granularity: float
    focal_size: float
    focal_position: tuple[float, float]
    repetition: float
    fragmentation: float
    flow: float
    dispersion: float
    background_complexity: float
    visual_weight: float
    spatial_balance: float
    directionality: float
    palette_scheme: str
    palette: tuple[str, ...]
    lighting: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AnalysisBundle:
    """One cached analysis shared by descriptions, prompts and renderers."""

    analysis: AudioAnalysis
    visual_dna: VisualDNA
    song_description: str
    visual_brief: str
    visual_plan: VisualPlan
    language: str
    stage_order: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis": self.analysis.to_dict(),
            "visual_dna": self.visual_dna.to_dict(),
            "song_description": self.song_description,
            "visual_brief": self.visual_brief,
            "visual_plan": self.visual_plan.to_dict(),
            "language": self.language,
            "stage_order": self.stage_order,
        }
