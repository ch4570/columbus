#!/usr/bin/env python3
"""Build a reproducible source ZIP and SHA-256 inventory using only the stdlib."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
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


def build_bundle(root: Path, output: Path) -> dict:
    root, output = root.resolve(strict=True), output.resolve()
    version = package_version(root)
    contents = bundle_contents(root)
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
    args = parser.parse_args(argv)
    print(json.dumps(build_bundle(ROOT, args.output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
