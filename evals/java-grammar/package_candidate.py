"""Stamp an experimental checkout and record generated-source provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

REVISION = '6018d681d319aada6d9fe1b8a8d17f9f4d6c758e'
VERSION = '0.23.5+columbus.1'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('checkout', type=Path)
    parser.add_argument('receipt', type=Path)
    args = parser.parse_args()
    root = args.checkout.resolve()
    revision = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != REVISION:
        raise SystemExit(f'Unexpected upstream revision: {revision}')
    metadata = root / 'pyproject.toml'
    original = metadata.read_text(encoding='utf-8')
    needle = 'version = "0.23.5"'
    if original.count(needle) != 1:
        raise SystemExit('Unexpected upstream package version')
    metadata.write_text(original.replace(needle, f'version = "{VERSION}"'), encoding='utf-8')
    files = ['grammar.js', 'src/parser.c', 'src/node-types.json', 'pyproject.toml',
             'setup.py', 'bindings/python/tree_sitter_java/binding.c', 'LICENSE']
    receipt = {'upstream_revision': revision, 'package_version': VERSION,
               'generator': 'tree-sitter-cli@0.27.0', 'abi': 14,
               'files_sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files},
               'patch_sha256': hashlib.sha256(Path(__file__).with_name('dimensions.patch').read_bytes()).hexdigest()}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
