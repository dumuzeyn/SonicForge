"""Read-only verification of the packaged icon and editor toggle in a Windows EXE."""
import argparse
import hashlib
from pathlib import Path
import struct
import types

import pefile
from PyInstaller.archive.readers import CArchiveReader


def constants(value):
    if isinstance(value, types.CodeType):
        yield value.co_name
        yield from value.co_names
        for item in value.co_consts:
            yield from constants(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from constants(item)
    elif isinstance(value, str):
        yield value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    artwork = (root / 'assets/sonic_forge_mark.ico').read_bytes()
    installed_artwork = (args.exe.parent / '_internal/assets/sonic_forge_mark.ico').read_bytes()
    assert artwork == installed_artwork, 'The packaged icon is stale'
    count = struct.unpack_from('<H', artwork, 4)[0]
    expected = set()
    for index in range(count):
        length, offset = struct.unpack_from('<II', artwork, 6 + index * 16 + 8)
        expected.add(hashlib.sha256(artwork[offset:offset + length]).hexdigest())
    with pefile.PE(str(args.exe)) as executable:
        actual = set()
        for resource in executable.DIRECTORY_ENTRY_RESOURCE.entries:
            if resource.id == 3:  # RT_ICON
                for icon in resource.directory.entries:
                    for language in icon.directory.entries:
                        data = language.data.struct
                        actual.add(hashlib.sha256(executable.get_data(data.OffsetToData, data.Size)).hexdigest())
        assert expected <= actual, 'EXE contains a stale or incomplete Windows icon'
    archive = CArchiveReader(str(args.exe))
    embedded = archive.open_embedded_archive('PYZ.pyz')
    editor_constants = set(constants(embedded.extract('ui.editor')))
    assert {'toggle_cursor_selection', 'Завершить выделение', 'Начать выделение'} <= editor_constants, 'Editor toggle missing from EXE'
    window_constants = set(constants(embedded.extract('ui.windowing')))
    assert 'set_native_window_icon' in window_constants, 'Native window icons missing'
    assert 'atomic_layout' not in window_constants, 'Flickering forced repaint still included'
    layout_constants = set(constants(embedded.extract('ui.layout')))
    assert {'page_layers', '_current_layer', 'editor_context', 'batch_context'} <= layout_constants, 'Stable layouts missing'
    assert 'settings_link_descriptions' in layout_constants and 'settings_link_addresses' not in layout_constants, 'Settings still shows raw URLs'
    assert not any(entry[-1] == 'l' for entry in archive.toc.values()), 'Old rectangular bootloader splash still included'
    assert 'splash_runtime' in archive.toc, 'Early transparent splash hook missing'
    splash_constants = set(constants(embedded.extract('startup_splash')))
    assert {'UpdateLayeredWindow', 'premultiply_bgra', 'sonic_forge_mark.ico', 'hide_splash.flag'} <= splash_constants, 'Per-pixel transparent splash missing'
    identity_constants = set(constants(embedded.extract('app_identity')))
    assert {'SonicForge', '2.1.0', 'https://github.com/dumuzeyn/SonicForge',
            'https://pay.cloudtips.ru/p/53cc3806'} <= identity_constants, 'Current title or project links missing'
    assert not any(name == 'mutagen' or name.startswith('mutagen.') for name in embedded.toc), 'Test-only checker is included in the application'
    assert 'audio_tags' in embedded.toc, 'Current tag writer is missing'
    assert (args.exe.parent / '_internal/licenses/sonicforge/LICENSE').is_file(), 'Project license missing'
    assert (args.exe.parent / '_internal/licenses/ffmpeg/LICENSE').is_file(), 'Independent media-tool license missing'
    strings = set(constants(embedded.extract('ui.i18n')))
    assert any('добровольное пожертвование' in value and 'не открывает дополнительных функций' in value
               for value in strings), 'Donation notice missing'
    print(f'Verified {len(expected)} icon sizes, transparent splash runtime, native icons and stable page layers: {args.exe}')


if __name__ == '__main__':
    main()
