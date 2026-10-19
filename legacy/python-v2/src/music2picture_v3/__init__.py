"""M2Pv3: organic M2Pv2 surfaces over a chronological spectral background."""
from .audio_analysis import SongStructure, analyze_structure, analyze_structure_array
from .renderer import GENERATOR_VERSION, render_cover

__all__ = ['SongStructure', 'analyze_structure', 'analyze_structure_array',
           'GENERATOR_VERSION', 'render_cover']
