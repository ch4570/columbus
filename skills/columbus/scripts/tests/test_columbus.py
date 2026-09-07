import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ENTRY = Path(__file__).resolve().parents[1]/"columbus.py"


class EntrypointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/"main.py"
        self.source.write_text("def original_name(): return 1\n")

    def call(self, command, *extra):
        return subprocess.run([sys.executable, str(ENTRY), command, "--repo", str(self.root), *extra],
                              capture_output=True, text=True)

    def test_query_syncs_new_and_changed_sources(self):
        first = self.call("search", "original_name")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)["hits"][0]["name"], "original_name")
        self.source.write_text("def changed_name(): return 2\n")
        second = self.call("search", "changed_name")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(second.stdout)["hits"][0]["name"], "changed_name")
        self.assertNotEqual(json.loads(first.stdout)["revision"], json.loads(second.stdout)["revision"])

    def test_sync_failure_stops_query(self):
        self.assertEqual(self.call("sync").returncode, 0)
        self.source.write_bytes(b'\xff\xfe\x80')
        failed = self.call("search", "original_name")
        self.assertEqual(failed.returncode, 2)
        self.assertEqual(failed.stdout, "")

    def test_context_budget_and_snapshot_opt_out(self):
        packed = self.call("context", "original_name", "--budget-bytes", "2048")
        self.assertEqual(packed.returncode, 0, packed.stderr)
        self.assertLessEqual(len(packed.stdout.encode()), 2048)
        self.source.write_text("def changed_name(): return 2\n")
        saved = self.call("search", "original_name", "--snapshot")
        self.assertEqual(saved.returncode, 0, saved.stderr)
        self.assertEqual(json.loads(saved.stdout)["hits"][0]["name"], "original_name")
        self.assertEqual(json.loads(saved.stdout)["freshness"], "index_snapshot")

    def test_cp1252_pipes_keep_utf8_lf_budgets_and_session_measurements(self):
        self.source.write_text('def original_name():\n    return "환불 😀"\n', encoding='utf-8', newline='\n')
        environment = {**os.environ, 'PYTHONIOENCODING': 'cp1252'}

        def run(*arguments):
            result = subprocess.run([sys.executable, str(ENTRY), *arguments],
                                    env=environment, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
            self.assertNotIn(b'\r\n', result.stdout)
            result.stdout.decode('utf-8')
            return result.stdout

        self.assertIn('Columbus —', run().decode('utf-8'))
        outputs = [run('--repo', str(self.root), 'explore', 'original_name', '--session',
                       'utf8-task', '--budget-bytes', '2048') for _ in range(3)]
        self.assertIn('환불 😀', outputs[0].decode('utf-8'))
        self.assertTrue(all(len(output) <= 2048 for output in outputs))
        log = self.root / '.columbus/sessions/utf8-task/queries.jsonl'
        rows = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
        self.assertEqual([row['output_bytes'] for row in rows], [len(output) for output in outputs])
        self.assertGreater(rows[0]['source_bytes'], 0)
        self.assertEqual(rows[-1]['source_bytes'], 0)
        stats = json.loads(run('--repo', str(self.root), 'stats', 'utf8-task', '--format', 'json'))
        self.assertEqual(stats['queries'], 3)
        self.assertEqual(stats['output_bytes'], sum(map(len, outputs)))


if __name__ == "__main__":
    unittest.main()
