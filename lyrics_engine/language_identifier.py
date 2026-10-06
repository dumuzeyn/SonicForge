"""Lazy, independent local language identification (never used at app startup)."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np


REPO = "christopherthompson81/voxlingua107-lid-onnx"
REVISION = "e02e1da805ae49635fe1aa7913c3f1e7f5f5fde6"
MODEL_SHA256 = "e2c3c3da39b99e3f9196d15fceef6a65f702320038bbc08813a4f21280255ce8"


def model_files():
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS) / "models" / "language_id"
        return base / "voxlingua107.onnx", base / "lang_map.json"
    from huggingface_hub import hf_hub_download
    from faster_whisper.utils import disabled_tqdm
    return tuple(Path(hf_hub_download(REPO, filename, revision=REVISION,
                                     tqdm_class=disabled_tqdm))
                 for filename in ("voxlingua107.onnx", "lang_map.json"))


class LocalLanguageIdentifier:
    def __init__(self):
        self._session = None
        self._labels = None

    def _load(self):
        if self._session is not None:
            return
        import onnxruntime as ort
        model_path, labels_path = model_files()
        with model_path.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        if checksum != MODEL_SHA256:
            raise ValueError("Invalid language identifier model checksum")
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
        self._labels = tuple(labels[str(i)]["iso"] for i in range(107))
        if len(set(self._labels)) != 107 or not all(code.isalpha() for code in self._labels):
            raise ValueError("Invalid language identifier labels")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(str(model_path), options,
                                           providers=["CPUExecutionProvider"])

    def detect_language(self, audio):
        self._load()
        logits = np.asarray(self._session.run(
            ["logits"], {"audio": np.asarray(audio, dtype=np.float32)[None]},
        )[0]).reshape(-1)
        scores = np.exp(logits - logits.max())
        scores /= scores.sum()
        best = int(scores.argmax())
        return self._labels[best], float(scores[best]), list(zip(self._labels, map(float, scores)))
