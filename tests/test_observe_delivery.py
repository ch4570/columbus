"""Delivery provenance must describe portable fixture inputs, not local caches."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('observe_delivery', ROOT / 'scripts/observe_delivery.py')
observe_delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observe_delivery)


class DeliveryFixtureTests(unittest.TestCase):
    def test_repeated_receipts_measure_complete_delivery_beyond_the_first_page(self):
        result = observe_delivery.observe_receipt_coverage(50)
        self.assertEqual({'json', 'text'}, {row['format'] for row in result['results']})
        for row in result['results']:
            self.assertEqual(50, row['complete_files'])
            self.assertEqual(0, row['duplicate_spans'])
            self.assertGreater(row['response_bytes'], 0)

    def test_current_and_preview_cache_files_never_enter_fixture_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = {'checkout.py': b'def checkout(): return 1\n', '.columbus.json': b'{}\n'}
            caches = {'.repoatlas/jvm-v2.sqlite': b'legacy index',
                      '.repoatlas/jvm-v2.sqlite-wal': b'legacy transaction',
                      '.columbus/index-v1.sqlite': b'new index',
                      '.git/config': b'local git configuration',
                      '__pycache__/checkout.pyc': b'compiled code'}
            for name, data in {**source, **caches}.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            self.assertEqual(observe_delivery.fixture_sources(root), source)
            self.assertEqual({name: (root / name).read_bytes() for name in caches}, caches)


if __name__ == '__main__':
    unittest.main()
