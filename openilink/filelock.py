"""Cross-platform file locking utility.

Uses fcntl on Unix and msvcrt on Windows to provide advisory file locks.
All file I/O to shared files (.ilink/inbox.jsonl, state.json, cursor files)
should go through the helpers in this module.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Generator

# --- Low-level lock / unlock ------------------------------------------------

if sys.platform == "win32":
    import msvcrt

    def _lock(fd: int, exclusive: bool = True) -> None:
        """Acquire a lock on an open file descriptor (Windows).

        Note: msvcrt does not support true shared (reader) locks.  Both
        exclusive and non-exclusive requests use LK_NBLCK (non-blocking
        exclusive).  For the non-exclusive/read path we simply retry with
        a short sleep, which gives acceptable concurrency for the light
        contention patterns in this project.
        """
        # msvcrt.locking works on the current file position for N bytes.
        # Lock a single byte at position 0 as an advisory lock sentinel.
        os.lseek(fd, 0, os.SEEK_SET)
        if exclusive:
            mode = msvcrt.LK_LOCK  # blocking exclusive
        else:
            mode = msvcrt.LK_NBLCK  # non-blocking; retry manually
        # Retry briefly – another process may hold the lock momentarily.
        for _ in range(50):
            try:
                msvcrt.locking(fd, mode, 1)
                return
            except OSError:
                time.sleep(0.05)
        # Final attempt – let the OSError propagate if it still fails.
        msvcrt.locking(fd, mode, 1)

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass

else:
    import fcntl

    def _lock(fd: int, exclusive: bool = True) -> None:
        """Acquire a lock on an open file descriptor (Unix)."""
        op = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        fcntl.flock(fd, op)

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


# --- Context manager --------------------------------------------------------

@contextlib.contextmanager
def file_lock(path: str | Path, exclusive: bool = True) -> Generator[None, None, None]:
    """Context manager that holds an advisory lock on *path*.lock.

    A separate .lock file is used so that readers and writers can coordinate
    without interfering with normal file operations (truncation, append, etc.).

    Parameters
    ----------
    path : str | Path
        The data file whose access should be serialised.
    exclusive : bool
        ``True`` for write locks (default), ``False`` for shared/read locks.
    """
    lock_path = str(path) + ".lock"
    # Ensure the parent directory exists before creating the lock file.
    Path(lock_path).parent.mkdir(parents=True, exist_ok=True)

    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    try:
        _lock(fd, exclusive=exclusive)
        yield
    finally:
        _unlock(fd)
        os.close(fd)


# --- Convenience helpers used across daemon / CLI / MCP ----------------------

def locked_read_text(path: Path) -> str:
    """Read the full text of *path* under a shared lock."""
    with file_lock(path, exclusive=False):
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""


def locked_write_text(path: Path, text: str) -> None:
    """Atomically write *text* to *path* under an exclusive lock."""
    with file_lock(path, exclusive=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def locked_append_line(path: Path, line: str) -> None:
    """Append a single line (with trailing newline) under an exclusive lock."""
    with file_lock(path, exclusive=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()


def locked_read_json(path: Path, default: dict | None = None) -> dict:
    """Read and parse a JSON file under a shared lock.

    Returns *default* (empty dict if not supplied) when the file is missing
    or contains invalid JSON.
    """
    if default is None:
        default = {}
    text = locked_read_text(path)
    if not text:
        return default
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return default


def locked_write_json(path: Path, obj: dict) -> None:
    """Serialise *obj* as JSON and write under an exclusive lock."""
    locked_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))


def locked_read_lines(path: Path) -> list[str]:
    """Read all lines from a file under a shared lock."""
    text = locked_read_text(path)
    if not text:
        return []
    return text.splitlines()
