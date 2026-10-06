"""Isolated CPU separator. Never imported by the application startup path."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import threading
import urllib.request
import wave

MODEL_FILE = '955717e8-8726e21a.th'
MODEL_URL = 'https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/' + MODEL_FILE
MODEL_SHA256 = '8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4'


def checked_model(directory, download=False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / MODEL_FILE
    if not path.exists() and download:
        temporary = path.with_suffix('.download')
        try:
            urllib.request.urlretrieve(MODEL_URL, temporary)
            digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
            if digest != MODEL_SHA256:
                raise ValueError('Model checksum mismatch')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != MODEL_SHA256:
        raise ValueError('Model checksum mismatch')
    return path


def separate(input_path, output_dir, progress_file, model_dir):
    import numpy as np
    import torch
    from demucs.apply import apply_model
    from demucs.states import load_model

    torch.set_num_threads(max(1, min(4, os.cpu_count() or 2)))
    torch.set_num_interop_threads(1)
    torch.manual_seed(0)
    path = checked_model(model_dir)
    # Only this pinned, checksum-verified upstream checkpoint is unpickled.
    model = load_model(torch.load(path, map_location='cpu', weights_only=False)).eval()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    with wave.open(str(input_path), 'rb') as audio:
        frames, rate = audio.getnframes(), audio.getframerate()
        if audio.getnchannels() != 2 or audio.getsampwidth() != 2 or rate != 44100 or not frames:
            raise ValueError('Expected non-empty stereo PCM16 / 44100 Hz')
        total = squares = count = 0
        while data := audio.readframes(65536):
            mono = np.frombuffer(data, dtype='<i2').reshape(-1, 2).astype(np.float64).mean(axis=1) / 32768
            total += mono.sum()
            squares += np.square(mono).sum()
            count += len(mono)
        mean = float(total / count)
        std = max(1e-6, float(max(0, squares / count - mean * mean) ** .5))
        streams = {}
        try:
            for name in model.sources:
                stream = (output_dir / (name + '.wav')).open('xb')
                stream.write(struct.pack('<4sI4s4sIHHIIHH4sI', b'RIFF', 36 + frames * 8, b'WAVE',
                    b'fmt ', 16, 3, 2, rate, rate * 8, 8, 32, b'data', frames * 8))
                streams[name] = stream
            # Bounded windows with context; do not allocate a four-stem tensor
            # for the whole song. Context is discarded, not duplicated in output.
            core = rate * 12
            context = int(rate * 3.9)
            for start in range(0, frames, core):
                stop = min(frames, start + core)
                left, right = max(0, start - context), min(frames, stop + context)
                audio.setpos(left)
                samples = np.frombuffer(audio.readframes(right - left), dtype='<i2').reshape(-1, 2).T.copy()
                tensor = torch.from_numpy(samples).float() / 32768
                if squares / count - mean * mean < 1e-12:
                    stems = torch.zeros((len(model.sources), 2, right - left))
                    stems[model.sources.index('other')] = tensor
                else:
                    with torch.inference_mode():
                        stems = apply_model(model, ((tensor - mean) / std)[None], shifts=0,
                                            split=True, overlap=.25, segment=7.8, device='cpu', num_workers=0)[0]
                        stems = stems * std + mean
                for index, name in enumerate(model.sources):
                    values = stems[index, :, start - left:stop - left].T.contiguous().numpy()
                    if not np.isfinite(values).all():
                        raise ValueError('Non-finite model output')
                    streams[name].write(values.astype('<f4').tobytes())
                with Path(progress_file).open('a', encoding='utf-8') as progress:
                    progress.write(json.dumps({'progress': stop / frames}) + '\n')
        finally:
            for stream in streams.values():
                stream.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare-model', type=Path)
    parser.add_argument('--model', type=Path)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--progress', type=Path)
    parser.add_argument('--parent-pid', type=int)
    args = parser.parse_args()
    if args.prepare_model:
        path = checked_model(args.prepare_model, download=True)
        print('Prepared model:', path.name, hashlib.sha256(path.read_bytes()).hexdigest())
        return
    if args.parent_pid and os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x00100000, False, args.parent_pid)
        if not handle:
            raise RuntimeError('Parent process is no longer available')
        def watch_parent():
            try:
                if kernel.WaitForSingleObject(handle, 0xFFFFFFFF) == 0:
                    os._exit(3)
            finally:
                kernel.CloseHandle(handle)
        threading.Thread(target=watch_parent, daemon=True).start()
    model_dir = args.model or Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1] / 'build')) / 'model'
    separate(args.input, args.output, args.progress, model_dir)


if __name__ == '__main__':
    main()
