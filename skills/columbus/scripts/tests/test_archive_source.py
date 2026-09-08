import gzip
import io
import json
import lzma
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from columbus.archive import archive, source_archive
from columbus.cli import main
from columbus.index import RepositoryIndex, compact
from columbus.presentation import archive_source_text


class ArchiveSourceTests(unittest.TestCase):
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
