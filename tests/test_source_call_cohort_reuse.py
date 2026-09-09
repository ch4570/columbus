"""Tiny synthetic archives + mocked Git only; never build an index or run a model."""
import copy
import hashlib
import importlib.util
import json
import lzma
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    '_test_source_call_reuse', ROOT / 'evals/source-call-sites-cohort/reuse.py')
REUSE = importlib.util.module_from_spec(SPEC)
with mock.patch.multiple(subprocess, Popen=mock.Mock(side_effect=AssertionError('process during import')),
                         run=mock.Mock(side_effect=AssertionError('process during import')),
                         check_output=mock.Mock(side_effect=AssertionError('process during import'))):
    SPEC.loader.exec_module(REUSE)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


class ReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.blobs, self.trees, self.sources, self.bindings = {}, {}, {}, {}
        self.producer, self.older, self.candidate = 'a' * 40, 'b' * 40, 'c' * 40
        self.exporter = b'def archive(index):\n    return index\n'
        runtime = {'columbus.py': b'# shim\n', 'SKILL.md': b'skill\n',
                   'columbus/cli.py': b'# cli\n', 'columbus/archive.py': self.exporter}
        runtime.update({'columbus/' + name: ('# ' + name + '\n').encode()
                        for name in REUSE._MODULES + ['jvm.py']})
        self.runtimes = {self.producer: runtime, self.older: dict(runtime),
                         self.candidate: dict(runtime, **{'SKILL.md': b'new skill\n',
                                                          'columbus/source_calls.py': b'# new\n'})}
        for commit, files in self.runtimes.items():
            paths = []
            for relative, raw in files.items():
                path = 'skills/columbus/' + ('' if relative == 'SKILL.md' else 'scripts/') + relative
                self.blobs[commit, path] = raw
                paths.append(path)
            self.trees[commit] = ('\n'.join(sorted(paths)) + '\n').encode()
        for number, language in enumerate(REUSE.common.LANGUAGES):
            self.make_language(language, number)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(REUSE.common, 'ROOT', self.root).start()
        mock.patch.dict(REUSE.common.RUNTIME_COMMITS, {'candidate': self.candidate}).start()
        self.git = mock.patch.object(REUSE.subprocess, 'check_output', side_effect=self.git_read).start()
        mock.patch.object(REUSE.subprocess, 'run', side_effect=AssertionError('unexpected run')).start()
        mock.patch.object(REUSE.subprocess, 'Popen', side_effect=AssertionError('unexpected Popen')).start()

    def git_read(self, argv, *, cwd):
        self.assertEqual(cwd, self.root)
        if argv[:2] == ['git', 'show'] and len(argv) == 3:
            commit, path = argv[2].split(':', 1)
            return self.blobs[commit, path]
        self.assertEqual(argv[:4], ['git', 'ls-tree', '-r', '--name-only'])
        self.assertEqual(argv[5:], ['--', 'skills/columbus/'])
        return self.trees[argv[4]]

    def make_language(self, language, number):
        javascript = language == 'javascript'
        producer, frozen = (self.older, 'e' * 40) if javascript else (self.producer, 'd' * 40)
        base = 'evals/' + ('overload-token-cohort' if javascript else 'quotes-three-arm')
        source_files = {'main.txt': b'full pinned source\n', 'omitted.txt': b'another source\n'}
        source_zip = self.root / (language + '.zip')
        with zipfile.ZipFile(source_zip, 'x') as archive:
            for path, raw in source_files.items():
                archive.writestr('full/' + path, raw)
        manifest = {path: sha(raw) for path, raw in source_files.items()}
        manifest_sha = sha(canonical(manifest))
        source = dict(fixture=str(source_zip), fixture_sha256=sha(source_zip.read_bytes()),
                      fixture_bytes=source_zip.stat().st_size, fixture_prefix='full/',
                      repository='https://example.test/public/source', commit='f' * 40,
                      source_files=2, source_bytes=sum(map(len, source_files.values())),
                      corpus_manifest_sha256=manifest_sha)
        modules = REUSE._MODULES + ([] if javascript else ['jvm.py'])
        fingerprint = sha(b'\n'.join(self.runtimes[producer]['columbus/' + name]
                                     for name in modules))[:20]
        graph_files = {'main.txt': source_files['main.txt']} if javascript else source_files
        counts = dict.fromkeys(REUSE._KINDS.values(), 0)
        counts['files'] = len(graph_files)
        revision = str(number) * 20
        header = {'record': 'manifest', 'data': {'format': 'columbus-graph', 'version': 1,
                  'revision': revision, 'analyzer_version': 'columbus-test',
                  'freshness': 'index_snapshot', 'semantic_complete': False, 'truncated': False,
                  'source_bodies_included': False, 'analyzer_fingerprint': {'versions': {
                      'engine': 'columbus-test', 'analyzer_code': fingerprint,
                      'python_ast': 'test', 'language_config': 'test'}}}}
        rows = [header] + [{'record': 'file', 'data': {'path': p, 'hash': sha(raw), 'size': len(raw)}}
                           for p, raw in graph_files.items()] + [{'record': 'end', 'data': counts}]
        lines = [canonical(row) + b'\n' for row in rows]
        graph = self.root / (language + '.jsonl.xz')
        graph.write_bytes(lzma.compress(b''.join(lines)))
        runtime = {path: sha(raw) for path, raw in self.runtimes[producer].items()}
        index = dict(files=len(graph_files), symbols=0, edges=0,
                     indexed_bytes=sum(map(len, graph_files.values())), revision=revision)
        archive = dict(archive_sha256=sha(graph.read_bytes()), revision=revision, counts=counts,
                       source_manifest=manifest, runtime_manifest=runtime)
        engine = dict(files=runtime, index=index, archive=archive)
        if javascript:
            engine['index_seconds'], archive['export_seconds'] = 1.25, 0.25
        else:
            engine.update(runtime_commit=producer, cold_index_seconds=1.25, cold_export_seconds=0.25)
        original = dict(repository=source['repository'], commit=source['commit'],
                        fixture_sha256=source['fixture_sha256'], fixture_bytes=source['fixture_bytes'],
                        files=2, archive_prefix='full/', source_bytes=source['source_bytes'],
                        corpus_manifest_sha256=manifest_sha)
        if language == 'kotlin':
            original['source_commit'] = original.pop('commit')
        arm = {'engine': engine, 'engine_sha256': sha(encoded(engine)), 'manifest': {
            'fixture_sha256': source['fixture_sha256'], 'source_bytes': source['source_bytes'],
            'source_manifest': manifest}}
        freeze_path = base + '/' + language + '/freeze.json'
        dependencies = {base + '/prepare.py': b'# frozen preparer\n',
                        'evals/exploration/observe_saved_callers.py': b'# frozen observer\n',
                        freeze_path: encoded(arm if javascript else {'quotes': arm}),
                        base + '/environment.json': encoded({'runtime_commit': producer} if javascript
                            else {'runtime_commits': {'quotes': producer}})}
        if not javascript:
            dependencies[base + '/common.py'] = b'# frozen common\n'
            dependencies[base + '/' + language + '/graph.jsonl.xz'] = graph.read_bytes()
        source_path = base + '/' + language + '/source.json'
        self.blobs[frozen, source_path] = encoded(original)
        input_path = base + '/input-hashes.json'
        # Shared historical cohorts have one inventory for both Java and Kotlin.
        inputs = json.loads(self.blobs[frozen, input_path]) if (frozen, input_path) in self.blobs else {}
        inputs.update({path: sha(raw) for path, raw in dependencies.items()})
        inputs[source_path] = sha(encoded(original))
        dependencies[input_path] = encoded(inputs)
        for path, raw in dependencies.items():
            self.blobs[frozen, path] = raw
        proof = dict(all_shared_runtime_files_identical_except=['SKILL.md'],
                     candidate_added_runtime_files=['columbus/source_calls.py'],
                     analyzer_modules_byte_identical=modules,
                     candidate_analyzer_code_recomputed_from_git=fingerprint,
                     producer_archive_module_sha256=sha(self.exporter),
                     candidate_archive_module_sha256=sha(self.exporter),
                     archive_export_function=dict(path=REUSE._ARCHIVE, function='archive',
                         physical_lines=[1, 2], bytes=len(self.exporter), sha256=sha(self.exporter)))
        selector = 'engine' if javascript else 'quotes.engine'
        binding = dict(fixture=str(graph), fixture_sha256=sha(graph.read_bytes()),
                       fixture_bytes=graph.stat().st_size, revision=revision, counts=counts,
                       producer_commit=producer, candidate_commit=self.candidate,
                       analyzer_version='columbus-test', analyzer_code=fingerprint,
                       analyzer_dependencies={'python_ast': 'test'}, source_fixture=str(source_zip),
                       source_fixture_sha256=source['fixture_sha256'], source_files=2,
                       source_bytes=source['source_bytes'], source_manifest_sha256=manifest_sha,
                       source_files_absent_from_graph=([{'path': 'omitted.txt', 'reason': 'synthetic exclusion'}]
                                                       if javascript else []), index=index,
                       historical_cold_index_seconds=1.25, historical_cold_export_seconds=0.25,
                       candidate_equivalence=proof, provenance=dict(frozen_commit=frozen,
                           dependency_sha256={p: sha(raw) for p, raw in dependencies.items()},
                           frozen_engine_selector=selector, original_engine={'sha256': arm['engine_sha256']},
                           decompressed_records_after_manifest_sha256=sha(b''.join(lines[1:])),
                           runtime_inventory=dict(files=len(runtime), sha256=sha(canonical(runtime)),
                               map_location=freeze_path + ':' + selector + '.files')))
        self.sources[language], self.bindings[language] = source, binding
        if language == 'kotlin':
            self.bindings['java']['provenance']['dependency_sha256'][input_path] = sha(dependencies[input_path])

    def check(self):
        before = {str(p): p.read_bytes() for p in self.root.iterdir()}
        try:
            return REUSE.check_bindings(self.sources, self.bindings)
        finally:
            self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.iterdir()})

    def test_all_three_read_only_receipts_keep_historical_timings(self):
        receipts = self.check()
        self.assertEqual(set(receipts), {'java', 'kotlin', 'javascript'})
        for language, receipt in receipts.items():
            self.assertEqual(receipt['preparation_mode'], 'historical_graph_reuse')
            self.assertIsNone(receipt['new_cold_index_seconds'])
            self.assertIsNone(receipt['new_cold_export_seconds'])
            self.assertEqual(receipt['historical_cold_index_seconds'], 1.25)
            self.assertEqual(len(receipt['source_manifest']), 2)
            self.assertEqual(receipt['source_files_absent_from_graph'],
                             self.bindings[language]['source_files_absent_from_graph'])
        self.assertTrue(self.git.call_count)

    def test_requires_exactly_three_bindings_before_git_reads(self):
        for mapping in (self.sources, self.bindings):
            removed = mapping.pop('java')
            with self.assertRaisesRegex(ValueError, 'exactly three'):
                self.check()
            mapping['java'] = removed
        self.git.assert_not_called()

    def test_changed_graph_rejected_without_writes(self):
        path = Path(self.bindings['java']['fixture'])
        path.write_bytes(path.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'graph hash/size'):
            self.check()

    def test_changed_source_rejected_without_writes(self):
        path = Path(self.sources['java']['fixture'])
        path.write_bytes(path.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'source ZIP hash/size'):
            self.check()

    def test_source_pin_manifest_and_size_changes_rejected(self):
        for field, changed in [('commit', '0' * 40), ('repository', 'wrong'),
                               ('corpus_manifest_sha256', '0' * 64), ('source_bytes', 999),
                               ('source_files', True), ('fixture_bytes', 1), ('fixture_prefix', '../')]:
            with self.subTest(field=field):
                saved = self.sources['java'][field]
                self.sources['java'][field] = changed
                with self.assertRaises(ValueError):
                    self.check()
                self.sources['java'][field] = saved

    def test_changed_original_git_dependency_rejected(self):
        self.blobs['d' * 40, 'evals/quotes-three-arm/prepare.py'] += b'changed'
        with self.assertRaisesRegex(ValueError, 'frozen Git dependency hash'):
            self.check()

    def test_changed_frozen_source_pin_blob_rejected(self):
        self.blobs['d' * 40, 'evals/quotes-three-arm/java/source.json'] += b' '
        with self.assertRaisesRegex(ValueError, 'frozen source pin input hash'):
            self.check()

    def test_changed_producer_runtime_rejected(self):
        self.blobs[self.producer, 'skills/columbus/scripts/columbus/parser.py'] += b'changed'
        with self.assertRaisesRegex(ValueError, 'producer Git runtime inventory'):
            self.check()

    def test_changed_candidate_analyzer_rejected_even_if_delta_declared(self):
        self.blobs[self.candidate, 'skills/columbus/scripts/columbus/parser.py'] += b'changed'
        self.bindings['java']['candidate_equivalence']['all_shared_runtime_files_identical_except'].append(
            'columbus/parser.py')
        with self.assertRaisesRegex(ValueError, 'candidate analyzer bytes'):
            self.check()

    def test_changed_candidate_exporter_rejected_even_if_module_hash_declared(self):
        raw = self.exporter.replace(b'return index', b'return None')
        self.blobs[self.candidate, REUSE._ARCHIVE] = raw
        proof = self.bindings['java']['candidate_equivalence']
        proof['all_shared_runtime_files_identical_except'].append('columbus/archive.py')
        proof['candidate_archive_module_sha256'] = sha(raw)
        with self.assertRaisesRegex(ValueError, 'archive exporter exact physical bytes'):
            self.check()

    def test_extra_candidate_runtime_file_and_wrong_commit_rejected(self):
        self.trees[self.candidate] += b'skills/columbus/scripts/columbus/extra.py\n'
        self.blobs[self.candidate, 'skills/columbus/scripts/columbus/extra.py'] = b'extra'
        with self.assertRaisesRegex(ValueError, 'candidate runtime delta'):
            self.check()
        self.bindings['java']['candidate_commit'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'candidate commit binding'):
            self.check()

    def test_selectors_and_missing_dependencies_rejected(self):
        self.bindings['java']['provenance']['frozen_engine_selector'] = 'control.engine'
        with self.assertRaisesRegex(ValueError, 'frozen engine selector'):
            self.check()
        self.bindings['java']['provenance']['frozen_engine_selector'] = 'quotes.engine'
        self.bindings['java']['provenance']['dependency_sha256'].pop('evals/quotes-three-arm/prepare.py')
        with self.assertRaisesRegex(ValueError, 'missing frozen dependency'):
            self.check()

    def test_timing_nan_and_exclusions_rejected(self):
        self.bindings['java']['historical_cold_index_seconds'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'historical timing binding'):
            self.check()
        self.bindings['java']['historical_cold_index_seconds'] = 1.25
        self.bindings['javascript']['source_files_absent_from_graph'] = []
        with self.assertRaisesRegex(ValueError, 'graph exclusions'):
            self.check()

    def test_graph_stream_rejects_forged_sizes_duplicate_files_footer_and_tail(self):
        binding = self.bindings['java']
        path = Path(binding['fixture'])
        original = [json.loads(line) for line in lzma.decompress(path.read_bytes()).splitlines()]
        files, sizes, _ = REUSE._source(self.sources['java'], binding)
        mutations = []
        bad = copy.deepcopy(original); bad[1]['data']['size'] += 1; mutations.append(bad)
        bad = copy.deepcopy(original); bad[2] = bad[1]; mutations.append(bad)
        bad = copy.deepcopy(original); bad[-1]['data']['files'] = 99; mutations.append(bad)
        mutations.extend([original[:-1], original + [original[-1]]])
        for rows in mutations:
            with self.subTest(rows=rows):
                path.write_bytes(lzma.compress(b''.join(canonical(row) + b'\n' for row in rows)))
                binding['fixture_sha256'], binding['fixture_bytes'] = sha(path.read_bytes()), path.stat().st_size
                with self.assertRaises(ValueError):
                    REUSE._graph(binding, files, sizes)

    def test_full_zip_rejects_unsafe_and_duplicate_members(self):
        for name in ('full/../unsafe', 'outside.txt', 'full/main.txt'):
            with self.subTest(name=name):
                source = copy.deepcopy(self.sources['java'])
                binding = copy.deepcopy(self.bindings['java'])
                path = self.root / 'bad.zip'
                with zipfile.ZipFile(path, 'w') as archive:
                    archive.writestr('full/main.txt', b'one')
                    with self.assertWarns(UserWarning) if name == 'full/main.txt' else self.subTest():
                        archive.writestr(name, b'two')
                source.update(fixture=str(path), fixture_sha256=sha(path.read_bytes()),
                              fixture_bytes=path.stat().st_size)
                binding.update(source_fixture=str(path), source_fixture_sha256=source['fixture_sha256'])
                with self.assertRaises(ValueError):
                    REUSE._source(source, binding)

    def test_malformed_bindings_are_value_errors(self):
        self.bindings['java']['counts'] = []
        with self.assertRaises(ValueError):
            self.check()


if __name__ == '__main__':
    unittest.main()
