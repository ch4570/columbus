"""Stage skill resources into the wheel without a second copy of the engine."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithSkill(build_py):
    def run(self):
        super().run()
        source = Path(__file__).resolve().parent / "skills/repoatlas-jvm"
        spec = importlib.util.spec_from_file_location("_repoatlas_build_installer", source / "scripts/install.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        manifest, contents = installer._bundle(source)
        if manifest["version"] != self.distribution.get_version():
            raise ValueError("Package and skill bundle versions must match before distribution")
        target = Path(self.build_lib) / "repoatlas/_bundle"
        # Incremental builds must not retain resources removed from the source.
        if target.exists():
            shutil.rmtree(target)
        for relative, data in contents.items():
            if relative.startswith("scripts/repoatlas/"):
                continue
            path = target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)


setup(cmdclass={"build_py": BuildWithSkill})
