"""Read-only Git identity and ordinary concurrent-edit detection for sync."""
from __future__ import annotations

from functools import cache
import os
from pathlib import Path
import subprocess

from .discovery import MAX_FILE_BYTES, safe_source

WINDOWS = os.name == "nt"


@cache
def _windows_change_reader():
    """Bind the read-only API once; Python's Windows ctime can mean creation."""
    import ctypes
    import msvcrt

    class FileBasicInfo(ctypes.Structure):
        _fields_ = [(name, ctypes.c_int64) for name in
                    ("CreationTime", "LastAccessTime", "LastWriteTime", "ChangeTime")]
        _fields_.append(("FileAttributes", ctypes.c_uint32))

    query = ctypes.WinDLL("kernel32", use_last_error=True).GetFileInformationByHandleEx
    query.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32)
    query.restype = ctypes.c_int

    def read(fd: int) -> int:
        info = FileBasicInfo()
        # FileBasicInfo = 0. Borrow the live stream's handle; never close it here.
        if not query(msvcrt.get_osfhandle(fd), 0, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if info.ChangeTime <= 0:
            raise OSError("Windows file change time is unavailable; cannot verify the snapshot")
        # FILETIME is 100 ns since 1601; persist Unix nanoseconds on every OS.
        return (info.ChangeTime - 116_444_736_000_000_000) * 100

    return read


def _windows_change_time(fd: int) -> int:
    return _windows_change_reader()(fd)


class SnapshotChanged(ValueError):
    """Caller should rerun sync against a stable working tree."""


def stat_signature(stat) -> list[int]:
    return [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino, stat.st_dev]


def descriptor_signature(fd: int) -> list[int]:
    signature = stat_signature(os.fstat(fd))
    if WINDOWS:
        signature[2] = _windows_change_time(fd)
    return signature


def file_stat(root: Path, relative: str) -> list[int]:
    path = safe_source(root, relative)
    if WINDOWS:
        # Use the same descriptor metadata as read_stable. Windows stat/fstat
        # can disagree on ctime, and creation time cannot detect restored mtime.
        with path.open("rb") as stream:
            return descriptor_signature(stream.fileno())
    return stat_signature(path.stat())


def read_stable(root: Path, relative: str, expected: list[int] | None = None,
                max_bytes: int = MAX_FILE_BYTES) -> tuple[bytes, list[int]]:
    path = safe_source(root, relative)
    before = file_stat(root, relative)
    if expected is not None and before != expected:
        raise SnapshotChanged(f"File changed during sync: {relative}; retry sync")
    with path.open("rb") as stream:
        opened = descriptor_signature(stream.fileno())
        data = stream.read(max_bytes + 1)
        after_open = descriptor_signature(stream.fileno())
    after = file_stat(root, relative)
    if before != opened or opened != after_open or after_open != after:
        raise SnapshotChanged(f"File changed while being read: {relative}; retry sync")
    if len(data) > max_bytes:
        raise ValueError(f"File exceeds {max_bytes} byte limit: {relative}")
    return data, after


def git_state(root: Path) -> dict:
    """Never run hooks, builds, shell commands, or a repository fsmonitor."""
    def run(*args: str, optional: bool = False):
        proc = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(root), *args],
                              capture_output=True, text=True, encoding='utf-8', timeout=10)
        if proc.returncode:
            if optional:
                return None
            raise ValueError("Git identity could not be read; retry sync")
        return proc.stdout.strip() or None

    try:
        top = run("rev-parse", "--show-toplevel", optional=True)
        if top is None:
            return {"is_git": False, "head": None, "branch": None,
                    "worktree_root": str(root), "git_dir": None, "common_dir": None}
        git_dir = run("rev-parse", "--absolute-git-dir")
        common_dir = run("rev-parse", "--git-common-dir")
        return {"is_git": True, "head": run("rev-parse", "--verify", "HEAD", optional=True),
                "branch": run("symbolic-ref", "--quiet", "--short", "HEAD", optional=True),
                "worktree_root": str(Path(top).resolve()), "git_dir": str(Path(git_dir).resolve()),
                "common_dir": str((root / common_dir).resolve())}
    except FileNotFoundError:
        return {"is_git": False, "head": None, "branch": None,
                "worktree_root": str(root), "git_dir": None, "common_dir": None}
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("Git state could not be checked; retry sync") from exc
