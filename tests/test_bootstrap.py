"""Bootstrap boundary tests; dependency installation is covered by real smoke QA."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
import bootstrap as b


def load_cli(name: str):
    spec = importlib.util.spec_from_file_location("bootstrap_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = load_cli("install")
runner = load_cli("run")


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="columbus package ")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name).resolve() / "target repository with spaces"
        self.repo.mkdir()
        (self.repo / "Example.kt").write_text("class Example\n")

    def call(self, main, *arguments):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            result = main(["--repo", str(self.repo), *arguments])
        return result, output.getvalue(), errors.getvalue()

    def environment(self, *, ready=True):
        runtime = self.repo / ".columbus/runtime"
        runtime.mkdir(parents=True)
        python = b.interpreter(self.repo, runtime)
        python.parent.mkdir()
        # Never executed in these boundary tests. Commands are captured below.
        python.write_text("placeholder")
        (runtime / "pyvenv.cfg").write_text("home = placeholder\n")
        state = {"owner": b.OWNER, "format": 1,
                 "requirements_sha256": b.requirements_digest(False) if ready else None}
        b.save_state(self.repo, runtime, state)
        return runtime, python

    def test_plan_has_no_filesystem_side_effects_or_subprocesses(self):
        before = sorted(path.relative_to(self.repo) for path in self.repo.rglob("*"))
        with patch.object(b, "invoke", side_effect=AssertionError("Plan must not run a subprocess")):
            code, output, _ = self.call(installer.main, "--plan")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["status"], "plan")
        self.assertEqual(before, sorted(path.relative_to(self.repo) for path in self.repo.rglob("*")))

    def test_existing_local_skill_edits_stop_before_runtime_mutation(self):
        b.bundle_plan(self.repo, apply=True)
        local = self.repo / b.SKILL_RELATIVE / "SKILL.md"
        local.write_text(local.read_text() + "\nLocal policy\n")
        with patch.object(b, "invoke", side_effect=AssertionError("Conflict must stop first")):
            code, _, errors = self.call(installer.main)
        self.assertEqual(code, 2)
        self.assertIn("local edits", errors)
        self.assertFalse((self.repo / ".columbus").exists())
        self.assertTrue(local.read_text().endswith("Local policy\n"))

    def test_unmanaged_environment_is_never_adopted(self):
        runtime = self.repo / ".columbus/runtime"
        runtime.mkdir(parents=True)
        user_file = runtime / "my data"
        user_file.write_text("keep")
        code, _, errors = self.call(installer.main)
        self.assertEqual(code, 2)
        self.assertIn("unmanaged runtime", errors)
        self.assertEqual(user_file.read_text(), "keep")
        self.assertFalse((self.repo / b.SKILL_RELATIVE).exists())

    def test_internal_runtime_and_marker_symlinks_are_refused(self):
        outside = Path(self.temporary.name).resolve() / "outside"
        outside.mkdir()
        (self.repo / ".columbus").symlink_to(outside, target_is_directory=True)
        code, _, errors = self.call(installer.main)
        self.assertEqual(code, 2)
        self.assertIn("Symlink", errors)
        self.assertEqual(list(outside.iterdir()), [])
        (self.repo / ".columbus").unlink()
        runtime = self.repo / ".columbus/runtime"
        runtime.mkdir(parents=True)
        target = outside / "marker.json"
        target.write_text(json.dumps({"owner": b.OWNER, "format": 1}))
        (runtime / b.MARKER).symlink_to(target)
        code, _, errors = self.call(installer.main)
        self.assertEqual(code, 2)
        self.assertIn("Symlink", errors)

    def test_repository_root_symlink_resolves_to_explicit_target(self):
        alias = Path(self.temporary.name) / "project alias"
        alias.symlink_to(self.repo, target_is_directory=True)
        self.assertEqual(b.repository(alias), self.repo)

    def test_lock_collision_does_not_remove_existing_lock(self):
        lock = self.repo / ".columbus/.bootstrap-lock"
        lock.mkdir(parents=True)
        code, _, errors = self.call(installer.main)
        self.assertEqual(code, 2)
        self.assertIn("locked", errors)
        self.assertTrue(lock.is_dir())
        self.assertFalse((self.repo / ".columbus/runtime").exists())

    def test_dependency_failure_preserves_retry_state_and_skill_is_not_applied(self):
        runtime, _ = self.environment(ready=False)
        def fail_install(command, **kwargs):
            return subprocess.CompletedProcess(command, 1 if "pip" in command else 0)
        with patch.object(b, "invoke", side_effect=fail_install):
            code, _, errors = self.call(installer.main, "--no-index")
        self.assertEqual(code, 2)
        self.assertIn("Install pinned dependencies failed", errors)
        self.assertFalse((self.repo / b.SKILL_RELATIVE).exists())
        self.assertIsNone(b.runtime_state(self.repo, runtime)["requirements_sha256"])
        self.assertFalse((self.repo / ".columbus/.bootstrap-lock").exists())
        calls = []
        def successful(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0)
        with patch.object(b, "invoke", side_effect=successful):
            code, output, _ = self.call(installer.main, "--no-index")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["bundle_status"], "applied")
        self.assertTrue(any("pip" in command for command in calls))
        self.assertTrue((self.repo / b.SKILL_RELATIVE / ".bundle-lock.json").is_file())

    def test_noop_bundle_repairs_broken_dependency_environment(self):
        b.bundle_plan(self.repo, apply=True)
        runtime, python = self.environment()
        calls = []
        doctor_calls = []
        def invoke(command, **kwargs):
            calls.append(command)
            # Initial doctor fails; pip repair and second doctor succeed.
            if "doctor" in command:
                doctor_calls.append(command)
            return subprocess.CompletedProcess(command, 1 if "doctor" in command and len(doctor_calls) == 1 else 0)
        with patch.object(b, "invoke", side_effect=invoke):
            code, output, _ = self.call(installer.main, "--no-index")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["bundle_status"], "noop")
        self.assertEqual(len(doctor_calls), 2)
        self.assertTrue(any("pip" in command for command in calls))
        self.assertTrue(all(command[:3] == [str(python), "-E", "-s"] for command in calls))

    def test_verified_noop_skips_pip_but_runs_doctor_and_sync(self):
        b.bundle_plan(self.repo, apply=True)
        self.environment()
        calls = []
        def invoke(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0)
        with patch.object(b, "invoke", side_effect=invoke):
            code, _, _ = self.call(installer.main)
        self.assertEqual(code, 0)
        self.assertFalse(any("pip" in command for command in calls))
        self.assertTrue(any("doctor" in command for command in calls))
        self.assertTrue(any("sync" in command and str(self.repo) in command for command in calls))

    def test_offline_install_uses_only_supplied_wheelhouse(self):
        self.environment(ready=False)
        wheels = Path(self.temporary.name) / "compatible wheels"
        wheels.mkdir()
        calls = []
        def invoke(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0)
        with patch.object(b, "invoke", side_effect=invoke):
            code, _, _ = self.call(installer.main, "--offline", "--wheelhouse", str(wheels), "--no-index")
        self.assertEqual(code, 0)
        pip = next(command for command in calls if "pip" in command)
        self.assertIn("--no-index", pip)
        self.assertEqual(pip[pip.index("--find-links") + 1], str(wheels.resolve()))

    def test_mcp_readiness_includes_import_and_exact_version(self):
        calls = []
        def invoke(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0 if len(calls) == 1 else 1)
        with patch.object(b, "invoke", side_effect=invoke):
            self.assertFalse(b.healthy(Path(sys.executable), mcp=True))
        self.assertIn("import mcp", calls[-1][-1])
        self.assertIn("2.1.1", calls[-1][-1])

    def test_runner_preserves_space_paths_arguments_and_exit_code(self):
        b.bundle_plan(self.repo, apply=True)
        _, python = self.environment()
        with patch.object(b, "invoke", return_value=subprocess.CompletedProcess([], 7)) as invoke:
            code, _, _ = self.call(runner.main, "context", "Payment Service", "--budget-bytes", "2000")
        self.assertEqual(code, 7)
        command = invoke.call_args.args[0]
        self.assertEqual(command[:3], [str(python), "-E", "-s"])
        self.assertEqual(command[-5:], ["--repo", str(self.repo), "Payment Service", "--budget-bytes", "2000"])

    def test_runner_stops_while_setup_is_locked(self):
        b.bundle_plan(self.repo, apply=True)
        self.environment()
        (self.repo / ".columbus/.bootstrap-lock").mkdir()
        with patch.object(b, "invoke", side_effect=AssertionError("Must not query during setup")):
            code, _, errors = self.call(runner.main, "search", "Example")
        self.assertEqual(code, 2)
        self.assertIn("setup is in progress", errors)

    def test_partial_environment_without_pip_is_repaired_on_retry(self):
        self.environment(ready=False)
        calls = []
        def invoke(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 1 if "-c" in command else 0)
        with patch.object(b, "invoke", side_effect=invoke):
            code, _, _ = self.call(installer.main, "--no-index")
        self.assertEqual(code, 0)
        creation = next(i for i, command in enumerate(calls) if "venv" in command)
        install = next(i for i, command in enumerate(calls) if "pip" in command)
        self.assertLess(creation, install)
        self.assertNotIn("--clear", calls[creation])


if __name__ == "__main__":
    unittest.main()
