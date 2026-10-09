import ctypes
import sys


APP_NAME = "SonicForge"
APP_LOCALIZED_NAME = "Кузница Звука"
APP_VERSION = "2.2.0"
APP_PUBLISHER = "Dumuzeyn"
APP_USER_MODEL_ID = "Dumuzeyn.SonicForge"
GITHUB_REPOSITORY_URL = "https://github.com/dumuzeyn/SonicForge"
AUTHOR_SUPPORT_URL = "https://pay.cloudtips.ru/p/53cc3806"


def set_windows_app_identity():
    """Give the process a stable taskbar identity before Tk creates a window."""
    if sys.platform != "win32":
        return False
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )
        return True
    except (AttributeError, OSError):
        return False
