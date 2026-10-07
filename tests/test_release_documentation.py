from pathlib import Path
import re
import unittest

from app_identity import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


def guide_sections():
    text = (ROOT / 'README.md').read_text(encoding='utf-8')
    russian, english = text.split('\n---\n\n<a id="english"></a>\n\n')
    return ((russian, 'ru'), (english, 'en'))


class ReleaseDocumentationTests(unittest.TestCase):
    def test_bilingual_guides_start_with_icon_and_distribute_screenshots(self):
        self.assertFalse((ROOT / 'README.en.md').exists())
        for text, language in guide_sections():
            self.assertTrue(text.startswith('<p align='))
            self.assertIn('assets/sonic_forge_mark.png', text.splitlines()[0])
            screenshots = re.findall(r'!\[[^]]*\]\(([^)]+)\)', text)
            self.assertEqual(len(screenshots), 11)
            self.assertTrue(all((ROOT / path).is_file() for path in screenshots))
            self.assertTrue(all(path.endswith(f'-{language}.png') for path in screenshots))
            for screenshot in screenshots:
                position = text.index(screenshot)
                self.assertIn('## ', text[:position])
            self.assertIn('SonicForge-Setup-2.1.0.exe', text)

    def test_version_is_consistent_and_installer_has_license(self):
        self.assertEqual(APP_VERSION, '2.1.0')
        installer = (ROOT / 'packaging/SonicForge.iss').read_text(encoding='utf-8')
        version = (ROOT / 'packaging/version_info.txt').read_text(encoding='utf-8')
        self.assertIn('MyAppVersion "2.1.0"', installer)
        self.assertIn('LicenseFile=..\\LICENSE', installer)
        self.assertIn("StringStruct('ProductVersion', '2.1.0')", version)
        self.assertIn('version="2.1.0.0"', (ROOT / 'packaging/SonicForge.manifest').read_text())

    def test_buttons_and_authorship_at_the_end_of_both_guides(self):
        for text, language in guide_sections():
            heading = '## Автор' if language == 'ru' else '## Author'
            before, after = text.split(heading)
            self.assertNotIn('Зейналов', before)
            self.assertNotIn('Dumuzeyn', before)
            self.assertIn('Зейналов У.Р.о. / Dumuzeyn', after)
            self.assertNotIn('\n## ', after)
            self.assertIn('style=for-the-badge', before)
            for asset in ('SonicForge-Setup-2.1.0.exe', 'SonicForge-2.1.0-windows-x64.zip'):
                self.assertIn(f'releases/download/v2.1.0/{asset}', before)
            self.assertIn('https://pay.cloudtips.ru/p/53cc3806', after)
            self.assertIn('href="#english"' if language == 'ru' else 'href="#russian"', before)

    def test_local_documentation_links_resolve_after_reorganization(self):
        for relative in ('README.md', 'docs/THIRD_PARTY_NOTICES.md'):
            file = ROOT / relative
            text = file.read_text(encoding='utf-8')
            links = re.findall(r'\]\(([^)]+)\)|(?:href|src)="([^"]+)"', text)
            for markdown, html in links:
                target = markdown or html
                if '://' not in target and not target.startswith('#'):
                    self.assertTrue((file.parent / target).is_file(), target)

    def test_license_scope_and_build_exclusion_of_test_only_checker(self):
        license_text = (ROOT / 'LICENSE').read_text(encoding='utf-8')
        self.assertIn('solely for', license_text)
        self.assertIn('noncommercial purposes', license_text)
        self.assertIn('teaching, learning', license_text)
        self.assertIn('does not replace', license_text)
        requirements = (ROOT / 'requirements/runtime.txt').read_text()
        self.assertNotIn('mutagen', requirements)
        self.assertIn("'mutagen'", (ROOT / 'packaging/SonicForge.spec').read_text())


if __name__ == '__main__':
    unittest.main()
