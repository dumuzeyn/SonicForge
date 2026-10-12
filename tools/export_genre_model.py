"""One-time export of upstream ISC musicnn; never needed by the application.

Python 3.12: tensorflow-cpu==2.16.2 tf-keras==2.16.0 tf2onnx==1.16.1
onnx==1.17.0 numpy==1.26.4 scipy==1.13.1. Run in an isolated export environment.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request

os.environ['TF_USE_LEGACY_KERAS'] = '1'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
REVISION = '516acb2a0ff5ef73f64547898e018e793152c506'
ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=ROOT / '.sonicforge/genre-export/source')
    args = parser.parse_args()
    for name in ('LICENSE.md', 'musicnn/models.py', 'musicnn/configuration.py',
                 'musicnn/MSD_musicnn/.index', 'musicnn/MSD_musicnn/.data-00000-of-00001'):
        target = args.source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            urllib.request.urlretrieve(f'https://raw.githubusercontent.com/jordipons/musicnn/{REVISION}/{name}', target)
    sys.path.insert(0, str(args.source))
    import tensorflow as tf
    import tf2onnx
    from musicnn import models, configuration
    tf.compat.v1.disable_eager_execution()
    x = tf.compat.v1.placeholder(tf.float32, [None, 187, 96], name='mel')
    y = tf.sigmoid(models.define_model(x, False, 'MSD_musicnn', 50)[0], name='tags')
    target = ROOT / 'assets/models/genre'
    target.mkdir(parents=True, exist_ok=True)
    with tf.compat.v1.Session() as session:
        tf.compat.v1.train.Saver().restore(session, str(args.source / 'musicnn/MSD_musicnn') + '/')
        frozen = tf.compat.v1.graph_util.convert_variables_to_constants(session, session.graph_def, ['tags'])
        tf2onnx.convert.from_graph_def(frozen, input_names=['mel:0'], output_names=['tags:0'],
                                    opset=13, output_path=str(target / 'msd_musicnn.onnx'))
        import numpy as np
        rng = np.random.default_rng(2026)
        probe = rng.uniform(0, 4, (2, 187, 96)).astype(np.float32)
        np.savez(ROOT / '.sonicforge/genre-export/parity.npz', mel=probe,
                 tags=session.run(y, {x: probe}))
    manifest = {
        'model': 'MSD_musicnn', 'upstream_revision': REVISION,
        'upstream': f'https://github.com/jordipons/musicnn/tree/{REVISION}',
        'license': 'ISC', 'labels': configuration.MSD_LABELS,
        'sha256': hashlib.sha256((target / 'msd_musicnn.onnx').read_bytes()).hexdigest(),
        'source_hashes': {str(p.relative_to(args.source)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in args.source.rglob('*') if p.is_file() and p.suffix != '.pyc'},
        'sample_rate': 16000, 'n_fft': 512, 'hop': 256, 'n_mels': 96,
        'frames': 187, 'preprocessing': 'Slaney mel power, log10(1 + 10000 * mel), no peak normalization',
    }
    (target / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (target / 'LICENSE.musicnn.txt').write_bytes((args.source / 'LICENSE.md').read_bytes())
    print(manifest['sha256'])


if __name__ == '__main__':
    main()
