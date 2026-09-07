import gzip
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from columbus.archive import archive, search_archive
from columbus.index import RepositoryIndex


class ArchiveTests(unittest.TestCase):
    def test_full_archive_exceeds_view_limits_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for batch in range(102):
                (root / f'many_{batch}.py').write_text(''.join(f'def f{i}(): return missing()\n' for i in range(batch*50, (batch+1)*50)))
            (root / 'imports.py').write_text('from external_dependency import helper\n')
            (root / 'bad.py').write_text('def broken(:\n')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            status = index.refresh(root)
            first = root / 'one.jsonl.gz'
            receipt = archive(index, first)
            second = root / 'two.jsonl.gz'
            archive(index, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with gzip.open(first, 'rt', encoding='utf-8') as stream:
                rows = [json.loads(line) for line in stream]
            self.assertEqual(rows[0]['record'], 'manifest')
            self.assertEqual(rows[-1]['record'], 'end')
            self.assertFalse(receipt['truncated'])
            self.assertGreater(receipt['nodes'], 5000)
            self.assertEqual(receipt['nodes'], status['symbols'])
            self.assertEqual(receipt['edges'], status['edges'])
            self.assertGreater(receipt['imports'], 0)
            self.assertEqual(receipt['imports'], sum(r['record']=='import' for r in rows))
            self.assertEqual(receipt['references'], status['references'])
            self.assertEqual(receipt['diagnostics'], len(status['diagnostics']))
            with sqlite3.connect(index.db) as conn:
                expected = {json.loads(row[0])['id']: json.loads(row[0]) for row in conn.execute('SELECT data FROM symbols')}
            actual = {r['data']['id']: r['data'] for r in rows if r['record'] == 'node'}
            self.assertEqual(actual, expected)
            packet = search_archive(first, 'f5099', budget_bytes=2048)
            self.assertEqual(packet['items'][0]['name'], 'f5099')
            self.assertEqual(packet['items'][0]['source_hash'], next(r['data']['hash'] for r in rows if r['record']=='file' and r['data']['path']==packet['items'][0]['path']))
            self.assertLessEqual(len((json.dumps(packet, ensure_ascii=False, separators=(',', ':'))+'\n').encode()), 2048)
            self.assertIn('source not checked', packet['freshness'])
            malformed = root / 'incomplete.gz'
            with gzip.open(malformed, 'wt') as stream:
                for row in rows[:-1]:
                    stream.write(json.dumps(row)+'\n')
            with self.assertRaisesRegex(ValueError, 'Incomplete archive'):
                search_archive(malformed, 'f5099')
            self.assertNotIn(str(root), gzip.decompress(first.read_bytes()).decode())
            with self.assertRaises(FileExistsError):
                archive(index, first)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_failed_archive_never_publishes_partial_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.py').write_text('def a(): pass\n')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            output = root / 'broken.jsonl.gz'
            before = set(root.iterdir())
            with patch('columbus.archive.decode_parse', side_effect=ValueError('damaged cache')):
                with self.assertRaisesRegex(ValueError, 'damaged cache'):
                    archive(index, output)
            self.assertEqual(set(root.iterdir()), before)
