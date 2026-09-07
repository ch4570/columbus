from contextlib import closing
import gzip
import lzma
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from columbus.archive import archive, search_archive, neighbors_archive
from columbus.index import RepositoryIndex


class ArchiveTests(unittest.TestCase):
    def test_search_text_preserves_ranked_evidence_and_rendered_budget(self):
        from columbus.presentation import render
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'calls.py').write_text('def target(): pass\n' + ''.join(f'def target_{i}(): pass\n' for i in range(30)), encoding='utf-8')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            rendered = []
            for codec in ['gzip', 'xz']:
                artifact = root / ('graph.' + codec)
                archive(index, artifact, compression=codec)
                expected = search_archive(artifact, 'target', limit=50, budget_bytes=64000)
                complete = search_archive(artifact, 'target', limit=50, budget_bytes=64000, output_format='text')
                self.assertEqual(complete, expected)
                packet = search_archive(artifact, 'target', limit=50, budget_bytes=2048, output_format='text')
                text = render(packet, 'text', 'archive-search')
                self.assertLessEqual(len(text.encode()), 2048)
                lines = text.splitlines()
                self.assertEqual(json.loads(lines[1][9:]), {k:v for k,v in packet.items() if k!='items'})
                self.assertEqual([json.loads(line) for line in lines[3:]], packet['items'])
                self.assertEqual(packet['items'], expected['items'][:len(packet['items'])])
                self.assertTrue(packet['truncated'])
                self.assertEqual(packet['items'][0]['name'], 'target')
                rendered.append(text)
                with self.assertRaisesRegex(ValueError, 'output_format'):
                    search_archive(artifact, 'target', output_format='invalid')
            self.assertEqual(*rendered)
            text = render(dict(complete, source_policy='bad\n\x1b\u2028data'), 'text', 'archive-search')
            self.assertNotIn('\x1b', text)
            self.assertNotIn('\u2028', text)

    def test_path_filter_precedes_counts_cursor_and_source_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'api.py').write_text('def target(): pass\n', encoding='utf-8')
            for folder in ['src', 'tests', 'UPPER']:
                (root / folder).mkdir()
                (root / folder / 'calls.py').write_text('from api import target\ndef call(): target(); target()\n', encoding='utf-8')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            target = index.search('target')['hits'][0]['id']
            artifact = root / 'graph.gz'
            archive(index, artifact)
            # Excluded source must not be read, even before a page is shortened.
            (root / 'tests/calls.py').unlink()
            for folder in ['src', 'UPPER']:
                first = neighbors_archive(artifact, target, 'in', ['calls'], limit=1, path=folder+'/*',
                                          repo=root, context_lines=0)
                self.assertEqual(first['matched_edges'], 2)
                self.assertEqual(first['next_offset'], 1)
                self.assertEqual(first['edges'][0]['path'], folder+'/calls.py')
                second = neighbors_archive(artifact, target, 'in', ['calls'], limit=1, offset=1,
                                           path=folder+'/*', repo=root, context_lines=0)
                self.assertIsNone(second['next_offset'])
                self.assertNotEqual(first['edges'][0]['evidence'], second['edges'][0]['evidence'])
                self.assertIn(target, {node['id'] for node in first['nodes']})
            empty = neighbors_archive(artifact, target, 'in', ['calls'], path='upper/*', repo=root, context_lines=0)
            self.assertEqual(empty['matched_edges'], 0)
            self.assertFalse(empty['truncated'])
            self.assertEqual(empty['call_context'], [])
            for pattern in ['', 1, 'x'*2049, '\0']:
                with self.assertRaisesRegex(ValueError, 'path must'):
                    neighbors_archive(artifact, target, path=pattern)

    def test_verified_call_context_merges_sites_and_rejects_stale_source(self):
        from columbus.presentation import render
        from columbus import sync_state
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'calls.py'
            content = '# coding: latin-1\r\ndef target(): pass\r\ndef outer():\r\n    def inner():\r\n        label = "caf\u00e9"\r\n        target(); target()\r\n        target()\r\n    return inner\r\n'
            source.write_bytes(content.encode('latin-1'))
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            target = index.search('target')['hits'][0]['id']
            for compression in ['gzip', 'xz']:
                artifact = root / ('graph.' + compression)
                archive(index, artifact, compression=compression)
                for fmt in ['json', 'text']:
                    with patch('columbus.sync_state.read_stable', wraps=sync_state.read_stable) as reader:
                        packet = neighbors_archive(artifact, target, 'in', ['calls'], repo=root,
                                                   context_lines=1, output_format=fmt)
                    self.assertEqual(reader.call_count, 1)
                    context, = packet['call_context']
                    self.assertEqual(context['call_lines'], [6, 6, 7])
                    self.assertEqual((context['start_line'], context['end_line']), (5, 7))
                    self.assertIn('caf\u00e9', context['source'])
                    self.assertNotIn('return inner', context['source'])
                    self.assertIn('returned source bytes match', packet['context_freshness'])
                    output = render(packet, fmt, 'archive-neighbors') + ('\n' if fmt == 'json' else '')
                    self.assertLessEqual(len(output.encode()), 6000)
                source.write_bytes(content.replace('caf\u00e9', 'test').encode('latin-1'))
                with self.assertRaisesRegex(ValueError, 'Stale source'):
                    neighbors_archive(artifact, target, 'in', ['calls'], repo=root, context_lines=0)
                self.assertEqual(len(neighbors_archive(artifact, target, 'in', ['calls'])['edges']), 3)
                source.write_bytes(content.encode('latin-1'))
            for kwargs in [{'context_lines': -1, 'repo': root}, {'context_lines': 41, 'repo': root},
                           {'context_lines': True, 'repo': root}, {'context_lines': 0}]:
                with self.assertRaisesRegex(ValueError, 'context-lines'):
                    neighbors_archive(artifact, target, 'in', ['calls'], **kwargs)
            with self.assertRaisesRegex(ValueError, 'context-lines'):
                neighbors_archive(artifact, target, repo=root, context_lines=1)
            malicious = root / 'outside.gz'
            with lzma.open(artifact, 'rt', encoding='utf-8') as stream:
                rows = [json.loads(line) for line in stream]
            for row in rows:
                if row['data'].get('path') == 'calls.py':
                    row['data']['path'] = '../outside.py'
            with gzip.open(malicious, 'wt', encoding='utf-8') as stream:
                stream.writelines(json.dumps(row) + '\n' for row in rows)
            with self.assertRaisesRegex(ValueError, 'inside the indexed repository'):
                neighbors_archive(malicious, target, 'in', ['calls'], repo=root, context_lines=0)

    def test_call_context_budget_pagination_retains_every_site(self):
        from columbus.presentation import render
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'calls.py'
            source.write_text('def target(): pass\n' + ''.join(f'def c{i}(): target(); target()\n' for i in range(9)), encoding='utf-8')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            target = index.search('target')['hits'][0]['id']
            artifact = root / 'graph.gz'
            archive(index, artifact)
            for fmt in ['json', 'text']:
                offset, edges, sites = 0, [], []
                while offset is not None:
                    packet = neighbors_archive(artifact, target, 'in', ['calls'], budget_bytes=3000,
                                               offset=offset, repo=root, context_lines=0, output_format=fmt)
                    output = render(packet, fmt, 'archive-neighbors') + ('\n' if fmt == 'json' else '')
                    self.assertLessEqual(len(output.encode()), 3000)
                    self.assertTrue(packet['edges'])
                    for context in packet['call_context']:
                        sites.extend((context['source_id'], line) for line in context['call_lines'])
                        self.assertEqual(context['source'], source.read_text().splitlines()[context['start_line']-1])
                    edges.extend(packet['edges'])
                    if packet['next_offset'] is not None:
                        self.assertGreater(packet['next_offset'], offset)
                    offset = packet['next_offset']
                self.assertEqual(sorted(sites), sorted((e['source'], e['line']) for e in edges))
                self.assertEqual(len(edges), 18)

    def test_xz_roundtrip_source_free_queries_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'demo.py'
            source.write_text('def target(): pass\ndef entry(): target(); target()\n')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            gz, xz, again = root / 'a.gz', root / 'b.data', root / 'c.xz'
            archive(index, gz)
            receipt = archive(index, xz, compression='xz')
            archive(index, again, compression='xz')
            self.assertEqual(receipt['format'], 'columbus-graph-jsonl-xz-v1')
            self.assertEqual(xz.read_bytes(), again.read_bytes())
            self.assertEqual(gzip.decompress(gz.read_bytes()), lzma.decompress(xz.read_bytes()))
            with self.assertRaises(FileExistsError):
                archive(index, xz, compression='xz')
            source.unlink()
            index.db.unlink()
            self.assertEqual(search_archive(gz, 'target'), search_archive(xz, 'target'))
            target = 'demo.py::target:function'
            expected = neighbors_archive(gz, target, direction='in', kinds=['calls'])
            self.assertEqual(expected, neighbors_archive(xz, target, direction='in', kinds=['calls']))
            self.assertEqual(len(expected['edges']), 2)
            original = xz.read_bytes()
            self.assertEqual(xz.read_bytes(), original)
            xz.write_bytes(original[:-8])
            for query in [lambda: search_archive(xz, 'target'), lambda: neighbors_archive(xz, target)]:
                with self.assertRaises(ValueError):
                    query()

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
            pages, offset = [], 0
            while offset is not None:
                page = neighbors_archive(artifact, caller, 'both', ['calls'], limit=1, offset=offset)
                pages.extend(page['edges'])
                offset = page['next_offset']
            self.assertEqual(pages, expected)
            self.assertEqual(neighbors_archive(artifact, caller, offset=999)['edges'], [])
            with self.assertRaisesRegex(ValueError, 'offset'):
                neighbors_archive(artifact, caller, offset=-1)
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


    def test_archive_pagination_crosses_edge_and_byte_caps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'many.py').write_text('def target(): pass\n' + ''.join(f'def caller_{i}(): target()\n' for i in range(65)))
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            target = index.search('target')['hits'][0]['id']
            artifact = root / 'graph.gz'
            archive(index, artifact)
            offset, edges, pages = 0, [], 0
            while offset is not None:
                page = neighbors_archive(artifact, target, 'in', ['calls'], budget_bytes=2048, offset=offset)
                self.assertLessEqual(len((json.dumps(page,separators=(',',':'))+'\n').encode()),2048)
                self.assertEqual(page['matched_edges'],65)
                self.assertTrue(page['edges'])
                if page['next_offset'] is not None:
                    self.assertGreater(page['next_offset'],offset)
                offset = page['next_offset']
                edges.extend(page['edges'])
                pages += 1
                self.assertLessEqual(pages,65)
            self.assertEqual(len(edges),65)
            self.assertEqual(len({e['source'] for e in edges}),65)
            self.assertGreater(pages,2)

    def test_text_pages_preserve_evidence_and_fit_rendered_budget(self):
        from columbus.presentation import archive_neighbors_text
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'many.py').write_text('def target(): pass\n' + ''.join(
                f'def caller_{i}(): target(); target()\n' for i in range(12)), encoding='utf-8')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            target = index.search('target')['hits'][0]['id']
            artifact = root / 'graph.xz'
            archive(index, artifact, compression='xz')
            expected = neighbors_archive(artifact, target, 'in', ['calls'], budget_bytes=64000)
            offset, edges = 0, []
            while offset is not None:
                packet = neighbors_archive(artifact, target, 'in', ['calls'], budget_bytes=3000,
                                           offset=offset, output_format='text')
                rendered = archive_neighbors_text(packet)
                self.assertLessEqual(len(rendered.encode()), 3000)
                files, nodes, decoded_edges = {}, {}, []
                section = None
                for line in rendered.splitlines():
                    if line.startswith(('files ', 'nodes ', 'edges ')):
                        section = line.split()[0]
                    elif line.startswith('metadata '):
                        self.assertEqual(json.loads(line[9:]), {k:v for k,v in packet.items() if k not in {'nodes','edges'}})
                    elif line.startswith('['):
                        row = json.loads(line)
                        if section == 'files':
                            files[row[0]] = row[1:]
                        elif section == 'nodes':
                            path, digest = files[row[1]]
                            nodes[row[0]] = dict(row[2], path=path, source_hash=digest)
                        else:
                            decoded_edges.append(dict(row[3], source=nodes[row[0]]['id'], target=nodes[row[1]]['id'], path=files[row[2]][0]))
                self.assertEqual(list(nodes.values()), packet['nodes'])
                self.assertEqual(decoded_edges, packet['edges'])
                edges.extend(decoded_edges)
                next_offset = packet['next_offset']
                if next_offset is not None:
                    self.assertEqual(next_offset, offset + len(decoded_edges))
                offset = next_offset
            self.assertEqual(edges, expected['edges'])
            self.assertEqual(len(edges), 24)
            adversarial = dict(expected, source_policy='bad\n\x1b[31m\u2028data')
            rendered = archive_neighbors_text(adversarial)
            self.assertNotIn('\x1b', rendered)
            self.assertNotIn('\u2028', rendered)
            with self.assertRaisesRegex(ValueError, 'output_format'):
                neighbors_archive(artifact, target, output_format='invalid')

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
