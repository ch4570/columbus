#!/usr/bin/env python3
"""Build a reproducible source ZIP and SHA-256 inventory using only the stdlib."""
from __future__ import annotations

import argparse
from email.parser import BytesParser
import ast
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = "BUNDLE-MANIFEST.json"


def package_version(root: Path) -> str:
    module = ast.parse((root / "skills/columbus/scripts/columbus/__init__.py").read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets):
            version = ast.literal_eval(node.value)
            if isinstance(version, str) and version and all(c.isalnum() or c in ".-_" for c in version):
                return version
    raise ValueError("A literal, filename-safe package __version__ is required")


def bundle_contents(root: Path) -> dict[str, bytes]:
    source = root / "skills/columbus"
    spec = importlib.util.spec_from_file_location("_columbus_distribution_installer", source / "scripts/install.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    _, skill = installer._bundle(source)
    contents = {f"skills/columbus/{relative}": data for relative, data in skill.items()}
    required = ("README.md", "LICENSE", "bootstrap.py", "install.py", "run.py", "get-columbus.py", "pyproject.toml",
                "setup.py", "MANIFEST.in", "scripts/build_bundle.py", "scripts/verify_distribution.py")
    for relative in required:
        contents[relative] = installer._read_regular(root / relative)
    for relative in ("VALIDATION.md", "README.ko.md", "INSTALL.md", "CONTRIBUTING.md", "CHANGELOG.md",
                     "SECURITY.md", "SUPPORT.md", ".editorconfig", ".gitattributes", ".gitignore", ".pre-commit-hooks.yaml"):
        if (root / relative).is_file():
            contents[relative] = installer._read_regular(root / relative)
    for directory in ("scripts", "tests", "skills/columbus/scripts/tests"):
        for path in installer._walk_files(root / directory, python_only=True):
            contents[path.relative_to(root).as_posix()] = installer._read_regular(path)
    for path in installer._walk_files(root / "examples"):
        contents[path.relative_to(root).as_posix()] = installer._read_regular(path)
    for directory in ("docs", "evals", ".github"):
        for path in installer._walk_files(root / directory):
            contents[path.relative_to(root).as_posix()] = installer._read_regular(path)
    return contents


def java_wheel_contents(wheelhouse: Path) -> dict[str, bytes]:
    """Bundle the reviewed parser build, retaining each wheel's upstream license."""
    version = "0.23.5+columbus.1"
    wheels = sorted(wheelhouse.glob("tree_sitter_java-*.whl"))
    if not wheels:
        raise ValueError("Java wheelhouse contains no tree_sitter_java wheels")
    contents = {}
    for wheel in wheels:
        if wheel.is_symlink() or not wheel.is_file():
            raise ValueError("Java wheel must be a regular, non-symlink file")
        data = wheel.read_bytes()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            metadata = [name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
            if len(metadata) != 1:
                raise ValueError("Java wheel must have exactly one package metadata entry")
            package = BytesParser().parsebytes(archive.read(metadata[0]))
            if (package.get_all('Name') != ['tree-sitter-java']
                    or package.get_all('Version') != [version]
                    or not wheel.name.startswith(f'tree_sitter_java-{version}-')):
                raise ValueError("Java wheel does not contain the reviewed candidate version")
            if not any(name.endswith('/LICENSE') for name in archive.namelist()):
                raise ValueError("Java wheel must retain its upstream license")
        contents['vendor/java/' + wheel.name] = data
    contents['vendor/java/constraints.txt'] = f'tree-sitter-java=={version}\n'.encode('ascii')
    inventory = {'format': 1, 'version': version,
                 'files': {name.removeprefix('vendor/java/'): hashlib.sha256(data).hexdigest()
                           for name, data in sorted(contents.items())}}
    contents['vendor/java/manifest.json'] = (json.dumps(inventory, sort_keys=True, indent=2)+'\n').encode()
    return contents


def build_bundle(root: Path, output: Path, *, java_wheelhouse: Path | None = None) -> dict:
    root, output = root.resolve(strict=True), output.resolve()
    version = package_version(root)
    contents = bundle_contents(root)
    if java_wheelhouse is not None:
        contents.update(java_wheel_contents(java_wheelhouse))
    metadata = json.loads(contents["skills/columbus/bundle.json"])
    if metadata.get("version") != version:
        raise ValueError("Package and skill bundle versions must match before distribution")
    inventory = {"format": 1, "name": "columbus", "version": version,
                 "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(contents.items())}}
    contents[INVENTORY] = (json.dumps(inventory, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    output.mkdir(parents=True, exist_ok=True)
    artifact = output / f"columbus-{version}.zip"
    prefix = f"columbus-{version}/"
    with zipfile.ZipFile(artifact, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(contents.items()):
            entry = zipfile.ZipInfo(prefix + name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    checksum = artifact.with_suffix(".zip.sha256")
    checksum.write_text(f"{digest}  {artifact.name}\n", encoding="ascii")
    return {"artifact": str(artifact), "sha256": digest, "checksum": str(checksum),
            "version": version, "files": len(contents), "bytes": artifact.stat().st_size}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--java-wheelhouse", type=Path, help="Embed reviewed Java candidate wheels as the ZIP bootstrap default")
    args = parser.parse_args(argv)
    print(json.dumps(build_bundle(ROOT, args.output_dir, java_wheelhouse=args.java_wheelhouse), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
