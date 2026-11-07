"""Temp-file cleanup. `remove_directory_tree` is called from a `finally`
block at the end of every download/audio task (guaranteed cleanup per
task); Phase 6 adds the periodic backstop sweep for anything a crashed
worker left behind before its `finally` could run.
"""

from pathlib import Path


def remove_directory_tree(path: Path) -> None:
    if not path.exists():
        return
    for child in path.glob("*"):
        try:
            child.unlink()
        except OSError:
            pass
    try:
        path.rmdir()
    except OSError:
        pass
