import gzip
import io
import json
import lzma
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from columbus.archive import _validated_rows, archive, source_archive, source_archive_many
from columbus.cli import main
from columbus.index import RepositoryIndex, compact
from columbus.presentation import archive_source_text
from columbus.sync_state import read_stable


class ArchiveSourceTests(unittest.TestCase):
    @staticmethod
    def source_rows(blocks):
        return [(block['path'], number, line) for block in blocks for number, line in
                enumerate(block['source'].split('\n'), block['start_line'])]

    def test_batch_single_scan_file_reads_overlap_and_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'z.py').write_text('class Outer:\n    def first(self):\n        return 1\n'
                                      '    def second(self):\n        return 2\n\nUNSELECTED = 3\n')
            (root / 'a.py').write_text('def alpha():\n    return "한글"\n', encoding='utf-8')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            queries = ['Outer.first', 'alpha', 'Outer']
            expected = [('z.py', number, line) for number, line in enumerate(
                (root / 'z.py').read_text().splitlines()[:5], 1)]
            expected += [('a.py', number, line) for number, line in enumerate(
                (root / 'a.py').read_text(encoding='utf-8').splitlines(), 1)]
            packets = []
            for codec in ('gzip', 'xz'):
                artifact = root / codec
                archive(index, artifact, codec)
                singles = [source_archive(artifact, query, root) for query in queries]
                with patch('columbus.archive._validated_rows', wraps=_validated_rows) as scanned, \
                        patch('columbus.sync_state.read_stable', wraps=read_stable) as reads:
                    packet = source_archive_many(artifact, queries, root)
                    self.assertEqual(scanned.call_count, 1)
                    self.assertEqual([call.args[1] for call in reads.call_args_list], ['z.py', 'a.py'])
                packets.append(packet)
                self.assertEqual(self.source_rows(packet['sources']), expected)
                self.assertEqual(set(self.source_rows(packet['sources'])), set(self.source_rows(singles)))
                self.assertEqual([target['id'] for target in packet['targets']], [p['target'] for p in singles])
                for target, single in zip(packet['targets'], singles):
                    for key in ('path', 'source_hash', 'declaration_start_line', 'declaration_end_line', 'partial', 'fidelity'):
                        self.assertEqual(target[key], single[key])
                self.assertEqual(packet['total_lines'], 7)
                self.assertIsNone(packet['next_offset'])
                self.assertFalse(packet['truncated'])
                self.assertFalse(packet['semantic_complete'])
                alias = source_archive_many(artifact, ['alpha', 'a.alpha'], root)
                self.assertEqual(len(alias['targets']), 1)
                self.assertEqual(alias['total_lines'], 2)
                with tempfile.TemporaryDirectory() as directory:
                    consumer = Path(directory)
                    for name in ('z.py', 'a.py'):
                        (consumer / name).write_bytes((root / name).read_bytes())
                    output = io.StringIO()
                    with redirect_stdout(output):
                        self.assertEqual(main(['archive-source', *queries, '--input', str(artifact),
                                               '--repo', str(consumer)]), 0)
                    self.assertEqual(json.loads(output.getvalue()), packet)
                    output = io.StringIO()
                    with redirect_stdout(output):
                        self.assertEqual(main(['archive-source', 'alpha', '--input', str(artifact),
                                               '--repo', str(consumer), '--format', 'text']), 0)
                    self.assertEqual(output.getvalue(), archive_source_text(singles[1]))
                    self.assertFalse((consumer / '.columbus').exists())
            self.assertEqual(packets[0], packets[1])

    def test_batch_multibyte_global_budget_and_pagination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = ['def first():'] + ['    # 한글 😀 ' + 'x' * 45 for _ in range(18)] + ['    return 1']
            later = ['def later():', '    return 2']
            second = ['def second():'] + ['    # 한글 😀 ' + 'x' * 45 for _ in range(12)] + ['    return 3']
            (root / 'z.py').write_text('\n'.join(first + ['# gap', ''] + later) + '\n', encoding='utf-8')
            (root / 'a.py').write_text('\n'.join(second) + '\n', encoding='utf-8')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            expected = [('z.py', number, line) for number, line in enumerate(first, 1)]
            expected += [('z.py', number, line) for number, line in enumerate(later, len(first) + 3)]
            expected += [('a.py', number, line) for number, line in enumerate(second, 1)]
            for codec in ('gzip', 'xz'):
                artifact = root / codec
                archive(index, artifact, codec)
                limited = source_archive_many(artifact, ['later', 'second', 'first'], root, limit=2)
                self.assertEqual(self.source_rows(limited['sources']), expected[:2])
                self.assertEqual(limited['next_offset'], 2)
                for fmt in ('json', 'text'):
                    recovered, offset = [], 0
                    while True:
                        page = source_archive_many(artifact, ['later', 'second', 'first'], root,
                                                   limit=400, budget_bytes=2048, offset=offset, output_format=fmt)
                        rendered = archive_source_text(page) if fmt == 'text' else compact(page) + '\n'
                        self.assertLessEqual(len(rendered.encode('utf-8')), 2048)
                        rows = self.source_rows(page['sources'])
                        self.assertTrue(1 <= len(rows) <= 400)
                        if offset == 0:
                            self.assertTrue(page['truncated'])
                        recovered.extend(rows)
                        self.assertEqual(page['total_lines'], len(expected))
                        self.assertEqual(page['truncated'], bool(offset or len(recovered) < len(expected)))
                        offset = page['next_offset']
                        if offset is None:
                            break
                        self.assertEqual(offset, len(recovered))
                    self.assertEqual(recovered, expected)
                    self.assertEqual(len({(path, number) for path, number, _ in recovered}), len(expected))
                with self.assertRaisesRegex(ValueError, 'outside'):
                    source_archive_many(artifact, ['first', 'second'], root, offset=len(first) + len(second))

    def test_batch_ambiguity_stale_and_late_archive_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.py').write_text('def target(): return 1\ndef keeper(): return 2\n')
            (root / 'b.py').write_text('def target(): return 3\n')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            for codec, opener in [('gzip', gzip.open), ('xz', lzma.open)]:
                artifact = root / codec
                archive(index, artifact, codec)
                for queries in (['target', 'keeper'], ['absent', 'keeper'], ['bad\nname', 'keeper']):
                    with self.assertRaisesRegex(ValueError, 'ambiguous or absent') as failure:
                        source_archive_many(artifact, queries, root)
                    self.assertIn(ascii(queries[0]), str(failure.exception))
                    self.assertNotIn('\n', str(failure.exception))
                valid = ['a.py::target:function', 'keeper']
                source_archive_many(artifact, valid, root)
                original = (root / 'a.py').read_bytes()
                (root / 'a.py').write_bytes(original + b'# changed\n')
                with self.assertRaisesRegex(ValueError, 'Stale source'):
                    source_archive_many(artifact, valid, root)
                (root / 'a.py').write_bytes(original)
                with opener(artifact, 'rt') as stream:
                    rows = stream.readlines()
                for malformed in (rows[:-1], rows + ['{"record":"node","data":{}}\n']):
                    with opener(artifact, 'wt') as stream:
                        stream.writelines(malformed)
                    with patch('columbus.sync_state.read_stable', wraps=read_stable) as reads:
                        with self.assertRaisesRegex(ValueError, 'Incomplete|after archive end'):
                            source_archive_many(artifact, valid, root, limit=1)
                        self.assertEqual(reads.call_count, 0)

    def test_batch_options_long_line_and_text_controls(self):
        for queries in ([], ['one'], ['same', 'same'], ['x' * 2049, 'two'], list(map(str, range(17)))):
            with self.assertRaisesRegex(ValueError, '2–16 unique'):
                source_archive_many('unused', queries, '.')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.py').write_text('LONG = "' + 'x' * 3000 + '"\nFLAG = "\\x1b"\n')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            artifact = root / 'graph.xz'
            archive(index, artifact, 'xz')
            with self.assertRaisesRegex(ValueError, 'one source line'):
                source_archive_many(artifact, ['a.py::module', 'FLAG'], root, budget_bytes=2048)
            packet = source_archive_many(artifact, ['a.py::module', 'FLAG'], root)
            packet['sources'][0]['source'] = '\x1b[31m'
            self.assertNotIn('\x1b', archive_source_text(packet))
            self.assertIn('\\u001b', archive_source_text(packet))

    def test_unique_names_suffixes_and_ambiguity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ('src/pkg', 'external/other'):
                path = root / folder
                path.mkdir(parents=True)
                (path / 'mod.py').write_text('class Owner:\n    def target(self): return 1\n', encoding='utf-8')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            target = 'src/pkg/mod.py::Owner.target:method'
            for codec, opener in [('gzip', gzip.open), ('xz', lzma.open)]:
                artifact = root / codec
                archive(index, artifact, codec)
                expected = source_archive(artifact, target, root)
                for query in ('src.pkg.mod.Owner.target', 'pkg.mod.Owner.target'):
                    self.assertEqual(source_archive(artifact, query, root), expected)
                for query in ('target', 'Owner.target', 'mod.Owner.target', 'kg.mod.Owner.target',
                              'PKG.mod.Owner.target', 'pkg.mod.WrongOwner.target'):
                    with self.assertRaisesRegex(ValueError, 'ambiguous or absent'):
                        source_archive(artifact, query, root)
                with opener(artifact, 'rt') as stream:
                    rows = [json.loads(line) for line in stream]
                other = 'external/other/mod.py::Owner.target:method'
                for module, ambiguous in [('pkg.mod', False), ('external.pkg.mod', True)]:
                    for row in rows:
                        if row['record'] == 'node' and row['data']['id'] == other:
                            row['data']['module'] = module
                    reordered = ([rows[0]] + [r for r in rows[1:-1] if r['record'] != 'node']
                                 + [r for r in rows[1:-1] if r['record'] == 'node'] + [rows[-1]])
                    with opener(artifact, 'wt') as stream:
                        stream.write(''.join(json.dumps(row) + '\n' for row in reordered))
                    if ambiguous:
                        with self.assertRaisesRegex(ValueError, 'ambiguous or absent'):
                            source_archive(artifact, 'pkg.mod.Owner.target', root)
                    else:
                        self.assertEqual(source_archive(artifact, 'pkg.mod.Owner.target', root),
                                         source_archive(artifact, other, root))
                    self.assertEqual(source_archive(artifact, target, root), expected)

    def test_no_edge_declaration_pagination_and_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = ['def isolated():'] + ['    # 한글 ' + 'x' * 80 for _ in range(90)] + ['    return 1']
            (root / 'source.py').write_text('\n'.join(body) + '\n', encoding='utf-8')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            for codec in ('gzip', 'xz'):
                artifact = root / codec
                archive(index, artifact, codec)
                for fmt in ('json', 'text'):
                    recovered, offset = [], 0
                    while True:
                        page = source_archive(artifact, 'source.py::isolated:function', root,
                                              budget_bytes=2048, offset=offset, output_format=fmt)
                        rendered = archive_source_text(page) if fmt == 'text' else compact(page) + '\n'
                        self.assertLessEqual(len(rendered.encode()), 2048)
                        self.assertEqual(page['start_line'], offset + 1)
                        recovered.extend(page['source'].split('\n'))
                        offset = page['next_offset']
                        if offset is None:
                            break
                        self.assertEqual(offset, len(recovered))
                    self.assertEqual(recovered, body)
                output = io.StringIO()
                with redirect_stdout(output):
                    code = main(['archive-source', 'source.py::isolated:function', '--input', str(artifact),
                                 '--repo', str(root), '--format', 'text', '--limit', '2'])
                self.assertEqual(code, 0)
                self.assertIn('1| def isolated():', output.getvalue())
                self.assertIn('"next_offset": 2', output.getvalue())
                with tempfile.TemporaryDirectory() as consumer:
                    clean = Path(consumer)
                    (clean / 'source.py').write_bytes((root / 'source.py').read_bytes())
                    with redirect_stdout(io.StringIO()):
                        self.assertEqual(main(['archive-source', 'source.py::isolated:function',
                                               '--input', str(artifact), '--repo', str(clean)]), 0)
                    self.assertFalse((clean / '.columbus').exists())
            (root / 'source.py').write_text('def isolated(): return 2\n')
            with self.assertRaisesRegex(ValueError, 'Stale source'):
                source_archive(artifact, 'source.py::isolated:function', root)

    def test_complete_archive_validation_and_exact_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.py').write_text('def target(): return 1\n')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            for codec, opener in [('gzip', gzip.open), ('xz', lzma.open)]:
                artifact = root / codec
                archive(index, artifact, codec)
                with self.assertRaisesRegex(ValueError, 'exact ID'):
                    source_archive(artifact, 'arget', root)
                self.assertEqual(source_archive(artifact, 'target', root),
                                 source_archive(artifact, 'a.py::target:function', root))
                with self.assertRaisesRegex(ValueError, 'offset'):
                    source_archive(artifact, 'a.py::target:function', root, offset=1)
                with opener(artifact, 'rt') as stream:
                    rows = [json.loads(line) for line in stream]
                with opener(artifact, 'wt') as stream:
                    stream.write(''.join(json.dumps(row) + '\n' for row in rows[:-1]))
                with self.assertRaisesRegex(ValueError, 'Incomplete'):
                    source_archive(artifact, 'a.py::target:function', root, limit=1)

    def test_long_line_budget_and_text_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.py').write_text('VALUE = "' + 'x' * 3000 + '"\nFLAG = "\\x1b"\n')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            artifact = root / 'graph.xz'
            archive(index, artifact, 'xz')
            with self.assertRaisesRegex(ValueError, 'one source line'):
                source_archive(artifact, 'a.py::module', root, budget_bytes=2048)
            page = source_archive(artifact, 'a.py::FLAG:assignment', root)
            page['source'] = '\x1b[31m'
            self.assertNotIn('\x1b', archive_source_text(page))
            self.assertIn('\\u001b', archive_source_text(page))
