#!/usr/bin/env python3
"""Collect one version's release assets and write their SHA-256 checksums."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil

from build_bundle import ROOT, package_version


def prepare(dist: Path, tag: str | None = None) -> list[Path]:
    version = package_version(ROOT)
    if tag is not None and tag != 'v' + version:
        raise ValueError('Release tag must match the package and bundle version: v' + version)
    if json.loads((ROOT / 'skills/repoatlas-jvm/bundle.json').read_text(encoding='utf-8'))['version'] != version:
        raise ValueError('Skill bundle version must match the package version')
    source = ast.parse((ROOT / 'get-repoatlas.py').read_text(encoding='utf-8'))
    defaults = [ast.literal_eval(node.value) for node in source.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == 'DEFAULT_VERSION' for target in node.targets)]
    if defaults != [version]:
        raise ValueError('Standalone installer DEFAULT_VERSION must match the package version')
    wheel = dist / f'repoatlas-{version}-py3-none-any.whl'
    bundle = dist / f'repoatlas-{version}.zip'
    for artifact in (wheel, bundle):
        if not artifact.is_file() or artifact.is_symlink():
            raise ValueError('Build the matching wheel and ZIP first: ' + artifact.name)
    installer = dist / 'get-repoatlas.py'
    shutil.copyfile(ROOT / 'get-repoatlas.py', installer)
    assets = [wheel, bundle, installer]
    checksum = dist / 'SHA256SUMS.txt'
    checksum.write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n'
                                for p in assets), encoding='ascii')
    return [*assets, checksum]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist')
    parser.add_argument('--tag', help='Reject a tag that differs from the source version')
    args = parser.parse_args()
    try:
        print(json.dumps({'assets': [str(p) for p in prepare(args.dist, args.tag)]}, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(2, str(exc) + '\n')
