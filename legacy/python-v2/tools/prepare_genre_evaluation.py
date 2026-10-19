"""Small deterministic artist-disjoint diagnostic set from MagnaTagATune.

Downloads only selected MP3 entries using validated HTTP ranges. Audio stays
in ignored .sonicforge, is never redistributed with SonicForge. Requires
access to the public MTT mirror; its audio rights are separate from musicnn.
"""
import csv
import hashlib
import io
import json
from pathlib import Path
import struct
import urllib.request
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
REVISION = '042e24c2c26a71168dd35edc3bc0cb47b2f3c3cd'
BASE = f'https://huggingface.co/datasets/confit/magnatagatune/resolve/{REVISION}/'
SIZE = 2972769864
GENRES = {'house': 'House', 'metal': 'Metal', 'rock': 'Rock', 'pop': 'Pop',
          'electronic': 'Electronic', 'jazz': 'Jazz', 'ambient': 'Ambient', 'folk': 'Folk'}


def byte_range(start, end):
    request = urllib.request.Request(BASE + f'mp3.zip?range={start}-{end}',
                                     headers={'Range': f'bytes={start}-{end}'})
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{SIZE}':
            raise RuntimeError('Server did not honor range; refusing a full archive download.')
        data = response.read(end - start + 2)
    if len(data) != end - start + 1:
        raise RuntimeError('Truncated range')
    return data


def main():
    directory = ROOT / '.sonicforge/genre-eval'
    directory.mkdir(parents=True, exist_ok=True)
    for filename in ('clip_info_final.csv', 'annotations_final.csv'):
        target = directory / filename
        if not target.exists():
            urllib.request.urlretrieve(BASE + filename, target)
    with (directory / 'clip_info_final.csv').open(encoding='utf-8', newline='') as handle:
        info = {row['clip_id']: row for row in csv.DictReader(handle, delimiter='\t')}
    with (directory / 'annotations_final.csv').open(encoding='utf-8', newline='') as handle:
        annotations = list(csv.DictReader(handle, delimiter='\t'))
    candidates = [r for r in annotations if r['clip_id'] in info]
    candidates.sort(key=lambda r: hashlib.sha256(r['clip_id'].encode()).hexdigest())
    selected, artists = [], set()
    for source_label in GENRES:
        matches = [r for r in candidates if r[source_label] == '1']
        count = 0
        for row in matches:
            meta = info[row['clip_id']]
            artist = meta['artist'].strip().casefold()
            if not artist or artist in artists or 'various' in artist or 'compilation' in artist:
                continue
            artists.add(artist)
            selected.append({
                'clip_id': row['clip_id'], 'artist': meta['artist'],
                'track_id': f"{artist}/{meta['album']}/{meta['track_number']}",
                'title': meta['title'], 'source_path': row['mp3_path'],
                'genres': [genre for tag, genre in GENRES.items() if row[tag] == '1'],
                'split': 'validation' if count < 2 else 'test',
                'selection_label': GENRES[source_label],
            })
            count += 1
            if count == 6:
                break
        print(source_label, count, flush=True)
    # Read central directory without fetching the three-gigabyte archive.
    tail = byte_range(SIZE - 65536, SIZE - 1)
    end = tail.rfind(b'PK\x05\x06')
    _, _, _, _, entry_count, central_size, central_offset, _ = struct.unpack('<4s4H2LH', tail[end:end + 22])
    central = byte_range(central_offset, central_offset + central_size - 1)
    fake_end = struct.pack('<4s4H2LH', b'PK\x05\x06', 0, 0, entry_count, entry_count, central_size, 0, 0)
    archive = zipfile.ZipFile(io.BytesIO(central + fake_end))
    entries = {entry.filename: entry for entry in archive.infolist()}
    for index, row in enumerate(selected):
        # Opaque filenames prevent the old algorithm seeing the reference label.
        path = directory / f"clip_{row['clip_id']}.mp3"
        entry = entries.get(row['source_path']) or entries['mp3/' + row['source_path']]
        if not path.exists():
            header = byte_range(entry.header_offset, entry.header_offset + 29)
            fields = struct.unpack('<4s5H3L2H', header)
            start = entry.header_offset + 30 + fields[-2] + fields[-1]
            compressed = byte_range(start, start + entry.compress_size - 1)
            audio = zlib.decompress(compressed, -15) if entry.compress_type == zipfile.ZIP_DEFLATED else compressed
            if len(audio) != entry.file_size or zlib.crc32(audio) != entry.CRC:
                raise RuntimeError('Archive CRC mismatch')
            path.write_bytes(audio)
        row['path'] = str(path.relative_to(ROOT)).replace('\\', '/')
        row['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"{index+1}/{len(selected)} {row['clip_id']} {row['genres']}", flush=True)
    manifest = {'dataset': 'MagnaTagATune crowdsourced tags', 'revision': REVISION,
                'source': BASE, 'genres': list(GENRES.values()),
                'protocol': 'Fixed operating threshold; no local training. One clip per artist, selection independent of predictions.',
                'limitations': 'Small selected diagnostic set; incomplete subjective labels; overlap with MSD pretraining cannot be ruled out.',
                'tracks': selected}
    output = ROOT / 'docs/genre_evaluation_manifest.json'
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
