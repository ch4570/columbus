"""Behavioral tests for managed repository skill installation and upgrades."""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


INSTALLER = Path(__file__).resolve().parents[1] / "install.py"
SPEC = importlib.util.spec_from_file_location("repoatlas_bundle_installer", INSTALLER)
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True, capture_output=True)
        self.source = self.root / "bundle"
        self.source.mkdir()
        self.write_source("SKILL.md", "---\nname: repoatlas-jvm\n---\nUse the graph.\n")
        self.write_source("bundle.json", json.dumps({"name": "repoatlas-jvm", "version": "0.2.0", "schema_version": "2"}))
        self.write_source("scripts/atlas.py", "print('atlas')\n")
        self.write_source("scripts/install.py", INSTALLER.read_text())
        self.write_source("scripts/repoatlas/index.py", "SCHEMA = 2\n")
        self.write_source("scripts/requirements.txt", "tree-sitter\n")
        self.write_source("references/sync.md", "Changes only.\n")
        self.write_source("agents/openai.yaml", "display_name: RepoAtlas\n")
        self.write_source("LICENSE", "Apache-2.0\n")
        self.destination = self.repo / ".agents/skills/repoatlas-jvm"

    def write_source(self, relative, text):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def apply(self):
        return installer.install_bundle(self.repo, self.source, apply=True)

    def installed_snapshot(self):
        return installer._snapshot(self.destination)

    def test_plan_is_read_only_and_apply_records_reproducible_hashes(self):
        plan = installer.install_bundle(self.repo, self.source)
        self.assertEqual(plan["status"], "planned")
        self.assertFalse((self.repo / ".agents").exists())
        result = self.apply()
        self.assertEqual(result["status"], "applied")
        lock = json.loads((self.destination / installer.MANIFEST).read_text())
        self.assertEqual(lock["version"], "0.2.0")
        self.assertEqual(lock["bundle_digest"], installer._digest(lock["files"]))
        for relative, digest in lock["files"].items():
            self.assertEqual(digest, installer._sha((self.destination / relative).read_bytes()))
        self.assertFalse((self.repo / "AGENTS.md").exists())
        self.assertFalse((self.repo / ".gitignore").exists())

    def test_idempotent_apply_does_not_rewrite_content_or_manifest(self):
        self.apply()
        before = {p.relative_to(self.destination).as_posix(): p.stat().st_mtime_ns for p in self.destination.rglob("*")}
        result = self.apply()
        after = {p.relative_to(self.destination).as_posix(): p.stat().st_mtime_ns for p in self.destination.rglob("*")}
        self.assertEqual(result["status"], "noop")
        self.assertEqual(before, after)

    def test_ui_assets_are_managed_across_updates(self):
        self.write_source("assets/icon.svg", '<svg xmlns="http://www.w3.org/2000/svg"/>')
        self.assertEqual(self.apply()["status"], "applied")
        self.assertTrue((self.destination / "assets/icon.svg").exists())
        self.write_source("assets/icon.svg", '<svg xmlns="http://www.w3.org/2000/svg"><title>New</title></svg>')
        result = self.apply()
        self.assertIn("assets/icon.svg", result["updated"])
        self.assertEqual((self.source / "assets/icon.svg").read_bytes(), (self.destination / "assets/icon.svg").read_bytes())
        (self.source / "assets/icon.svg").unlink()
        self.assertIn("assets/icon.svg", self.apply()["removed"])
        self.assertFalse((self.destination / "assets/icon.svg").exists())

    def test_same_version_content_update_changes_digest(self):
        first = self.apply()
        self.write_source("scripts/repoatlas/index.py", "SCHEMA = 3\n")
        second = self.apply()
        self.assertEqual(second["status"], "applied")
        self.assertEqual(first["version"], second["version"])
        self.assertNotEqual(first["bundle_digest"], second["bundle_digest"])
        self.assertEqual(second["updated"], ["scripts/repoatlas/index.py"])
        self.assertEqual((self.destination / "scripts/repoatlas/index.py").read_text(), "SCHEMA = 3\n")

    def test_version_update_is_recorded(self):
        self.apply()
        self.write_source("bundle.json", json.dumps({"name": "repoatlas-jvm", "version": "0.3.0", "schema_version": "2"}))
        result = self.apply()
        self.assertEqual(result["previous_version"], "0.2.0")
        self.assertEqual(result["version"], "0.3.0")

    def test_existing_repository_policy_and_runtime_files_are_untouched(self):
        (self.repo / "AGENTS.md").write_text("Team instructions\n")
        (self.repo / ".gitignore").write_text("build/\n")
        runtime = self.repo / ".repoatlas/index.sqlite3"
        runtime.parent.mkdir()
        runtime.write_bytes(b"existing database bytes")
        paths = [self.repo / "AGENTS.md", self.repo / ".gitignore", self.repo / ".git/config", runtime]
        original = {path: path.read_bytes() for path in paths}
        self.assertEqual(self.apply()["status"], "applied")
        self.assertEqual(original, {path: path.read_bytes() for path in paths})

    def test_clean_upstream_file_can_be_replaced_by_directory(self):
        self.write_source("references/topic", "Old topic\n")
        self.apply()
        (self.source / "references/topic").unlink()
        self.write_source("references/topic/details.md", "New topic\n")
        result = self.apply()
        self.assertEqual(result["status"], "applied")
        self.assertEqual((self.destination / "references/topic/details.md").read_text(), "New topic\n")

    def test_local_edit_conflicts_even_when_upstream_unchanged(self):
        self.apply()
        (self.destination / "SKILL.md").write_text("Locally customized instructions\n")
        snapshot = self.installed_snapshot()
        result = self.apply()
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["conflicts"][0]["path"], "SKILL.md")
        self.assertEqual(snapshot, self.installed_snapshot())

    def test_local_deletion_is_not_silently_restored(self):
        self.apply()
        (self.destination / "references/sync.md").unlink()
        result = self.apply()
        self.assertEqual(result["status"], "conflict")
        self.assertFalse((self.destination / "references/sync.md").exists())

    def test_upstream_removal_deletes_only_clean_managed_file(self):
        self.apply()
        extra = self.destination / "references/team-notes.md"
        extra.write_text("Our local notes\n")
        (self.source / "references/sync.md").unlink()
        result = self.apply()
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["removed"], ["references/sync.md"])
        self.assertFalse((self.destination / "references/sync.md").exists())
        self.assertEqual(extra.read_text(), "Our local notes\n")

    def test_upstream_removal_of_locally_edited_file_conflicts(self):
        self.apply()
        (self.destination / "references/sync.md").write_text("Important local changes\n")
        (self.source / "references/sync.md").unlink()
        result = self.apply()
        self.assertEqual(result["status"], "conflict")
        self.assertEqual((self.destination / "references/sync.md").read_text(), "Important local changes\n")

    def test_both_sides_deleted_file_is_clean_removal(self):
        self.apply()
        (self.destination / "references/sync.md").unlink()
        (self.source / "references/sync.md").unlink()
        self.assertEqual(self.apply()["status"], "applied")

    def test_unmanaged_extra_survives_update(self):
        self.apply()
        extra = self.destination / "team.txt"
        extra.write_text("private team instructions\n")
        self.write_source("references/sync.md", "new sync guidance\n")
        self.assertEqual(self.apply()["status"], "applied")
        self.assertEqual(extra.read_text(), "private team instructions\n")

    def test_new_path_collision_refuses_even_identical_content(self):
        self.apply()
        (self.destination / "references/new.md").write_text("local notes\n")
        self.write_source("references/new.md", "local notes\n")
        self.assertEqual(self.apply()["status"], "conflict")

    def test_new_path_parent_file_collision_refuses(self):
        self.apply()
        (self.destination / "references/team").write_text("local\n")
        self.write_source("references/team/notes.md", "upstream\n")
        self.assertEqual(self.apply()["status"], "conflict")

    def test_unmanaged_existing_directory_is_rejected(self):
        self.destination.mkdir(parents=True)
        (self.destination / "SKILL.md").write_text("Existing skill\n")
        snapshot = self.installed_snapshot()
        result = self.apply()
        self.assertEqual(result["status"], "error")
        self.assertIn("unmanaged", result["error"])
        self.assertEqual(snapshot, self.installed_snapshot())

    def test_custom_relative_destination(self):
        result = installer.install_bundle(self.repo, self.source, apply=True, skills_dir=".claude/skills")
        self.assertEqual(result["status"], "applied")
        self.assertTrue((self.repo / ".claude/skills/repoatlas-jvm/SKILL.md").is_file())
        self.assertFalse((self.repo / ".agents").exists())

    def test_explicit_root_alias_resolves_without_allowing_internal_links(self):
        alias = self.root / "repository alias"
        alias.symlink_to(self.repo, target_is_directory=True)
        result = installer.install_bundle(alias, self.source, apply=True)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(Path(result["destination"]), self.destination)

    def test_unsafe_destination_paths_are_rejected(self):
        for directory in ("../escape", "/tmp/escape", ".agents/../escape", "a//b", "a\\b", ".", ".git/skills", ".repoatlas/skills"):
            with self.subTest(directory=directory):
                result = installer.install_bundle(self.repo, self.source, apply=True, skills_dir=directory)
                self.assertEqual(result["status"], "error")
        self.assertEqual([p.name for p in self.repo.iterdir()], [".git"])

    def test_symlink_destination_parent_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.repo / ".agents").symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.apply()["status"], "error")
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlink_source_file_is_rejected(self):
        outside = self.root / "secret.txt"
        outside.write_text("Do not copy\n")
        (self.source / "references/secret.md").symlink_to(outside)
        result = self.apply()
        self.assertEqual(result["status"], "error")
        self.assertFalse(self.destination.exists())

    def test_symlink_installed_extra_is_rejected_without_following(self):
        self.apply()
        outside = self.root / "outside"
        outside.mkdir()
        (self.destination / "local-link").symlink_to(outside, target_is_directory=True)
        self.write_source("references/sync.md", "changed\n")
        self.assertEqual(self.apply()["status"], "error")
        self.assertTrue((self.destination / "local-link").is_symlink())
        self.assertEqual(list(outside.iterdir()), [])

    def test_manifest_traversal_cannot_write_outside_destination(self):
        self.apply()
        outside = self.root / "outside.txt"
        outside.write_text("untouched\n")
        lock_path = self.destination / installer.MANIFEST
        lock = json.loads(lock_path.read_text())
        lock["files"]["../../../../outside.txt"] = installer._sha(outside.read_bytes())
        lock["bundle_digest"] = installer._digest(lock["files"])
        lock_path.write_text(json.dumps(lock))
        snapshot = self.installed_snapshot()
        self.assertEqual(self.apply()["status"], "error")
        self.assertEqual(outside.read_text(), "untouched\n")
        self.assertEqual(snapshot, self.installed_snapshot())

    def test_malformed_or_inconsistent_manifest_is_rejected(self):
        self.apply()
        lock_path = self.destination / installer.MANIFEST
        original = lock_path.read_text()
        for content in ("not json", "[]", '{"files": []}', original.replace('"bundle_digest": "', '"bundle_digest": "bad')):
            with self.subTest(content=content[:30]):
                lock_path.write_text(content)
                self.assertEqual(self.apply()["status"], "error")

    def test_runtime_and_python_cache_are_not_bundled(self):
        self.write_source(".repoatlas/index.sqlite3", "runtime data")
        self.write_source("scripts/repoatlas/__pycache__/index.pyc", "cache")
        self.write_source("scripts/repoatlas/.venv/injected.py", "venv code")
        self.write_source("scripts/tests/test_extra.py", "test code")
        self.write_source("references/.repoatlas/index.sqlite3", "runtime data")
        self.assertEqual(self.apply()["status"], "applied")
        self.assertFalse((self.destination / ".repoatlas").exists())
        self.assertFalse((self.destination / "scripts/repoatlas/__pycache__").exists())
        self.assertFalse((self.destination / "scripts/repoatlas/.venv").exists())
        self.assertFalse((self.destination / "scripts/tests").exists())
        self.assertFalse((self.destination / "references/.repoatlas").exists())

    def test_promotion_failure_rolls_back_entire_prior_directory(self):
        self.apply()
        snapshot = self.installed_snapshot()
        self.write_source("references/sync.md", "changed upstream\n")
        original_rename = Path.rename

        def fail_stage_promotion(path, target):
            if path.name.startswith(".repoatlas-jvm.stage-"):
                raise OSError("simulated promotion failure")
            return original_rename(path, target)

        with mock.patch.object(Path, "rename", fail_stage_promotion):
            result = self.apply()
        self.assertEqual(result["status"], "error")
        self.assertIn("simulated promotion failure", result["error"])
        self.assertEqual(snapshot, self.installed_snapshot())
        self.assertEqual([p.name for p in self.destination.parent.iterdir()], ["repoatlas-jvm"])

    def test_concurrent_unmanaged_edit_is_preserved_and_apply_aborts(self):
        self.apply()
        extra = self.destination / "team.txt"
        extra.write_text("original\n")
        self.write_source("references/sync.md", "new upstream\n")
        copytree = shutil.copytree

        def copy_then_edit(source, target, *args, **kwargs):
            result = copytree(source, target, *args, **kwargs)
            if Path(source) == self.destination:
                extra.write_text("concurrent local change\n")
            return result

        with mock.patch.object(installer.shutil, "copytree", side_effect=copy_then_edit):
            result = self.apply()
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(extra.read_text(), "concurrent local change\n")
        self.assertEqual((self.destination / "references/sync.md").read_text(), "Changes only.\n")

    def test_existing_install_lock_blocks_update(self):
        self.apply()
        lock = self.destination.parent / ".repoatlas-jvm.install-lock"
        lock.mkdir()
        self.write_source("references/sync.md", "new\n")
        result = self.apply()
        self.assertEqual(result["status"], "error")
        self.assertIn("locked", result["error"])
        self.assertTrue(lock.is_dir())

    def test_cli_is_read_only_by_default_and_returns_two_on_conflict(self):
        command = [sys.executable, str(INSTALLER), "--repo", str(self.repo), "--source", str(self.source)]
        planned = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(planned.returncode, 0, planned.stderr)
        self.assertEqual(json.loads(planned.stdout)["status"], "planned")
        self.assertFalse(self.destination.exists())
        self.apply()
        (self.destination / "SKILL.md").write_text("customized\n")
        conflict = subprocess.run([*command, "--apply"], capture_output=True, text=True, check=False)
        self.assertEqual(conflict.returncode, 2)
        self.assertEqual(json.loads(conflict.stdout)["status"], "conflict")


if __name__ == "__main__":
    unittest.main()
