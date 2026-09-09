"""Ranked search pages cover complete candidate sets within one bound snapshot."""
import base64
import json
from pathlib import Path
import tempfile
import unittest

from columbus.index import RepositoryIndex


class SearchPaginationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'repo'
        self.root.mkdir()
        self.index = RepositoryIndex(self.root / '.columbus/index.sqlite')

    def write(self, name, source):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding='utf-8')

    def pages(self, query, *, limit=7, **options):
        hits, cursors, cursor = [], set(), None
        while True:
            page = self.index.search(query, limit=limit, cursor=cursor, **options)
            self.assertLessEqual(len(page['hits']), limit)
            self.assertEqual(page['candidate_limit'], limit)
            self.assertIsInstance(page['cursor'], str)
            self.assertEqual(page['truncated'], page['next_cursor'] is not None)
            self.assertEqual(self.index.search(query, limit=limit, cursor=page['cursor'], **options), page)
            self.assertNotIn(page['cursor'], cursors)
            cursors.add(page['cursor'])
            hits.extend(page['hits'])
            cursor = page['next_cursor']
            if cursor is None:
                break
            self.assertTrue(page['hits'])
        self.assertEqual(len(hits), len({hit['id'] for hit in hits}))
        return hits

    @staticmethod
    def order(hit):
        rank = hit['retrieval']
        return (not rank['exact_name'], hit['kind'] == 'module', rank['bm25'], hit['id'])

    def test_more_than_150_fts_matches_are_stably_paged_without_duplicates(self):
        self.write('workers.py', '\n'.join(f'def worker_{number:03d}(): return "needle"' for number in range(230)))
        self.index.refresh(self.root)
        hits = self.pages('needle')
        self.assertEqual(len(hits), 231)
        self.assertEqual({hit['name'] for hit in hits if hit['kind'] == 'function'},
                         {f'worker_{number:03d}' for number in range(230)})
        self.assertEqual(hits, sorted(hits, key=self.order))
        self.assertEqual(hits[-1]['kind'], 'module')
        self.assertEqual(hits, self.pages('needle', limit=50))
        tied = [hit for hit in hits if hit['kind'] == 'function']
        self.assertEqual(len({hit['retrieval']['bm25'] for hit in tied}), 1)
        self.assertEqual([hit['id'] for hit in tied], sorted(hit['id'] for hit in tied))

    def test_more_than_51_exact_matches_outrank_fts(self):
        for number in range(70):
            self.write(f'pkg/entry_{number:02d}.py', 'def target(): return 1\n'
                       f'class Group{number:02d}:\n    class Owner:\n        def target(self): return 2\n')
        self.write('exact.py', 'class Owner:\n    def target(self): return 3\n')
        self.write('noise.py', 'def unrelated(): return "Owner target"\n')
        self.index.refresh(self.root)
        exact = self.pages('target', limit=9)
        exact_hits = [hit for hit in exact if hit['retrieval']['exact_name']]
        self.assertEqual(len(exact_hits), 141)
        self.assertEqual(exact[:141], exact_hits)
        self.assertTrue(all(hit['retrieval']['bm25'] == 0 for hit in exact_hits))
        qualified = self.pages('Owner.target', limit=6)
        self.assertEqual(qualified[0]['qualname'], 'Owner.target')
        self.assertTrue(qualified[0]['retrieval']['exact_name'])
        self.assertTrue(all('qualified_suffix' not in hit['retrieval'] for hit in qualified))
        self.assertEqual(qualified, sorted(qualified, key=self.order))
        self.assertEqual(qualified, self.pages('Owner.target', limit=50))

    def test_filters_unicode_and_existing_exact_ids_are_authoritative(self):
        self.write('left/a.py', 'def Café(): return "needle"\nclass Owner:\n    def Écrire(self): return 1\n')
        self.write('right/b.py', 'def café(): return "needle"\nclass Outer:\n    class Owner:\n        def Écrire(self): return 2\n')
        self.write('right/c.js', 'function café() { return "needle"; }\n')
        self.index.refresh(self.root)
        exact = self.pages('CAFÉ', limit=1)
        self.assertEqual(len([hit for hit in exact if hit['retrieval']['exact_name']]), 3)
        self.assertTrue(all(hit['retrieval']['exact_name'] for hit in exact[:3]))
        qualified = self.pages('Owner.ÉCRIRE', limit=1)
        self.assertEqual(qualified[0]['qualname'], 'Owner.Écrire')
        self.assertTrue(qualified[0]['retrieval']['exact_name'])
        self.assertIn('Outer.Owner.Écrire', [hit['qualname'] for hit in qualified])
        filtered = self.pages('needle', limit=1, path='right/*', language='python')
        self.assertTrue(filtered)
        self.assertTrue(all(hit['path'] == 'right/b.py' and hit['language'] == 'python' for hit in filtered))
        identifier = 'left/a.py::Café:function'
        page = self.index.search(identifier)
        self.assertEqual([hit['id'] for hit in page['hits']], [identifier])
        self.assertTrue(page['hits'][0]['retrieval']['exact_id'])
        self.assertIsNone(page['next_cursor'])
        for options in ({'path': 'right/*'}, {'language': 'javascript'}):
            empty = self.index.search(identifier, **options)
            self.assertEqual(empty['hits'], [])
            self.assertIsNone(empty['next_cursor'])
        self.assertEqual(self.pages('missing'), [])

    def test_cursor_binds_snapshot_repository_query_filters_and_internal_scope(self):
        self.write('a.py', 'def first(): return "needle"\ndef second(): return "needle"\n')
        self.index.refresh(self.root)
        page = self.index.search('needle', limit=1, path='*.py', language='python', cursor_scope='a' * 64)
        cursor = page['next_cursor']
        self.assertIsNotNone(cursor)
        for changes in ({'query': 'first'}, {'path': 'a.py'}, {'language': None}, {'cursor_scope': None},
                        {'cursor_scope': 'b' * 64}):
            options = dict(query='needle', path='*.py', language='python', cursor_scope='a' * 64)
            options.update(changes)
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, 'another revision'):
                self.index.search(**options, cursor=cursor)
        # Changing the page size does not change the query's position.
        later = self.index.search('needle', limit=50, path='*.py', language='python', cursor_scope='a' * 64, cursor=cursor)
        self.assertTrue(later['hits'])
        self.assertNotEqual(later['hits'][0]['id'], page['hits'][0]['id'])
        other = Path(self.temporary.name) / 'other'
        other.mkdir()
        (other / 'a.py').write_bytes((self.root / 'a.py').read_bytes())
        other_index = RepositoryIndex(other / '.columbus/index.sqlite')
        other_index.refresh(other)
        with self.assertRaisesRegex(ValueError, 'another revision'):
            other_index.search('needle', path='*.py', language='python', cursor_scope='a' * 64, cursor=cursor)
        self.write('a.py', 'def first(): return "needle changed"\ndef second(): return "needle"\n')
        self.index.refresh(self.root)
        with self.assertRaisesRegex(ValueError, 'another revision'):
            self.index.search('needle', path='*.py', language='python', cursor_scope='a' * 64, cursor=cursor)

    def test_malformed_and_nonfinite_cursors_are_rejected(self):
        self.write('a.py', 'def first(): return "needle"\ndef second(): return "needle"\n')
        self.index.refresh(self.root)
        original = self.index.search('needle', limit=1)['next_cursor']
        decoded = json.loads(base64.urlsafe_b64decode(original + '=' * (-len(original) % 4)))
        def token(value):
            return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')
        invalid = [None, [], {}, dict(decoded, version=True), dict(decoded, version=2),
                   dict(decoded, binding='bad'), dict(decoded, extra=1)]
        invalid += [dict(decoded, after=value) for value in (
            [], [1, 0, 0], [True, 0, 0, 'id'], [1, 2, 0, 'id'],
            [1, 0, True, 'id'], [1, 0, float('nan'), 'id'],
            [1, 0, float('-inf'), 'id'], [1, 0, -(10 ** 400), 'id'],
            [0, 0, -1.0, 'id'], [1, 0, 1.0, 'id'], [1, 0, 0, ''],
            [1, 0, 0, '\0'], [1, 0, 0, 'x' * 4097], [1, 0, 0, []])]
        for malformed in [False, 1, '', '!', 'a', 'x' * 32769, *[token(value) for value in invalid]]:
            with self.subTest(cursor=str(malformed)[:80]), self.assertRaises(ValueError):
                self.index.search('needle', cursor=malformed)
        duplicate = '{"version":1,"version":1,"binding":' + json.dumps(decoded['binding']) + ',"after":null}'
        with self.assertRaises(ValueError):
            self.index.search('needle', cursor=base64.urlsafe_b64encode(duplicate.encode()).decode().rstrip('='))
        for scope in ('', True, 'z', 'a' * 65):
            with self.assertRaisesRegex(ValueError, 'cursor_scope'):
                self.index.search('needle', cursor_scope=scope)


if __name__ == '__main__':
    unittest.main()
