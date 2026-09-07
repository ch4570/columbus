"""Assemble one three-OS parser ZIP, then verify identical bytes on each runner."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from build_bundle import build_bundle, java_wheel_contents
from verify_distribution import verify, verify_archive
from package_candidate import REVISION, VERSION

PLATFORMS = ('ubuntu-latest', 'macos-latest', 'windows-latest')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')


def select(inputs):
    selected = []
    for platform in PLATFORMS:
        folder = inputs/f'java-candidate-{platform}-py3.11'
        provenance = json.loads((folder/'provenance.json').read_text(encoding='utf-8'))
        runtime = json.loads((folder/'runtime.json').read_text(encoding='utf-8'))
        distribution = json.loads((folder/'distribution.json').read_text(encoding='utf-8'))
        if (provenance['upstream_revision'] != REVISION or provenance['package_version'] != VERSION
                or provenance['generator'] != 'tree-sitter-cli@0.27.0' or provenance['abi'] != 14
                or provenance['patch_sha256'] != sha(Path(__file__).with_name('dimensions.patch'))
                or runtime['package_version'] != VERSION or distribution['status'] != 'passed'
                or distribution['bundled_java_default'] is not True):
            raise ValueError('Candidate provenance/installation gate failed: '+platform)
        for name, invalid in [('primitive', False), ('array', False), ('generic', False), ('invalid_after_ellipsis', True)]:
            if runtime['fixtures'][name]['partial'] is not invalid:
                raise ValueError('Candidate grammar gate failed: '+platform)
        wheels = list(folder.glob('*.whl'))
        if len(wheels) != 1:
            raise ValueError('Expected one candidate wheel: '+platform)
        wheel = wheels[0]
        java_wheel_contents(folder)  # Metadata/version/license validation.
        if not runtime['binary_sha256']:
            raise ValueError('Missing tested native binary hashes: '+platform)
        with zipfile.ZipFile(wheel) as archive:
            for name, digest in runtime['binary_sha256'].items():
                matches = [member for member in archive.namelist() if Path(member).name == name]
                if len(matches) != 1 or hashlib.sha256(archive.read(matches[0])).hexdigest() != digest:
                    raise ValueError('Wheel differs from tested native binary: '+platform)
        selected.append({'platform': platform, 'build_python': '3.11', 'filename': wheel.name,
                         'sha256': sha(wheel), 'provenance': provenance,
                         'tested_binary_sha256': runtime['binary_sha256'], '_path': wheel})
    for field in ('grammar.js', 'src/parser.c', 'src/node-types.json', 'bindings/python/tree_sitter_java/binding.c', 'LICENSE'):
        if len({r['provenance']['files_sha256'][field] for r in selected}) != 1:
            raise ValueError('Candidate generated sources disagree: '+field)
    if len({r['filename'] for r in selected}) != len(PLATFORMS):
        raise ValueError('Candidate wheel filenames collide')
    return selected


def assemble(inputs, output):
    selected = select(inputs)
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='columbus aggregate wheels ') as temporary:
        wheels = Path(temporary)
        for record in selected:
            shutil.copyfile(record['_path'], wheels/record['filename'])
        bundle = build_bundle(ROOT, output, java_wheelhouse=wheels)
    subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--wheel-dir', str(output), str(ROOT)], check=True)
    wheel, = output.glob('columbus-*.whl')
    selected = [{k: v for k, v in r.items() if k != '_path'} for r in selected]
    manifest = {'format': 1, 'source_revision': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
                'source_tracked_dirty': subprocess.run(['git', '-C', str(ROOT), 'diff', '--quiet', 'HEAD']).returncode != 0,
                'selection': 'Python 3.11 abi3 build for each OS; this exact combined artifact requires all consumer checks',
                'selected': selected,
                'files': {path.name: sha(path) for path in (wheel, Path(bundle['artifact']))}}
    dump(output/'aggregate.json', manifest)
    return manifest


def verify_aggregate(artifacts, output):
    manifest = json.loads((artifacts/'aggregate.json').read_text(encoding='utf-8'))
    files = manifest['files']
    if manifest['format'] != 1 or len(files) != 2:
        raise ValueError('Unexpected aggregate manifest')
    for name, digest in files.items():
        if Path(name).name != name or '/' in name or '\\' in name:
            raise ValueError('Unsafe aggregate filename')
        path = artifacts/name
        if path.is_symlink() or not path.is_file() or sha(path) != digest:
            raise ValueError('Aggregate checksum mismatch: '+name)
    wheel, = [artifacts/name for name in files if name.endswith('.whl')]
    bundle, = [artifacts/name for name in files if name.endswith('.zip')]
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='columbus aggregate verify ') as temporary:
        extracted = verify_archive(bundle, Path(temporary))
        wheels = extracted/'vendor/java'
        if {p.name: sha(p) for p in wheels.glob('*.whl')} != {r['filename']: r['sha256'] for r in manifest['selected']}:
            raise ValueError('Bundled wheels differ from aggregate selection')
        distribution = verify(wheel, wheelhouse=wheels, bundle=bundle,
                              expected_java_version=VERSION, bundled_java_default=True)
        dump(output/'distribution.json', distribution)
        subprocess.run([sys.executable, str(Path(__file__).with_name('verify_bootstrap_upgrade.py')),
                        str(wheels), str(output/'upgrade.json'), '--bundle', str(bundle)], check=True)
    if any(sha(artifacts/name) != digest for name, digest in files.items()):
        raise ValueError('Aggregate changed during verification')
    result = {'status': 'passed', 'artifact_sha256': files, 'source_revision': manifest['source_revision'],
              'python': sys.version, 'platform': sys.platform, 'same_bytes_after_verification': True}
    dump(output/'verification.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['assemble', 'verify'])
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    function = assemble if args.action == 'assemble' else verify_aggregate
    print(json.dumps(function(args.input.resolve(), args.output.resolve()), indent=2))


if __name__ == '__main__':
    main()
