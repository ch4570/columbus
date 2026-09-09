"""Model-free Requests quote extraction and bounded, offline retained replay."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
COMMIT = 'b25c87d7cb8d6a18a37fa12442b5f883f9e41741'
ZIP_SHA = '753ea160ac0af1c4c83c584c6f05bebe716ca5d3b0780802bc8cbc8d5d82adab'
GRAPH_SHA = 'f315a1101ab14109424a60ce8c3b459f422808962fe74db5065462afacd6d3de'
SELECTED = {'src/requests/api.py': 'fd96fd39aeedcd5222cd32b016b3e30c463d7a3b66fce9d2444467003c46b10b',
            'src/requests/sessions.py': '0a5d5da449ce7f0af3ccf6e4bbe7a67a935e37846dff4ff9f08cb6c7e2464e6f',
            'LICENSE': '09e8a9bcec8067104652c168685ab0931e7868f9c8284b66f5ae6edae5f1130b'}
RANGES = [('src/requests/api.py', 55, 59), ('src/requests/sessions.py', 451, 452),
          ('src/requests/sessions.py', 454, 455), ('src/requests/sessions.py', 794, 797)]
IDS = ['src/requests/api.py::request:function', 'src/requests/sessions.py::Session.__enter__:method',
       'src/requests/sessions.py::Session.__exit__:method', 'src/requests/sessions.py::Session.close:method']


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def read(path):
    require(not path.is_symlink() and path.is_file() and path.stat().st_size <= 16_777_216,
            'Expected bounded regular file: ' + str(path))
    return path.read_bytes()


def tree(repo):
    return {path.relative_to(repo).as_posix(): sha(read(path)) for path in sorted(repo.rglob('*'))
            if '.git' != path.relative_to(repo).parts[0] and not path.is_dir()}


def runtime():
    scripts = ROOT / 'skills/columbus/scripts'
    paths = [*sorted((scripts / 'columbus').glob('*.py')), scripts / 'columbus.py', Path(__file__).resolve()]
    return {path.relative_to(ROOT).as_posix(): sha(read(path)) for path in paths}


def inputs(args):
    previous = None
    if args.replay_from:
        retained = args.replay_from.resolve()
        previous = json.loads(read(retained / 'results.json'))
        expected = previous['retained_files']
        require(set(tree(retained)) == set(expected) | {'results.json'}, 'Retained file inventory changed')
        for name, digest in expected.items():
            require(sha(read(retained / name)) == digest, 'Retained file changed: ' + name)
        require(runtime() == previous['runtime_files'], 'Replay requires the recorded runtime and verifier bytes')
        repo, archive = retained / 'fixture', retained / 'graph.jsonl.xz'
        provenance = previous['provenance']
    else:
        require(args.repo and args.archive and args.source_zip, 'Provide --repo, --archive and --source-zip')
        repo, archive = args.repo.resolve(), args.archive.resolve()
        require(sha(read(args.source_zip)) == ZIP_SHA, 'Wrong pinned Requests ZIP')
        with zipfile.ZipFile(args.source_zip) as source:
            records = [entry for entry in source.infolist() if not entry.is_dir()]
            inventory, total = {}, 0
            for entry in records:
                path = Path(entry.filename)
                require(path.parts[0] == 'requests' and len(path.parts) > 1 and '..' not in path.parts,
                        'Invalid ZIP path')
                name = Path(*path.parts[1:]).as_posix()
                require(name not in inventory and entry.file_size <= 16_777_216, 'Invalid ZIP member')
                raw = source.read(entry)
                inventory[name], total = sha(raw), total + len(raw)
        require(len(inventory) == 132 and total == 5_190_867 and tree(repo) == inventory,
                'Full 132-file ZIP and source snapshot must match exactly, excluding only .git metadata')
        provenance = {'repository': 'https://github.com/psf/requests', 'commit': COMMIT,
                      'pin_url': 'https://github.com/psf/requests/tree/' + COMMIT,
                      'source_zip': str(args.source_zip.resolve()), 'source_zip_sha256': ZIP_SHA,
                      'full_source_validation': {'files': 132, 'bytes': total, 'inventory': inventory},
                      'original_repository': str(repo), 'original_archive': str(archive)}
    require(sha(read(archive)) == GRAPH_SHA, 'Wrong original graph archive bytes')
    for name, digest in SELECTED.items():
        require(sha(read(repo / name)) == digest, 'Wrong selected source/license: ' + name)
    return repo, archive, provenance, previous


def verify(repo, archive):
    prefix = [sys.executable, '-B', str(ROOT / 'skills/columbus/scripts/columbus.py')]
    common = ['--input', str(archive), '--repo', str(repo), '--budget-bytes', '6000']
    quotes = prefix + ['archive-quotes', *common]
    for path, start, end in RANGES:
        quotes += ['--range', path, str(start), str(end)]
    commands = {'archive_quotes': quotes,
                'archive_source_batch': prefix + ['archive-source', *IDS, *common, '--format', 'text', '--offset', '41', '--limit', '13'],
                'ordinary_exact_ranges': ['/bin/sh', '-c', "sed -n '55,59p' src/requests/api.py\nsed -n '451,452p;454,455p;794,797p' src/requests/sessions.py"]}
    measurements, payloads = {}, {}
    for name, argv in commands.items():
        run = subprocess.run(argv, cwd=repo, capture_output=True, timeout=60, check=False)
        require(run.returncode == 0 and not run.stderr, 'Read-only variant failed: ' + name)
        command = shlex.join(argv)
        measurements[name] = {'argv': argv, 'cwd': str(repo), 'command': command, 'command_utf8_bytes': len(command.encode()),
                              'stdout_bytes': len(run.stdout), 'stdout_sha256': sha(run.stdout),
                              'stderr_bytes': len(run.stderr), 'stderr_sha256': sha(run.stderr), 'return_code': run.returncode}
        payloads[name + '.stdout'], payloads[name + '.stderr'] = run.stdout, run.stderr
    expected = []
    for path, start, end in RANGES:
        lines = read(repo / path).decode('utf-8').replace('\r\n', '\n').replace('\r', '\n').split('\n')
        expected.extend((path, number, lines[number - 1]) for number in range(start, end + 1))
    packet = json.loads(payloads['archive_quotes.stdout'])
    require(packet['format'] == 'columbus-quotes/v1' and packet['semantic_complete'] is False, 'Quote envelope changed')
    require(len(packet['quotes']) == len(RANGES), 'Missing or extra quotes')
    actual = []
    for quote, requested in zip(packet['quotes'], RANGES):
        path, start, end = requested
        require((quote['path'], quote['start_line'], quote['end_line']) == requested
                and quote['source_hash'] == SELECTED[path] and quote['language'] == 'python', 'Quote identity changed')
        actual.extend((path, number, line) for number, line in enumerate(quote['quote'].split('\n'), start))
    require(actual == expected, 'Quote coverage differs from exact pinned source')
    files, batch, block, file_mode = {}, [], None, False
    for line in payloads['archive_source_batch.stdout'].decode().split('\n'):
        if line.startswith('metadata '):
            metadata = json.loads(line[9:])
        elif line.startswith('files '): file_mode = True
        elif line.startswith('targets '): file_mode = False
        elif file_mode and line.startswith('['):
            number, path, digest = json.loads(line)
            require(digest == SELECTED[path], 'Batch source hash differs')
            files[number] = path
        elif line.startswith('source '): block = json.loads(line[7:])
        elif block is not None and '| ' in line and line.split('| ', 1)[0].isdigit():
            number, text = line.split('| ', 1)
            batch.append((files[block['file_number']], int(number), text))
    ordinary = payloads['ordinary_exact_ranges.stdout'].decode().split('\n')
    require(ordinary[-1] == '' and ordinary[:-1] == [text for _, _, text in expected] and batch == expected,
            'Efficient comparators must return the same ordered source lines')
    quote_bytes = sum(len(item['quote'].encode()) for item in packet['quotes'])
    require(len(expected) == 13 and quote_bytes == 548, 'Requested source coverage changed')
    require(metadata['total_lines'] == 54 and metadata['offset'] == 41 and metadata['next_offset'] is None, 'Batch page changed')
    return {'measurements': measurements, 'coverage': {'equal': True, 'rows': expected, 'decoded_quote_bytes': quote_bytes},
            'quote_metadata': {key: value for key, value in packet.items() if key != 'quotes'}, 'batch_metadata': metadata}, payloads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'archive', 'source-zip', 'output-dir', 'replay-from'):
        parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    require(not args.replay_from or not any((args.repo, args.archive, args.source_zip)), 'Replay inputs are exclusive')
    require(args.replay_from or args.output_dir, 'Initial retention requires a NEW --output-dir')
    if args.output_dir:
        require(not os.path.lexists(args.output_dir) and args.output_dir.parent.is_dir(), 'Output must be a NEW directory with an existing parent')
    repo, archive, provenance, previous = inputs(args)
    before, code = tree(repo), runtime()
    result, payloads = verify(repo, archive)
    require(tree(repo) == before and runtime() == code and sha(read(archive)) == GRAPH_SHA, 'Source/runtime/archive changed during reads')
    if previous:
        require(all(value['stdout_sha256'] == previous['measurements'][name]['stdout_sha256']
                    for name, value in result['measurements'].items()), 'Replay stdout differs from retained outputs')
    payloads['graph.jsonl.xz'] = read(archive)
    payloads.update({'fixture/' + name: read(repo / name) for name in SELECTED})
    result.update(schema='columbus.archive-quotes-workflow/v1', provenance=provenance, runtime_files=code,
                  python={'executable': sys.executable, 'version': sys.version}, archive_sha256=GRAPH_SHA,
                  validation_mode='minimal retained replay; full ZIP not revalidated' if previous else 'full ZIP and 132-file snapshot validated',
                  retained_files={name: sha(raw) for name, raw in payloads.items()},
                  limitations=['New operation on previously used Requests; not held-out repository or semantic/model evaluation.',
                               'Identical source coverage, different metadata; bytes are not actual model tokens.',
                               'Retained fixture contains only two source files and LICENSE; it is not the full repository.',
                               'Replay needs the recorded utility/verifier bytes, compatible Python and /bin/sh with sed.'])
    if args.output_dir:
        require(not args.output_dir.resolve().is_relative_to(repo.resolve()), 'Output must not modify the source repository')
        args.output_dir.mkdir(exist_ok=False)
        for name, raw in {**payloads, 'results.json': encoded(result)}.items():
            path = args.output_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream: stream.write(raw)
    print(json.dumps({'verified': True, 'mode': result['validation_mode'], 'measurements': result['measurements'],
                      'retained_payload_bytes': sum(map(len, payloads.values())), 'results_sha256': sha(encoded(result))}, indent=2))


if __name__ == '__main__':
    main()
