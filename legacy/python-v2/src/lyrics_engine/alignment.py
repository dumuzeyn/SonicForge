"""Parent-side timing-only bridge; no speech decoder runs in the GUI process."""
import os
from .isolated import IsolatedLyricsProvider


def alignment_worker_command():
    from stem_separation import worker_command
    return [*worker_command(), '--alignment-worker', '--parent-pid', str(os.getpid())]


def timing_provider():
    return IsolatedLyricsProvider(command_factory=alignment_worker_command)
