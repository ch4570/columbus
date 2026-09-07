import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from columbus.cli import main
from columbus.index import RepositoryIndex
from columbus.parser import parse_source, resolve_files
from columbus.presentation import text_output


class ReceiverCandidatesTests(unittest.TestCase):
    def test_runtime_counterexamples_remain_unresolved(self):
        base = "class C:\n    def helper(self): pass\n    def run(self):\n        BODY\n"
        for body, extra, expected in [
            ('self.helper()', '', True),
            ('self = object(); self.helper()', '', False),
            ('self.helper = lambda: None; self.helper()', '', False),
            ('setattr(self, "helper", lambda: None); self.helper()', '', False),
            ('self.__dict__["helper"] = lambda: None; self.helper()', '', False),
            ('self.helper()', 'class D(C):\n    def helper(self): pass\n', False),
            ('def inner(): self.helper()\n        inner()', '', True),
        ]:
            with self.subTest(body=body, extra=extra):
                parsed = parse_source('case.py', base.replace('BODY', body) + extra, 'case')
                edges = resolve_files([parsed])
                refs = [r for r in parsed['references'] if r['name'] == 'self.helper']
                self.assertEqual(1, len(refs))
                self.assertFalse(refs[0]['resolved'])
                self.assertEqual(expected, bool(refs[0].get('retrieval_candidates')))
                self.assertFalse(any(e['evidence'] == 'self.helper' for e in edges))

    def test_decorators_and_static_receiver(self):
        for target_decorator, source_decorator, expected in [
            ('', '', True), ('    @staticmethod\n', '', True),
            ('    @replace\n', '', False), ('', '    @staticmethod\n', False),
        ]:
            with self.subTest(target=target_decorator, source=source_decorator):
                source = ('class C:\n' + target_decorator + '    def helper(self): pass\n'
                          + source_decorator + '    def run(self): self.helper()\n')
                parsed = parse_source('case.py', source, 'case')
                resolve_files([parsed])
                ref = next(r for r in parsed['references'] if r['name'] == 'self.helper')
                self.assertEqual(expected, bool(ref.get('retrieval_candidates')))
                self.assertFalse(ref['resolved'])

    def test_opt_in_hops_persistence_bounds_and_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'repo'
            root.mkdir()
            source = root / 'case.py'
            source.write_text('def leaf(): pass\ndef read(): leaf()\nclass C:\n'
                              '    @staticmethod\n    def helper(): read()\n'
                              '    def run(self): self.helper()\n')
            db = Path(tmp) / 'index.sqlite'
            index = RepositoryIndex(db)
            index.refresh(root)
            run = 'case.py::C.run:method'
            leaf = 'case.py::leaf:function'
            self.assertEqual([], index.neighbors(run, direction='out', hops=3, kinds=['calls'])['edges'])
            result = index.neighbors(run, direction='out', hops=3, kinds=['calls'], include_candidates=True)
            self.assertIn(leaf, [n['id'] for n in result['nodes']])
            self.assertEqual(['candidate_calls', 'calls', 'calls'], [e['kind'] for e in result['edges']])
            self.assertIn('not resolved calls', text_output(result, 'neighbors'))
            self.assertEqual(result, RepositoryIndex(db).neighbors(run, direction='out', hops=3,
                             kinds=['calls'], include_candidates=True))
            reverse = index.neighbors(leaf, direction='in', hops=3, kinds=['calls'], include_candidates=True)
            self.assertIn(run, [n['id'] for n in reverse['nodes']])
            self.assertTrue(index.neighbors(run, limit=1, include_candidates=True)['truncated'])
            self.assertFalse(index.neighbors(run, kinds=['inherits'], include_candidates=True)['edges'])
            self.assertFalse(any(e['kind'] == 'candidate_calls' for e in index.graph()['edges']))
            for command, center in [('neighbors', run), ('impact', leaf)]:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = main([command, center, '--repo', str(root), '--db', str(db),
                                 '--snapshot', '--include-candidates', '--hops', '3', '--format', 'json'])
                self.assertEqual(0, code)
                self.assertTrue(any(e['kind'] == 'candidate_calls' for e in json.loads(output.getvalue())['edges']))
            source.write_text(source.read_text().replace('self.helper()', 'self = object(); self.helper()'))
            index.refresh(root)
            self.assertFalse(index.neighbors(run, direction='out', kinds=['calls'], include_candidates=True)['edges'])
