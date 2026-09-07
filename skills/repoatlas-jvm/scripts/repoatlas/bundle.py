"""Install the same managed skill from a checkout, wheel, pipx, or uv tool."""
from __future__ import annotations

from contextlib import contextmanager
import importlib.util
from pathlib import Path
import shutil
import tempfile
from typing import Iterator


@contextmanager
def bundled_source() -> Iterator[Path]:
    package = Path(__file__).resolve().parent
    resources = package / "_bundle"
    if not resources.is_dir():
        # A source checkout, editable install, or repository-local skill already
        # has a complete bundle beside the canonical package.
        source = package.parent.parent
        if not (source / "SKILL.md").is_file() or not (source / "scripts/install.py").is_file():
            raise FileNotFoundError("RepoAtlas skill resources are missing; reinstall the package")
        yield source
        return
    with tempfile.TemporaryDirectory(prefix="repoatlas-bundle-") as temporary:
        source = Path(temporary).resolve() / "repoatlas-jvm"
        shutil.copytree(resources, source)
        engine = source / "scripts/repoatlas"
        engine.mkdir()
        for module in sorted(package.glob("*.py")):
            shutil.copyfile(module, engine / module.name)
        yield source


def install_bundle(repo: str | Path, *, apply: bool = False,
                   skills_dir: str = ".agents/skills") -> dict:
    """Plan or install pinned skill files; preserve locally modified content."""
    with bundled_source() as source:
        spec = importlib.util.spec_from_file_location("_repoatlas_installer", source / "scripts/install.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        return installer.install_bundle(Path(repo), source, apply=apply, skills_dir=skills_dir)
