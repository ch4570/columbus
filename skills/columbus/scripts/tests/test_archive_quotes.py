"""Exact source quotes are coupled to verified archive bytes, never repaired or paged."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import gzip
import hashlib
import io
import json
import lzma
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from columbus.archive import _validated_rows, archive
from columbus.cli import main
from columbus.index import RepositoryIndex
from columbus.quotes import quotes_archive, render_quotes
from columbus.sync_state import SnapshotChanged, read_stable


class ArchiveQuotesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / 'consumer'
        self.repo.mkdir()
        self.serial = 0

    @staticmethod
    def complete(records):
        counts = dict(files=0, nodes=0, scopes=0, edges=0, references=0,
                      imports=0, diagnostics=0)
        names = dict(file='files', node='nodes', scope='scopes', edge='edges',
                     reference='references', diagnostic='diagnostics')
        names['import'] = 'imports'
        for row in records:
            counts[names[row['record']]] += 1
        return [dict(record='manifest', data=dict(format='columbus-graph', version=1,
                    revision='test-revision', analyzer_version='fixture',
                    analyzer_fingerprint={}, semantic_complete=False,
                    source_bodies_included=False))] + records + [dict(record='end', data=counts)]

    def records(self, files):
        rows = []
        for path, (body, language) in files.items():
            target = self.repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            rows.extend([
                dict(record='file', data=dict(path=path, hash=hashlib.sha256(body).hexdigest(), size=len(body))),
                dict(record='node', data=dict(path=path, id=path + '::module', name=path,
                     qualname=path, kind='module', language=language, start_line=1,
                     end_line=1, fidelity='text', partial=True)),
            ])
        return rows

    def emit(self, rows, codec='gzip'):
        self.serial += 1
        artifact = self.root / f'graph-{self.serial}.{codec}'
        opener = gzip.open if codec == 'gzip' else lzma.open
        with opener(artifact, 'wt', encoding='utf-8', newline='\n') as stream:
            stream.write(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
        return artifact

    def fixture(self, files=None, codec='gzip'):
        files = files or {'a.py': (b'first\nsecond\nthird\n', 'python')}
        return self.emit(self.complete(self.records(files)), codec)

    def assert_before_read(self, artifact, ranges):
        with patch('columbus.sync_state.read_stable', side_effect=AssertionError('source read before rejection')) as read:
            with self.assertRaises(ValueError):
                quotes_archive(artifact, ranges, self.repo)
            read.assert_not_called()

    def cli(self, artifact, *arguments):
        # Pin imports to this checkout, even when invoked from another checkout's venv.
        environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        return subprocess.run([sys.executable, '-m', 'columbus', 'archive-quotes',
                               '--input', str(artifact), '--repo', str(self.repo), *arguments],
                              cwd=self.repo, env=environment, capture_output=True, timeout=15)

    def test_exported_gzip_xz_relocation_and_cli_without_index(self):
        producer = self.root / 'producer'
        producer.mkdir()
        body = b'# header\ndef first():\n    return 1\n\n# outside declaration\n'
        (producer / 'a.py').write_bytes(body)
        index = RepositoryIndex(producer / '.columbus/index.sqlite')
        index.refresh(producer)
        (self.repo / 'a.py').write_bytes(body)
        packets = []
        for codec in ('gzip', 'xz'):
            with self.subTest(codec=codec):
                artifact = self.root / ('exported.' + codec)
                archive(index, artifact, codec)
                packet = quotes_archive(artifact, [('a.py', 1, 5)], self.repo)
                packets.append(packet)
                self.assertEqual(packet['format'], 'columbus-quotes/v1')
                self.assertFalse(packet['semantic_complete'])
                self.assertEqual(packet['quotes'], [dict(path='a.py', start_line=1, end_line=5,
                    source_hash=hashlib.sha256(body).hexdigest(), language='python',
                    quote=body.decode().removesuffix('\n'))])
                process = self.cli(artifact, '--range', 'a.py', '1', '5', '--format', 'json')
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertEqual(process.stderr, b'')
                self.assertEqual(process.stdout, render_quotes(packet).encode('utf-8'))
                self.assertFalse((self.repo / '.columbus').exists())
        self.assertEqual(packets[0], packets[1])

    def test_order_overlaps_and_one_complete_scan_one_read_per_file(self):
        artifact = self.fixture({'a.py': (b'a1\na2\na3\na4\n', 'python'),
                                 'b.kt': (b'b1\nb2\nb3\n', 'kotlin')})
        requests = [('b.kt', 2, 3), ('a.py', 1, 3), ('a.py', 2, 4)]
        scanned_to_end = False

        def scan(raw):
            nonlocal scanned_to_end
            yield from _validated_rows(raw)
            scanned_to_end = True

        def read(*args, **kwargs):
            self.assertTrue(scanned_to_end, 'source opened before validating the archive footer')
            return read_stable(*args, **kwargs)

        with patch('columbus.quotes._validated_rows', side_effect=scan) as scans, \
                patch('columbus.sync_state.read_stable', side_effect=read) as reads:
            packet = quotes_archive(artifact, requests, self.repo)
        self.assertEqual(scans.call_count, 1)
        self.assertEqual([call.args[1] for call in reads.call_args_list], ['b.kt', 'a.py'])
        self.assertEqual([(q['path'], q['start_line'], q['end_line']) for q in packet['quotes']], requests)
        self.assertEqual([q['quote'] for q in packet['quotes']], ['b2\nb3', 'a1\na2\na3', 'a2\na3\na4'])
        self.assertNotIn('next_offset', packet)
        self.assertNotIn('truncated', packet)

    def test_literal_range_does_not_add_brace_or_stitch_unselected_lines(self):
        body = b'fun first() {\n  chosen()\n}\n// omitted gap\nfun second() = other()\n'
        artifact = self.fixture({'A.kt': (body, 'kotlin')})
        packet = quotes_archive(artifact, [('A.kt', 1, 2), ('A.kt', 5, 5)], self.repo)
        self.assertEqual([q['quote'] for q in packet['quotes']],
                         ['fun first() {\n  chosen()', 'fun second() = other()'])
        self.assertEqual(packet['quotes'][0]['end_line'], 2)

    def test_option_and_portable_path_validation_precedes_archive_open(self):
        missing = self.root / 'never-opened'
        requests = [None, [], 'a.py', [('a.py', 1)], [('a.py', 1, 1, 'extra')],
                    [('a.py', 1, 1)] * 2, [('a.py', n, n) for n in range(1, 18)]]
        paths = ['', '/a.py', '../a.py', 'a/../b.py', './a.py', 'a/./b.py',
                 'a//b.py', 'a.py/', '\\a.py', 'a\\b.py', 'C:/a.py',
                 'a.py:stream', 'a\0.py', 'a' * 2049, None, 17]
        requests += [[(path, 1, 1)] for path in paths]
        requests += [[('a.py', start, end)] for start, end in
                     [(0, 1), (-1, 2), (2, 1), (True, 1), (1, True),
                      ('1', 1), (1, '2'), (1.0, 2), (1, None), (1, 401)]]
        for ranges in requests:
            with self.subTest(ranges=ranges), self.assertRaises(ValueError):
                quotes_archive(missing, ranges, self.repo)
        for budget in (511, 64001, True, 6000.0, '6000', None):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                quotes_archive(missing, [('a.py', 1, 1)], self.repo, budget_bytes=budget)

    def test_request_and_aggregate_line_caps_include_overlaps(self):
        artifact = self.fixture({'a.py': (b'x\n' * 401, 'python')})
        sixteen = [('a.py', number, number) for number in range(1, 17)]
        self.assertEqual(len(quotes_archive(artifact, sixteen, self.repo, 64000)['quotes']), 16)
        self.assertEqual(len(quotes_archive(artifact, [('a.py', 1, 400)], self.repo)['quotes']), 1)
        self.assert_before_read(artifact, [('a.py', 1, 300), ('a.py', 200, 300)])

    def test_out_of_file_bounds_and_empty_versus_blank_physical_lines(self):
        artifact = self.fixture({'empty.py': (b'', 'python'), 'blank.py': (b'\n', 'python'),
                                 'last.py': (b'one\n\n', 'python'), 'no-lf.py': (b'one', 'python')})
        for path, start, end in [('empty.py', 1, 1), ('blank.py', 1, 2),
                                 ('last.py', 3, 3), ('no-lf.py', 2, 2)]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                quotes_archive(artifact, [(path, start, end)], self.repo)
        packet = quotes_archive(artifact, [('blank.py', 1, 1), ('last.py', 2, 2), ('no-lf.py', 1, 1)], self.repo)
        self.assertEqual([q['quote'] for q in packet['quotes']], ['', '', 'one'])

    def test_budget_is_exact_serialized_utf8_with_newline_and_never_partial(self):
        artifact = self.fixture({'a.py': (('# 😀 한글 ' + '\x1b\x7f\x85' * 30 + '\n').encode(), 'python'),
                                 'b.py': (b'# later\n', 'python')})
        requests = [('a.py', 1, 1), ('b.py', 1, 1)]
        packet = quotes_archive(artifact, requests, self.repo, 64000)
        rendered = render_quotes(packet)
        required = len(rendered.encode('utf-8'))
        self.assertGreater(required, 512)
        self.assertTrue(rendered.endswith('\n'))
        self.assertFalse(rendered.endswith('\n\n'))
        self.assertEqual(quotes_archive(artifact, requests, self.repo, required), packet)
        with self.assertRaises(ValueError):
            quotes_archive(artifact, requests, self.repo, required - 1)
        process = self.cli(artifact, '--range', 'a.py', '1', '1', '--range', 'b.py', '1', '1',
                           '--budget-bytes', str(required - 1))
        self.assertEqual(process.returncode, 2)
        self.assertEqual(process.stdout, b'')
        self.assertTrue(process.stderr)
        self.assertFalse((self.repo / '.columbus').exists())

    def test_default_budget_rejects_long_line_instead_of_trimming(self):
        body = b'x' * 6100 + b'\n'
        artifact = self.fixture({'a.py': (body, 'python')})
        with self.assertRaises(ValueError):
            quotes_archive(artifact, [('a.py', 1, 1)], self.repo)
        self.assertEqual(quotes_archive(artifact, [('a.py', 1, 1)], self.repo, 64000)['quotes'][0]['quote'],
                         body[:-1].decode())

    def test_renderer_escapes_controls_without_changing_decoded_quote(self):
        controls = ''.join(chr(n) for n in [*range(32), *range(127, 160), 0x2028, 0x2029])
        packet = {'quotes': [{'path': 'a\x1b.py', 'quote': '\\u001b " 😀 ' + controls}]}
        original = deepcopy(packet)
        rendered = render_quotes(packet)
        self.assertEqual(json.loads(rendered), original)
        self.assertEqual(packet, original)
        for character in controls:
            self.assertNotIn(character, rendered[:-1])
        self.assertEqual(rendered.count('\n'), 1)

    def test_encoding_and_physical_newlines_use_archived_language(self):
        separators = 'one\r\ntwo\rthree\x85four\u2028five\u2029six\n'
        files = {'j.custom': (separators.encode('utf-8'), 'java'),
                 'k.custom': (separators.encode('utf-8'), 'kotlin'),
                 'other.custom': (separators.encode('utf-8'), 'domain'),
                 'cookie.custom': (b'# coding: latin-1\r\nname = "caf\xe9"\r\n', 'python'),
                 'bom.custom': ('\ufeff// 😀\r\nlast\n'.encode('utf-8'), 'kotlin')}
        artifact = self.fixture(files)
        # A relocated consumer's current config is irrelevant, even if malformed.
        (self.repo / '.columbus.json').write_bytes(b'{ invalid config')
        packet = quotes_archive(artifact, [('j.custom', 1, 2), ('k.custom', 2, 2),
            ('other.custom', 2, 3), ('cookie.custom', 1, 2), ('bom.custom', 1, 2)], self.repo)
        self.assertEqual([q['quote'] for q in packet['quotes']], [
            'one\ntwo\rthree\x85four\u2028five\u2029six',
            'two\rthree\x85four\u2028five\u2029six',
            'two\nthree\x85four\u2028five\u2029six',
            '# coding: latin-1\nname = "café"', '// 😀\nlast'])
        for quote in packet['quotes']:
            self.assertEqual(quote['source_hash'], hashlib.sha256(files[quote['path']][0]).hexdigest())
        self.assertEqual(json.loads(render_quotes(packet)), packet)

    def test_exported_configured_extension_retains_language_after_relocation(self):
        producer = self.root / 'producer'
        producer.mkdir()
        (producer / '.columbus.json').write_bytes(b'{"extensions":{".custom":"python"}}')
        body = b'# coding: latin-1\ndef greeting(): return "caf\xe9"\n'
        (producer / 'a.custom').write_bytes(body)
        index = RepositoryIndex(producer / '.columbus/index.sqlite')
        index.refresh(producer)
        artifact = self.root / 'configured.xz'
        archive(index, artifact, 'xz')
        (self.repo / 'a.custom').write_bytes(body)
        quote = quotes_archive(artifact, [('a.custom', 2, 2)], self.repo)['quotes'][0]
        self.assertEqual(quote['language'], 'python')
        self.assertEqual(quote['quote'], 'def greeting(): return "café"')
        self.assertFalse((self.repo / '.columbus').exists())

    def test_complete_archive_validation_precedes_any_source_read(self):
        rows = self.complete(self.records({'a.py': (b'one\n', 'python')}))
        bad_count = deepcopy(rows)
        bad_count[-1]['data']['nodes'] += 1
        bad_manifest = deepcopy(rows)
        bad_manifest[0]['data']['version'] = 999
        for codec in ('gzip', 'xz'):
            for malformed in [rows[:-1], rows + [dict(record='node', data={})], bad_count,
                              bad_manifest, rows[:-1] + [dict(record='unknown', data={}), rows[-1]],
                              rows[:-1] + [None, rows[-1]]]:
                with self.subTest(codec=codec, malformed=malformed[-1]):
                    self.assert_before_read(self.emit(malformed, codec), [('a.py', 1, 1)])
            artifact = self.emit(rows, codec)
            artifact.write_bytes(artifact.read_bytes()[:-6])
            self.assert_before_read(artifact, [('a.py', 1, 1)])

    def test_invalid_gzip_deflate_is_clean_error_before_source_reads(self):
        artifact = self.root / 'bad-deflate.gz'
        artifact.write_bytes(bytes.fromhex('1f8b08000000000002ff07') + b'\0' * 8)
        self.assert_before_read(artifact, [('a.py', 1, 1)])
        process = self.cli(artifact, '--range', 'a.py', '1', '1')
        self.assertEqual(process.returncode, 2)
        self.assertEqual(process.stdout, b'')
        self.assertTrue(process.stderr.startswith(b'columbus: '))
        self.assertNotIn(b'Traceback', process.stderr)
        self.assertFalse((self.repo / '.columbus').exists())

    def test_cli_explicit_empty_telemetry_rejected_at_both_option_positions(self):
        artifact = self.fixture()
        before = sorted(path.relative_to(self.repo).as_posix() for path in self.repo.rglob('*'))
        commands = [
            ['archive-quotes', '--telemetry', ''],
            ['--telemetry', '', 'archive-quotes'],
        ]
        environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        for arguments in commands:
            with self.subTest(arguments=arguments):
                process = subprocess.run([sys.executable, '-m', 'columbus', *arguments,
                    '--input', str(artifact), '--repo', str(self.repo), '--range', 'a.py', '1', '1'],
                    cwd=self.repo, env=environment, capture_output=True, timeout=15)
                self.assertEqual(process.returncode, 2)
                self.assertEqual(process.stdout, b'')
                self.assertIn(b'telemetry', process.stderr)
                self.assertNotIn(b'Traceback', process.stderr)
                self.assertEqual(sorted(path.relative_to(self.repo).as_posix() for path in self.repo.rglob('*')), before)

    def test_cli_diagnostics_escape_untrusted_controls_without_changing_quotes(self):
        controls = ''.join(chr(n) for n in [*range(32), *range(127, 160), 0x2028, 0x2029])
        message = 'Cannot decode source: dir/' + controls + '/file.py'
        arguments = ['archive-quotes', '--input', str(self.root / 'mocked-archive'),
                     '--repo', str(self.repo), '--range', 'a.py', '1', '1']
        output, errors = io.StringIO(), io.StringIO()
        with patch('columbus.quotes.quotes_archive', side_effect=ValueError(message)), \
                redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(main(arguments), 2)
        diagnostic = errors.getvalue()
        self.assertEqual(output.getvalue(), '')
        self.assertTrue(diagnostic.startswith('columbus: '))
        self.assertTrue(diagnostic.endswith('\n'))
        self.assertEqual(diagnostic.count('\n'), 1)
        for character in controls:
            self.assertNotIn(character, diagnostic[:-1])
        self.assertEqual(json.loads('"' + diagnostic.removeprefix('columbus: ').removesuffix('\n') + '"'), message)
        # Success uses lossless JSON serialization, not the diagnostic representation.
        packet = {'format': 'columbus-quotes/v1', 'quotes': [dict(path='a.py', start_line=1,
            end_line=1, source_hash='0' * 64, language='python', quote='literal 😀 ' + controls)]}
        output, errors = io.StringIO(), io.StringIO()
        with patch('columbus.quotes.quotes_archive', return_value=packet), \
                redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(main(arguments), 0)
        self.assertEqual(errors.getvalue(), '')
        self.assertEqual(json.loads(output.getvalue()), packet)

    def test_duplicate_file_and_invalid_hash_size_records_reject_before_reads(self):
        records = self.records({'a.py': (b'one\n', 'python'), 'b.py': (b'two\n', 'python')})
        for field, value in [('hash', ''), ('hash', 'A' * 64), ('hash', 'z' * 64),
                             ('hash', None), ('size', -1), ('size', True), ('size', '4'),
                             ('size', 1_000_001), ('size', None)]:
            changed = deepcopy(records)
            changed[2]['data'][field] = value
            with self.subTest(field=field, value=value):
                self.assert_before_read(self.emit(self.complete(changed)), [('a.py', 1, 1), ('b.py', 1, 1)])
        for change in ({}, {'hash': '0' * 64}, {'size': 5}):
            duplicate = deepcopy(records[2])
            duplicate['data'].update(change)
            self.assert_before_read(self.emit(self.complete(records + [duplicate])), [('a.py', 1, 1), ('b.py', 1, 1)])

    def test_missing_file_or_unanimous_language_rejects_before_reads(self):
        records = self.records({'a.py': (b'one\n', 'python'), 'b.py': (b'two\n', 'python')})
        variants = [[row for row in records if not (row['record'] == kind and row['data']['path'] == 'b.py')]
                    for kind in ('file', 'node')]
        for language in (None, '', 'Python', 'python\n', 'x' * 41, 7, ['python']):
            changed = deepcopy(records)
            changed[3]['data']['language'] = language
            variants.append(changed)
        missing_language = deepcopy(records)
        del missing_language[3]['data']['language']
        variants.append(missing_language)
        conflict = deepcopy(records[3])
        conflict['data'].update(id='b.py::other', language='kotlin')
        variants.append(records + [conflict])
        for changed in variants:
            with self.subTest(changed=changed[-1]):
                self.assert_before_read(self.emit(self.complete(changed)), [('a.py', 1, 1), ('b.py', 1, 1)])
        artifact = self.emit(self.complete(records))
        (self.repo / 'unindexed.py').write_bytes(b'private\n')
        self.assert_before_read(artifact, [('unindexed.py', 1, 1)])
        same_language = deepcopy(records[3])
        same_language['data']['id'] = 'b.py::another'
        self.assertEqual(quotes_archive(self.emit(self.complete(records + [same_language])),
                         [('b.py', 1, 1)], self.repo)['quotes'][0]['quote'], 'two')

    def test_later_stale_hash_or_size_fails_whole_cli_batch(self):
        records = self.records({'a.py': (b'one\n', 'python'), 'b.py': (b'two\n', 'python')})
        artifact = self.emit(self.complete(records))
        (self.repo / 'b.py').write_bytes(b'new\n')  # Equal size still needs the content hash.
        with self.assertRaises(ValueError):
            quotes_archive(artifact, [('a.py', 1, 1), ('b.py', 1, 1)], self.repo)
        process = self.cli(artifact, '--range', 'a.py', '1', '1', '--range', 'b.py', '1', '1')
        self.assertEqual(process.returncode, 2)
        self.assertEqual(process.stdout, b'')
        (self.repo / 'b.py').write_bytes(b'two\n')
        records[2]['data']['size'] += 1
        with self.assertRaises(ValueError):
            quotes_archive(self.emit(self.complete(records)), [('b.py', 1, 1)], self.repo)

    def test_concurrent_edit_signal_and_binary_or_undecodable_source_fail(self):
        artifact = self.fixture()
        with patch('columbus.sync_state.read_stable', side_effect=SnapshotChanged('changed while read')):
            with self.assertRaises(ValueError):
                quotes_archive(artifact, [('a.py', 1, 1)], self.repo)
        for body, language in [(b'one\0two\n', 'python'), (b'\xff\n', 'kotlin')]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                quotes_archive(self.fixture({'a.py': (body, language)}), [('a.py', 1, 1)], self.repo)

    def test_directory_and_fifo_reject_before_opening_stream(self):
        records = self.records({'a.py': (b'one\n', 'python')})
        artifact = self.emit(self.complete(records))
        target = self.repo / 'a.py'
        target.unlink()
        target.mkdir()
        self.assert_before_read(artifact, [('a.py', 1, 1)])
        target.rmdir()
        if hasattr(os, 'mkfifo'):
            os.mkfifo(target)
            # Mocking read_stable prevents a regression from blocking on a FIFO.
            self.assert_before_read(artifact, [('a.py', 1, 1)])

    def test_symlink_file_and_parent_are_not_followed(self):
        records = self.records({'a.py': (b'one\n', 'python'), 'nested/b.py': (b'two\n', 'python')})
        artifact = self.emit(self.complete(records))
        outside = self.root / 'outside.py'
        outside.write_bytes(b'one\n')
        (self.repo / 'a.py').unlink()
        try:
            (self.repo / 'a.py').symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f'symlinks unavailable: {exc}')
        self.assert_before_read(artifact, [('a.py', 1, 1)])
        moved = self.root / 'moved'
        (self.repo / 'nested').rename(moved)
        (self.repo / 'nested').symlink_to(moved, target_is_directory=True)
        self.assert_before_read(artifact, [('nested/b.py', 1, 1)])

    def test_cli_invalid_ranges_and_write_options_leave_empty_stdout(self):
        artifact = self.fixture()
        options = [[], ['--range', 'a.py', 'one', '2'], ['--range', 'a.py', '0', '1'],
                   ['--range', '../a.py', '1', '1'], ['--range', 'a.py', '1', '99'],
                   ['--range', 'a.py', '1', '1', '--format', 'text'],
                   ['--range', 'a.py', '1', '1', '--pretty'],
                   ['--range', 'a.py', '1', '1', '--db', str(self.repo / 'forbidden.sqlite')],
                   ['--range', 'a.py', '1', '1', '--telemetry', str(self.repo / 'forbidden.jsonl')]]
        before = sorted(path.relative_to(self.repo).as_posix() for path in self.repo.rglob('*'))
        for arguments in options:
            with self.subTest(arguments=arguments):
                process = self.cli(artifact, *arguments)
                self.assertEqual(process.returncode, 2, process.stderr)
                self.assertEqual(process.stdout, b'')
                self.assertTrue(process.stderr)
                self.assertEqual(sorted(path.relative_to(self.repo).as_posix() for path in self.repo.rglob('*')), before)

    def test_cli_single_dot_prefix_and_literal_special_paths_without_writes(self):
        files = {'-file.py': (b'# selected hyphen file\n', 'python'),
                 'nested space/한글 #file.py': ('# selected 😀 Unicode path\n'.encode('utf-8'), 'python'),
                 'a.py': (b'# canonical path exists; repeated prefixes must still fail\n', 'python')}
        artifact = self.fixture(files)
        before = {path.relative_to(self.repo).as_posix(): path.read_bytes()
                  for path in self.repo.rglob('*') if path.is_file()}
        archive_before = artifact.read_bytes()
        process = self.cli(artifact, '--range', './-file.py', '1', '1',
                           '--range', 'nested space/한글 #file.py', '1', '1')
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, b'')
        self.assertEqual(json.loads(process.stdout)['quotes'], [
            dict(path=path, start_line=1, end_line=1, language=language,
                 source_hash=hashlib.sha256(body).hexdigest(), quote=body.decode('utf-8').removesuffix('\n'))
            for path, (body, language) in files.items() if path != 'a.py'])
        # Only the CLI accepts one syntactic prefix; the archive API stays canonical.
        self.assert_before_read(artifact, [('./-file.py', 1, 1)])
        for invalid in ('././a.py', './../../outside.py', './/a.py', './../a.py', './C:a.py'):
            with self.subTest(path=invalid):
                process = self.cli(artifact, '--range', invalid, '1', '1')
                self.assertEqual(process.returncode, 2)
                self.assertEqual(process.stdout, b'')
                self.assertTrue(process.stderr)
        process = self.cli(artifact, '--range', 'a.py', '1', '1', '--range', './a.py', '1', '1')
        self.assertEqual(process.returncode, 2)
        self.assertEqual(process.stdout, b'')
        self.assertTrue(process.stderr)
        self.assertEqual({path.relative_to(self.repo).as_posix(): path.read_bytes()
                          for path in self.repo.rglob('*') if path.is_file()}, before)
        self.assertEqual(artifact.read_bytes(), archive_before)
        self.assertFalse((self.repo / '.columbus').exists())


if __name__ == '__main__':
    unittest.main()
