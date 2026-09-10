from contextlib import closing, contextmanager
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from columbus import index as index_module
from columbus.index import RepositoryIndex, compact
from columbus.parse_cache import decode_parse_cache
from columbus.sync_state import SnapshotChanged


class RefreshFastPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        self.index = RepositoryIndex(self.base / "index.sqlite")

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def seed(self):
        self.write("one.py", "def one(): return 1\n")
        self.write("two.py", "from one import one\ndef two(): return one()\n")
        return self.index.refresh(self.root, fast=True)

    @contextmanager
    def forbid_cached_parse_reads(self):
        connect = sqlite3.connect
        reads = []

        def guarded_connect(*args, **kwargs):
            conn = connect(*args, **kwargs)

            def authorize(action, table, column, database, trigger):
                if action == sqlite3.SQLITE_READ and table == "files" and column == "parsed":
                    reads.append((table, column))
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK

            conn.set_authorizer(authorize)
            return conn

        with patch.object(index_module.sqlite3, "connect", side_effect=guarded_connect):
            yield
        self.assertEqual(reads, [], "unchanged refresh fetched cached parse bodies")

    def assert_summary_equal(self, first, second):
        for key in ("diagnostics", "references", "resolved_references", "unresolved_references",
                    "files", "symbols", "edges", "indexed_bytes"):
            self.assertEqual(first[key], second[key], key)

    def test_unchanged_fast_refresh_never_materializes_cached_parse_bodies(self):
        first = self.seed()
        with self.forbid_cached_parse_reads(), patch.object(
                index_module, "read_stable", side_effect=AssertionError("source body read")):
            second = self.index.refresh(self.root, fast=True)
        self.assert_summary_equal(first, second)
        self.assertEqual(first["revision"], second["revision"])
        self.assertEqual(second["refresh"]["metadata_reused_files"], 2)
        self.assertEqual(second["refresh"]["hashed_files"], 0)
        self.assertFalse(second["refresh"]["global_relink"])

    def test_full_hash_and_identical_touched_file_also_reuse_summary(self):
        first = self.seed()
        with self.forbid_cached_parse_reads():
            full = self.index.refresh(self.root)
        self.assertEqual(full["refresh"]["hashed_files"], 2)
        self.assertEqual(full["freshness"], "content_hash_verified")
        self.assert_summary_equal(first, full)
        source = self.root / "one.py"
        stamp = source.stat().st_mtime_ns + 10_000_000
        os.utime(source, ns=(stamp, stamp))
        with self.forbid_cached_parse_reads():
            touched = self.index.refresh(self.root, fast=True)
            unchanged = self.index.refresh(self.root, fast=True)
        self.assertEqual(touched["refresh"]["hashed_files"], 1)
        self.assertEqual(unchanged["refresh"]["hashed_files"], 0)
        self.assert_summary_equal(first, touched)
        self.assertEqual(first["revision"], touched["revision"])

    def test_unchanged_parse_diagnostics_still_fail_strict_refresh(self):
        self.seed()
        self.write("broken.py", "def broken(:\n")
        first = self.index.refresh(self.root, fast=True)
        self.assertTrue(first["diagnostics"])
        with self.forbid_cached_parse_reads():
            second = self.index.refresh(self.root, fast=True)
            before = self.index.status()
            with self.assertRaisesRegex(ValueError, "Incomplete parse"):
                self.index.refresh(self.root, fast=True, require_complete=True)
            self.assertEqual(before, self.index.status())
        self.assert_summary_equal(first, second)

    def test_excluded_file_diagnostics_follow_current_discovery(self):
        self.seed()
        self.write("broken.py", "def broken(:\n")
        old_large = self.write("old_large.py", "#" * 1_000_001)
        first = self.index.refresh(self.root, fast=True)
        parse_diagnostics = [d for d in first["diagnostics"] if d["path"] == "broken.py"]
        old_large.unlink()
        self.write("new_large.py", "#" * 1_000_001)
        with self.forbid_cached_parse_reads():
            second = self.index.refresh(self.root, fast=True)
        self.assertEqual(second["diagnostics"], [
            {"path": "new_large.py", "message": "excluded: file exceeds 1 MB"}, *parse_diagnostics])
        self.assertFalse(second["refresh"]["global_relink"])
        self.assertEqual(first["revision"], second["revision"])

    def test_missing_cached_summary_is_reconstructed_from_parse_facts(self):
        first = self.seed()
        with closing(sqlite3.connect(self.index.db)) as conn, conn:
            conn.execute("DELETE FROM metadata WHERE key='references'")
        second = self.index.refresh(self.root, fast=True)
        self.assert_summary_equal(first, second)
        self.assertEqual(first["revision"], second["revision"])
        self.assertFalse(second["refresh"]["global_relink"])

    def test_compressed_and_legacy_facts_support_queries_and_relink_after_reopen(self):
        first = self.seed()
        with closing(sqlite3.connect(self.index.db)) as conn, conn:
            rows = conn.execute("SELECT path,parsed FROM files ORDER BY path").fetchall()
            self.assertTrue(all(isinstance(row[1], bytes) for row in rows))
            path, encoded = rows[0]
            conn.execute("UPDATE files SET parsed=? WHERE path=?", (compact(decode_parse_cache(encoded)), path))
        self.index = RepositoryIndex(self.index.db)
        with self.forbid_cached_parse_reads():
            self.assert_summary_equal(first, self.index.refresh(self.root, fast=True))
        self.assertIn("return 1", self.index.symbol("one.py::one:function")["source"])
        self.assertIn("return one()", self.index.symbol("two.py::two:function")["source"])
        self.write("three.py", "from two import two\ndef three(): return two()\n")
        changed = self.index.refresh(self.root, fast=True)
        clean = RepositoryIndex(self.base / "clean.sqlite")
        self.assert_summary_equal(changed, clean.refresh(self.root))
        self.assertEqual(self.index.graph(), clean.graph())

    def test_corrupt_cached_stream_aborts_relink_without_replacing_snapshot(self):
        self.seed()
        before = self.index.status()
        graph = self.index.graph()
        with closing(sqlite3.connect(self.index.db)) as conn, conn:
            conn.execute("UPDATE files SET parsed=? WHERE path='one.py'", (b"corrupt-cache",))
        self.write("two.py", "def changed(): return 2\n")
        with self.assertRaisesRegex(ValueError, "parse cache"):
            self.index.refresh(self.root, fast=True)
        self.assertEqual(before, self.index.status())
        self.assertEqual(graph, self.index.graph())
        self.assertTrue(self.index.search("two")["hits"])

    def test_cache_encoding_failure_rolls_back_graph_and_fts_writes(self):
        self.seed()
        before = self.index.status()
        graph = self.index.graph()
        self.write("two.py", "def changed(): return 2\n")
        with patch.object(index_module, "encode_parse_cache", side_effect=ValueError("cache encoding failed")):
            with self.assertRaisesRegex(ValueError, "cache encoding failed"):
                self.index.refresh(self.root, fast=True)
        self.assertEqual(before, self.index.status())
        self.assertEqual(graph, self.index.graph())
        self.assertTrue(self.index.search("two")["hits"])

    def test_relinked_cached_facts_match_full_rebuild_after_change_and_delete(self):
        self.seed()
        self.write("one.py", "def changed(): return 2\n")
        changed = self.index.refresh(self.root, fast=True)
        clean = RepositoryIndex(self.base / "clean.sqlite")
        rebuilt = clean.refresh(self.root)
        self.assert_summary_equal(changed, rebuilt)
        self.assertEqual(self.index.graph(), clean.graph())
        self.assertEqual(changed["refresh"]["reused_files"], 1)
        (self.root / "one.py").unlink()
        deleted = self.index.refresh(self.root, fast=True)
        rebuilt = clean.refresh(self.root)
        self.assert_summary_equal(deleted, rebuilt)
        self.assertEqual(self.index.graph(), clean.graph())
        self.assertEqual(deleted["refresh"]["removed_files"], 1)
        self.assertGreater(deleted["unresolved_references"], 0)

    def test_unchanged_refresh_checks_second_enumeration_and_stat_races(self):
        self.seed()
        self.write(".gitignore", "ignored/\n")
        discover = index_module.discover
        for mutation in ("source", "config", "add", "delete"):
            with self.subTest(mutation=mutation):
                self.write("one.py", "def one(): return 1\n")
                self.index.refresh(self.root, fast=True)
                before = self.index.status()
                calls = 0

                def racing_discover(*args, **kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        if mutation == "source":
                            self.write("one.py", "def one(): return 2\n")
                        elif mutation == "config":
                            self.write(".gitignore", "new_ignored/\n")
                        elif mutation == "add":
                            self.write("added.py", "def added(): return 3\n")
                        else:
                            (self.root / "one.py").unlink()
                    return discover(*args, **kwargs)

                with self.forbid_cached_parse_reads(), patch.object(
                        index_module, "discover", side_effect=racing_discover):
                    with self.assertRaisesRegex(SnapshotChanged, "changed during sync"):
                        self.index.refresh(self.root, fast=True)
                self.assertEqual(calls, 2)
                self.assertEqual(before, self.index.status())

    def test_unchanged_refresh_checks_git_identity_before_commit(self):
        self.seed()
        before = self.index.status()
        state = before["git_state"]
        with self.forbid_cached_parse_reads(), patch.object(index_module, "git_state", side_effect=[
                state, {**state, "branch": "changed-during-refresh"}]):
            with self.assertRaisesRegex(SnapshotChanged, "Git HEAD/branch/worktree changed"):
                self.index.refresh(self.root, fast=True)
        self.assertEqual(before, self.index.status())


if __name__ == "__main__":
    unittest.main()
