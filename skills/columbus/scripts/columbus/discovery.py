"""Enumerate safe source and text without executing code or following symlinks."""
from __future__ import annotations

import fnmatch
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tokenize

from .language_profiles import EXTENSION_LANGUAGES, NAME_LANGUAGES, language_for

# A previous private-preview runtime is data, never source for a new index.
EXCLUDED_DIRS = {".git", ".columbus", ".repoatlas", ".omx", ".venv", "venv", "node_modules", "vendor",
                 "dist", "build", "__pycache__", ".mypy_cache", ".pytest_cache",
                 ".agents", ".claude", ".codex", ".gradle", ".idea", "target",
                 "out", "generated", ".next", ".nuxt", ".cache", "coverage", "Pods", "Carthage"}
SECRET_NAMES = {"credentials.py", "secrets.py", "id_rsa", "id_ed25519", ".npmrc",
                ".pypirc", ".netrc", "credentials.json", "service-account.json"}
SECRET_EXTENSIONS = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}
BINARY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip",
                     ".gz", ".tar", ".tgz", ".bz2", ".xz", ".7z", ".jar", ".war", ".class",
                     ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe", ".o", ".a", ".lib",
                     ".db", ".sqlite", ".sqlite3", ".wasm", ".woff", ".woff2", ".ttf",
                     ".mp3", ".mp4", ".mov", ".wav", ".lockb"}
