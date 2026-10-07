"""Decode a bounded mono waveform once per song, including explicit-language runs."""
import io

import av
import numpy as np

SAMPLE_RATE = 16000
MAX_SECONDS = 60 * 30


def decode_song_audio(path, cancel_event=None):
    resampler = av.AudioResampler(format='s16', layout='mono', rate=SAMPLE_RATE)
    buffer = io.BytesIO()
    samples = 0
    with av.open(str(path), mode='r', metadata_errors='ignore') as container:
        for frame in container.decode(audio=0):
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError('Lyrics recognition was cancelled.')
            # Discontinuous container timestamps must not break resampling.
            frame.pts = None
            for converted in resampler.resample(frame):
                samples += converted.samples
                if samples > SAMPLE_RATE * MAX_SECONDS:
                    raise ValueError('Recognition accepts recordings up to 30 minutes; split longer audio first.')
                buffer.write(converted.to_ndarray().tobytes())
        for converted in resampler.resample(None):
            samples += converted.samples
            if samples > SAMPLE_RATE * MAX_SECONDS:
                raise ValueError('Recording exceeds the 30-minute recognition limit.')
            buffer.write(converted.to_ndarray().tobytes())
    waveform = np.frombuffer(buffer.getbuffer(), dtype='<i2').astype(np.float32)
    waveform *= 1 / 32768.0
    return waveform
