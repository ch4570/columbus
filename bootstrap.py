"""Local bootstrap helpers. No network access occurs except the explicit pip step."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
SOURCE = Path(__file__).resolve().parent / "skills" / "columbus"
SKILL_RELATIVE = Path(".agents/skills/columbus")
MARKER = ".columbus-runtime.json"
OWNER = "columbus-bootstrap"


class SetupError(RuntimeError):
    pass


def repository(value: str | Path) -> Path:
    # Resolve the explicitly selected root, including macOS /tmp -> /private/tmp.
    root = Path(value).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise SetupError(f"Repository must be an existing directory: {root}")
    return root


def internal(root: Path, relative: str | Path) -> Path:
    """Validate internal paths without resolving away an unexpected symlink."""
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise SetupError("Internal path must remain within the repository")
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise SetupError(f"Symlink inside the installation is refused: {current}")
        if current != root / relative and current.exists() and not current.is_dir():
            raise SetupError(f"Installation parent must be a directory: {current}")
    return current


def layout(root: Path) -> tuple[Path, Path, Path]:
    cache = internal(root, ".columbus")
    runtime = internal(root, ".columbus/runtime")
    skill = internal(root, SKILL_RELATIVE)
    for path in (cache, runtime, skill):
        if path.exists() and not path.is_dir():
            raise SetupError(f"Installation path must be a directory: {path}")
    return cache, runtime, skill


def runtime_state(root: Path, runtime: Path) -> dict | None:
    if not runtime.exists():
        return None
    path = internal(root, runtime.relative_to(root) / MARKER)
    if not path.is_file():
        raise SetupError(f"Refusing unmanaged runtime directory: {runtime}. Choose another repository or move that directory yourself.")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SetupError(f"Invalid runtime ownership marker: {path}") from exc
    if not isinstance(state, dict) or state.get("owner") != OWNER or state.get("format") != 1:
        raise SetupError(f"Runtime ownership marker does not belong to this installer: {path}")
    return state


def save_state(root: Path, runtime: Path, state: dict) -> None:
    path = internal(root, runtime.relative_to(root) / MARKER)
    fd, temporary = tempfile.mkstemp(prefix=".runtime-state-", dir=runtime)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, indent=2)
            stream.write("\n")
        internal(root, path.relative_to(root))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def setup_lock(root: Path):
    cache, _, _ = layout(root)
    cache.mkdir(exist_ok=True)
    lock = internal(root, ".columbus/.bootstrap-lock")
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise SetupError(f"Setup is locked: {lock}. Check for a running installer before removing a stale lock manually.") from exc
    try:
        yield
    finally:
        lock.rmdir()


def bundled_installer():
    spec = importlib.util.spec_from_file_location("_columbus_bundle_installer", SOURCE / "scripts/install.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bundle_plan(root: Path, *, apply: bool = False) -> dict:
    result = bundled_installer().install_bundle(root, SOURCE, apply=apply)
    if result["status"] in {"error", "conflict"}:
        raise SetupError("Bundle install stopped: " + json.dumps(result, ensure_ascii=False))
    return result


def interpreter(root: Path, runtime: Path) -> Path:
    relative = runtime.relative_to(root) / ("Scripts" if os.name == "nt" else "bin")
    directory = internal(root, relative)
    # A venv Python is commonly a symlink. Validate its directory, not the link.
    return directory / ("python.exe" if os.name == "nt" else "python")


def invoke(command: list[str], *, quiet: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(command, stdout=subprocess.DEVNULL if quiet else None,
                          stderr=subprocess.DEVNULL if quiet else None, check=False)


def checked(command: list[str], phase: str) -> None:
    print(f"[columbus] {phase}", file=sys.stderr, flush=True)
    result = invoke(command)
    if result.returncode:
        raise SetupError(f"{phase} failed (exit {result.returncode}). Existing files are retained; fix the reported error and rerun the same install command. Dependencies may have been partially changed.")


def python_command(python: Path, *arguments: str) -> list[str]:
    return [str(python), "-E", "-s", *map(str, arguments)]


def requirements_digest(mcp: bool) -> str:
    files = [SOURCE / "scripts/requirements.txt"]
    if mcp:
        files.append(SOURCE / "scripts/requirements-mcp.txt")
    return hashlib.sha256(b"\0".join(path.read_bytes() for path in files)).hexdigest()


def wheelhouse_digest(wheelhouse: Path | None) -> str | None:
    """Track the explicit local candidates, including same-name replacements."""
    if wheelhouse is None:
        return None
    digest = hashlib.sha256()
    for wheel in sorted(wheelhouse.glob("*.whl")):
        if wheel.is_symlink() or not wheel.is_file():
            raise SetupError(f"Wheelhouse candidate must be a regular, non-symlink file: {wheel}")
        with wheel.open("rb") as stream:
            content = hashlib.file_digest(stream, "sha256").hexdigest()
        digest.update(wheel.name.encode("utf-8") + b"\0" + content.encode("ascii") + b"\0")
    return digest.hexdigest()


def healthy(python: Path, *, mcp: bool, quiet: bool = True) -> bool:
    result = invoke(python_command(python, SOURCE / "scripts/columbus.py", "doctor"), quiet=quiet)
    if result.returncode:
        return False
    if mcp:
        result = invoke(python_command(python, "-c", "import importlib.metadata as m; import mcp; assert m.version('mcp') == '2.1.1', 'MCP version must be 2.1.1'"), quiet=quiet)
    return result.returncode == 0


def bundled_java() -> tuple[Path, dict] | None:
    """Verify the optional release parser payload before changing a runtime."""
    source_root = Path(__file__).resolve().parent
    directory = internal(source_root, "vendor/java")
    if not directory.exists():
        return None
    try:
        manifest = json.loads(internal(source_root, "vendor/java/manifest.json").read_text(encoding="utf-8"))
        files = manifest['files']
        if (manifest['format'] != 1 or manifest['version'] != '0.23.5+columbus.1'
                or not isinstance(files, dict) or 'constraints.txt' not in files
                or not any(name.endswith('.whl') for name in files)
                or set(path.name for path in directory.iterdir()) != set(files) | {'manifest.json'}):
            raise ValueError("Unexpected bundled parser inventory")
        for name, digest in files.items():
            if Path(name).name != name or '/' in name or "\\" in name:
                raise ValueError("Unsafe bundled parser filename")
            path = internal(source_root, Path('vendor/java') / name)
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("Bundled parser checksum mismatch: " + name)
        if (directory/'constraints.txt').read_text(encoding='ascii') != 'tree-sitter-java==0.23.5+columbus.1\n':
            raise ValueError("Unexpected bundled parser constraint")
        return directory, manifest
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SetupError("Invalid bundled Java parser: " + str(exc)) from exc


def bundled_java_ready(python: Path, payload: tuple[Path, dict] | None) -> bool:
    if payload is None:
        return True
    return invoke(python_command(python, '-c',
        "import importlib.metadata as m, sys; assert m.version('tree-sitter-java') == sys.argv[1]",
        payload[1]['version']), quiet=True).returncode == 0


def ensure_runtime(root: Path, *, mcp: bool, offline: bool, wheelhouse: Path | None) -> Path:
    payload = bundled_java() if wheelhouse is None else None
    if payload is not None:
        wheelhouse = payload[0]
    candidates = wheelhouse_digest(wheelhouse)
    _, runtime, _ = layout(root)
    state = runtime_state(root, runtime)
    if state is None:
        runtime.mkdir()
        state = {"owner": OWNER, "format": 1, "requirements_sha256": None}
        save_state(root, runtime, state)
    python = interpreter(root, runtime)
    config = internal(root, runtime.relative_to(root) / "pyvenv.cfg")
    probe = "import sys, pip; from pathlib import Path; assert sys.version_info >= (3, 11); assert Path(sys.prefix).resolve() == Path(sys.argv[1]).resolve()"
    usable = python.is_file() and config.is_file() and invoke(
        python_command(python, "-c", probe, runtime), quiet=True).returncode == 0
    if not usable:
        checked(python_command(Path(sys.executable), "-m", "venv", str(runtime)), "Create dedicated Python environment")
    fingerprint = requirements_digest(mcp)
    changed_candidates = state.get("wheelhouse_sha256") != candidates
    ready = (state.get("requirements_sha256") == fingerprint and not changed_candidates
             and healthy(python, mcp=mcp) and bundled_java_ready(python, payload))
    if not ready:
        requirement = SOURCE / "scripts" / ("requirements-mcp.txt" if mcp else "requirements.txt")
        command = python_command(python, "-m", "pip", "--disable-pip-version-check", "install", "--no-input")
        if offline:
            command.append("--no-index")
        if wheelhouse:
            command.extend(["--find-links", str(wheelhouse), "--upgrade"])
            if changed_candidates:
                command.append("--force-reinstall")
        if payload is not None:
            command.extend(["--constraint", str(payload[0]/"constraints.txt")])
        command.extend(["-r", str(requirement)])
        checked(command, "Install pinned dependencies")
    if not healthy(python, mcp=mcp, quiet=False) or not bundled_java_ready(python, payload):
        raise SetupError("Runtime doctor failed. Review parser versions and SQLite FTS5 support, then rerun the same install command.")
    if (wheelhouse_digest(wheelhouse) != candidates
            or (payload is not None and bundled_java() != payload)):
        raise SetupError("Wheelhouse changed during installation; rerun with stable candidate files.")
    state.update(requirements_sha256=fingerprint, mcp_requested=mcp, wheelhouse_sha256=candidates)
    save_state(root, runtime, state)
    return python