MAX_FILE_BYTES = 1_000_000
SOURCE_EXTENSIONS = set(EXTENSION_LANGUAGES)
CONFIG_NAMES = {"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts",
                "pom.xml", "gradle.properties", "gradle.lockfile", "libs.versions.toml",
                ".columbusignore", ".columbus.json", ".gitignore", "package.json", "tsconfig.json",
                "jsconfig.json", "Cargo.toml", "go.mod", "pyproject.toml", "setup.cfg", "Gemfile",
                "composer.json", "pubspec.yaml", "CMakeLists.txt", "Package.swift", "mix.exs"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_python(data: bytes) -> str:
    encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    return data.decode(encoding)


def safe_source(root: Path, relative: str) -> Path:
    part = Path(relative)
    if part.is_absolute() or ".." in part.parts:
        raise ValueError("Source path must stay inside the indexed repository")
    current = root
    for segment in part.parts:
        current = current / segment
        if current.is_symlink():
            raise ValueError("Symlink source is excluded")
    resolved = current.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("Source path escapes repository")
    return resolved


def module_name(relative: str, source_root: str = ".") -> str:
    path = Path(relative)
    if source_root != ".":
        path = path.relative_to(source_root)
    parts = list(path.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or "__root__"


def load_config(root: Path) -> dict:
    """Read bounded declarative configuration; repository code never executes."""
    path = root / ".columbus.json"
    if not path.exists():
        return {}
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65_536:
        raise ValueError(".columbus.json must be a regular non-symlink file of at most 64 KiB")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid .columbus.json: {exc}") from exc
    if not isinstance(value, dict) or set(value) - {"include", "exclude", "extensions", "declarations"}:
        raise ValueError(".columbus.json accepts only include, exclude, extensions and declarations")
    for key in ("include", "exclude"):
        patterns = value.get(key, [])
        if not isinstance(patterns, list) or len(patterns) > 100 or any(
                not isinstance(p, str) or not p or len(p) > 240 for p in patterns):
            raise ValueError(f".columbus.json {key} must be a list of at most 100 nonempty glob strings")
    extensions = value.get("extensions", {})
    if not isinstance(extensions, dict) or len(extensions) > 100 or any(
            not re.fullmatch(r"\.[A-Za-z0-9_+-]{1,20}", ext)
            or not isinstance(lang, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", lang)
            for ext, lang in extensions.items()):
        raise ValueError(".columbus.json extensions maps dotted suffixes to lowercase language names")
    value["extensions"] = {ext.lower(): lang for ext, lang in extensions.items()}
    declarations = value.get("declarations", {})
    if not isinstance(declarations, dict) or len(declarations) > 100:
        raise ValueError(".columbus.json declarations must map language names to keyword lists")
    for lang, keywords in declarations.items():
        if (not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", lang) or not isinstance(keywords, list)
                or len(keywords) > 30 or any(not isinstance(k, str) or not re.fullmatch(
                    r"[A-Za-z][A-Za-z0-9_. -]{0,39}", k) for k in keywords)):
            raise ValueError(".columbus.json declaration keywords must be short literal words, not regexes")
    return value


def _matches(relative: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(relative, p) or fnmatch.fnmatchcase(Path(relative).name, p)
               or (p.startswith("**/") and fnmatch.fnmatchcase(relative, p[3:]))
               or (p.endswith("/") and relative.startswith(p)) for p in patterns)


def discover(root: Path, source_root: str = ".") -> tuple[list[str], dict]:
    scan_root = safe_source(root, source_root)
    if not scan_root.is_dir():
        raise ValueError("source_root must be an existing directory inside the repository")
    config = load_config(root)
    custom = root / ".columbusignore"
    patterns = list(config.get("exclude", []))
    if custom.is_file() and not custom.is_symlink():
        patterns.extend(line.strip() for line in custom.read_text().splitlines()
                        if line.strip() and not line.lstrip().startswith("#"))
    stats = {"enumeration": "filesystem", "candidate_files": 0, "excluded_files": 0,
             "oversized_paths": [], "unsupported_extensions": {}, "binary_paths": [],
             "language_config": config, "detected_languages": {}, "probe_files": 0, "probe_bytes": 0}
    filesystem = False
    try:
        proc = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(root), "ls-files", "--cached",
                               "--others", "--exclude-standard", "-z"],
                              capture_output=True, timeout=30, check=True)
        paths = sorted(set(os.fsdecode(p) for p in proc.stdout.split(b"\0") if p))
        stats["enumeration"] = "git (tracked + untracked, respects untracked ignores)"
        if not paths:
            ignored = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(root),
                                      "check-ignore", "-q", "--", "."], capture_output=True, timeout=30)
            if ignored.returncode == 0:
                # The caller selected this directory explicitly. An enclosing
                # project's ignored temp/cache folder must not hide its sources.
                filesystem = True
                stats["enumeration"] = "filesystem (explicit root ignored by enclosing Git repository)"
    except (OSError, subprocess.SubprocessError):
        filesystem = True
    if filesystem:
        paths = []
        for folder, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS
                             and not (Path(folder) / d).is_symlink())
            paths.extend((Path(folder) / f).relative_to(root).as_posix() for f in files)
        paths.sort()
    paths = sorted(set(paths) | {name for name in (".columbusignore", ".gitignore", ".columbus.json")
                                 if (root / name).exists()})
    included, configs = [], []
    for rel in paths:
        path = Path(rel)
        if path.name in CONFIG_NAMES and not any(p in EXCLUDED_DIRS for p in path.parts):
            try:
                if safe_source(root, rel).is_file():
                    configs.append(rel)
            except (OSError, ValueError):
                pass
        if path.name in {".columbus.json", ".columbusignore", ".gitignore"}:
            continue
        if source_root != "." and not path.is_relative_to(source_root):
            continue
        if (any(p in EXCLUDED_DIRS for p in path.parts)
                or path.name.lower() in SECRET_NAMES or path.name.startswith(".env")
                or path.suffix.lower() in SECRET_EXTENSIONS or _matches(rel, patterns)
                or (config.get("include") and not _matches(rel, config["include"]))):
            stats["excluded_files"] += 1
            continue
        try:
            actual = safe_source(root, rel)
            if not actual.is_file():
                continue
            stats["candidate_files"] += 1
            if actual.stat().st_size > MAX_FILE_BYTES:
                stats["oversized_paths"].append(rel)
                stats["excluded_files"] += 1
                continue
            if path.suffix.lower() in BINARY_EXTENSIONS:
                stats["binary_paths"].append(rel)
                stats["excluded_files"] += 1
                continue
            known = (path.suffix.lower() in SOURCE_EXTENSIONS or path.name in NAME_LANGUAGES
                     or path.suffix.lower() in config.get("extensions", {}))
            language = language_for(rel, config=config)
            if not known:
                # Only unknown suffixes/extensionless files need content-based
                # detection. Known source files remain metadata-only on fast sync.
                sample = actual.read_bytes()
                stats["probe_files"] += 1
                stats["probe_bytes"] += len(sample)
                shebang_language = language_for(rel, sample[:8192].decode("utf-8-sig", errors="replace"), config)
                try:
                    sample_text = decode_python(sample) if shebang_language == "python" else sample.decode("utf-8-sig")
                except UnicodeError:
                    sample_text = ""
                    sample = b"\0"
                if b"\0" in sample or any(ord(c) < 32 and c not in "\n\r\t\f\b" for c in sample_text):
                    stats["binary_paths"].append(rel)
                    stats["excluded_files"] += 1
                    continue
                language = language_for(rel, sample_text, config)
        except (ValueError, OSError):
            stats["excluded_files"] += 1
            continue
        included.append(rel)
        stats["detected_languages"][rel] = language
        if language == "text" and path.suffix.lower() not in SOURCE_EXTENSIONS and path.name not in NAME_LANGUAGES:
            suffix = path.suffix or "[no extension]"
            stats["unsupported_extensions"][suffix] = stats["unsupported_extensions"].get(suffix, 0) + 1
    stats["config_paths"] = configs
    return included, stats
