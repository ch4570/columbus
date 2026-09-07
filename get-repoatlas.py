#!/usr/bin/env python3
"""Install a checksum-verified RepoAtlas release without pipx or uv (Python 3.11+)."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


DEFAULT_VERSION = "0.5.0"
RELEASES = "https://github.com/ch4570/repo-graph/releases/download"
OWNER = "repoatlas-release-installer"
PREFIX_MARKER = ".repoatlas-install.json"
RUNTIME_MARKER = ".repoatlas-runtime.json"
MAX_WHEEL_BYTES = 20 * 1024 * 1024
MAX_CHECKSUM_BYTES = 256 * 1024
WINDOWS = os.name == "nt"


class InstallError(RuntimeError):
    pass


def version_number(value: str) -> str:
    if not re.fullmatch(r"(?:0|[1-9][0-9]{0,7})\.(?:0|[1-9][0-9]{0,7})\.(?:0|[1-9][0-9]{0,7})", value):
        raise argparse.ArgumentTypeError("Use a release version such as 0.5.0 (X.Y.Z).")
    return value


def default_paths() -> tuple[Path, Path]:
    if WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return base / "RepoAtlas", base / "RepoAtlas/bin"
    return Path.home() / ".local/share/repoatlas", Path.home() / ".local/bin"


def plain_path(value: Path) -> Path:
    """Keep lexical paths so a symlink or Windows junction cannot disappear in resolve()."""
    path = value.expanduser().absolute()
    if ".." in path.parts or any(ord(char) < 32 for char in str(path)):
        raise InstallError(f"Choose a path without '..' or control characters: {path}")
    for current in reversed([path, *path.parents]):
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise InstallError(f"Symlink or junction in installation path is refused: {current}")
        if current != path and not stat.S_ISDIR(info.st_mode):
            raise InstallError(f"Installation parent is not a directory: {current}")
    return path


def directory(path: Path, *, create: bool = False) -> Path:
    path = plain_path(path)
    if path.exists() and not path.is_dir():
        raise InstallError(f"Installation path is not a directory: {path}")
    if create:
        path.mkdir(parents=True, exist_ok=True)
        plain_path(path)
    return path


def read_marker(path: Path, prefix: Path, *, version: str | None = None) -> dict:
    plain_path(path)
    try:
        if path.stat().st_size > 8192 or not path.is_file():
            raise ValueError("not a small regular file")
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise InstallError(f"Missing or invalid ownership marker: {path}. Existing files are preserved; choose another --prefix.") from error
    if (not isinstance(state, dict) or state.get("owner") != OWNER or state.get("format") != 1
            or state.get("prefix") != str(prefix) or (version is not None and state.get("version") != version)):
        raise InstallError(f"Refusing an unmanaged installation: {path}. Choose another --prefix.")
    return state


def marker(prefix: Path, **fields) -> dict:
    return {"owner": OWNER, "format": 1, "prefix": str(prefix), **fields}


def write_marker(path: Path, value: dict, *, replace: bool = False) -> None:
    plain_path(path)
    if replace:
        read_marker(path, Path(value["prefix"]), version=value.get("version"))
    data = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if not replace:
        with path.open("xb") as stream:
            stream.write(data)
        return
    descriptor, temporary = tempfile.mkstemp(prefix=".repoatlas-state-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        plain_path(path)
        os.replace(temporary, path)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


@contextmanager
def installation_lock(prefix: Path):
    directory(prefix)
    if prefix.exists():
        read_marker(prefix / PREFIX_MARKER, prefix)
    else:
        prefix.mkdir(parents=True, mode=0o700)
        plain_path(prefix)
        write_marker(prefix / PREFIX_MARKER, marker(prefix))
    lock = plain_path(prefix / ".install-lock")
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise InstallError(f"An installer is already running, or its lock remains: {lock}. After confirming no installer is running, remove this empty lock directory and retry.") from error
    try:
        yield
    finally:
        lock.rmdir()


def limited_copy(source, destination, limit: int) -> None:
    total = 0
    deadline = time.monotonic() + 120
    while True:
        block = source.read(min(64 * 1024, limit - total + 1))
        total += len(block)
        if total > limit:
            raise InstallError(f"Artifact exceeds the {limit}-byte download limit.")
        if time.monotonic() > deadline:
            raise InstallError("Artifact download exceeded 120 seconds.")
        if not block:
            return
        destination.write(block)


class HTTPSRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        if not newurl.startswith("https://"):
            raise InstallError("Release download redirected away from HTTPS.")
        return super().redirect_request(request, response, code, message, headers, newurl)


def download(url: str, target: Path, limit: int) -> None:
    print(f"[repoatlas] Download {url}", file=sys.stderr, flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "RepoAtlas-installer/1"})
    opener = urllib.request.build_opener(HTTPSRedirects())
    try:
        response = opener.open(request, timeout=30)
    except urllib.error.HTTPError as error:
        if error.code in {401, 403, 404}:
            raise InstallError("Release is unavailable or requires GitHub sign-in. Download the wheel and "
                               "SHA256SUMS.txt from the authenticated release page, then use --wheel PATH "
                               "--checksum-file PATH. Check that the requested release exists.") from error
        raise
    with response, target.open("xb") as output:
        length = response.headers.get("Content-Length")
        if length is not None and int(length) > limit:
            raise InstallError(f"Artifact exceeds the {limit}-byte download limit.")
        limited_copy(response, output, limit)


def checksum_for(path: Path, wheel_name: str) -> str:
    if path.stat().st_size > MAX_CHECKSUM_BYTES:
        raise InstallError("Checksum file is too large.")
    matches = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([a-fA-F0-9]{64}) [ *](.+)", line)
        if match and match.group(2) == wheel_name:
            matches.append(match.group(1).lower())
    if len(matches) != 1:
        raise InstallError(f"Checksum file must contain exactly one SHA256 entry for {wheel_name}.")
    return matches[0]


def verified_wheel(args, temporary: Path) -> tuple[Path, str]:
    name = f"repoatlas-{args.version}-py3-none-any.whl"
    wheel, checksums = temporary / name, temporary / "SHA256SUMS.txt"
    if args.wheel:
        if args.wheel.name != name:
            raise InstallError(f"Expected wheel filename {name}; received {args.wheel.name}.")
        for source, target, limit in ((args.wheel, wheel, MAX_WHEEL_BYTES),
                                      (args.checksum_file, checksums, MAX_CHECKSUM_BYTES)):
            with source.open("rb") as incoming, target.open("xb") as outgoing:
                limited_copy(incoming, outgoing, limit)
    else:
        url = f"{RELEASES}/v{args.version}"
        download(f"{url}/SHA256SUMS.txt", checksums, MAX_CHECKSUM_BYTES)
        download(f"{url}/{name}", wheel, MAX_WHEEL_BYTES)
    expected = checksum_for(checksums, name)
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if digest != expected:
        raise InstallError("Wheel SHA256 does not match SHA256SUMS.txt. Nothing will be installed.")
    return wheel, digest


def environment() -> dict[str, str]:
    result = {name: value for name, value in os.environ.items()
              if not name.upper().startswith(("PYTHON", "PIP_")) and name.upper() != "VIRTUAL_ENV"}
    # pip honors this even in isolated mode: no system/user/site pip config can
    # redirect installation into a target, prefix, or system environment.
    result["PIP_CONFIG_FILE"] = os.devnull
    return result


def invoke(command: list[str | Path], *, capture: bool = False, timeout: int = 600):
    return subprocess.run([str(part) for part in command], env=environment(), check=False,
                          capture_output=capture, text=True, encoding="utf-8", timeout=timeout)


def binaries(runtime: Path) -> tuple[Path, Path]:
    binary = directory(runtime / ("Scripts" if WINDOWS else "bin"))
    return binary / ("python.exe" if WINDOWS else "python"), binary / ("repoatlas.exe" if WINDOWS else "repoatlas")


def check_boundary(runtime: Path) -> Path:
    python, _ = binaries(runtime)
    config = plain_path(runtime / "pyvenv.cfg")
    if not config.is_file() or not re.search(r"^include-system-site-packages\s*=\s*false\s*$", config.read_text(encoding="utf-8"), re.MULTILINE | re.IGNORECASE):
        raise InstallError(f"Runtime is not an isolated virtual environment: {runtime}")
    probe = "import json,sys; print(json.dumps({'prefix':sys.prefix,'base_prefix':sys.base_prefix}))"
    result = invoke([python, "-I", "-c", probe], capture=True, timeout=60)
    if result.returncode:
        raise InstallError(f"Virtual environment verification failed: {result.stderr.strip()}")
    try:
        info = json.loads(result.stdout)
        valid = Path(info["prefix"]).resolve() == runtime.resolve() and info["prefix"] != info["base_prefix"]
    except (ValueError, KeyError, TypeError):
        valid = False
    if not valid:
        raise InstallError(f"Python does not belong to this isolated environment: {runtime}")
    return python


def check_health(runtime: Path, version: str) -> None:
    python = check_boundary(runtime)
    _, entrypoint = binaries(runtime)
    plain_path(entrypoint)
    if not entrypoint.is_file():
        raise InstallError(f"Runtime has no RepoAtlas executable: {entrypoint}")
    result = invoke([python, "-I", "-c", "import importlib.metadata as m; print(m.version('repoatlas'))"], capture=True, timeout=60)
    if result.returncode or result.stdout.strip() != version:
        raise InstallError(f"Installed package must be RepoAtlas {version} inside {runtime}.")
    result = invoke([python, "-I", "-m", "repoatlas", "doctor"], capture=True, timeout=60)
    try:
        report = json.loads(result.stdout)
        ready = report["ready"] is True and report["bundle"]["version"] == version
    except (ValueError, KeyError, TypeError):
        ready = False
    if result.returncode or not ready:
        raise InstallError(f"RepoAtlas doctor failed in {runtime}:\n{result.stdout}{result.stderr}")


def resumable_runtime(runtime: Path) -> None:
    """Only the interpreter links and Linux lib64 link may leave a partial tree."""
    for path in runtime.rglob("*"):
        info = path.lstat()
        if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
            raise InstallError(f"Unexpected hard link in incomplete environment: {path}. Choose another --prefix; existing files are preserved.")
        if stat.S_ISLNK(info.st_mode):
            relative = path.relative_to(runtime)
            python_link = (not WINDOWS and len(relative.parts) == 2 and relative.parts[0] == "bin"
                           # Python 3.14's stdlib venv also creates this alias.
                           and (re.fullmatch(r"python(?:[0-9]+(?:\.[0-9]+)?)?", relative.name) or relative.name == "𝜋thon")
                           and path.resolve() == Path(sys.executable).resolve())
            lib_link = relative.parts == ("lib64",) and path.resolve() == runtime / "lib"
            if python_link or lib_link:
                continue
        elif stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode):
            if not getattr(info, "st_file_attributes", 0) & 0x400:
                continue
        raise InstallError(f"Unexpected link or special file in incomplete environment: {path}. Choose another --prefix; existing files are preserved.")
    config = runtime / "pyvenv.cfg"
    python, _ = binaries(runtime)
    if config.exists() and python.exists():
        check_boundary(runtime)


def windows_helper(prefix: Path, version: str) -> str:
    identity = hashlib.sha256(str(prefix).encode("utf-8")).hexdigest()[:16]
    return f".repoatlas-{identity}-{version}.exe"


def windows_launcher(prefix: Path, version: str) -> bytes:
    # The adjacent pip-generated .exe contains the original Unicode interpreter
    # path. ASCII batch text avoids code-page corruption of paths and uses no
    # interpolated shell commands or executable lookup through PATH.
    return (f"@echo off\r\nrem RepoAtlas managed launcher {version}\r\n"
            f"setlocal DisableDelayedExpansion\r\n"
            f'"%~dp0{windows_helper(prefix, version)}" %*\r\n').encode("ascii")


def owned_launcher(launcher: Path, prefix: Path) -> str | None:
    directory(launcher.parent)
    if WINDOWS:
        for suffix in (".exe", ".com", ".bat", ""):
            alternate = launcher.parent / ("repoatlas" + suffix)
            if os.path.lexists(alternate):
                raise InstallError(f"Another command would shadow the managed launcher: {alternate}. Choose another --bin-dir.")
    if not os.path.lexists(launcher):
        return None
    if WINDOWS:
        plain_path(launcher)
        if not launcher.is_file() or launcher.stat().st_size > 1024:
            raise InstallError(f"Refusing to overwrite an unmanaged launcher: {launcher}")
        data = launcher.read_bytes()
        match = re.search(rb"\r\nrem RepoAtlas managed launcher ([0-9.]+)\r\n", data)
        version = match.group(1).decode("ascii") if match else ""
        try:
            version_number(version)
        except argparse.ArgumentTypeError:
            raise InstallError(f"Refusing to overwrite an unmanaged launcher: {launcher}") from None
        if data != windows_launcher(prefix, version):
            raise InstallError(f"Refusing to overwrite an unmanaged launcher: {launcher}")
    else:
        if not launcher.is_symlink():
            raise InstallError(f"Refusing to overwrite an unmanaged launcher: {launcher}")
        target = Path(os.readlink(launcher))
        try:
            relative = target.relative_to(prefix / "versions")
            version = version_number(relative.parts[0])
        except (ValueError, IndexError, argparse.ArgumentTypeError):
            raise InstallError(f"Refusing to overwrite an unmanaged launcher: {launcher}") from None
        if relative.parts != (version, "bin", "repoatlas"):
            raise InstallError(f"Refusing to overwrite an unmanaged launcher: {launcher}")
    state = read_marker(prefix / "versions" / version / RUNTIME_MARKER, prefix, version=version)
    if state.get("status") != "ready":
        raise InstallError(f"Existing launcher does not refer to a verified installation: {launcher}")
    return version


def activate(prefix: Path, bin_dir: Path, runtime: Path, version: str) -> Path:
    directory(bin_dir, create=True)
    launcher = bin_dir / ("repoatlas.cmd" if WINDOWS else "repoatlas")
    previous = owned_launcher(launcher, prefix)
    _, entrypoint = binaries(runtime)
    if WINDOWS:
        helper = plain_path(bin_dir / windows_helper(prefix, version))
        source = entrypoint.read_bytes()
        if helper.exists():
            if not helper.is_file() or helper.stat().st_size != len(source) or helper.read_bytes() != source:
                raise InstallError(f"Refusing to overwrite an unmanaged Windows launcher helper: {helper}")
        else:
            with helper.open("xb") as stream:
                stream.write(source)
        data = windows_launcher(prefix, version)
        if previous == version:
            return launcher
        descriptor, name = tempfile.mkstemp(prefix=".repoatlas-launcher-", dir=bin_dir)
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
    else:
        if previous == version:
            return launcher
        if previous is None:
            launcher.symlink_to(entrypoint)
            return launcher
        descriptor, name = tempfile.mkstemp(prefix=".repoatlas-launcher-", dir=bin_dir)
        os.close(descriptor)
        temporary = Path(name)
        temporary.unlink()
        temporary.symlink_to(entrypoint)
    try:
        if owned_launcher(launcher, prefix) != previous:
            raise InstallError("Launcher changed during installation; rerun after other installers finish.")
        if previous is None:
            # An exclusive hard link cannot overwrite a command another
            # installer created between the ownership check and activation.
            os.link(temporary, launcher)
        else:
            os.replace(temporary, launcher)
    finally:
        temporary.unlink(missing_ok=True)
    return launcher


def install(args) -> tuple[Path, bool]:
    prefix, bin_dir = directory(args.prefix), directory(args.bin_dir)
    if prefix.exists():
        read_marker(prefix / PREFIX_MARKER, prefix)
    launcher = bin_dir / ("repoatlas.cmd" if WINDOWS else "repoatlas")
    owned_launcher(launcher, prefix)
    with installation_lock(prefix):
        versions = directory(prefix / "versions")
        runtime = directory(versions / args.version)
        state = read_marker(runtime / RUNTIME_MARKER, prefix, version=args.version) if runtime.exists() else None
        if state and state.get("status") not in {"installing", "ready"}:
            raise InstallError(f"Unexpected installation state at {runtime}. Existing files are preserved; choose another --prefix.")
        ready = state is not None and state["status"] == "ready"
        if ready:
            try:
                check_health(runtime, args.version)
            except (InstallError, OSError, subprocess.TimeoutExpired) as error:
                raise InstallError(f"Existing version failed verification and was preserved: {runtime}. Choose another --prefix to install a fresh environment. {error}") from error
        with tempfile.TemporaryDirectory(prefix="repoatlas-release-") as temporary:
            if not ready or args.wheel:
                wheel, digest = verified_wheel(args, Path(temporary))
                if state and state.get("wheel_sha256") != digest:
                    raise InstallError("This version is already installed from different wheel bytes. Existing files are preserved; choose another --prefix.")
            if not ready:
                directory(versions, create=True)
                if state:
                    resumable_runtime(runtime)
                else:
                    runtime.mkdir(mode=0o700)
                    write_marker(runtime / RUNTIME_MARKER, marker(prefix, version=args.version, status="installing", wheel_sha256=digest))
                print(f"[repoatlas] Create isolated environment: {runtime}", file=sys.stderr, flush=True)
                result = invoke([sys.executable, "-I", "-m", "venv", runtime])
                if result.returncode:
                    raise InstallError("Creating the virtual environment failed. Install Python's venv/ensurepip support, then rerun the same command; the old command is preserved.")
                python = check_boundary(runtime)
                command = [python, "-I", "-m", "pip", "--isolated", "--disable-pip-version-check", "install",
                           "--no-input", "--no-cache-dir", "--only-binary=:all:"]
                if args.offline:
                    command.append("--no-index")
                if args.wheelhouse:
                    command.extend(["--find-links", args.wheelhouse])
                if state:
                    command.append("--force-reinstall")
                command.append(wheel)
                result = invoke(command)
                if result.returncode:
                    raise InstallError(f"Package installation failed; the old command is preserved. Fix the reported issue and rerun the same command to resume {runtime}.")
                check_health(runtime, args.version)
                write_marker(runtime / RUNTIME_MARKER, marker(prefix, version=args.version, status="ready", wheel_sha256=digest), replace=True)
        return activate(prefix, bin_dir, runtime, args.version), ready


def main(argv: list[str] | None = None) -> int:
    prefix, bin_dir = default_paths()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", type=version_number, default=DEFAULT_VERSION, help="Pinned release to install (default: %(default)s)")
    parser.add_argument("--prefix", type=Path, default=prefix, help=f"Managed environments (default: {prefix})")
    parser.add_argument("--bin-dir", type=Path, default=bin_dir, help=f"Public command directory (default: {bin_dir})")
    parser.add_argument("--wheel", type=Path, help="Local release wheel; requires --checksum-file")
    parser.add_argument("--checksum-file", type=Path, help="Local SHA256SUMS.txt; requires --wheel")
    parser.add_argument("--wheelhouse", type=Path, help="Directory containing compatible dependency wheels")
    parser.add_argument("--offline", action="store_true", help="Use only the supplied wheel, checksums, and wheelhouse")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required.")
    if bool(args.wheel) != bool(args.checksum_file):
        parser.error("--wheel and --checksum-file must be supplied together.")
    if args.offline and not (args.wheel and args.checksum_file and args.wheelhouse):
        parser.error("--offline requires --wheel, --checksum-file, and --wheelhouse.")
    try:
        if args.wheelhouse:
            args.wheelhouse = args.wheelhouse.expanduser().resolve(strict=True)
            if not args.wheelhouse.is_dir():
                raise InstallError("--wheelhouse must be a directory.")
        for name in ("wheel", "checksum_file"):
            if getattr(args, name):
                value = getattr(args, name).expanduser().absolute()
                if not value.is_file():
                    raise InstallError(f"--{name.replace('_', '-')} must be a regular file: {value}")
                setattr(args, name, value)
        launcher, repeated = install(args)
    except (InstallError, OSError, ValueError, subprocess.TimeoutExpired, urllib.error.URLError) as error:
        print(f"[repoatlas] Installation stopped: {error}", file=sys.stderr)
        return 1
    print(f"RepoAtlas {args.version} {'already installed and verified' if repeated else 'installed and verified'}.")
    print(f"Command: {launcher}")
    paths = {os.path.normcase(os.path.abspath(part)) for part in os.environ.get("PATH", "").split(os.pathsep) if part}
    existing_command = shutil.which("repoatlas")
    shadowed = existing_command and os.path.normcase(os.path.abspath(existing_command)) != os.path.normcase(str(launcher))
    if shadowed:
        print(f"Another repoatlas command appears first on PATH: {existing_command}")
    if os.path.normcase(str(launcher.parent)) not in paths or shadowed:
        print(f"Add this directory to PATH: {launcher.parent}")
        if WINDOWS:
            escaped = str(launcher.parent).replace("'", "''")
            print(f"For this PowerShell session: $env:Path = '{escaped};' + $env:Path")
        else:
            import shlex
            print(f"For this shell session: export PATH={shlex.quote(str(launcher.parent))}:\"$PATH\"")
    print("Next: repoatlas doctor")
    print("      repoatlas explore --repo /path/to/your/project")
    print("Shell profiles and existing project files were not modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
