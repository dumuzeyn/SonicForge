"""Read-only independent language-ID check; audio stays on this computer."""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--wide", action="store_true")
    args = parser.parse_args()
    from huggingface_hub import hf_hub_download
    import onnxruntime as ort
    import numpy as np
    from faster_whisper.audio import decode_audio
    from lyrics_engine.language_detection import language_windows

    repo = "christopherthompson81/voxlingua107-lid-onnx"
    revision = "e02e1da805ae49635fe1aa7913c3f1e7f5f5fde6"
    path = hf_hub_download(repo, "voxlingua107.onnx", revision=revision, local_files_only=True)
    labels_path = hf_hub_download(repo, "lang_map.json", revision=revision, local_files_only=True)
    labels = json.loads(Path(labels_path).read_text(encoding="utf-8"))
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(path, options, providers=["CPUExecutionProvider"])
    print(json.dumps({"inputs": [(i.name, i.shape) for i in session.get_inputs()],
                      "outputs": [(i.name, i.shape) for i in session.get_outputs()]}, ensure_ascii=True), flush=True)
    audio = decode_audio(args.audio, sampling_rate=16000)
    windows = language_windows(audio)
    if args.wide:
        width = min(len(audio), 40 * 16000)
        starts = sorted({max(0, min(len(audio) - width, int(len(audio) * f) - width // 2)) for f in (.15, .35, .55, .75, .9)})
        windows = [(start / 16000, audio[start:start + width]) for start in starts]
    for start, sample in windows:
        started = time.monotonic()
        logits = np.asarray(session.run(None, {session.get_inputs()[0].name: sample[None].astype(np.float32)})[0]).reshape(-1)
        scores = np.exp(logits - np.max(logits))
        scores /= scores.sum()
        indices = np.argsort(scores)[-5:][::-1]
        ranked = [(labels[str(int(i))] if isinstance(labels, dict) else labels[int(i)], float(scores[i])) for i in indices]
        print(json.dumps({"start": start, "predictions": ranked,
                          "seconds": round(time.monotonic() - started, 2)}, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
