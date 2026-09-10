"""CLI summaries retain checked freshness evidence without source path inventories."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from columbus.cli import main
from columbus.index import RepositoryIndex


class CLISummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        (self.root / "source.py").write_text("def value(): return 1\n")
        (self.root / "build.gradle").write_text("plugins {}\n")
        self.index = RepositoryIndex(Path(self.temp.name) / "index.sqlite")
        self.index.refresh(self.root)

    def call(self, *args):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            status = main(["--repo", str(self.root), "--db", str(self.index.db), *args])
        self.assertEqual(0, status, error.getvalue())
        return output.getvalue()

    def test_checked_summary_retains_stale_source_config_counts_and_reasons(self):
        (self.root / "source.py").write_text("def value(): return 2\n")
        (self.root / "new.py").write_text("def added(): return 3\n")
        (self.root / "build.gradle").write_text("plugins { id 'java' }\n")
        full = json.loads(self.call("status", "--check-files"))
        summary = json.loads(self.call("status", "--check-files", "--summary"))
        self.assertEqual("stale", summary["freshness"])
        self.assertEqual("content_hash_verified", summary["check"])
        self.assertEqual({"source.py", "new.py", "build.gradle"}, set(full["stale_paths"]))
        self.assertEqual(len(full["stale_paths"]), summary["stale_paths_count"])
        self.assertEqual(1, summary["stale_config_paths_count"])
        self.assertEqual(full["stale_reasons"], summary["stale_reasons"])
        self.assertIn("configuration_changed", summary["stale_reasons"])
        self.assertEqual(full["revision"], summary["revision"])
        for omitted in ("inventory", "stale_paths", "stale_config_paths", "diagnostics", "stale", "config_stale"):
            self.assertNotIn(omitted, summary)
        self.assertTrue(summary["inventory_omitted"])

    def test_clean_counts_are_distinct_from_an_unchecked_snapshot(self):
        checked = json.loads(self.call("status", "--verify-content", "--summary"))
        self.assertEqual("checked_clean", checked["freshness"])
        self.assertEqual(0, checked["stale_paths_count"])
        self.assertEqual(0, checked["stale_config_paths_count"])
        self.assertEqual([], checked["stale_reasons"])
        unchecked = json.loads(self.call("status", "--summary"))
        self.assertIn("not checked", unchecked["freshness"])
        for unknown in ("stale_paths_count", "stale_config_paths_count", "stale_reasons"):
            self.assertNotIn(unknown, unchecked)

    def test_sync_summary_keeps_refresh_counters_and_diagnostics_count(self):
        revision = self.index.status()["revision"]
        result = json.loads(self.call("sync", "--summary"))
        self.assertEqual(revision, result["revision"])
        self.assertEqual(0, result["refresh"]["parsed_files"])
        self.assertEqual(0, result["diagnostics_count"])
        self.assertNotIn("inventory", result)

    def test_resource_cli_snapshot_json_and_text_obey_complete_output_budgets(self):
        source = self.root / "Routes.java"
        source.write_text('''import org.springframework.web.bind.annotation.GetMapping;
class Routes {
    @GetMapping("/original/a") void first() {}
    @GetMapping("/original/b") void second() {}
}
''')
        self.index.refresh(self.root)
        source.write_text("class Routes {}\n")
        for format_ in ("json", "text"):
            with patch.object(RepositoryIndex, "refresh", side_effect=AssertionError("snapshot must not refresh")):
                output = self.call("resources", "original", "--snapshot", "--format", format_,
                                   "--budget-bytes", "4500", "--budget-tokens", "1200", "--limit", "1")
            self.assertLessEqual(len(output.encode()), 3600)
            self.assertIn("/original/", output)
            if format_ == "json":
                packet = json.loads(output)
                self.assertEqual(len(output.encode()), packet["used_bytes"])
                self.assertEqual("index_snapshot", packet["graph_freshness"])
                self.assertEqual(1, len(packet["items"]))
                self.assertIsNotNone(packet["next_cursor"])
                self.assertFalse(packet["runtime_verified"])
            else:
                self.assertIn("runtime_verified=false", output)
                self.assertIn("resolution=literal", output)
                self.assertIn("next_cursor=", output)

    def test_repository_runner_accepts_resource_and_implementation_commands(self):
        runner = Path(__file__).resolve().parents[4] / "run.py"
        if not runner.is_file():
            self.skipTest("Repository runner is not included inside an installed skill")
        result = subprocess.run([sys.executable, str(runner), "--help"], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        for command in ("resources", "implementations"):
            self.assertIn(command, result.stdout)
            attempt = subprocess.run([sys.executable, str(runner), "--repo", str(self.root), command],
                                     capture_output=True, text=True)
            self.assertEqual(2, attempt.returncode)
            self.assertNotIn("invalid choice", attempt.stderr)
            self.assertIn("Runtime setup is incomplete", attempt.stderr)
        self.assertFalse((self.root / ".columbus").exists())


if __name__ == "__main__":
    unittest.main()
