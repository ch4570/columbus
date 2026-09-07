import json
from pathlib import Path
import tempfile
import unittest
from columbus.index import RepositoryIndex
from columbus.presentation import render


class CallerPacketTests(unittest.TestCase):
    def test_same_line_calls_keep_distinct_utf8_positions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'demo.py').write_text('def target(value): return value\ndef caller(): é = target(1); return target(2)\n')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            item, = index.callers('target')['items']
            self.assertEqual(item['call_sites'], 2)
            edges = index.neighbors('target', direction='in', kinds=['calls'])['edges']
            self.assertEqual(len(edges), 2)
            spans = [json.loads(edge['evidence']) for edge in edges]
            self.assertEqual(len({span['callee_span']['col_offset'] for span in spans}), 2)
            line = (root / 'demo.py').read_text().splitlines()[1].encode()
            for evidence in spans:
                span = evidence['callee_span']
                self.assertEqual(line[span['col_offset']:span['end_col_offset']], b'target')
                self.assertEqual(evidence['column_unit'], 'utf8_bytes')

    def test_filtered_context_counts_and_hash_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'prod').mkdir()
            (root / 'tests').mkdir()
            (root / 'target.py').write_text('def target(): pass\n')
            source = 'from target import target\ndef use(flag):\n    if flag:\n        x = 1\n        y = 2\n        target()\n        z = 3\n        target()\n'
            (root / 'prod/a.py').write_text(source)
            (root / 'tests/a.py').write_text(source)
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            (root / 'tests/a.py').write_text('# stale excluded caller\n')
            packet = index.callers('target.py::target:function', path='prod/*', context_lines=40, limit=1)
            self.assertEqual(packet['matched_callers'], 1)
            self.assertFalse(packet['truncated'])
            item, = packet['items']
            self.assertEqual((item['start_line'], item['end_line']), (2, 8))
            self.assertEqual(item['call_sites'], 2)
            self.assertIn('if flag:', item['source'])
            one, = index.callers('target.py::target:function', path='prod/*', context_lines=0)['items']
            self.assertEqual(one['start_line'], one['end_line'])
            self.assertEqual(index.callers('target.py::target:function', path='absent/*')['matched_callers'], 0)
            with self.assertRaisesRegex(ValueError, 'Stale source'):
                index.callers('target.py::target:function', context_lines=40)
            for invalid in [-1, 41, True, 1.5]:
                with self.assertRaises(ValueError):
                    index.callers('target.py::target:function', context_lines=invalid)

    def test_nested_ownership_evidence_budget_and_stale_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'x.py'
            source.write_text('def target(): pass\ndef outer():\n    def inner():\n        target()\n    inner()\ndef other():\n    target()\n', encoding='utf-8')
            source.write_text(source.read_text(encoding='utf-8').replace('target()\n', 'target() # ' + 'é' * 300 + '\n'), encoding='utf-8')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            packet = index.callers('target')
            self.assertEqual({'outer.inner', 'other'}, {i['qualname'] for i in packet['items']})
            self.assertFalse(packet['semantic_complete'])
            self.assertFalse(packet['truncated'])
            for item in packet['items']:
                self.assertIn('target()', item['source'])
                self.assertTrue(item['confidence'])
                self.assertEqual(64, len(item['source_hash']))
            text_packet = index.callers('target', output_format='text')
            displayed = render(text_packet, 'text', 'callers')
            self.assertEqual(packet, text_packet)
            self.assertIn('semantic_complete=false', displayed)
            for item in text_packet['items']:
                self.assertIn(f"{item['call_line']}| ", displayed)
                self.assertIn(item['source_hash'], displayed)
                self.assertIn(f"call_sites={item['call_sites']}", displayed)
            limited_text = index.callers('target', budget_bytes=1024, output_format='text')
            self.assertLessEqual(len(render(limited_text, 'text', 'callers').encode()), 1024)
            self.assertTrue(limited_text['truncated'])
            small = index.callers('target', budget_bytes=1024)
            self.assertLessEqual(len((json.dumps(small, separators=(',', ':'), ensure_ascii=False)+'\n').encode()), 1024)
            self.assertTrue(small['truncated'])
            self.assertEqual(2, small['matched_callers'])
            source.write_text(source.read_text(encoding='utf-8')+'# changed\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Stale source'):
                index.callers('target')

    def test_unicode_text_separators_do_not_replace_call_site_lines(self):
        for separator in ('\u0085', '\u2028', '\u2029', '\x0b', '\x0c'):
            for newline in ('\n', '\r\n', '\r'):
                with self.subTest(separator=repr(separator), newline=repr(newline)), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    source = newline.join(['def target(): pass', 'def caller():',
                                           f'    value = "a{separator}b"', '    target()', ''])
                    (root/'x.py').write_bytes(source.encode())
                    index = RepositoryIndex(root/'.columbus/index.sqlite')
                    index.refresh(root)
                    packet = index.callers('target', output_format='text')
                    item, = packet['items']
                    self.assertEqual((3, 4, 4), (item['start_line'], item['end_line'], item['call_line']))
                    self.assertEqual(f'    value = "a{separator}b"\n    target()', item['source'])
                    self.assertIn('4|     target()', render(packet, 'text', 'callers'))
                    symbol = index.symbol('caller')
                    self.assertIn(separator, symbol['source'])
                    self.assertIn('    target()', symbol['source'])
                    self.assertEqual(4, symbol['excerpt_end_line'])

    def test_jvm_unicode_separator_keeps_parser_line_coordinates(self):
        sources = {
            'java': 'class C {\n static void target() {}\n static void caller() {\n  String value="a\u2028b";\n  target();\n }\n}\n',
            'kt': 'fun target() {}\nfun caller() {\n val value="a\u2028b"\n target()\n}\n',
        }
        for language, source in sources.items():
            for newline in ('\n', '\r\n'):
                with self.subTest(language=language, newline=repr(newline)), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    (root/('C.'+language)).write_bytes(source.replace('\n', newline).encode())
                    index = RepositoryIndex(root/'.columbus/index.sqlite')
                    index.refresh(root)
                    item, = index.callers('target')['items']
                    self.assertIn('\u2028', item['source'])
                    self.assertIn('target()', item['source'].split('\n')[item['call_line']-item['start_line']])

    def test_ambiguous_names_require_id(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'a.py').write_text('def target(): pass\n', encoding='utf-8')
            (root/'b.py').write_text('def target(): pass\n', encoding='utf-8')
            index = RepositoryIndex(root/'.columbus/index.sqlite')
            index.refresh(root)
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                index.callers('target')
