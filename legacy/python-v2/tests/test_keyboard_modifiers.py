import unittest
from unittest.mock import patch

from ui.keyboard import alt_pressed


class KeyboardModifierTests(unittest.TestCase):
    def test_windows_numlock_does_not_disable_control_shortcuts(self):
        with patch('ui.keyboard.sys.platform', 'win32'):
            self.assertFalse(alt_pressed(4 | 8))
            self.assertFalse(alt_pressed(4 | 1 | 8))
            self.assertTrue(alt_pressed(4 | 0x20000))

    def test_x11_mod1_remains_alt(self):
        with patch('ui.keyboard.sys.platform', 'linux'):
            self.assertFalse(alt_pressed(4))
            self.assertTrue(alt_pressed(4 | 8))
