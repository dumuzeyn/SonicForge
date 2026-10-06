from .formats import embed_lyrics, find_sidecar, load_sidecar, save_lyrics
from .batch import recognize_batch
from .models import LyricsResult, TranscriptSegment
from .service import LyricsService

__all__ = [
    "LyricsResult",
    "LyricsService",
    "TranscriptSegment",
    "embed_lyrics",
    "find_sidecar",
    "load_sidecar",
    "recognize_batch",
    "save_lyrics",
]
