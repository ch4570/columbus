import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('observe', HERE / 'observe.py')
observe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observe)


class ObservationTests(unittest.TestCase):
    def test_usage_cache_is_subset_and_output_not_estimated(self):
        result = observe.parse_events([
            {'type':'item.completed','item':{'type':'command_execution','command':'rg name','exit_code':0,'aggregated_output':'환불\n'}},
            {'type':'turn.completed','usage':{'input_tokens':10000,'cached_input_tokens':7000,'output_tokens':500,'reasoning_output_tokens':100}}
        ])
        self.assertEqual(result['usage']['uncached_input_tokens'], 3000)
        self.assertEqual(result['usage']['output_tokens'], 500)
        self.assertEqual(result['command_count'], 1)
        self.assertEqual(result['command_output_bytes'], 7)

    def test_missing_usage_is_not_zero_and_bad_cache_is_rejected(self):
        self.assertIsNone(observe.parse_events([])['usage'])
        with self.assertRaises(ValueError):
            observe.parse_events([{'type':'turn.completed','usage':{'input_tokens':1,'cached_input_tokens':2,'output_tokens':0}}])
        with self.assertRaises(ValueError):
            observe.parse_events([{'type':'turn.completed','usage':{'input_tokens':True,'cached_input_tokens':0,'output_tokens':0}}])

    def test_source_grounding_rejects_wrong_location_or_fabricated_quote(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'guard.py').write_text("if output.exists():\n    raise ValueError('exists')\n")
            case = {'findings':[{'id':'guard','path':'guard.py','marker':'if output.exists():'}]}
            finding = {'id':'guard','path':'guard.py','start_line':1,'end_line':2,'quote':'if output.exists():','explanation':'reject existing output'}
            self.assertTrue(observe.grade({'findings':[finding]},case,root)['passed'])
            indented = root/'guard.py'
            indented.write_text("    if output.exists():\n        raise ValueError('exists')\n")
            dedented = {**finding, 'quote': "if output.exists():\n    raise ValueError('exists')"}
            self.assertTrue(observe.grade({'findings':[dedented]},case,root)['passed'])
            for update in ({'quote':'fabricated'}, {'start_line':2}, {'path':'elsewhere.py'}, {'end_line':100}, {'end_line':40}):
                self.assertFalse(observe.grade({'findings':[{**finding,**update}]},case,root)['passed'])

    def test_failed_or_incomplete_comparison_does_not_become_savings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            observe.dump(root/'manifest.json',{'case_ids':['one'],'cases_sha256':observe.sha((HERE/'cases.json').read_bytes())})
            common={'case':'one','repeat':1,'model_requested':'same-model','effort_requested':'high','return_code':0,'timed_out':False,'turn_failed':False,'source_unchanged':True,'quality':{'passed':True},'usage':{'input_tokens':100,'cached_input_tokens':20,'uncached_input_tokens':80,'output_tokens':10},'other_tool_types':[],'command_count':2,'command_output_bytes':1000,'elapsed_seconds':2}
            (root/'runtime').mkdir()
            observe.dump(root/'engine.json',{'files':{},'index':{'files':1,'symbols':1,'indexed_bytes':50}})
            observe.dump(root/'trials/baseline/result.json',{**common,'condition':'baseline'})
            self.assertEqual(observe.summary(root)['pairs'],[])
            observe.dump(root/'trials/atlas/result.json',{**common,'condition':'repoatlas','quality':{'passed':False}})
            self.assertFalse(observe.summary(root)['pairs'][0]['quality_gated'])
            observe.dump(root/'trials/atlas/result.json',{**common,'condition':'repoatlas','model_requested':'different-model'})
            self.assertFalse(observe.summary(root)['pairs'][0]['quality_gated'])
            observe.dump(root/'trials/atlas/result.json',{**common,'condition':'repoatlas'})
            self.assertTrue(observe.summary(root)['pairs'][0]['quality_gated'])
            observe.dump(root/'engine.json',{'files':{},'index':{'files':0,'symbols':0,'indexed_bytes':0}})
            self.assertFalse(observe.summary(root)['pairs'][0]['quality_gated'])
            observe.dump(root/'manifest.json',{'case_ids':['one'],'cases_sha256':'changed'})
            with self.assertRaises(ValueError):
                observe.summary(root)

    def test_empty_index_cannot_pass_preflight(self):
        self.assertFalse(observe.index_ready({'files':0,'symbols':0,'indexed_bytes':0}))
        self.assertFalse(observe.index_ready({'files':True,'symbols':10,'indexed_bytes':100}))
        self.assertTrue(observe.index_ready({'files':4,'symbols':20,'indexed_bytes':1000}))

    def test_real_fixture_and_catalog_markers_are_reproducible(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'run'
            first=observe.prepare(root)
            self.assertEqual(first['source_manifest'],observe.manifest(root/'repository'))
            with self.assertRaises(ValueError):
                observe.prepare(root)

    def test_published_engine_recreates_the_recorded_nonempty_index(self):
        published = json.loads((HERE/'results/2026-09-07/controlled.json').read_text())
        archive = HERE/'fixtures/repoatlas-engine-observed-0.4.0.zip'
        self.assertEqual(observe.sha(archive.read_bytes()), published['engine_fixture_sha256'])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/'run'
            observe.prepare(root)
            observe.freeze_engine(root, archive)
            self.assertEqual(observe.manifest(root/'runtime'), published['engine']['files'])
            index = json.loads((root/'engine.json').read_text())['index']
            self.assertTrue(observe.index_ready(index))
            self.assertEqual(index['files'], published['engine']['index']['files'])
            frozen = json.loads((root/'engine.json').read_text())
            self.assertTrue(observe.live_index_preflight(root, frozen)['passed'])
            with self.assertRaises(ValueError):
                observe.freeze_engine(root, archive)
            (root/'repository/.repoatlas/jvm-v2.sqlite').unlink()
            with patch.object(observe.subprocess, 'Popen') as model:
                with self.assertRaisesRegex(ValueError, 'Prebuilt index is missing'):
                    observe.trial(root, 'export-safety', 'repoatlas', model='unused', effort='high', repeat=1, timeout=5)
                model.assert_not_called()

    def test_engine_archive_cannot_escape_or_inject_unlisted_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root/'unsafe.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('atlas.py', 'raise AssertionError("must not execute")')
                output.writestr('../escape.py', 'bad')
            with self.assertRaisesRegex(ValueError, 'Engine archive'):
                observe.freeze_engine(root, archive)
            self.assertFalse((root/'escape.py').exists())


if __name__ == '__main__':
    unittest.main()
