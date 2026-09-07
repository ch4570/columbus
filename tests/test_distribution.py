"""Distribution inventory and installed resource regression tests without network."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/columbus/scripts"))
sys.path.insert(0, str(ROOT / "scripts"))
from columbus import bundle


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("_columbus_zip_builder", ROOT / "scripts/build_bundle.py")
verifier = load("_columbus_distribution_verifier", ROOT / "scripts/verify_distribution.py")
release = load("_columbus_release_assets", ROOT / "scripts/release_assets.py")


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="columbus packaging ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_zip_reproducibility_complete_inventory_and_archive_validation(self):
        first = builder.build_bundle(ROOT, self.root / "first")
        second = builder.build_bundle(ROOT, self.root / "second")
        self.assertEqual(first["sha256"], second["sha256"])
        artifact = Path(first["artifact"])
        self.assertEqual(first["sha256"], hashlib.sha256(artifact.read_bytes()).hexdigest())
        extracted = verifier.verify_archive(artifact, self.root / "extract")
        inventory = json.loads((extracted / builder.INVENTORY).read_text(encoding="utf-8"))
        for relative in ("bootstrap.py", "install.py", "get-columbus.py", "run.py", "pyproject.toml", "setup.py",
                         "skills/columbus/SKILL.md", "skills/columbus/scripts/install.py",
                         "skills/columbus/scripts/columbus/bundle.py",
                         "README.ko.md", "docs/token-efficiency.md", "docs/assets/columbus-hero.png",
                         "evals/exploration/observe.py", "scripts/observe_delivery.py",
                         "scripts/verify_distribution.py", "tests/test_distribution.py"):
            self.assertIn(relative, inventory["files"])
        for relative in inventory["files"]:
            self.assertFalse(any(part in {".omx", ".columbus", ".git", "__pycache__", "dist", "build"} for part in Path(relative).parts))
        with zipfile.ZipFile(artifact) as archive:
            self.assertTrue(all(member.date_time == (1980, 1, 1, 0, 0, 0) for member in archive.infolist()))

    def test_archive_tampering_and_traversal_are_rejected(self):
        artifact = self.root / "tampered.zip"
        inventory = {"files": {"install.py": hashlib.sha256(b"original").hexdigest()}}
        with zipfile.ZipFile(artifact, "w") as archive:
            archive.writestr("columbus/BUNDLE-MANIFEST.json", json.dumps(inventory))
            archive.writestr("columbus/install.py", b"changed")
        with self.assertRaisesRegex(verifier.VerificationError, "checksum mismatch"):
            verifier.verify_archive(artifact, self.root / "extract")
        with zipfile.ZipFile(artifact, "w") as archive:
            archive.writestr("columbus/../outside.txt", b"bad")
        with self.assertRaisesRegex(verifier.VerificationError, "Unsafe archive path"):
            verifier.verify_archive(artifact, self.root / "extract")
        self.assertFalse((self.root / "outside.txt").exists())

    def test_release_checks_tag_bundle_and_default_installer_version_before_publication(self):
        source = self.root / 'source'
        package = source / 'skills/columbus/scripts/columbus'
        package.mkdir(parents=True)
        (package / '__init__.py').write_text('__version__ = "1.0.0"\n')
        metadata = source / 'skills/columbus/bundle.json'
        metadata.write_text('{"version":"1.0.0"}')
        installer = source / 'get-columbus.py'
        installer.write_text('DEFAULT_VERSION = "0.4.0"\n')
        dist = self.root / 'dist'
        dist.mkdir()
        for name in ('columbus-1.0.0-py3-none-any.whl', 'columbus-1.0.0.zip'):
            (dist / name).write_bytes(b'previously built artifact')
        with patch.object(release, 'ROOT', source):
            with self.assertRaisesRegex(ValueError, 'DEFAULT_VERSION'):
                release.prepare(dist, 'v1.0.0')
            self.assertFalse((dist / 'get-columbus.py').exists())
            installer.write_text('DEFAULT_VERSION = "1.0.0"\n')
            with self.assertRaisesRegex(ValueError, 'tag must match'):
                release.prepare(dist, 'v0.6.0')
            metadata.write_text('{"version":"0.4.0"}')
            with self.assertRaisesRegex(ValueError, 'bundle version'):
                release.prepare(dist, 'v1.0.0')
            metadata.write_text('{"version":"1.0.0"}')
            assets = release.prepare(dist, 'v1.0.0')
        self.assertEqual(len(assets), 4)
        self.assertEqual((dist / 'get-columbus.py').read_bytes(), installer.read_bytes())
        for line in (dist / 'SHA256SUMS.txt').read_text().splitlines():
            digest, name = line.split('  ', 1)
            self.assertEqual(digest, hashlib.sha256((dist / name).read_bytes()).hexdigest())

    def test_installed_resources_reconstruct_canonical_engine_and_preserve_edits(self):
        source = ROOT / "skills/columbus"
        installer = load("_columbus_resource_installer", source / "scripts/install.py")
        _, contents = installer._bundle(source)
        package = self.root / "installed site packages/columbus"
        resources = package / "_bundle"
        for relative, data in contents.items():
            if relative.startswith("scripts/columbus/"):
                path = package / Path(relative).name
            else:
                path = resources / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.assertFalse((resources / "scripts/columbus").exists())
        repo = self.root / "target repository with spaces"
        repo.mkdir()
        with patch.object(bundle, "__file__", str(package / "bundle.py")):
            with bundle.bundled_source() as reconstructed:
                _, rebuilt = installer._bundle(reconstructed)
                self.assertEqual(contents, rebuilt)
            self.assertFalse(reconstructed.exists())
            self.assertEqual(bundle.install_bundle(repo)["status"], "planned")
            self.assertFalse((repo / ".agents").exists())
            applied = bundle.install_bundle(repo, apply=True)
            self.assertEqual(applied["status"], "applied")
            self.assertEqual(bundle.install_bundle(repo, apply=True)["status"], "noop")
            local = repo / ".agents/skills/columbus/SKILL.md"
            local.write_text("Local instructions\n", encoding="utf-8")
            self.assertEqual(bundle.install_bundle(repo, apply=True)["status"], "conflict")
            self.assertEqual(local.read_text(encoding="utf-8"), "Local instructions\n")

    def test_source_checkout_uses_existing_bundle_without_staging(self):
        with bundle.bundled_source() as source:
            self.assertEqual(source, ROOT / "skills/columbus")


if __name__ == "__main__":
    unittest.main()
