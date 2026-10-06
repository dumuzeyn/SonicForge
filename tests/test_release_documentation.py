from pathlib import Path
import re
import unittest

from app_identity import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


class ReleaseDocumentationTests(unittest.TestCase):
    def test_bilingual_guides_start_with_icon_and_distribute_screenshots(self):
        for name, language in (('README.md', 'ru'), ('README.en.md', 'en')):
            text = (ROOT / name).read_text(encoding='utf-8')
            self.assertTrue(text.startswith('<p align='))
            self.assertIn('assets/sonic_forge_mark.png', text.splitlines()[0])
            screenshots = re.findall(r'!\[[^]]*\]\(([^)]+)\)', text)
            self.assertEqual(len(screenshots), 10)
            self.assertTrue(all((ROOT / path).is_file() for path in screenshots))
            self.assertTrue(all(path.endswith(f'-{language}.png') for path in screenshots))
            for screenshot in screenshots:
                position = text.index(screenshot)
                self.assertIn('## ', text[:position])
            self.assertIn('SonicForge-Setup-2.0.0.exe', text)

    def test_version_is_consistent_and_installer_has_license(self):
        self.assertEqual(APP_VERSION, '2.0.0')
        installer = (ROOT / 'packaging/SonicForge.iss').read_text(encoding='utf-8')
        version = (ROOT / 'packaging/version_info.txt').read_text(encoding='utf-8')
        self.assertIn('MyAppVersion "2.0.0"', installer)
        self.assertIn('LicenseFile=..\\LICENSE', installer)
        self.assertIn("StringStruct('ProductVersion', '2.0.0')", version)
        self.assertIn('version="2.0.0.0"', (ROOT / 'packaging/SonicForge.manifest').read_text())

    def test_license_scope_and_build_exclusion_of_test_only_checker(self):
        license_text = (ROOT / 'LICENSE').read_text(encoding='utf-8')
        self.assertIn('solely for', license_text)
        self.assertIn('noncommercial purposes', license_text)
        self.assertIn('teaching, learning', license_text)
        self.assertIn('does not replace', license_text)
        requirements = (ROOT / 'requirements.txt').read_text()
        self.assertNotIn('mutagen', requirements)
        self.assertIn("'mutagen'", (ROOT / 'SonicForge.spec').read_text())


if __name__ == '__main__':
    unittest.main()
