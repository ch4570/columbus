import json
from pathlib import Path
import tempfile
import unittest
from columbus.index import RepositoryIndex


class CallerPacketTests(unittest.TestCase):
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
            small = index.callers('target', budget_bytes=1024)
            self.assertLessEqual(len((json.dumps(small, separators=(',', ':'), ensure_ascii=False)+'\n').encode()), 1024)
            self.assertTrue(small['truncated'])
            self.assertEqual(2, small['matched_callers'])
            source.write_text(source.read_text(encoding='utf-8')+'# changed\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Stale source'):
                index.callers('target')

    def test_ambiguous_names_require_id(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'a.py').write_text('def target(): pass\n', encoding='utf-8')
            (root/'b.py').write_text('def target(): pass\n', encoding='utf-8')
            index = RepositoryIndex(root/'.columbus/index.sqlite')
            index.refresh(root)
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                index.callers('target')
