import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from repoatlas.index import RepositoryIndex
from repoatlas import index as index_module
from repoatlas.sync_state import SnapshotChanged
from repoatlas import languages


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        self.index = RepositoryIndex(self.root / ".repoatlas" / "index.sqlite")

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def git(self, *args, root=None):
        return subprocess.run(["git", "-C", str(root or self.root), *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    def init_git(self):
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "RepoAtlas Test")
        self.git("config", "user.email", "repoatlas-test@example.invalid")
        self.write(".gitignore", ".repoatlas/\n")

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")

    def graph(self, index=None):
        return (index or self.index).graph()

    def test_fast_noop_never_reads_source_bodies(self):
        self.write("one.py", "def one(): return 1\n")
        self.write("two.py", "def two(): return 2\n")
        first = self.index.refresh(self.root, fast=True)
        with patch.object(index_module, "read_stable", side_effect=AssertionError("source body read")):
            report = self.index.refresh(self.root, fast=True)
        self.assertEqual(report["revision"], first["revision"])
        self.assertEqual(report["refresh"]["hashed_files"], 0)
        self.assertEqual(report["refresh"]["hashed_bytes"], 0)
        self.assertEqual(report["refresh"]["metadata_reused_files"], 2)
        self.assertEqual(report["freshness"], "metadata_checked")
        self.assertFalse(report["refresh"]["global_relink"])
        self.assertIn("not checked", self.index.status()["freshness"])

    def test_touch_same_content_hashes_once_then_reuses(self):
        source = self.write("a.py", "def one(): return 1\n")
        first = self.index.refresh(self.root, fast=True)
        timestamp = source.stat().st_mtime_ns + 10_000_000
        os.utime(source, ns=(timestamp, timestamp))
        touched = self.index.refresh(self.root, fast=True)
        self.assertEqual(touched["refresh"]["hashed_files"], 1)
        self.assertEqual(touched["refresh"]["parsed_files"], 0)
        self.assertEqual(touched["revision"], first["revision"])
        self.assertEqual(self.index.refresh(self.root, fast=True)["refresh"]["hashed_files"], 0)

    def test_same_size_edit_with_restored_mtime_is_detected_by_ctime(self):
        source = self.write("a.py", "def one(): return 1\n")
        self.index.refresh(self.root, fast=True)
        stat = source.stat()
        source.write_text("def one(): return 2\n")
        os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        report = self.index.refresh(self.root, fast=True)
        self.assertEqual(report["refresh"]["parsed_files"], 1)
        self.assertIn("return 2", self.index.symbol("one")["source"])

    def test_dirty_untracked_delete_rename_matches_full_rebuild(self):
        self.init_git()
        self.write("one.py", "def one(): return 1\n")
        self.write("two.py", "def two(): return 2\n")
        self.write("three.py", "def three(): return 3\n")
        self.commit()
        self.index.refresh(self.root, fast=True)
        self.write("one.py", "def renamed_one(): return 100\n")
        (self.root / "two.py").rename(self.root / "renamed.py")
        (self.root / "three.py").unlink()
        self.write("untracked.py", "from one import renamed_one\ndef untracked(): return renamed_one()\n")
        report = self.index.refresh(self.root, fast=True)
        self.assertEqual(report["refresh"]["removed_files"], 2)
        self.assertEqual(report["refresh"]["added_files"], 2)
        clean = RepositoryIndex(self.base / "rebuilt.sqlite")
        clean.refresh(self.root)
        self.assertEqual(self.graph(), self.graph(clean))
        self.assertEqual(self.index.search("one"), clean.search("one"))
        self.assertNotIn("two.py", {n["path"] for n in self.graph()["nodes"]})

    def test_branch_change_forces_hash_even_when_commit_identical(self):
        self.init_git()
        self.write("a.py", "def a(): return 1\n")
        self.commit()
        first = self.index.refresh(self.root, fast=True)
        self.git("switch", "-qc", "feature")
        stale = self.index.status(True)
        self.assertEqual(stale["freshness"], "stale")
        self.assertIn("git_state_changed", stale["stale_reasons"])
        second = self.index.refresh(self.root, fast=True)
        self.assertEqual(second["refresh"]["hashed_files"], 1)
        self.assertEqual(second["refresh"]["parsed_files"], 0)
        self.assertTrue(second["refresh"]["branch_changed"])
        self.assertNotEqual(first["revision"], second["revision"])

    def test_checkout_other_commit_reconciles_deletions(self):
        self.init_git()
        self.write("a.py", "def a(): return 1\n")
        self.commit()
        self.git("switch", "-qc", "feature")
        self.write("b.py", "def b(): return 2\n")
        self.commit()
        self.index.refresh(self.root, fast=True)
        self.git("switch", "-q", "main")
        report = self.index.refresh(self.root, fast=True)
        self.assertTrue(report["refresh"]["head_changed"])
        self.assertEqual(report["refresh"]["removed_files"], 1)
        self.assertFalse(self.index.search("b")["hits"])

    def test_config_outside_source_root_changes_revision(self):
        self.write("src/a.py", "def a(): return 1\n")
        self.write("build.gradle", "plugins {}\n")
        first = self.index.refresh(self.root, source_root="src", fast=True)
        self.write("build.gradle", "plugins { id 'java' }\n")
        status = self.index.status(True)
        self.assertEqual(status["stale_config_paths"], ["build.gradle"])
        second = self.index.refresh(self.root, fast=True)
        self.assertTrue(second["refresh"]["config_changed"])
        self.assertTrue(second["refresh"]["global_relink"])
        self.assertNotEqual(first["revision"], second["revision"])
        self.assertEqual(self.index.status(True)["freshness"], "checked_clean")
        (self.root / "build.gradle").unlink()
        self.assertTrue(self.index.refresh(self.root, fast=True)["refresh"]["config_changed"])

    def test_ignore_change_removes_old_graph_and_fts(self):
        self.write("keep.py", "def keep(): return 1\n")
        self.write("hide.py", "def hidden(): return 2\n")
        self.index.refresh(self.root, fast=True)
        self.write(".repoatlasignore", "hide.py\n")
        report = self.index.refresh(self.root, fast=True)
        self.assertEqual(report["files"], 1)
        self.assertTrue(report["refresh"]["config_changed"])
        self.assertFalse(self.index.search("hidden")["hits"])

    def test_worktrees_have_separate_identity_and_root_binding(self):
        self.init_git()
        self.write("a.py", "def a(): return 1\n")
        self.commit()
        worktree = self.base / "feature-worktree"
        self.git("worktree", "add", "-qb", "feature", str(worktree))
        first = self.index.refresh(self.root, fast=True)
        alternate = RepositoryIndex(worktree / ".repoatlas" / "index.sqlite")
        second = alternate.refresh(worktree, fast=True)
        self.assertEqual(first["git_state"]["common_dir"], second["git_state"]["common_dir"])
        self.assertNotEqual(first["git_state"]["git_dir"], second["git_state"]["git_dir"])
        with self.assertRaisesRegex(ValueError, "another repository or worktree"):
            self.index.refresh(worktree, fast=True)

    def test_graph_and_fts_rollback_on_resolution_error(self):
        self.write("a.py", "def original(): return 1\n")
        self.index.refresh(self.root)
        original_graph = self.graph()
        original_search = self.index.search("original")
        self.write("a.py", "def changed(): return 2\n")
        with patch.object(index_module, "resolve_files", side_effect=RuntimeError("simulated linker failure")):
            with self.assertRaisesRegex(RuntimeError, "linker failure"):
                self.index.refresh(self.root, fast=True)
        self.assertEqual(self.graph(), original_graph)
        self.assertEqual(self.index.search("original"), original_search)

    def test_concurrent_source_change_rolls_back_after_graph_write(self):
        source = self.write("a.py", "def original(): return 1\n")
        self.index.refresh(self.root)
        original = self.graph()
        source.write_text("def changed(): return 2\n")
        original_resolve = index_module.resolve_files
        def changing_resolve(files):
            result = original_resolve(files)
            source.write_text("def raced(): return 3\n")
            return result
        with patch.object(index_module, "resolve_files", side_effect=changing_resolve):
            with self.assertRaisesRegex(SnapshotChanged, "changed during sync"):
                self.index.refresh(self.root, fast=True)
        self.assertEqual(self.graph(), original)
        self.assertTrue(self.index.search("original")["hits"])

    def test_concurrent_branch_change_rolls_back_after_graph_write(self):
        self.init_git()
        self.write("a.py", "def original(): return 1\n")
        self.commit()
        self.index.refresh(self.root)
        original = self.graph()
        self.write("a.py", "def changed(): return 2\n")
        original_resolve = index_module.resolve_files
        def changing_resolve(files):
            result = original_resolve(files)
            self.git("switch", "-qc", "mid-sync")
            return result
        with patch.object(index_module, "resolve_files", side_effect=changing_resolve):
            with self.assertRaisesRegex(SnapshotChanged, "Git HEAD/branch/worktree changed"):
                self.index.refresh(self.root, fast=True)
        self.assertEqual(self.graph(), original)

    def test_schema_one_database_is_untouched_and_rejected(self):
        self.index.db.parent.mkdir()
        with sqlite3.connect(self.index.db) as conn:
            conn.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)")
            conn.execute("INSERT INTO metadata VALUES('schema_version', ?)", (json.dumps("1"),))
        original = self.index.db.read_bytes()
        with self.assertRaisesRegex(ValueError, "choose a new --db"):
            self.index.refresh(self.root, fast=True)
        self.assertEqual(self.index.db.read_bytes(), original)

    def test_snapshot_status_does_not_scan_sources(self):
        self.write("a.py", "def a(): return 1\n")
        self.index.refresh(self.root, fast=True)
        with patch.object(index_module, "discover", side_effect=AssertionError("unexpected scan")):
            self.assertEqual(self.index.status()["files"], 1)

    def test_java_kotlin_dispatch_incremental_rebuild_and_utf8_bom(self):
        self.write("Api.kt", "\ufeffpackage demo\nfun greet() = \"안녕\"\n")
        self.write("Worker.java", "package demo; class Worker { void run() {} }\n")
        self.write("build.gradle.kts", "plugins { java }\n")
        first = self.index.refresh(self.root, fast=True)
        self.assertEqual(first["files"], 3)
        self.assertEqual(first["analyzer_fingerprint"]["languages"], ["java", "kotlin"])
        for package in languages.JVM_DEPENDENCIES:
            self.assertIn(package, first["analyzer_fingerprint"]["versions"])
        self.assertIn("안녕", self.index.symbol("greet")["source"])
        noop = self.index.refresh(self.root, fast=True)
        self.assertEqual(noop["refresh"]["hashed_files"], 0)
        self.assertEqual(noop["refresh"]["config_hashed_files"], 0)
        self.write("Api.kt", "package demo\nfun salute() = \"반가워\"\n")
        changed = self.index.refresh(self.root, fast=True)
        self.assertEqual(changed["refresh"]["parsed_files"], 1)
        rebuilt = RepositoryIndex(self.base / "jvm-rebuilt.sqlite")
        rebuilt.refresh(self.root)
        self.assertEqual(self.graph(), self.graph(rebuilt))
        self.assertFalse(self.index.search("greet")["hits"])

    def test_missing_jvm_dependency_aborts_without_removing_old_graph(self):
        self.write("a.py", "def original(): return 1\n")
        self.index.refresh(self.root)
        graph = self.graph()
        self.write("Worker.java", "class Worker {}\n")
        with patch.object(languages.metadata, "version", side_effect=languages.metadata.PackageNotFoundError):
            with self.assertRaisesRegex(RuntimeError, "JVM analyzer dependency missing"):
                self.index.refresh(self.root, fast=True)
        self.assertEqual(self.graph(), graph)


if __name__ == "__main__":
    unittest.main()
