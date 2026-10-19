"""Verify NumPy frontend and ONNX export against upstream on REAL audio.

Run with the isolated export environment after producing real_input.npz with
audio (N,48000), mel (N,187,96) from decoded real musical recordings.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

os.environ['TF_USE_LEGACY_KERAS'] = '1'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.sonicforge/genre-export/source'))
sys.path.insert(0, str(ROOT / 'src'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare-input', action='store_true', help='Run with application Python, before TF verification')
    parser.add_argument('--check-onnx', action='store_true', help='Run with application Python, after TF verification')
    args = parser.parse_args()
    import numpy as np
    work = ROOT / '.sonicforge/genre-export'
    if args.prepare_input:
        from genre_classifier import decode_fragment, log_mel
        manifest = json.loads((ROOT / 'docs/genre_evaluation_manifest.json').read_text(encoding='utf-8'))
        rows = manifest['tracks'][:8]
        audio = np.stack([decode_fragment(ROOT / r['path'], seconds=3)[:48000] for r in rows])
        np.savez(work / 'real_input.npz', audio=audio, mel=np.stack([log_mel(a) for a in audio]))
        (work / 'real_inputs.json').write_text(json.dumps([
            {'clip_id': r['clip_id'], 'sha256': r['sha256']} for r in rows], indent=2), encoding='utf-8')
        print('Prepared eight pinned real musical inputs')
        return
    if args.check_onnx:
        from genre_classifier import model_session, model_directory
        session, _ = model_session()
        reference = np.load(work / 'real_reference.npz')
        actual = session.run(None, {session.get_inputs()[0].name: reference['mel']})[0]
        error = float(np.max(np.abs(actual - reference['tags'])))
        if error > 2e-5:
            raise ValueError(f'ONNX mismatch: {error}')
        random_input = np.load(work / 'parity.npz')
        random_error = float(np.max(np.abs(session.run(None, {session.get_inputs()[0].name: random_input['mel']})[0] - random_input['tags'])))
        report = {'real_music_fragments': len(actual),
                  'inputs': json.loads((work / 'real_inputs.json').read_text()),
                  'frontend_max_abs_error': float(reference['frontend_max_abs_error']),
                  'onnx_vs_tensorflow_max_abs_error': error,
                  'random_input_onnx_max_abs_error': random_error,
                  'model_sha256': hashlib.sha256((model_directory() / 'msd_musicnn.onnx').read_bytes()).hexdigest()}
        (ROOT / 'docs/genre_model_verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(report)
        return
    import librosa
    import tensorflow as tf
    from musicnn import models
    probe = np.load(ROOT / '.sonicforge/genre-export/real_input.npz')
    reference = np.stack([np.log10(1 + 10000 * librosa.feature.melspectrogram(
        y=audio, sr=16000, n_fft=512, hop_length=256, n_mels=96,
        pad_mode='reflect', norm='slaney').T[:187]) for audio in probe['audio']])
    error = float(np.max(np.abs(reference - probe['mel'])))
    if error > 2e-5:
        raise ValueError(f'Frontend mismatch: {error}')
    tf.compat.v1.disable_eager_execution()
    x = tf.compat.v1.placeholder(tf.float32, [None, 187, 96], name='mel')
    y = tf.sigmoid(models.define_model(x, False, 'MSD_musicnn', 50)[0])
    with tf.compat.v1.Session() as session:
        tf.compat.v1.train.Saver().restore(session, str(ROOT / '.sonicforge/genre-export/source/musicnn/MSD_musicnn') + '/')
        tags = session.run(y, {x: reference})
    np.savez(ROOT / '.sonicforge/genre-export/real_reference.npz', tags=tags, mel=reference,
             frontend_max_abs_error=error)
    print('Real audio frontend max abs error:', error)


if __name__ == '__main__':
    main()
