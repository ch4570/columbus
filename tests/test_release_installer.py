"""Release-installer boundaries; real offline installation also runs in distribution QA."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_installer", ROOT / "get-columbus.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class ReleaseInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="columbus release tests ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.prefix = self.root / "managed installation"
        self.bin_dir = self.root / "commands with spaces"
        self.calls = []
        self.fail_pip = False
        self.fail_doctor = False
        self.reported_version = None
        self.report_global_prefix = False
        self.wheelhouse = self.root / "dependency wheels"
        self.wheelhouse.mkdir()

    def arguments(self, version="1.0.0"):
        files = self.root / ("artifacts-" + version)
        files.mkdir(exist_ok=True)
        wheel = files / f"columbus-{version}-py3-none-any.whl"
        wheel.write_bytes(("fixture wheel " + version).encode())
        checksum = files / "SHA256SUMS.txt"
        checksum.write_text(hashlib.sha256(wheel.read_bytes()).hexdigest() + "  " + wheel.name + "\n")
        return SimpleNamespace(version=version, prefix=self.prefix, bin_dir=self.bin_dir,
                               wheel=wheel, checksum_file=checksum, wheelhouse=self.wheelhouse, offline=True)

    def fake_invoke(self, command, **kwargs):
        command = [str(part) for part in command]
        self.calls.append(command)
        if "venv" in command:
            runtime = Path(command[-1])
            python, entrypoint = installer.binaries(runtime)
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("test interpreter")
            entrypoint.write_bytes(("test executable " + runtime.name).encode())
            (runtime / "pyvenv.cfg").write_text("include-system-site-packages = false\n")
            return subprocess.CompletedProcess(command, 0)
        runtime = Path(command[0]).parent.parent
        version = runtime.name
        if "pip" in command:
            return subprocess.CompletedProcess(command, int(self.fail_pip))
        if "doctor" in command:
            return subprocess.CompletedProcess(command, int(self.fail_doctor),
                                               json.dumps({"ready": not self.fail_doctor, "bundle": {"version": version}}), "")
        if "m.version('columbus')" in command[-1]:
            return subprocess.CompletedProcess(command, 0, (self.reported_version or version) + "\n", "")
        prefix = "/global-python" if self.report_global_prefix else str(runtime)
        return subprocess.CompletedProcess(command, 0, json.dumps({"prefix": prefix, "base_prefix": "/base-python"}), "")

    def install(self, args=None):
        with patch.object(installer, "invoke", side_effect=self.fake_invoke):
            return installer.install(args or self.arguments())

    def test_release_version_rejects_paths_shell_text_prereleases_and_newlines(self):
        self.assertEqual(installer.version_number("1.0.0"), "1.0.0")
        for value in ("../1.0.0", "v1.0.0", "1.0.0rc1", "1.0.0\n", "1.0.0;echo bad", "01.5.0", "-1.2.3"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                installer.version_number(value)

    def test_checksum_requires_exact_unique_wheel_entry(self):
        args = self.arguments()
        expected = hashlib.sha256(args.wheel.read_bytes()).hexdigest()
        self.assertEqual(installer.checksum_for(args.checksum_file, args.wheel.name), expected)
        for contents in (expected + "  other-" + args.wheel.name + "\n",
                         expected + "  subdir/" + args.wheel.name + "\n",
                         args.checksum_file.read_text() * 2,
                         "0" * 63 + "  " + args.wheel.name + "\n"):
            args.checksum_file.write_text(contents)
            with self.assertRaisesRegex(installer.InstallError, "exactly one"):
                installer.checksum_for(args.checksum_file, args.wheel.name)

    def test_checksum_mismatch_stops_before_venv_or_command_creation(self):
        args = self.arguments()
        args.wheel.write_bytes(b"changed after checksums")
        with patch.object(installer, "invoke", side_effect=AssertionError("No installation may run")):
            with self.assertRaisesRegex(installer.InstallError, "SHA256 does not match"):
                installer.install(args)
        self.assertFalse((self.prefix / "versions").exists())
        self.assertFalse(self.bin_dir.exists())

    def test_download_is_pinned_https_bounded_and_times_out(self):
        args = self.arguments()
        args.wheel = args.checksum_file = None
        received = []
        checksum_data = hashlib.sha256(b"wheel").hexdigest().encode() + b"  columbus-1.0.0-py3-none-any.whl\n"

        def open_response(request, timeout):
            received.append((request.full_url, timeout))
            response = io.BytesIO(checksum_data if request.full_url.endswith(".txt") else b"wheel")
            response.headers = {}
            return response

        target = self.root / "download"
        target.mkdir()
        with patch.object(installer.urllib.request, "build_opener") as opener:
            opener.return_value.open.side_effect = open_response
            wheel, _ = installer.verified_wheel(args, target)
        self.assertEqual(wheel.read_bytes(), b"wheel")
        self.assertEqual(received, [(installer.RELEASES + "/v1.0.0/SHA256SUMS.txt", 30),
                                    (installer.RELEASES + "/v1.0.0/columbus-1.0.0-py3-none-any.whl", 30)])
        with self.assertRaisesRegex(installer.InstallError, "download limit"):
            installer.limited_copy(io.BytesIO(b"abcd"), io.BytesIO(), 3)
        with patch.object(installer.time, "monotonic", side_effect=[0, 121]):
            with self.assertRaisesRegex(installer.InstallError, "120 seconds"):
                installer.limited_copy(io.BytesIO(b"abc"), io.BytesIO(), 10)
        with self.assertRaisesRegex(installer.InstallError, "away from HTTPS"):
            installer.HTTPSRedirects().redirect_request(None, None, 302, "redirect", {}, "http://example.test/wheel")

    def test_unmanaged_prefix_and_command_are_preserved(self):
        self.prefix.mkdir()
        user_file = self.prefix / "keep.txt"
        user_file.write_text("user data")
        with self.assertRaisesRegex(installer.InstallError, "ownership marker"):
            self.install()
        self.assertEqual(user_file.read_text(), "user data")
        self.prefix = self.root / "other managed installation"
        self.bin_dir.mkdir()
        command = self.bin_dir / ("columbus.cmd" if installer.WINDOWS else "columbus")
        command.write_text("my existing command")
        with self.assertRaisesRegex(installer.InstallError, "unmanaged launcher"):
            self.install()
        self.assertEqual(command.read_text(), "my existing command")
        self.assertFalse(self.prefix.exists())

    def test_parent_symlink_and_marker_symlink_are_refused(self):
        outside = self.root / "outside"
        outside.mkdir()
        linked = self.root / "redirected parent"
        try:
            linked.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks requires developer mode or elevated rights on this Windows runner")
        self.prefix = linked / "application"
        with self.assertRaisesRegex(installer.InstallError, "Symlink or junction"):
            self.install()
        self.assertEqual(list(outside.iterdir()), [])
        self.prefix = self.root / "real prefix"
        self.prefix.mkdir()
        data = outside / "marker"
        data.write_text(json.dumps(installer.marker(self.prefix)))
        (self.prefix / installer.PREFIX_MARKER).symlink_to(data)
        with self.assertRaisesRegex(installer.InstallError, "Symlink or junction"):
            self.install()

    def test_first_install_is_isolated_offline_and_repeated_install_skips_pip_and_downloads(self):
        args = self.arguments()
        command, repeated = self.install(args)
        self.assertFalse(repeated)
        pip = next(call for call in self.calls if "pip" in call)
        self.assertEqual(pip[:3], [str(installer.binaries(self.prefix / "versions/1.0.0")[0]), "-I", "-m"])
        self.assertIn("--isolated", pip)
        self.assertIn("--no-index", pip)
        self.assertEqual(pip[pip.index("--find-links") + 1], str(self.wheelhouse))
        self.assertEqual(installer.owned_launcher(command, self.prefix), "1.0.0")
        state = installer.read_marker(self.prefix / "versions/1.0.0" / installer.RUNTIME_MARKER, self.prefix, version="1.0.0")
        self.assertEqual(state["status"], "ready")
        args.wheel = args.checksum_file = None
        args.offline = False
        self.calls.clear()
        with patch.object(installer, "download", side_effect=AssertionError("Healthy repeats need no network")):
            _, repeated = self.install(args)
        self.assertTrue(repeated)
        self.assertFalse(any("pip" in call or "venv" in call for call in self.calls))
        self.assertTrue(any("doctor" in call for call in self.calls))

    def test_failed_update_keeps_old_command_and_owned_partial_install_can_resume(self):
        command, _ = self.install(self.arguments("0.4.0"))
        self.fail_pip = True
        args = self.arguments()
        with self.assertRaisesRegex(installer.InstallError, "rerun the same command"):
            self.install(args)
        self.assertEqual(installer.owned_launcher(command, self.prefix), "0.4.0")
        self.assertEqual(installer.read_marker(self.prefix / "versions/1.0.0" / installer.RUNTIME_MARKER,
                                              self.prefix, version="1.0.0")["status"], "installing")
        self.fail_pip = False
        self.calls.clear()
        self.install(args)
        self.assertEqual(installer.owned_launcher(command, self.prefix), "1.0.0")
        self.assertTrue((self.prefix / "versions/0.4.0" / installer.RUNTIME_MARKER).is_file())
        self.assertTrue(any("pip" in call and "--force-reinstall" in call for call in self.calls))
        self.assertFalse((self.prefix / ".install-lock").exists())

    def test_doctor_failure_and_wrong_installed_version_never_publish(self):
        args = self.arguments()
        self.fail_doctor = True
        with self.assertRaisesRegex(installer.InstallError, "doctor failed"):
            self.install(args)
        self.assertFalse(self.bin_dir.exists())
        self.fail_doctor = False
        self.reported_version = "0.4.0"
        with self.assertRaisesRegex(installer.InstallError, "must be Columbus 1.0.0"):
            self.install(args)
        self.assertFalse(self.bin_dir.exists())

    def test_global_interpreter_probe_stops_before_pip(self):
        self.report_global_prefix = True
        with self.assertRaisesRegex(installer.InstallError, "does not belong"):
            self.install()
        self.assertFalse(any("pip" in call for call in self.calls))

    def test_ready_runtime_with_global_site_packages_is_preserved(self):
        args = self.arguments()
        command, _ = self.install(args)
        config = self.prefix / "versions/1.0.0/pyvenv.cfg"
        config.write_text("include-system-site-packages = true\n")
        self.calls.clear()
        with self.assertRaisesRegex(installer.InstallError, "preserved"):
            self.install(args)
        self.assertIn("true", config.read_text())
        self.assertEqual(self.calls, [])
        self.assertEqual(installer.owned_launcher(command, self.prefix), "1.0.0")

    def test_partial_runtime_redirect_cannot_write_outside_prefix(self):
        args = self.arguments()
        self.fail_pip = True
        with self.assertRaises(installer.InstallError):
            self.install(args)
        outside = self.root / "external packages"
        outside.mkdir()
        redirected = self.prefix / "versions/1.0.0/lib"
        try:
            redirected.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks requires developer mode or elevated rights on this Windows runner")
        self.calls.clear()
        with self.assertRaisesRegex(installer.InstallError, "Unexpected link"):
            self.install(args)
        self.assertEqual(self.calls, [])
        self.assertEqual(list(outside.iterdir()), [])

    def test_hard_linked_partial_venv_config_stops_before_subprocesses_and_preserves_external_bytes(self):
        args = self.arguments()
        self.fail_pip = True
        with self.assertRaises(installer.InstallError):
            self.install(args)
        external = self.root / "external configuration sentinel"
        original = b"# User-owned external data\ninclude-system-site-packages = false\n"
        external.write_bytes(original)
        config = self.prefix / "versions/1.0.0/pyvenv.cfg"
        config.unlink()
        os.link(external, config)
        self.assertEqual(config.stat().st_nlink, 2)
        self.fail_pip = False
        self.calls.clear()
        with self.assertRaisesRegex(installer.InstallError, "hard link"):
            self.install(args)
        self.assertEqual(self.calls, [])
        self.assertEqual(external.read_bytes(), original)
        self.assertEqual(config.read_bytes(), original)
        self.assertFalse(self.bin_dir.exists())

    @unittest.skipIf(installer.WINDOWS, "Python 3.14 creates this interpreter alias on POSIX")
    def test_python_314_interpreter_alias_can_resume_only_when_it_targets_the_current_python(self):
        args = self.arguments()
        self.fail_pip = True
        with self.assertRaises(installer.InstallError):
            self.install(args)
        runtime = self.prefix / "versions/1.0.0"
        alias = runtime / "bin/𝜋thon"
        alias.symlink_to(Path(sys.executable).resolve())
        with patch.object(installer, "invoke", side_effect=self.fake_invoke):
            installer.resumable_runtime(runtime)
        alias.unlink()
        alias.symlink_to(runtime / "bin/python")
        with self.assertRaisesRegex(installer.InstallError, "Unexpected link"):
            installer.resumable_runtime(runtime)

    def test_lock_collision_is_not_removed(self):
        args = self.arguments()
        self.install(args)
        lock = self.prefix / ".install-lock"
        lock.mkdir()
        self.calls.clear()
        with self.assertRaisesRegex(installer.InstallError, "already running"):
            self.install(args)
        self.assertTrue(lock.is_dir())
        self.assertEqual(self.calls, [])

    def test_local_different_wheel_bytes_cannot_replace_ready_version(self):
        args = self.arguments()
        command, _ = self.install(args)
        args.wheel.write_bytes(b"another build under the same version")
        args.checksum_file.write_text(hashlib.sha256(args.wheel.read_bytes()).hexdigest() + "  " + args.wheel.name + "\n")
        with self.assertRaisesRegex(installer.InstallError, "different wheel bytes"):
            self.install(args)
        self.assertEqual(installer.owned_launcher(command, self.prefix), "1.0.0")

    def test_windows_batch_is_ascii_and_uses_adjacent_pinned_executable(self):
        self.prefix = self.root / "사용자 %data%! with spaces"
        with patch.object(installer, "WINDOWS", True):
            command, _ = self.install()
            data = command.read_bytes()
            self.assertTrue(data.isascii())
            self.assertEqual(data.count(b"setlocal DisableDelayedExpansion"), 1)
            self.assertIn(b'"%~dp0.columbus-', data)
            self.assertIn(b'" %*\r\n', data)
            helper = self.bin_dir / installer.windows_helper(self.prefix, "1.0.0")
            self.assertEqual(helper.read_bytes(), b"test executable 1.0.0")
            self.assertEqual(installer.owned_launcher(command, self.prefix), "1.0.0")
            helper.write_bytes(b"someone else's helper")
            with self.assertRaisesRegex(installer.InstallError, "unmanaged Windows launcher helper"):
                self.install()
            self.assertEqual(helper.read_bytes(), b"someone else's helper")

    def test_python_and_pip_configuration_cannot_redirect_installation(self):
        with patch.dict(os.environ, {"PIP_TARGET": "/global", "PIP_PREFIX": "/global", "PYTHONPATH": "/outside",
                                     "PYTHONHOME": "/outside", "VIRTUAL_ENV": "/outside", "PIP_CONFIG_FILE": "/user-pip.ini"}):
            env = installer.environment()
        self.assertEqual(env["PIP_CONFIG_FILE"], os.devnull)
        self.assertNotIn("PYTHONPATH", env)
        self.assertNotIn("PYTHONHOME", env)
        self.assertNotIn("VIRTUAL_ENV", env)
        self.assertNotIn("PIP_TARGET", env)
        self.assertNotIn("PIP_PREFIX", env)

    def test_existing_windows_executable_is_not_hidden_by_a_new_cmd_launcher(self):
        self.bin_dir.mkdir()
        executable = self.bin_dir / "columbus.exe"
        executable.write_bytes(b"another installer owns this")
        with patch.object(installer, "WINDOWS", True):
            with self.assertRaisesRegex(installer.InstallError, "shadow the managed launcher"):
                self.install()
        self.assertFalse(self.prefix.exists())
        self.assertEqual(executable.read_bytes(), b"another installer owns this")

    def test_cli_requires_offline_inputs_and_prints_usable_path_guidance(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
            installer.main(["--offline"])
        self.assertEqual(stopped.exception.code, 2)
        args = self.arguments(installer.DEFAULT_VERSION)
        output = io.StringIO()
        with patch.object(installer, "invoke", side_effect=self.fake_invoke), contextlib.redirect_stdout(output):
            result = installer.main(["--prefix", str(self.prefix), "--bin-dir", str(self.bin_dir),
                                     "--wheel", str(args.wheel), "--checksum-file", str(args.checksum_file),
                                     "--wheelhouse", str(self.wheelhouse), "--offline"])
        self.assertEqual(result, 0)
        self.assertIn(str(self.bin_dir), output.getvalue())
        self.assertIn("Add this directory to PATH", output.getvalue())
        self.assertIn("columbus explore", output.getvalue())
        self.assertIn("profiles and existing project files were not modified", output.getvalue())


if __name__ == "__main__":
    unittest.main()
