"""Watch actual system pressure, not an arbitrary model working-set ceiling."""
from dataclasses import dataclass
import os

MIB = 1024 ** 2
GIB = 1024 ** 3


def available_commit():
    if os.name != 'nt':
        return None
    import ctypes
    from ctypes import wintypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = [('length', wintypes.DWORD), ('load', wintypes.DWORD)] + [
            (name, ctypes.c_ulonglong) for name in
            ('total_physical', 'available_physical', 'total_commit', 'available_commit',
             'total_virtual', 'available_virtual', 'extended_virtual')]

    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    query = ctypes.windll.kernel32.GlobalMemoryStatusEx
    query.argtypes = [ctypes.POINTER(MemoryStatus)]
    query.restype = wintypes.BOOL
    return status.available_commit if query(ctypes.byref(status)) else None


@dataclass(frozen=True)
class MemorySnapshot:
    total: int
    available: int
    rss: int
    private: int
    commit_available: int | None = None


def memory_snapshot(process):
    import psutil
    system = psutil.virtual_memory()
    usage = psutil.Process(process.pid).memory_info()
    return MemorySnapshot(system.total, system.available, usage.rss,
                          getattr(usage, 'private', usage.rss), available_commit())


class RecognitionMemoryError(MemoryError):
    def __init__(self, snapshot, resource):
        self.snapshot, self.resource = snapshot, resource
        details = f'available RAM: {snapshot.available // MIB} MB; worker: {snapshot.rss // MIB} MB'
        if snapshot.commit_available is not None:
            details += f'; available system commit: {snapshot.commit_available // MIB} MB'
        super().__init__(f'Recognition stopped because of {resource} pressure ({details}). '
                         'Close memory-heavy applications and retry this file; other files can continue.')


class MemoryWatch:
    def __init__(self):
        self._low_since = None

    def check(self, snapshot, now):
        physical_low = snapshot.available < 384 * MIB
        commit_low = snapshot.commit_available is not None and snapshot.commit_available < 512 * MIB
        if not physical_low and not commit_low:
            self._low_since = None
            return
        critical = (snapshot.available < 128 * MIB or
                    (snapshot.commit_available is not None and snapshot.commit_available < 128 * MIB))
        if self._low_since is None:
            self._low_since = now
        if critical or now - self._low_since >= 6:
            raise RecognitionMemoryError(snapshot, 'system commit' if commit_low else 'RAM')


def recycle_when_idle(snapshot):
    # Recycle only after delivering the result. A large model is allowed to
    # finish on machines with sufficient RAM; no active file is discarded.
    return (snapshot.private > max(2 * GIB, snapshot.total // 4)
            or snapshot.available < 768 * MIB
            or (snapshot.commit_available is not None and snapshot.commit_available < GIB))
