"""Implementation candidates must retain declaration evidence and ambiguity."""
import json
from contextlib import redirect_stdout, redirect_stderr
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest

from columbus.index import RepositoryIndex


class ImplementationNavigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        (self.root / 'Flow.kt').write_text('''package demo
interface UseCase {
 fun perform(value: String)
}
class Alpha : UseCase {
 override fun perform(value: String) {}
 fun perform(value: Int) {}
}
class Beta : UseCase {
 override fun perform(value: String) {}
}
class Unrelated {
 fun perform(value: String) {}
}
''')
        self.index = RepositoryIndex(Path(self.temp.name) / 'index.sqlite')
        self.index.refresh(self.root)
        self.target = self.index.search('demo.UseCase.perform')['hits'][0]['id']

    def query(self, **kwargs):
        from columbus.navigation import implementations
        return implementations(self.index, self.target, **kwargs)

    def test_multiple_implementations_exclude_unrelated_and_wrong_overload(self):
        before = self.index.status()['edges']
        result = self.query()
        self.assertEqual({'demo.Alpha.perform', 'demo.Beta.perform'}, {i['qualname'] for i in result['items']})
        self.assertEqual([['String'], ['String']], [i['parameter_types'] for i in result['items']])
        self.assertTrue(all(i['relation'] == 'implementation_candidate' and i['inheritance'] for i in result['items']))
        self.assertFalse(result['semantic_complete'])
        self.assertFalse(result['runtime_verified'])
        self.assertEqual(before, self.index.status()['edges'])

    def test_cursor_delivers_every_candidate_once_and_binds_query_revision(self):
        first = self.query(limit=1)
        self.assertTrue(first['next_cursor'])
        second = self.query(limit=1, cursor=first['next_cursor'])
        self.assertEqual(2, len({i['id'] for p in [first, second] for i in p['items']}))
        self.assertIsNone(second['next_cursor'])
        (self.root / 'Other.kt').write_text('package demo\nclass Extra {}\n')
        self.index.refresh(self.root)
        with self.assertRaisesRegex(ValueError, 'revision|scope'):
            self.query(cursor=first['next_cursor'])

    def test_json_and_text_fit_full_byte_budget_and_disclose_candidate_semantics(self):
        from columbus.presentation import render
        for format_ in ['json', 'text']:
            result = self.query(budget_tokens=700, output_format=format_)
            rendered = render(result, format_)
            self.assertLessEqual(len(rendered.encode()), 2100)
            self.assertEqual(len(rendered.encode()), result['used_bytes'])
            self.assertIn('implementation_candidate', rendered)
            self.assertIn('runtime_verified', rendered)

    def test_same_short_parameter_name_in_other_package_is_not_a_match(self):
        (self.root / 'Api.kt').write_text('''package api
import first.Value
interface Port { fun handle(value: Value) }
''')
        (self.root / 'Impl.kt').write_text('''package impl
import api.Port
import second.Value
class Bad : Port { fun handle(value: Value) {} }
''')
        (self.root / 'First.kt').write_text('package first\nclass Value {}\n')
        (self.root / 'Second.kt').write_text('package second\nclass Value {}\n')
        self.index.refresh(self.root)
        self.target = self.index.search('api.Port.handle')['hits'][0]['id']
        self.assertEqual([], self.query()['items'])

    def test_cycle_is_bounded_and_invalid_cursor_or_limits_rejected(self):
        with sqlite3.connect(self.index.db) as c:
            base = self.index.search('demo.UseCase')['hits'][0]['id']
            child = self.index.search('demo.Alpha')['hits'][0]['id']
            c.execute('insert into edges values(?,?,?,?,?,?,?)', (base, child, 'inherits', 'heuristic', 'cycle fixture', 'Flow.kt', 1))
        self.assertEqual(2, len(self.query()['items']))
        for kwargs in [{'limit': 0}, {'hops': 0}, {'cursor': 'junk'}]:
            with self.assertRaises(ValueError):
                self.query(**kwargs)

    def test_non_overridable_target_is_rejected(self):
        for modifier in ['private', 'static', 'final']:
            with self.subTest(modifier=modifier):
                (self.root / 'Methods.java').write_text(
                    f'class Base {{ {modifier} void run() {{}} }}\n'
                    'class Child extends Base { public void run() {} }\n')
                self.index.refresh(self.root)
                self.target = self.index.search('Base.run')['hits'][0]['id']
                with self.assertRaisesRegex(ValueError, 'overrid'):
                    self.query()

    def test_annotation_text_is_not_a_declaration_modifier(self):
        (self.root / 'Methods.java').write_text('''
interface Port { void run(); }
class Impl implements Port {
 @Tag("private route static abstract") public void run() {}
}
''')
        self.index.refresh(self.root)
        self.target = self.index.search('Port.run')['hits'][0]['id']
        self.assertEqual(['Impl.run'], [i['qualname'] for i in self.query()['items']])

    def test_imported_nested_type_and_varargs_array_match(self):
        (self.root / 'Methods.java').write_text('''
import java.util.Map;
interface Port { void run(Map.Entry item, String... names); }
class Impl implements Port {
 public void run(java.util.Map.Entry item, String[] names) {}
}
''')
        self.index.refresh(self.root)
        self.target = self.index.search('Port.run')['hits'][0]['id']
        items = self.query()['items']
        self.assertEqual(['Impl.run'], [i['qualname'] for i in items])
        self.assertEqual('declared_parameter_types', items[0]['signature_match'])

    def test_legacy_method_metadata_requires_refresh(self):
        with sqlite3.connect(self.index.db) as conn:
            value = json.loads(conn.execute('select data from symbols where id=?', [self.target]).fetchone()[0])
            value.pop('declaration_modifiers', None)
            conn.execute('update symbols set data=? where id=?', [json.dumps(value), self.target])
        with self.assertRaisesRegex(ValueError, 'sync'):
            self.query()

    def test_java_package_private_method_excludes_other_package(self):
        (self.root / 'A.java').write_text('package p; public class A { void run() {} }\n')
        (self.root / 'B.java').write_text('package q; public class B extends p.A { public void run() {} }\n')
        (self.root / 'C.java').write_text('package p; public class C extends A { public void run() {} }\n')
        self.index.refresh(self.root)
        self.target = self.index.search('p.A.run')['hits'][0]['id']
        self.assertEqual(['p.C.run'], [i['qualname'] for i in self.query()['items']])

    def test_cli_implementation_and_summary_contracts(self):
        from columbus.cli import main
        for command in [['implementations', self.target, '--snapshot'], ['sync', '--summary']]:
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                status = main(['--repo', str(self.root), '--db', str(self.index.db), *command])
            self.assertEqual(0, status, err.getvalue())
            result = json.loads(out.getvalue())
            if command[0] == 'implementations':
                self.assertEqual(2, len(result['items']))
                self.assertLessEqual(len(out.getvalue().encode()), result['budget_bytes'])
            else:
                self.assertTrue(result['summary'])
                self.assertNotIn('inventory', result)
                self.assertIn('diagnostics_count', result)
                self.assertEqual(0, result['refresh']['parsed_files'])


if __name__ == '__main__':
    unittest.main()
