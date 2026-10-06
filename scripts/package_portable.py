"""Archive an already verified folder build and produce SHA-256 download hashes."""
from pathlib import Path
import hashlib
import zipfile


def main():
    root = Path(__file__).resolve().parents[1]
    dist = root / 'dist'
    folder = dist / 'SonicForge'
    installer = dist / 'SonicForge-Setup-2.0.0.exe'
    archive = dist / 'SonicForge-2.0.0-windows-x64.zip'
    if not (folder / 'SonicForge.exe').is_file() or not installer.is_file():
        raise RuntimeError('Build the application and installer before packaging')
    if archive.exists():
        raise FileExistsError('Refusing to overwrite an existing portable archive')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=5) as output:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                if path.is_symlink():
                    raise ValueError('Linked files are not accepted in a release')
                output.write(path, path.relative_to(dist).as_posix())
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
