import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ui.folder_picker import WindowsFolderDialog


@unittest.skipUnless(os.name == "nt", "Windows COM dialog")
class WindowsFolderPickerTests(unittest.TestCase):
    def test_native_dialog_can_be_prepared_on_its_worker_thread(self):
        def prepare():
            with WindowsFolderDialog() as dialog:
                dialog.configure("Sonic Forge", Path.home())
                self.assertTrue(dialog.dialog)
            self.assertFalse(dialog.dialog)
            self.assertFalse(dialog.initialized)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(prepare).result(timeout=10)
