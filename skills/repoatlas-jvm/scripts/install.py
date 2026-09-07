#!/usr/bin/env python3
"""Plan or safely apply a pinned RepoAtlas skill bundle to a local repository.

No network access, git commands, hooks, runtime databases, or repository policy
files are involved. An installation is staged beside its destination and the old
directory is retained until promotion succeeds. This provides rollback for normal
errors, not crash-perfect atomic directory replacement.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from typing import Iterator


NAME = "repoatlas-jvm"
MANIFEST = ".bundle-lock.json"
EXCLUDED = {"__pycache__", ".venv", "venv", ".git", ".repoatlas", ".pytest_cache"}
NOTES = [
    "Commit the installed skill and .bundle-lock.json together to pin its contents.",
    "Suggested repository ignore patterns: .repoatlas/ and **/__pycache__/.",
    "No AGENTS.md, .gitignore, runtime index, hooks, or git history is modified.",
    "A staging directory and backup support rollback on normal errors; a process or host crash may require recovery.",
]


class BundleError(ValueError):
    """Unsafe, malformed, or incompatible bundle input."""


def _safe_relative(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise BundleError("Expected a nonempty relative POSIX path")
    path = PurePosixPath(value)
    if not path.parts or path.is_absolute() or any(part in {".", ".."} for part in path.parts):
        raise BundleError(f"Unsafe relative path: {value!r}")
    if path.as_posix() != value or ":" in path.parts[0]:
        raise BundleError(f"Noncanonical relative path: {value!r}")
    return value


def _absolute(path: Path) -> Path:
    """Resolve explicitly chosen roots, including macOS /var and /tmp aliases.

    Descendants are still inspected without resolution so an internal symlink
    cannot redirect managed reads or writes outside the selected root.
    """
    return path.expanduser().resolve(strict=True)


def _check_ancestors(path: Path) -> None:
    for item in (*reversed(path.parents), path):
        if item.is_symlink():
            raise BundleError(f"Symlink paths are refused: {item}")
        if item != path and item.exists() and not item.is_dir():
            raise BundleError(f"A parent path is not a directory: {item}")


def _read_regular(path: Path) -> bytes:
    _check_ancestors(path)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise BundleError(f"Only regular files are supported: {path}")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise BundleError(f"Only regular files are supported: {path}")
        return stream.read()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(files: dict[str, str]) -> str:
    canonical = "".join(f"{path}\0{files[path]}\n" for path in sorted(files))
    return _sha(canonical.encode("utf-8"))


def _walk_files(root: Path, *, python_only: bool = False) -> Iterator[Path]:
    if not root.exists():
        if root.is_symlink():
            raise BundleError(f"Symlink paths are refused: {root}")
        return
    _check_ancestors(root)
    if not root.is_dir():
        raise BundleError(f"Expected bundle directory: {root}")
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name not in EXCLUDED)
        for name in dirs:
            _check_ancestors(Path(directory) / name)
        for name in sorted(files):
            path = Path(directory) / name
            if path.is_symlink():
                raise BundleError(f"Symlink paths are refused: {path}")
            if not python_only or path.suffix == ".py":
                yield path


def _bundle(source: Path) -> tuple[dict, dict[str, bytes]]:
    _check_ancestors(source)
    if not source.is_dir():
        raise BundleError(f"Bundle source is not a directory: {source}")
    candidates = [source / name for name in ("SKILL.md", "bundle.json", "LICENSE")]
    candidates += [source / "scripts" / name for name in ("atlas.py", "install.py")]
    _check_ancestors(source / "scripts")
    candidates += sorted((source / "scripts").glob("requirements*.txt"))
    candidates += list(_walk_files(source / "agents"))
    candidates += list(_walk_files(source / "assets"))
    candidates += list(_walk_files(source / "references"))
    candidates += list(_walk_files(source / "scripts" / "repoatlas", python_only=True))
    contents = {}
    for path in candidates:
        if path.exists() or path.is_symlink():
            relative = _safe_relative(path.relative_to(source).as_posix())
            contents[relative] = _read_regular(path)
    if not {"SKILL.md", "bundle.json"}.issubset(contents):
        raise BundleError("Source must contain SKILL.md and bundle.json")
    try:
        metadata = json.loads(contents["bundle.json"])
    except (ValueError, UnicodeError) as error:
        raise BundleError(f"Invalid bundle.json: {error}") from error
    if not isinstance(metadata, dict) or metadata.get("name") != NAME:
        raise BundleError(f"bundle.json name must be {NAME!r}")
    if not isinstance(metadata.get("version"), str) or not metadata["version"].strip():
        raise BundleError("bundle.json requires a nonempty version string")
    if str(metadata.get("schema_version")) != "2":
        raise BundleError("Unsupported bundle schema_version (expected 2)")
    hashes = {path: _sha(data) for path, data in contents.items()}
    manifest = {
        "lock_version": 1,
        "name": NAME,
        "version": metadata["version"],
        "bundle_digest": _digest(hashes),
        "files": dict(sorted(hashes.items())),
    }
    return manifest, contents


def _load_manifest(destination: Path) -> dict:
    path = destination / MANIFEST
    if not path.exists() and not path.is_symlink():
        raise BundleError(f"Existing skill directory is unmanaged (missing {MANIFEST})")
    try:
        manifest = json.loads(_read_regular(path))
    except (ValueError, UnicodeError) as error:
        raise BundleError(f"Invalid installed manifest: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("lock_version") != 1 or manifest.get("name") != NAME:
        raise BundleError("Invalid installed manifest name or lock_version")
    if not isinstance(manifest.get("version"), str) or not manifest["version"].strip():
        raise BundleError("Invalid installed manifest version")
    files = manifest.get("files")
    if not isinstance(files, dict) or not {"SKILL.md", "bundle.json"}.issubset(files):
        raise BundleError("Invalid installed manifest files")
    for relative, digest in files.items():
        _safe_relative(relative)
        if relative == MANIFEST or any(part in EXCLUDED for part in PurePosixPath(relative).parts):
            raise BundleError(f"Invalid managed file path: {relative}")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise BundleError(f"Invalid managed hash: {relative}")
    if manifest.get("bundle_digest") != _digest(files):
        raise BundleError("Installed manifest digest does not match its file list")
    return manifest


def _snapshot(root: Path) -> dict[str, tuple]:
    """Fingerprint all content so concurrent edits to unmanaged files survive."""
    if not root.exists():
        if root.is_symlink():
            raise BundleError(f"Symlink paths are refused: {root}")
        return {}
    _check_ancestors(root)
    if not root.is_dir():
        raise BundleError(f"Skill destination is not a directory: {root}")
    result = {"": ("directory", stat.S_IMODE(root.stat().st_mode))}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs):
            path = Path(directory) / name
            _check_ancestors(path)
            result[path.relative_to(root).as_posix()] = ("directory", stat.S_IMODE(path.stat().st_mode))
        for name in sorted(files):
            path = Path(directory) / name
            data = _read_regular(path)
            result[path.relative_to(root).as_posix()] = ("file", _sha(data), stat.S_IMODE(path.stat().st_mode))
    return result


def _plan(destination: Path, manifest: dict) -> tuple[dict, dict[str, tuple]]:
    result = {
        "status": "planned",
        "destination": str(destination),
        "version": manifest["version"],
        "bundle_digest": manifest["bundle_digest"],
        "added": [], "updated": [], "removed": [], "conflicts": [],
        "notes": NOTES,
    }
    _check_ancestors(destination)
    snapshot = _snapshot(destination)
    if not destination.exists():
        result["added"] = sorted(manifest["files"])
        return result, snapshot
    old = _load_manifest(destination)
    result["previous_version"] = old["version"]
    old_files, new_files = old["files"], manifest["files"]
    for relative, previous_hash in old_files.items():
        current = snapshot.get(relative)
        if current is None:
            if relative in new_files:
                result["conflicts"].append({"path": relative, "reason": "Managed file was locally deleted"})
        elif current[0] != "file" or current[1] != previous_hash:
            result["conflicts"].append({"path": relative, "reason": "Managed file has local edits"})
        if relative not in new_files:
            result["removed"].append(relative)
    for relative, next_hash in new_files.items():
        current = snapshot.get(relative)
        if relative not in old_files:
            if current is not None:
                result["conflicts"].append({"path": relative, "reason": "New managed path collides with existing content"})
            result["added"].append(relative)
        elif old_files[relative] != next_hash:
            result["updated"].append(relative)
        for parent in PurePosixPath(relative).parents:
            parent_key = parent.as_posix()
            existing_parent = snapshot.get(parent_key)
            if existing_parent and existing_parent[0] != "directory":
                if parent_key not in old_files or parent_key in new_files:
                    result["conflicts"].append({"path": relative, "reason": f"Parent path is a file: {parent_key}"})
    for key in ("added", "updated", "removed"):
        result[key].sort()
    if result["conflicts"]:
        result["status"] = "conflict"
    elif not any(result[key] for key in ("added", "updated", "removed")) and old == manifest:
        result["status"] = "noop"
    return result, snapshot


@contextmanager
def _installation_lock(parent: Path) -> Iterator[None]:
    lock = parent / f".{NAME}.install-lock"
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise BundleError(f"Installation is locked: {lock}. Check for an active installer; recover a stale lock manually.") from error
    try:
        yield
    finally:
        lock.rmdir()


def _apply(destination: Path, manifest: dict, contents: dict[str, bytes], plan: dict,
           snapshot: dict[str, tuple]) -> dict:
    parent = destination.parent
    stage = Path(tempfile.mkdtemp(prefix=f".{NAME}.stage-", dir=parent))
    backup = None
    promoted = False
    try:
        if destination.exists():
            shutil.copytree(destination, stage, dirs_exist_ok=True, symlinks=False)
        for relative in plan["removed"]:
            path = stage / relative
            if path.exists():
                path.unlink()
        for relative, data in contents.items():
            path = stage / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if relative in plan["added"] or relative in plan["updated"]:
                path.write_bytes(data)
        (stage / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _check_ancestors(destination)
        if _snapshot(destination) != snapshot:
            return {**plan, "status": "conflict", "conflicts": [{"path": ".", "reason": "Destination changed while staging; retry after reviewing local edits"}]}
        if destination.exists():
            backup = Path(tempfile.mkdtemp(prefix=f".{NAME}.backup-", dir=parent))
            backup.rmdir()
            destination.rename(backup)
        try:
            stage.rename(destination)
            promoted = True
        except BaseException:
            if backup is not None:
                backup.rename(destination)
                backup = None
            raise
        result = {**plan, "status": "applied"}
        if backup is not None:
            try:
                shutil.rmtree(backup)
                backup = None
            except OSError as error:
                result["notes"] = [*NOTES, f"Installation succeeded; old backup retained at {backup}: {error}"]
        return result
    finally:
        if not promoted and stage.exists():
            shutil.rmtree(stage)


def install_bundle(repo: Path, source: Path | None = None, apply: bool = False,
                   skills_dir: str = ".agents/skills") -> dict:
    """Return a read-only plan unless apply=True; conflicts never overwrite edits."""
    try:
        skills_dir = _safe_relative(skills_dir)
        if any(part in EXCLUDED for part in PurePosixPath(skills_dir).parts):
            raise BundleError("Skill destination cannot be a runtime, environment, or git directory")
        repo = _absolute(Path(repo))
        _check_ancestors(repo)
        if not repo.is_dir():
            raise BundleError(f"Repository directory does not exist: {repo}")
        source = _absolute(Path(source) if source is not None else Path(__file__).parents[1])
        manifest, contents = _bundle(source)
        destination = repo / skills_dir / NAME
        plan, snapshot = _plan(destination, manifest)
        if not apply or plan["status"] in {"conflict", "noop"}:
            return plan
        _check_ancestors(destination.parent)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with _installation_lock(destination.parent):
            # Recompute after locking: another installer may have run since plan.
            plan, snapshot = _plan(destination, manifest)
            if plan["status"] in {"conflict", "noop"}:
                return plan
            return _apply(destination, manifest, contents, plan, snapshot)
    except (BundleError, OSError) as error:
        return {"status": "error", "conflicts": [], "error": str(error), "notes": NOTES}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--source", type=Path, help="Local trusted skill source (default: this bundle)")
    parser.add_argument("--skills-dir", default=".agents/skills", help="Safe repository-relative skill directory")
    parser.add_argument("--apply", action="store_true", help="Apply the plan if there are no conflicts")
    args = parser.parse_args(argv)
    result = install_bundle(args.repo, args.source, args.apply, args.skills_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["status"] in {"conflict", "error"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
