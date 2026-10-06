from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from pathlib import Path
from typing import Callable, Mapping

from .audio_analysis import analyze_audio_file
from .models import AnalysisBundle
from .semantics import build_visual_dna, create_song_description, create_visual_brief, detect_language
from .utils import file_cache_key
from .visual_plan import build_visual_plan


ProgressCallback = Callable[[str], None]
STAGE_ORDER = (
    "loading_audio",
    "analysing_rhythm",
    "analysing_timbre",
    "analysing_harmony",
    "analysing_structure",
    "building_visual_dna",
    "creating_song_description",
    "creating_visual_plan",
    "creating_visual_brief",
)


class Music2PicturePipeline:
    """Text-first Music2Picture v2 pipeline with a bounded in-memory cache."""

    def __init__(self, cache_size: int = 12):
        self.cache_size = max(1, int(cache_size))
        self._cache: OrderedDict[str, AnalysisBundle] = OrderedDict()

    def analyse(
        self,
        audio_path: str | Path,
        metadata: Mapping[str, object] | None = None,
        lyrics: str = "",
        mood_override: str = "auto",
        variation: int = 0,
        progress: ProgressCallback | None = None,
        force: bool = False,
    ) -> AnalysisBundle:
        path = Path(audio_path).resolve()
        metadata = dict(metadata or {})
        metadata_text = " ".join(str(value) for value in metadata.values() if value)
        extra = json.dumps(
            {
                "metadata": metadata,
                "lyrics_hash": hashlib.sha256(lyrics.encode("utf-8", errors="replace")).hexdigest(),
                "mood": mood_override,
                "variation": int(variation),
                "version": 3,
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        key = file_cache_key(path, extra)
        cached = None if force else self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached

        self._progress(progress, "loading_audio")
        analysis = analyze_audio_file(path)
        for stage in STAGE_ORDER[1:5]:
            self._progress(progress, stage)
        self._progress(progress, "building_visual_dna")
        visual_dna = build_visual_dna(analysis, metadata_text, lyrics, mood_override)
        language = detect_language(f"{metadata_text} {lyrics[:2000]}")
        self._progress(progress, "creating_song_description")
        song_description = create_song_description(
            visual_dna, "ru" if language in {"ru", "mixed"} else "en", lyrics=lyrics
        )
        self._progress(progress, "creating_visual_plan")
        visual_plan = build_visual_plan(visual_dna, variation=variation)
        self._progress(progress, "creating_visual_brief")
        visual_brief = create_visual_brief(visual_dna, visual_plan)
        bundle = AnalysisBundle(
            analysis=analysis,
            visual_dna=visual_dna,
            song_description=song_description,
            visual_brief=visual_brief,
            visual_plan=visual_plan,
            language=language,
            stage_order=STAGE_ORDER,
        )
        self._cache[key] = bundle
        self._cache.move_to_end(key)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)
        return bundle

    @staticmethod
    def _progress(callback: ProgressCallback | None, stage: str) -> None:
        if callback is not None:
            callback(stage)


DEFAULT_PIPELINE = Music2PicturePipeline()
