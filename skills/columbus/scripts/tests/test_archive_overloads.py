"""Opt-in declaration families must not turn ambiguous owners into source evidence."""
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from columbus.archive import archive, source_archive, source_archive_many
from columbus.cli import main
from columbus.index import RepositoryIndex, compact
from columbus.presentation import archive_source_text


class ArchiveOverloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'C.java').write_text(
            'package p;\nclass C {\n'
            '  C() {}\n  C(int x) {}\n'
            '  int read() {\n    // 한글\n    return 1;\n  }\n'
            '  int read(int x) {\n    return x;\n  }\n'
            '  int other() { return 2; }\n}\n', encoding='utf-8')
        (self.root / 'K.kt').write_text(
            'package p\nfun pick(): Int = 1\nfun pick(x: Int): Int = x\n'
            'fun String.ext(): Int = 1\nfun Int.ext(): Int = 2\n')
        self.index = RepositoryIndex(self.root / '.columbus/index.sqlite')

    def artifact(self, codec='gzip'):
        self.index.refresh(self.root)
        output = self.root / (codec + '.graph')
        archive(self.index, output, codec)
        return output

    @staticmethod
    def rows(packet):
        return [(b['path'], n, line) for b in packet['sources'] for n, line in
                enumerate(b['source'].split('\n'), b['start_line'])]

    def test_groups_keep_source_parity_exact_ids_and_global_pagination(self):
        for codec in ('gzip', 'xz'):
            artifact = self.artifact(codec)
            queries = ['C.read', 'p.pick', 'C.<init>', 'C.other']
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                source_archive_many(artifact, queries, self.root)
            packet = source_archive_many(artifact, queries, self.root, overloads=True)
            ids = [node['id'] for node in packet['targets']]
            self.assertEqual(len(ids), 7)
            expected = source_archive_many(artifact, ids, self.root)
            self.assertEqual(packet['targets'], expected['targets'])
            self.assertEqual(self.rows(packet), self.rows(expected))
            self.assertIn('not runtime dispatch', packet['selection'])
            # Exact identities and redundant aliases still select each declaration once.
            single = source_archive_many(artifact, [ids[0]], self.root, overloads=True)
            self.assertEqual([n['id'] for n in single['targets']], ids[:1])
            self.assertEqual(single['sources'][0]['source'], source_archive(artifact, ids[0], self.root)['source'])
            alias = source_archive_many(artifact, ['C.read', 'p.C.read', ids[0]], self.root, overloads=True)
            self.assertEqual(len(alias['targets']), 2)
            for fmt in ('json', 'text'):
                delivered, offset = [], 0
                while True:
                    page = source_archive_many(artifact, ['C.read'], self.root, overloads=True,
                                               limit=2, offset=offset, budget_bytes=2048, output_format=fmt)
                    output = archive_source_text(page) if fmt == 'text' else compact(page) + '\n'
                    self.assertLessEqual(len(output.encode('utf-8')), 2048)
                    delivered.extend(self.rows(page))
                    if page['next_offset'] is None:
                        break
                    self.assertGreater(page['next_offset'], offset)
                    offset = page['next_offset']
                self.assertEqual(delivered, self.rows(alias))
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(['archive-source', 'C.read', '--overloads', '--input', str(artifact),
                                       '--repo', str(self.root)]), 0)
            self.assertEqual(len(json.loads(output.getvalue())['targets']), 2)

    def test_different_files_owners_receivers_and_python_definitions_stay_ambiguous(self):
        (self.root / 'Other.java').write_text(
            'package q; class C { int read() { return 3; } }\n'
            'class Outer { class C { int read(int x) { return x; } } }\n')
        (self.root / 'P.py').write_text('def repeated(): return 1\ndef repeated(x): return x\n')
        artifact = self.artifact()
        for query in ('C.read', 'read', 'p.ext', 'P.repeated'):
            with self.subTest(query=query), self.assertRaisesRegex(ValueError, 'ambiguous'):
                source_archive_many(artifact, [query], self.root, overloads=True)
        valid = source_archive_many(artifact, ['p.C.read'], self.root, overloads=True)
        self.assertEqual(len(valid['targets']), 2)
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            source_archive_many(artifact, ['p.C.read', 'p.ext'], self.root, overloads=True)

    def test_duplicate_signatures_or_malformed_group_identity_are_rejected(self):
        artifact = self.artifact()
        with gzip.open(artifact, 'rt') as stream:
            rows = [json.loads(line) for line in stream]
        group = [row['data'] for row in rows if row['record'] == 'node'
                 and row['data'].get('qualname') == 'p.C.read']
        for key, value in (('parameter_types', group[0]['parameter_types']), ('parent_id', None),
                           ('receiver_type', None), ('local', True)):
            previous = group[1][key]
            group[1][key] = value
            changed = self.root / ('invalid-' + key)
            with gzip.open(changed, 'wt') as stream:
                stream.write(''.join(json.dumps(row) + '\n' for row in rows))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'ambiguous'):
                source_archive_many(changed, ['C.read'], self.root, overloads=True)
            group[1][key] = previous

    def test_validation_and_stale_later_file_are_not_skipped_for_early_page(self):
        artifact = self.artifact()
        (self.root / 'K.kt').write_text('package p\nfun pick(): Int = 99\n')
        with self.assertRaisesRegex(ValueError, 'Stale source'):
            source_archive_many(artifact, ['C.read', 'p.pick'], self.root, overloads=True, limit=1)
        with gzip.open(artifact, 'rt') as stream:
            rows = stream.readlines()
        damaged = self.root / 'damaged'
        with gzip.open(damaged, 'wt') as stream:
            stream.writelines(rows[:-1])
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            source_archive_many(damaged, ['C.read'], self.root, overloads=True, limit=1)
        for options in ({'overloads': 'yes'}, {'overloads': True, 'offset': -1}):
            with self.assertRaises(ValueError):
                source_archive_many(artifact, ['C.read'], self.root, **options)

    def test_group_and_combined_caps_reject_before_source_reads(self):
        methods = ['  int many(' + 'int' + '[]' * n + ' x) { return 1; }' for n in range(65)]
        methods += ['  int more(' + 'int' + '[]' * n + ' x) { return 2; }' for n in range(33)]
        (self.root / 'Large.java').write_text('class Large {\n' + '\n'.join(methods) + '\n}\n')
        artifact = self.artifact()
        with patch('columbus.sync_state.read_stable', side_effect=AssertionError('must reject before reading')):
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                source_archive_many(artifact, ['Large.many'], self.root, overloads=True)
        # A valid exact ID is still readable in a family that exceeds the group cap.
        exact = 'Large.java::Large.many:method(int)'
        page = source_archive_many(artifact, [exact], self.root, overloads=True)
        self.assertEqual([item['id'] for item in page['targets']], [exact])
        many_ids = ['Large.java::Large.many:method(' + 'int' + '[]' * n + ')' for n in range(33)]
        # 33 + 33 same-owner declarations exceed the combined 64-declaration limit.
        with gzip.open(artifact, 'rt') as stream:
            rows = [json.loads(line) for line in stream]
        removed = [row for row in rows if row['record'] == 'node'
                   and row['data'].get('qualname') == 'Large.many' and row['data']['id'] not in many_ids]
        rows = [row for row in rows if row not in removed]
        rows[-1]['data']['nodes'] -= len(removed)
        limited = self.root / 'limited.graph'
        with gzip.open(limited, 'wt') as stream:
            stream.write(''.join(json.dumps(row) + '\n' for row in rows))
        with patch('columbus.sync_state.read_stable', side_effect=AssertionError('must reject before reading')):
            with self.assertRaisesRegex(ValueError, 'At most 64'):
                source_archive_many(limited, ['Large.many', 'Large.more'], self.root, overloads=True)


if __name__ == '__main__':
    unittest.main()
