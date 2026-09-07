from contextlib import closing
import gzip
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from columbus.archive import archive, search_archive, neighbors_archive
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
            with closing(sqlite3.connect(index.db)) as conn:
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

    def test_source_free_qualified_suffix_outranks_substrings(self):
        with tempfile.TemporaryDirectory() as consumer:
            artifact = Path(consumer) / "graph.jsonl.gz"
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for package, name in [("a", "OtherLoader"), ("b", "Loader"), ("c", "Loader")]:
                    (root / (package + ".java")).write_text("package " + package + "; class " + name + " { void getResource() {} }")
                index = RepositoryIndex(root / ".columbus/index.sqlite")
                index.refresh(root)
                archive(index, artifact)
            self.assertFalse(root.exists())
            packet = search_archive(artifact, "Loader.getResource", limit=2)
            self.assertEqual([i["path"] for i in packet["items"]], ["b.java", "c.java"])
            self.assertTrue(packet["truncated"])
            exact = search_archive(artifact, "a.OtherLoader.getResource", limit=1)
            self.assertEqual(exact["items"][0]["path"], "a.java")
            self.assertEqual(list(Path(consumer).iterdir()), [artifact])

    def test_archive_relationships_survive_source_removal_and_enforce_caps(self):
        with tempfile.TemporaryDirectory() as consumer:
            artifact = Path(consumer) / "graph.jsonl.gz"
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "a.py").write_text("def leaf(): pass\ndef caller():\n    leaf()\n    caller()\ndef other(): caller()\n")
                index = RepositoryIndex(root / ".columbus/index.sqlite")
                index.refresh(root)
                caller = index.search("caller")["hits"][0]["id"]
                with index._read() as conn:
                    expected = [dict(r) for r in conn.execute("SELECT * FROM edges WHERE kind='calls' AND (source=? OR target=?) ORDER BY source,target,kind,path,line,confidence,evidence", (caller, caller))]
                archive(index, artifact)
            self.assertFalse(root.exists())
            before = artifact.read_bytes()
            full = neighbors_archive(artifact, caller, 'both', ['calls'])
            self.assertEqual(full['edges'], expected)
            self.assertFalse(full['truncated'])
            self.assertFalse(full['semantic_complete'])
            self.assertEqual(full['matched_edges'], 3)
            self.assertEqual(len([e for e in full['edges'] if e['source']==e['target']]), 1)
            limited = neighbors_archive(artifact, caller, 'both', ['calls'], limit=1, budget_bytes=2048)
            self.assertTrue(limited['truncated'])
            self.assertLessEqual(len((json.dumps(limited,separators=(',',':'))+'\n').encode()),2048)
            self.assertEqual({n['id'] for n in limited['nodes']}, {caller} | {e[k] for e in limited['edges'] for k in ['source','target']})
            for direction, field in [('out','source'),('in','target')]:
                result = neighbors_archive(artifact, caller, direction, ['calls'])
                self.assertEqual(result['edges'], [e for e in expected if e[field]==caller])
            with self.assertRaisesRegex(ValueError, 'Exact symbol ID'):
                neighbors_archive(artifact, 'caller')
            broken = Path(consumer) / 'broken.gz'
            with gzip.open(broken,'wb') as stream:
                stream.write(b'\n'.join(gzip.decompress(before).splitlines()[:-1])+b'\n')
            with self.assertRaisesRegex(ValueError,'Incomplete'):
                neighbors_archive(broken, caller, limit=1)
            self.assertEqual(artifact.read_bytes(), before)
            self.assertEqual(sorted(p.name for p in Path(consumer).iterdir()), ['broken.gz','graph.jsonl.gz'])
            from columbus import archive as archive_module
            original_rows = archive_module._validated_rows
            passes = []
            def changed_between_passes(raw):
                yield from original_rows(raw)
                passes.append(True)
                if len(passes) == 1:
                    with artifact.open('ab') as writer:
                        writer.write(b'\0')
            with patch.object(archive_module, '_validated_rows', side_effect=changed_between_passes):
                with self.assertRaisesRegex(ValueError, 'Archive changed'):
                    neighbors_archive(artifact, caller)


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
