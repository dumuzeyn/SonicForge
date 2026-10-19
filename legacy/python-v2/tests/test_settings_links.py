import unittest
from unittest.mock import patch

from app_identity import GITHUB_REPOSITORY_URL, AUTHOR_SUPPORT_URL
from music_polisher_gui import SonicForgeApp


class SettingsLinksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch('ui.layout.webbrowser.open_new_tab') as browser:
            cls.app = SonicForgeApp()
            cls.app.update()
            browser.assert_not_called()

    @classmethod
    def tearDownClass(cls):
        cls.app._close()

    def tearDown(self):
        if self.app.language != 'ru':
            self.app.toggle_language()

    def test_title_is_exactly_sonicforge_in_both_languages(self):
        for language in ('ru', 'en'):
            if self.app.language != language:
                self.app.toggle_language()
            self.assertEqual(self.app.title(), 'SonicForge')

    def test_settings_shows_only_buttons_and_descriptions_without_opening_links(self):
        view = self.app.view
        with patch('ui.layout.webbrowser.open_new_tab') as browser:
            view.show_tab('settings')
            self.app.update()
            browser.assert_not_called()
        self.assertFalse(hasattr(view, 'settings_link_addresses'))
        for description in view.settings_link_descriptions.values():
            self.assertTrue(description.winfo_ismapped())
            self.assertTrue(description.cget('text'))
            self.assertNotIn('https://', description.cget('text'))
        for button in view.settings_link_buttons.values():
            self.assertNotIn('https://', button.cget('text'))

    def test_explicit_click_opens_only_the_requested_page_in_browser(self):
        view = self.app.view
        for key, address in (('project_repository', GITHUB_REPOSITORY_URL),
                             ('author_support', AUTHOR_SUPPORT_URL)):
            with patch('ui.layout.webbrowser.open_new_tab', return_value=True) as browser:
                view.settings_link_buttons[key].invoke()
                browser.assert_called_once_with(address)

    def test_settings_links_align_and_notice_fits_in_both_languages(self):
        view = self.app.view
        for language in ('ru', 'en'):
            if self.app.language != language:
                self.app.toggle_language()
            view.show_tab('settings')
            self.app.update()
            descriptions = list(view.settings_link_descriptions.values())
            self.assertEqual(descriptions[0].winfo_rootx(), descriptions[1].winfo_rootx())
            notice = view.donation_notice
            page = view.tab_pages['settings']
            self.assertLessEqual(notice.winfo_rooty() + notice.winfo_height(), page.winfo_rooty() + page.winfo_height())

    def test_donation_is_explicitly_voluntary_and_unlocks_no_features(self):
        for language in ('ru', 'en'):
            if self.app.language != language:
                self.app.toggle_language()
            notice = self.app.view.donation_notice.cget('text')
            if language == 'ru':
                self.assertIn('добровольное пожертвование', notice)
                self.assertIn('не открывает дополнительных функций', notice)
                self.assertIn('не влияет на доступ', notice)
            else:
                self.assertIn('voluntary donation', notice)
                self.assertIn('does not unlock any features', notice)
            self.assertEqual(self.app.view.settings_link_buttons['author_support'].cget('text'),
                             self.app.t('author_support'))

    def test_unknown_url_is_rejected_and_browser_failure_is_reported(self):
        with patch('ui.layout.webbrowser.open_new_tab', return_value=False) as browser, \
                patch('ui.layout.messagebox.showerror') as error:
            self.assertFalse(self.app.view._open_project_link('file:///C:/untrusted.exe'))
            browser.assert_not_called()
            error.assert_not_called()
            self.assertFalse(self.app.view._open_project_link(GITHUB_REPOSITORY_URL))
            error.assert_called_once_with('SonicForge', self.app.t('link_open_failed'), parent=self.app)

    def test_browser_exception_does_not_escape_into_the_ui(self):
        with patch('ui.layout.webbrowser.open_new_tab', side_effect=OSError('browser missing')), \
                patch('ui.layout.messagebox.showerror') as error:
            self.assertFalse(self.app.view._open_project_link(AUTHOR_SUPPORT_URL))
            error.assert_called_once()


if __name__ == '__main__':
    unittest.main()
