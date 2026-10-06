"""Local metadata access and bounded, atomic ID3 lyric updates.

Container probing uses the existing PyAV runtime. ID3 parsing/writing is a
small independent implementation of the published ID3v2.3/2.4 format; unknown
frames and MPEG audio bytes are retained unchanged. Complex tag headers are
rejected for writing rather than silently losing unrelated metadata.
"""
from dataclasses import dataclass
from pathlib import Path
import os
import re
import shutil
import tempfile

MAX_TAG_BYTES = 32 * 1024 * 1024
FRAME_ID = re.compile(rb'[A-Z0-9]{4}')
TEXT_KEYS = {'TIT2': 'title', 'TPE1': 'artist', 'TPE2': 'album_artist',
             'TALB': 'album', 'TCOM': 'composer', 'TCON': 'genre',
             'TDRC': 'date', 'TYER': 'date', 'TRCK': 'track', 'TPOS': 'disc',
             'TPUB': 'publisher', 'TCOP': 'copyright'}
CUSTOM_KEYS = {'SONICFORGE_LYRICS_LANGUAGE': 'lyrics_language',
               'SONICFORGE_LYRICS_ALPHABET': 'lyrics_alphabet'}


def _synchsafe(data):
    if len(data) != 4 or any(byte & 128 for byte in data):
        raise ValueError('Invalid ID3 size')
    return sum(byte << (7 * (3 - index)) for index, byte in enumerate(data))


def _size_bytes(size):
    if not 0 <= size < 1 << 28:
        raise ValueError('ID3 size is out of range')
    return bytes((size >> shift) & 127 for shift in (21, 14, 7, 0))


def _decode(data, encoding):
    codecs = {0: 'latin-1', 1: 'utf-16', 2: 'utf-16-be', 3: 'utf-8'}
    if encoding not in codecs:
        raise ValueError('Unknown ID3 text encoding')
    if not data:
        return ''
    return data.decode(codecs[encoding], errors='replace').rstrip('\0')


def _split_text(data, encoding):
    if encoding in (1, 2):
        for index in range(0, len(data) - 1, 2):
            if data[index:index + 2] == b'\0\0':
                return data[:index], data[index + 2:]
        return data, b''
    before, _, after = data.partition(b'\0')
    return before, after


@dataclass(frozen=True)
class ID3Frame:
    name: str
    payload: bytes
    flags: bytes = b'\0\0'

    @property
    def text(self):
        data = self.payload
        if not data or self.flags != b'\0\0':
            return ''
        if self.name in ('USLT', 'COMM'):
            _, text = _split_text(data[4:], data[0])
        elif self.name == 'TXXX':
            _, text = _split_text(data[1:], data[0])
        else:
            text = data[1:]
        return _decode(text, data[0])

    @property
    def description(self):
        if not self.payload or self.name != 'TXXX' or self.flags != b'\0\0':
            return ''
        description, _ = _split_text(self.payload[1:], self.payload[0])
        return _decode(description, self.payload[0])

    @property
    def language(self):
        return self.payload[1:4].decode('ascii', errors='replace') if self.name == 'USLT' else ''


def read_id3(path):
    """Return version, audio offset and raw frames; bound all allocations."""
    with Path(path).open('rb') as source:
        header = source.read(10)
        if not header.startswith(b'ID3'):
            return 3, 0, ()
        if len(header) != 10 or header[3] not in (3, 4) or header[4] != 0:
            raise ValueError('Only ID3v2.3.0 and ID3v2.4.0 are supported for lyric updates')
        # Extended headers, global unsynchronisation and footers require
        # rewriting checksums/size rules; do not guess or damage the source.
        if header[5] & ~0x20:
            raise ValueError('This ID3 header requires a different tag editor')
        size = _synchsafe(header[6:10])
        if size > MAX_TAG_BYTES:
            raise ValueError('ID3 tag exceeds the safe size limit')
        body = source.read(size)
        if len(body) != size:
            raise ValueError('Truncated ID3 tag')
    frames, index = [], 0
    while index < size:
        if body[index] == 0:
            if any(body[index:]):
                raise ValueError('Invalid ID3 padding')
            break
        frame = body[index:index + 10]
        if len(frame) != 10 or FRAME_ID.fullmatch(frame[:4]) is None:
            raise ValueError('Invalid ID3 frame header')
        length = _synchsafe(frame[4:8]) if header[3] == 4 else int.from_bytes(frame[4:8], 'big')
        end = index + 10 + length
        if length < 1 or end > size:
            raise ValueError('Invalid ID3 frame size')
        frames.append(ID3Frame(frame[:4].decode('ascii'), body[index + 10:end], frame[8:10]))
        index = end
    return header[3], 10 + size, tuple(frames)


