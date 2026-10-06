"""Read-only check of recognition model loading in a windowed EXE environment."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lyrics_engine.providers import FasterWhisperProvider


def main():
    provider = FasterWhisperProvider()
    streams = sys.stdout, sys.stderr
    print("Checking native model loading without console streams...", flush=True)
    try:
        sys.stdout = sys.stderr = None
        model = provider._get_native_model("ka")
    finally:
        sys.stdout, sys.stderr = streams
    print("Windowless native model load OK:", type(model).__name__, flush=True)


if __name__ == "__main__":
    main()
