"""Archive an already verified folder build and produce SHA-256 download hashes."""
from pathlib import Path
import argparse
import hashlib
import zipfile


def main():
    root = Path(__file__).resolve().parents[1]
    dist = root / 'dist'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, default=dist / 'SonicForge',
                        help='Clean, verified folder build to include in the release')
    folder = parser.parse_args().folder.resolve(strict=True)
    installer = dist / 'SonicForge-Setup-2.1.0.exe'
    archive = dist / 'SonicForge-2.1.0-windows-x64.zip'
    if not (folder / 'SonicForge.exe').is_file() or not installer.is_file():
        raise RuntimeError('Build the application and installer before packaging')
    import pefile
    for executable in (folder / 'SonicForge.exe', installer):
        with pefile.PE(str(executable), fast_load=True) as image:
            image.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_RESOURCE']])
            info = image.VS_FIXEDFILEINFO[0]
            version = (info.FileVersionMS >> 16, info.FileVersionMS & 65535,
                       info.FileVersionLS >> 16, info.FileVersionLS & 65535)
            if version != (2, 1, 0, 0):
                raise ValueError(f'Wrong executable version in release: {executable}: {version}')
    if archive.exists():
        raise FileExistsError('Refusing to overwrite an existing portable archive')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=5) as output:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                if path.is_symlink():
                    raise ValueError('Linked files are not accepted in a release')
                output.write(path, (Path('SonicForge') / path.relative_to(folder)).as_posix())
    with zipfile.ZipFile(archive) as output:
        broken = output.testzip()
        if broken:
            raise RuntimeError(f'Portable archive verification failed: {broken}')
    hashes = []
    for path in (installer, archive):
        with path.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        hashes.append(f'{digest}  {path.name}')
        print(f'{path.name}: {path.stat().st_size} bytes; SHA256 {digest}', flush=True)
    (dist / 'SHA256SUMS.txt').write_text('\n'.join(hashes) + '\n', encoding='ascii')


if __name__ == '__main__':
    main()