def update_id3(path, added, remove_names=(), remove_custom=()):
    """Replace selected frames only, using a unique temporary and atomic rename."""
    path = Path(path)
    if path.suffix.lower() != '.mp3' or path.is_symlink() or not path.is_file():
        raise ValueError('ID3 updates require a regular local MP3 file')
    original_stamp = path.stat()
    version, offset, frames = read_id3(path)
    kept = [frame for frame in frames if frame.name not in remove_names
            and not (frame.name == 'TXXX' and frame.description in remove_custom)]
    encoded = []
    for frame in (*kept, *added):
        name = frame.name.encode('ascii')
        if FRAME_ID.fullmatch(name) is None or not frame.payload or len(frame.flags) != 2:
            raise ValueError('Invalid new ID3 frame')
        size = _size_bytes(len(frame.payload)) if version == 4 else len(frame.payload).to_bytes(4, 'big')
        encoded.append(name + size + frame.flags + frame.payload)
    body = b''.join(encoded) + b'\0' * 1024
    if len(body) > MAX_TAG_BYTES:
        raise ValueError('Updated ID3 tag exceeds the safe size limit')
    # Reads and writes use independent handles and never load the entire song.
    temporary = None
    try:
        with path.open('rb') as source, tempfile.NamedTemporaryFile(
                prefix='.sonicforge-tags-', suffix='.tmp', dir=path.parent, delete=False) as destination:
            temporary = Path(destination.name)
            destination.write(b'ID3' + bytes((version, 0, 0)) + _size_bytes(len(body)) + body)
            source.seek(offset)
            shutil.copyfileobj(source, destination, 1024 * 1024)
            destination.flush()
            os.fsync(destination.fileno())
        current = path.stat()
        if (current.st_size, current.st_mtime_ns, current.st_ino) != (
                original_stamp.st_size, original_stamp.st_mtime_ns, original_stamp.st_ino):
            raise OSError('The audio file changed during the tag update')
        shutil.copymode(path, temporary)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def text_frame(name, text, description=None, language='und'):
    encoded = str(text).encode('utf-16')
    if name == 'USLT':
        payload = b'\x01' + language.encode('ascii') + ''.encode('utf-16') + b'\0\0' + encoded
    elif name == 'TXXX':
        payload = b'\x01' + str(description).encode('utf-16') + b'\0\0' + encoded
    else:
        payload = b'\x01' + encoded
    return ID3Frame(name, payload)


def probe_audio(path):
    """Inspect container/stream headers without decoding or loading models."""
    import av
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Audio probing requires a regular local file')
    with av.open(str(path.resolve(strict=True)), mode='r') as container:
        stream = next(iter(container.streams.audio), None)
        if stream is None:
            raise ValueError('No audio stream found')
        duration = (float(stream.duration * stream.time_base) if stream.duration is not None
                    and stream.time_base else float(container.duration or 0) / av.time_base)
        metadata = dict(container.metadata)
        metadata.update(stream.metadata)
        return {'duration': max(0.0, duration), 'sample_rate': stream.codec_context.sample_rate or 44100,
                'channels': stream.codec_context.channels or 2, 'metadata': metadata}


def read_metadata(path):
    try:
        data = probe_audio(path)['metadata']
    except (OSError, ValueError):
        data = {}
    aliases = {'albumartist': 'album_artist', 'tracknumber': 'track', 'discnumber': 'disc',
               'organization': 'publisher', 'year': 'date'}
    tags = {aliases.get(str(key).lower(), str(key).lower()): str(value).strip()
            for key, value in data.items() if str(value).strip()}
    if Path(path).suffix.lower() == '.mp3':
        try:
            _, _, frames = read_id3(path)
        except ValueError:
            return tags  # PyAV can still read less common ID3 variants.
        for frame in frames:
            target = TEXT_KEYS.get(frame.name) or {'COMM': 'comment', 'USLT': 'lyrics'}.get(frame.name)
            if frame.name == 'TXXX':
                target = CUSTOM_KEYS.get(frame.description)
            if target and frame.text:
                tags[target] = frame.text
    return tags
