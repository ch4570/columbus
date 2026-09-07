"""Opt-in local Git hook installation and compact working-tree synchronization."""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
import shlex
import subprocess
import sys

from .index import RepositoryIndex
from .sync_state import git_state


def update(root: Path, db: Path | None = None, *, strict: bool = False) -> dict:
    """Index the visible worktree. Never stage files or claim Git-index parity."""
    result = RepositoryIndex(db or root / '.columbus/index-v1.sqlite').refresh(
        root, fast=True, require_complete=strict)
    fidelity = result['analyzer_fingerprint']['fidelity']
    coverage = Counter(fidelity.get(language, 'text') for language in
                       result['inventory'].get('detected_languages', {}).values())
    return dict(scope='visible_worktree', revision=result['revision'],
                files=result['files'], parsed_files=result['refresh']['parsed_files'],
                removed_files=result['refresh']['removed_files'],
                diagnostics=len(result['diagnostics']),
                fidelity_files=dict(coverage),
                parse_complete=not result['diagnostics'],
                semantic_complete=False, elapsed_seconds=result['refresh']['elapsed_seconds'])


def install(root: Path, *, apply: bool = False) -> dict:
    """Install only into an unoccupied standard hook path; never chain unknown code."""
    state = git_state(root)
    if not state['is_git'] or Path(state['worktree_root']) != root:
        raise ValueError('Hook installation requires the Git worktree root')
    configured = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-C', str(root),
                                 'config', '--get', 'core.hooksPath'],
                                capture_output=True, text=True, timeout=10)
    if configured.returncode not in {0, 1}:
        raise ValueError('Cannot inspect core.hooksPath')
    if configured.returncode == 0:
        raise ValueError('core.hooksPath is configured; add columbus hook-update to your existing hook manager')
    directory = Path(state['common_dir']) / 'hooks'
    if directory.is_symlink():
        raise ValueError('Symlink hook directories are refused')
    target = directory / 'pre-commit'
    # Git runs pre-commit at the committing worktree root. Do not bake a repo
    # path into a hook that is shared by linked worktrees.
    python = str(Path(sys.executable).absolute()).replace('\\', '/')
    bundled_entry = Path(__file__).resolve().parent.parent / 'columbus.py'
    is_bundle = bundled_entry.is_file() and (bundled_entry.parent.parent / 'SKILL.md').is_file()
    entry = ([python, str(bundled_entry).replace('\\', '/')]
             if is_bundle else [python, '-m', 'columbus'])
    content = ('#!/bin/sh\n# Columbus managed pre-commit v1\n'
               '# Refresh the visible worktree; never modify the Git index.\n'
               'exec ' + ' '.join(shlex.quote(arg) for arg in entry) + ' hook-update --repo .\n').encode()
    if target.is_symlink():
        raise ValueError('Existing symlink pre-commit hook is preserved')
    if target.exists():
        if not target.is_file() or target.read_bytes() != content:
            raise ValueError('Existing pre-commit hook is preserved; add columbus hook-update to your hook manager')
        if not os.access(target, os.X_OK):
            raise ValueError('Managed hook is not executable; restore its executable permission')
        return dict(status='noop', path=str(target), scope='shared_git_hooks')
    if apply:
        directory.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(content)
        target.chmod(0o755)
    return dict(status='installed' if apply else 'planned', path=str(target),
                scope='shared_git_hooks', interpreter=python)
