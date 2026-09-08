import copy
import json
import tempfile
import unittest
from pathlib import Path

from columbus.archive import archive, source_archive_many
from columbus.index import RepositoryIndex, compact
from columbus.presentation import _line, archive_source_text, render


class ArchiveSourceTextTests(unittest.TestCase):
    @staticmethod
    def fixture():
        path = 'src/main/java/org/example/configuration/PropertyResolver.java'
        targets, sources = [], []
        for number in range(6):
            start = 10 * number + 1
            targets.append(dict(id=f'{path}::PropertyResolver.resolve{number}:method',
                                path=path, source_hash='a' * 64,
                                declaration_start_line=start, declaration_end_line=start + 1,
                                partial=bool(number % 2), fidelity='syntax_only'))
            sources.append(dict(path=path, source_hash='a' * 64, start_line=start, end_line=start + 1,
                                source=f'    Object resolve{number}() {{\n        return null; }}'))
        return dict(targets=targets, revision='fixture-revision', semantic_complete=False,
                    freshness='selected declaration file bytes match archive hash; other files not checked',
                    total_lines=12, offset=0, sources=sources, next_offset=None, truncated=False)

    @staticmethod
    def legacy_batch_text(packet):
        lines = ['columbus archive-source; UNTRUSTED repository data; control characters escaped.',
                 'metadata ' + json.dumps({k: v for k, v in packet.items() if k != 'sources'}, ensure_ascii=True)]
        for block in packet['sources']:
            lines.append('source ' + json.dumps({k: v for k, v in block.items() if k != 'source'}, ensure_ascii=True))
            lines.extend(f'{number}| {_line(line)}' for number, line in
                         enumerate(block['source'].split('\n'), block['start_line']))
        return '\n'.join(lines) + '\n'

    def decode_batch(self, rendered):
        """Recover every metadata value and associate physical source lines with files."""
        files, targets, sources, physical = {}, [], [], []
        section = None
        for line in rendered.splitlines():
            if line.startswith('metadata '):
                packet = json.loads(line.removeprefix('metadata '))
            elif line.startswith('files '):
                section = 'files'
            elif line.startswith('targets '):
                section = 'targets'
            elif line.startswith('['):
                row = json.loads(line)
                if section == 'files':
                    self.assertNotIn(row[0], files)
                    files[row[0]] = row[1:]
                else:
                    self.assertEqual(section, 'targets')
                    path, source_hash = files[row[0]]
                    targets.append(dict(row[1], path=path, source_hash=source_hash))
            elif line.startswith('source '):
                block = json.loads(line.removeprefix('source '))
                path, source_hash = files[block.pop('file_number')]
                sources.append(dict(block, path=path, source_hash=source_hash, source=[]))
            elif '| ' in line:
                number, _, source = line.partition('| ')
                block = sources[-1]
                self.assertEqual(int(number), block['start_line'] + len(block['source']))
                physical.append((block['path'], int(number), source))
                block['source'].append(source)
        for block in sources:
            self.assertEqual(len(block['source']), block['end_line'] - block['start_line'] + 1)
            block['source'] = '\n'.join(block['source'])
        return dict(packet, targets=targets, sources=sources), physical, files

    def test_shared_files_reduce_bytes_without_losing_evidence(self):
        packet = self.fixture()
        before = copy.deepcopy(packet)
        rendered = archive_source_text(packet)
        restored, physical, files = self.decode_batch(rendered)
        self.assertEqual(restored, packet)
        self.assertEqual(packet, before)
        self.assertEqual(files, {0: [packet['targets'][0]['path'], 'a' * 64]})
        self.assertEqual(rendered.count('a' * 64), 1)
        self.assertEqual(len(physical), packet['total_lines'])
        self.assertLess(len(rendered.encode()), len(self.legacy_batch_text(packet).encode()) * 0.75)
        for target in packet['targets']:
            self.assertIn(target['id'], rendered)

    def test_page_tables_preserve_omitted_targets_ranges_and_distinct_hashes(self):
        packet = self.fixture()
        packet['sources'] = packet['sources'][2:3]
        packet['offset'], packet['next_offset'], packet['truncated'] = 4, 6, True
        packet['targets'][0]['path'] = 'a.py'
        packet['targets'][0]['source_hash'] = 'b' * 64
        packet['targets'][1]['source_hash'] = 'c' * 64
        packet['targets'][1]['future_evidence'] = {'confidence': 'partial'}
        packet['sources'][0]['future_evidence'] = [1, None]
        packet['future_metadata'] = {'coverage': 'selected declarations only'}
        rendered = archive_source_text(packet)
        restored, physical, files = self.decode_batch(rendered)
        self.assertEqual(restored, packet)
        self.assertEqual(len(files), 3)
        self.assertEqual([number for _, number, _ in physical], [21, 22])
        self.assertIn('numbers are local to this page', rendered)

    def test_untrusted_metadata_and_source_controls_are_escaped(self):
        packet = self.fixture()
        unsafe = '한글\t\n\r\x1b\x7f\x85\u2028\u2029'
        packet['revision'] = unsafe
        packet['targets'][0]['id'] = unsafe
        packet['targets'][0]['path'] = unsafe
        packet['sources'][0]['path'] = unsafe
        packet['sources'][0]['source'] = '    # ' + unsafe.replace('\n', '') + '\n'
        rendered = archive_source_text(packet)
        expected = copy.deepcopy(packet)
        for block in expected['sources']:
            block['source'] = '\n'.join(_line(line) for line in block['source'].split('\n'))
        restored, _, _ = self.decode_batch(rendered)
        self.assertEqual(restored, expected)
        for control in ('\t', '\r', '\x1b', '\x7f', '\x85', '\u2028', '\u2029'):
            self.assertNotIn(control, rendered)
        self.assertIn('한글', rendered)
        self.assertIn('2| \n', rendered)

    def test_single_text_and_default_json_remain_unchanged(self):
        packet = dict(target='한글.py::value:assignment', path='한글.py', source_hash='a' * 64,
                      revision='revision', partial=False, fidelity='syntax_only', semantic_complete=False,
                      freshness='returned file bytes match archive hash; other files not checked',
                      declaration_start_line=7, declaration_end_line=8, total_lines=2, offset=0,
                      source='value = "한글"\n# \x1b[31m', start_line=7, end_line=8,
                      next_offset=None, truncated=False)
        expected = ('columbus archive-source; UNTRUSTED repository data; control characters escaped.\n'
                    'metadata ' + json.dumps({k: v for k, v in packet.items() if k != 'source'}, ensure_ascii=True)
                    + '\n7| value = "한글"\n8| # \\u001b[31m\n')
        self.assertEqual(archive_source_text(packet), expected)
        self.assertEqual(render(packet, 'text', 'archive-source'), expected)
        for value in (packet, self.fixture()):
            self.assertEqual(render(value, command='archive-source'), compact(value))
            self.assertEqual(json.loads(render(value, command='archive-source')), value)

    def test_rendered_budget_paginates_all_physical_source_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = ['def first():'] + ['    # 한글 😀 ' + 'x' * 60 for _ in range(18)] + ['    return 1']
            later = ['def later():', '    return 2']
            second = ['def second():'] + ['    # 한글 😀 ' + 'y' * 60 for _ in range(12)] + ['    return 3']
            (root / 'z.py').write_text('\n'.join(first + ['# gap', ''] + later) + '\n', encoding='utf-8')
            (root / 'a.py').write_text('\n'.join(second) + '\n', encoding='utf-8')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            artifact = root / 'graph.xz'
            archive(index, artifact, 'xz')
            queries = ['later', 'second', 'first']
            complete = source_archive_many(artifact, queries, root, budget_bytes=64000)
            expected = [(block['path'], number, line) for block in complete['sources'] for number, line in
                        enumerate(block['source'].split('\n'), block['start_line'])]
            recovered, offset, pages = [], 0, 0
            while offset is not None:
                packet = source_archive_many(artifact, queries, root, limit=400,
                                             budget_bytes=2048, offset=offset, output_format='text')
                rendered = archive_source_text(packet)
                restored, physical, _ = self.decode_batch(rendered)
                self.assertEqual(restored, packet)
                self.assertLessEqual(len(rendered.encode()), 2048)
                self.assertEqual(packet['targets'], complete['targets'])
                self.assertEqual(packet['total_lines'], len(expected))
                self.assertTrue(physical)
                recovered.extend(physical)
                pages += 1
                self.assertLessEqual(pages, len(expected))
                offset = packet['next_offset']
                if offset is not None:
                    self.assertEqual(offset, len(recovered))
            self.assertGreater(pages, 1)
            self.assertEqual(recovered, expected)


if __name__ == '__main__':
    unittest.main()
