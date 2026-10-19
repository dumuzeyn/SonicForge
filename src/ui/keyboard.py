"""Tk modifier bits differ between Windows and X11."""
import sys


def alt_pressed(state):
    # On Windows 0x8 is Mod1/NumLock, while Alt uses the extended 0x20000 bit.
    # Rejecting Mod1 there disables physical Ctrl shortcuts whenever NumLock is on.
    return bool(state & (0x20000 if sys.platform == 'win32' else 0x8))
