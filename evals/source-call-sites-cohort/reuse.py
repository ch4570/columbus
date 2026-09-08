"""Read-only, pre-mutation proof for the three explicitly bound historical graphs.

Only Git blobs are read: no producer/candidate runtime is imported or executed.
The returned cold timings belong to the original producers, never to this reuse.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
import lzma
import math
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import zipfile

_PATH = Path(__file__).resolve().with_name('common.py')
_KEY = '_source_call_cohort_' + hashlib.sha256(str(_PATH).encode()).hexdigest()[:16]
if _KEY not in sys.modules:
    _SPEC = importlib.util.spec_from_file_location(_KEY, _PATH)
    _COMMON = importlib.util.module_from_spec(_SPEC)
    sys.modules[_KEY] = _COMMON
    _SPEC.loader.exec_module(_COMMON)
common = sys.modules[_KEY]

_KINDS = dict(file='files', node='nodes', scope='scopes', edge='edges',
              reference='references', import_='imports', diagnostic='diagnostics')
_KINDS['import'] = _KINDS.pop('import_')
_MODULES = ['parser.py', 'discovery.py', 'language_profiles.py', 'polyglot.py',
            'languages.py', 'index.py']
_PREFIX = 'skills/columbus/'
_ARCHIVE = _PREFIX + 'scripts/columbus/archive.py'


def _require(value, message):
    if not value:
        raise ValueError(message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def _json(raw):
    return json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def _hex(value, length):
    _require(isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(length) + '}', value),
             'invalid pinned hash or commit')
    return value


def _relative(value):
    _require(isinstance(value, str) and value and not any(c in value for c in '\\:\0'),
             'unsafe relative path')
    path = PurePosixPath(value)
    _require(not path.is_absolute() and all(p not in ('', '.', '..') for p in value.split('/')),
             'unsafe relative path')
    return value


def _stamp(path):
    info = Path(path).lstat()
    _require(stat.S_ISREG(info.st_mode), 'input is not a regular non-symlink file')
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _file_hash(path):
    before = _stamp(path)
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    _require(before == _stamp(path), 'input changed while hashing')
    return digest.hexdigest(), before


def _source(source, binding):
    _require(all(type(source[key]) is int and source[key] >= 0 for key in
                 ('fixture_bytes', 'source_files', 'source_bytes')) and
             all(type(binding[key]) is int and binding[key] >= 0 for key in
                 ('fixture_bytes', 'source_files', 'source_bytes')), 'source/graph size schema')
    for key in ('fixture_sha256', 'corpus_manifest_sha256'):
        _hex(source[key], 64)
    _hex(source['commit'], 40)
    _require(source['fixture'] == binding['source_fixture'] and
             source['fixture_sha256'] == binding['source_fixture_sha256'], 'source fixture binding')
    before = _stamp(source['fixture'])
    raw = Path(source['fixture']).read_bytes()
    _require(before == _stamp(source['fixture']) and _sha(raw) == source['fixture_sha256'] and
             len(raw) == source['fixture_bytes'], 'source ZIP hash/size/stability')
    prefix = source['fixture_prefix']
    _require(isinstance(prefix, str) and prefix.endswith('/'), 'source ZIP prefix')
    _relative(prefix[:-1])
    files, sizes, members = {}, {}, set()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for member in archive.infolist():
            name = member.filename
            _require(name not in members, 'duplicate ZIP member')
            members.add(name)
            _relative(name.rstrip('/'))
            _require(name.startswith(prefix), 'ZIP member outside full declared scope')
            mode = stat.S_IFMT(member.external_attr >> 16)
            _require(mode in ((0, stat.S_IFDIR) if member.is_dir() else (0, stat.S_IFREG)),
                     'nonregular ZIP member')
            if member.is_dir():
                continue
            path = _relative(name[len(prefix):])
            content = archive.read(member)
            files[path], sizes[path] = _sha(content), len(content)
    _require(len(files) == source['source_files'] == binding['source_files'] and
             sum(sizes.values()) == source['source_bytes'] == binding['source_bytes'],
             'complete source file count/size')
    _require(_sha(_canonical(files)) == source['corpus_manifest_sha256'] ==
             binding['source_manifest_sha256'], 'complete source manifest hash')
    return files, sizes, before


def _graph(binding, files, sizes):
    checksum, stamp = _file_hash(binding['fixture'])
    _require(checksum == _hex(binding['fixture_sha256'], 64) and
             stamp[2] == binding['fixture_bytes'], 'graph hash/size')
    counts = dict.fromkeys(_KINDS.values(), 0)
    _require(set(binding['counts']) == set(counts) and
             all(type(n) is int and n >= 0 for n in binding['counts'].values()), 'graph counts schema')
    seen, ended, tail = set(), False, hashlib.sha256()
    with lzma.open(binding['fixture'], 'rb') as stream:
        header = _json(next(stream))
        _require(header['record'] == 'manifest', 'graph first record')
        manifest = header['data']
        expected = {'format': 'columbus-graph', 'version': 1, 'revision': binding['revision'],
                    'analyzer_version': binding['analyzer_version'], 'freshness': 'index_snapshot',
                    'semantic_complete': False, 'truncated': False, 'source_bodies_included': False}
        _require(all(type(manifest.get(k)) is type(v) and manifest[k] == v for k, v in expected.items()),
                 'graph manifest binding')
        versions = manifest['analyzer_fingerprint']['versions']
        _require(versions['analyzer_code'] == binding['analyzer_code'] and
                 versions['engine'] == binding['analyzer_version'] and
                 {k: v for k, v in versions.items() if k not in ('engine', 'analyzer_code',
                                                               'language_config')} ==
                 binding['analyzer_dependencies'], 'graph analyzer fingerprint')
        for line in stream:
            tail.update(line)
            _require(not ended, 'records after graph footer')
            record = _json(line)
            kind, data = record['record'], record['data']
            _require(isinstance(data, dict), 'graph data is not an object')
            if kind == 'end':
                _require(data == counts == binding['counts'] and
                         all(type(n) is int for n in data.values()), 'graph footer/actual counts')
                ended = True
                continue
            _require(kind in _KINDS, 'unknown graph record')
            counts[_KINDS[kind]] += 1
            if kind == 'file':
                path = _relative(data['path'])
                _require(path not in seen and path in files and data['hash'] == files[path] and
                         type(data['size']) is int and data['size'] == sizes[path],
                         'graph file differs from complete source ZIP')
                seen.add(path)
    _require(ended, 'missing graph footer')
    excluded = binding['source_files_absent_from_graph']
    _require(isinstance(excluded, list) and all(isinstance(row, dict) and
             isinstance(row.get('reason'), str) and row['reason'].strip() for row in excluded),
             'graph exclusions schema')
    _require(sorted(row['path'] for row in excluded) == sorted(set(files) - seen), 'graph exclusions')
    _require(binding['index']['indexed_bytes'] == sum(sizes[path] for path in seen),
             'historical indexed source bytes')
    tail_hash = binding['provenance'].get('decompressed_records_after_manifest_sha256')
    if tail_hash is not None:
        _require(tail.hexdigest() == _hex(tail_hash, 64), 'decompressed graph records hash')
    _require(_file_hash(binding['fixture']) == (checksum, stamp), 'graph changed while validating')
    return stamp


def _git_reader():
    blobs = {}

    def blob(commit, path):
        key = (_hex(commit, 40), _relative(path))
        if key not in blobs:
            blobs[key] = subprocess.check_output(['git', 'show', commit + ':' + path], cwd=common.ROOT)
        return blobs[key]

    def runtime(commit):
        names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', _hex(commit, 40),
                                         '--', _PREFIX], cwd=common.ROOT).decode().splitlines()
        result = {}
        for name in names:
            _require(name.startswith(_PREFIX), 'runtime Git tree prefix')
            suffix = name[len(_PREFIX):]
            if suffix.startswith('scripts/') and suffix.endswith('.py'):
                relative = suffix[len('scripts/'):]
                if relative != 'columbus.py' and not (relative.startswith('columbus/') and
                                                     relative.count('/') == 1):
                    continue
            elif suffix == 'SKILL.md' or suffix.startswith('references/'):
                relative = suffix
            else:
                continue
            _require(relative not in result, 'duplicate exported runtime path')
            result[relative] = _sha(blob(commit, name))
        _require('columbus.py' in result and 'SKILL.md' in result, 'incomplete runtime Git inventory')
        return result

    return blob, runtime


def _history(language, source, binding, files, blob, runtime):
    provenance = binding['provenance']
    frozen = _hex(provenance['frozen_commit'], 40)
    base = 'evals/' + ('overload-token-cohort' if language == 'javascript' else 'quotes-three-arm')
    freeze_path = base + '/' + language + '/freeze.json'
    selector = 'engine' if language == 'javascript' else 'quotes.engine'
    _require(provenance['frozen_engine_selector'] == selector and
             provenance['runtime_inventory']['map_location'] == freeze_path + ':' + selector + '.files',
             'frozen engine selector')
    dependencies = provenance['dependency_sha256']
    required = {base + '/' + name for name in ('input-hashes.json', 'environment.json', 'prepare.py')}
    required |= {freeze_path, 'evals/exploration/observe_saved_callers.py'}
    if language != 'javascript':
        required |= {base + '/common.py', base + '/' + language + '/graph.jsonl.xz'}
    _require(isinstance(dependencies, dict) and required <= set(dependencies), 'missing frozen dependency')
    for path, checksum in dependencies.items():
        _require(_sha(blob(frozen, path)) == _hex(checksum, 64), 'frozen Git dependency hash: ' + path)
    frozen_inputs = _json(blob(frozen, base + '/input-hashes.json'))
    for path, checksum in dependencies.items():
        if path != base + '/input-hashes.json':
            _require(frozen_inputs.get(path) == checksum, 'dependency absent/different in frozen input map')
    source_path = base + '/' + language + '/source.json'
    source_raw = blob(frozen, source_path)
    _require(_sha(source_raw) == frozen_inputs[source_path], 'frozen source pin input hash')
    original = _json(source_raw)
    _require(source['repository'] == original['repository'] and
             source['commit'] == original.get('commit', original.get('source_commit')),
             'historical source pin')
    if 'source_commit' in original:
        _require(source['commit'] == original['source_commit'], 'contradictory historical source pin')
    for key, aliases in {'fixture_sha256': ('fixture_sha256', 'sha256'),
                         'fixture_bytes': ('fixture_bytes', 'zip_bytes'),
                         'source_files': ('files', 'source_files'),
                         'fixture_prefix': ('archive_prefix', 'fixture_prefix'),
                         'source_bytes': ('source_bytes',),
                         'corpus_manifest_sha256': ('corpus_manifest_sha256',)}.items():
        for alias in aliases:
            if alias in original:
                _require(source[key] == original[alias], 'historical source metadata: ' + key)
    freeze = _json(blob(frozen, freeze_path))
    arm = freeze if language == 'javascript' else freeze['quotes']
    engine, manifest = arm['engine'], arm['manifest']
    archive = engine['archive']
    _require(arm['engine_sha256'] == provenance['original_engine']['sha256'], 'original engine hash binding')
    _require(_sha((json.dumps(engine, indent=2) + '\n').encode()) == arm['engine_sha256'],
             'original engine serialized hash')
    _require(manifest['fixture_sha256'] == source['fixture_sha256'] and
             manifest['source_bytes'] == source['source_bytes'] and
             manifest['source_manifest'] == archive['source_manifest'] == files, 'frozen complete source map')
    _require(archive['archive_sha256'] == binding['fixture_sha256'] and
             archive['revision'] == binding['revision'] and archive['counts'] == binding['counts'] and
             archive.get('bytes', binding['fixture_bytes']) == binding['fixture_bytes'], 'frozen graph binding')
    producer = _hex(binding['producer_commit'], 40)
    environment = _json(blob(frozen, base + '/environment.json'))
    declared = (environment['runtime_commit'] if language == 'javascript' else
                environment['runtime_commits']['quotes'])
    _require(declared == producer and engine.get('runtime_commit', producer) == producer,
             'actual graph producer commit')
    produced = runtime(producer)
    inventory = provenance['runtime_inventory']
    _require(produced == engine['files'] == archive['runtime_manifest'] and
             len(produced) == inventory['files'] and _sha(_canonical(produced)) == inventory['sha256'],
             'producer Git runtime inventory')
    _require(engine['index'] == binding['index'] and binding['index']['revision'] == binding['revision'] and
             binding['index']['files'] == binding['counts']['files'] and
             binding['index']['symbols'] == binding['counts']['nodes'] and
             binding['index']['edges'] == binding['counts']['edges'], 'historical index summary')
    timings = (engine['index_seconds'], archive['export_seconds']) if language == 'javascript' else (
        engine['cold_index_seconds'], engine['cold_export_seconds'])
    for value, key in zip(timings, ('historical_cold_index_seconds', 'historical_cold_export_seconds')):
        _require(type(value) in (int, float) and math.isfinite(value) and value >= 0 and
                 value == binding[key], 'historical timing binding')
    return produced


def _candidate(language, binding, produced, blob, runtime):
    producer, candidate = binding['producer_commit'], binding['candidate_commit']
    _require(candidate == common.RUNTIME_COMMITS['candidate'], 'candidate commit binding')
    current, proof = runtime(candidate), binding['candidate_equivalence']
    _require(not (set(produced) - set(current)) and
             sorted(set(current) - set(produced)) == sorted(proof['candidate_added_runtime_files']) and
             sorted(path for path in produced if produced[path] != current[path]) ==
             sorted(proof['all_shared_runtime_files_identical_except']), 'candidate runtime delta')
    modules = _MODULES + ([] if language == 'javascript' else ['jvm.py'])
    _require(proof['analyzer_modules_byte_identical'] == modules, 'analyzer module inventory')
    raw_modules = []
    for name in modules:
        path = _PREFIX + 'scripts/columbus/' + name
        raw = blob(producer, path)
        _require(raw == blob(candidate, path), 'candidate analyzer bytes: ' + name)
        raw_modules.append(raw)
    fingerprint = _sha(b'\n'.join(raw_modules))[:20]
    _require(fingerprint == binding['analyzer_code'] == proof['candidate_analyzer_code_recomputed_from_git'],
             'analyzer code fingerprint')
    function = proof['archive_export_function']
    _require(function['path'] == _ARCHIVE and function['function'] == 'archive', 'archive exporter selector')
    extracted = []
    for commit, key in ((producer, 'producer_archive_module_sha256'),
                        (candidate, 'candidate_archive_module_sha256')):
        raw = blob(commit, _ARCHIVE)
        _require(_sha(raw) == proof[key], 'archive module hash')
        definitions = [node for node in ast.parse(raw).body if isinstance(node, ast.FunctionDef)
                       and node.name == 'archive']
        _require(len(definitions) == 1, 'archive exporter definition')
        node = definitions[0]
        code = b''.join(raw.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])
        _require([node.lineno, node.end_lineno] == function['physical_lines'] and
                 len(code) == function['bytes'] and _sha(code) == function['sha256'],
                 'archive exporter exact physical bytes')
        extracted.append(code)
    _require(extracted[0] == extracted[1], 'candidate archive exporter changed')


def check_bindings(sources, bindings):
    """Return all three reuse receipts only after every read-only check succeeds.

    Call this before mkdir/copy/export/extraction. The caller still must hash-check
    copied bytes and retain these inputs in its prospective freeze manifest.
    """
    _require(isinstance(sources, dict) and isinstance(bindings, dict) and
             set(sources) == set(bindings) == set(common.LANGUAGES), 'exactly three source/graph bindings required')
    receipts, stable = {}, []
    blob, runtime = _git_reader()
    try:
        for language in common.LANGUAGES:
            source, binding = sources[language], bindings[language]
            files, sizes, source_stamp = _source(source, binding)
            graph_stamp = _graph(binding, files, sizes)
            produced = _history(language, source, binding, files, blob, runtime)
            _candidate(language, binding, produced, blob, runtime)
            stable.extend(((source['fixture'], source_stamp), (binding['fixture'], graph_stamp)))
            receipts[language] = {key: binding[key] for key in (
                'fixture', 'fixture_sha256', 'fixture_bytes', 'producer_commit', 'candidate_commit',
                'revision', 'counts', 'source_manifest_sha256', 'index',
                'historical_cold_index_seconds', 'historical_cold_export_seconds',
                'source_files_absent_from_graph')}
            receipts[language].update(preparation_mode='historical_graph_reuse', source_manifest=files,
                new_cold_index_seconds=None, new_cold_export_seconds=None,
                provenance={'frozen_commit': binding['provenance']['frozen_commit'],
                    'dependency_sha256': binding['provenance']['dependency_sha256'],
                    'producer_runtime_inventory_sha256': _sha(_canonical(produced)),
                    'analyzer_code': binding['analyzer_code'],
                    'archive_export_sha256': binding['candidate_equivalence']['archive_export_function']['sha256']})
        _require(all(_stamp(path) == expected for path, expected in stable), 'input changed during reuse validation')
    except (KeyError, TypeError, IndexError, StopIteration, OSError, SyntaxError,
            zipfile.BadZipFile, lzma.LZMAError, EOFError, subprocess.SubprocessError) as exc:
        raise ValueError('invalid historical graph reuse proof: ' + str(exc)) from exc
    return receipts
