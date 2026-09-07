"""Read-only Git identity and ordinary concurrent-edit detection for sync."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

from .discovery import MAX_FILE_BYTES, safe_source


class SnapshotChanged(ValueError):
    """Caller should rerun sync against a stable working tree."""


def stat_signature(stat) -> list[int]:
    return [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino, stat.st_dev]


def file_stat(root: Path, relative: str) -> list[int]:
    return stat_signature(safe_source(root, relative).stat())


def read_stable(root: Path, relative: str, expected: list[int] | None = None,
                max_bytes: int = MAX_FILE_BYTES) -> tuple[bytes, list[int]]:
    path = safe_source(root, relative)
    before = stat_signature(path.stat())
    if expected is not None and before != expected:
        raise SnapshotChanged(f"File changed during sync: {relative}; retry sync")
    with path.open("rb") as stream:
        opened = stat_signature(os.fstat(stream.fileno()))
        data = stream.read(max_bytes + 1)
        after_open = stat_signature(os.fstat(stream.fileno()))
    after = stat_signature(safe_source(root, relative).stat())
    if before != opened or opened != after_open or after_open != after:
        raise SnapshotChanged(f"File changed while being read: {relative}; retry sync")
    if len(data) > max_bytes:
        raise ValueError(f"File exceeds {max_bytes} byte limit: {relative}")
    return data, after


def git_state(root: Path) -> dict:
    """Never run hooks, builds, shell commands, or a repository fsmonitor."""
    def run(*args: str, optional: bool = False):
        proc = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(root), *args],
                              capture_output=True, text=True, timeout=10)
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
