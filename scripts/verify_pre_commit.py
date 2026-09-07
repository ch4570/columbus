#!/usr/bin/env python3
"""Exercise pre-commit's partial-staging restore with an isolated wheel install."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile


def verify(wheel: Path, pre_commit: Path) -> dict:
    environment = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV'):
        environment.pop(key, None)
    with tempfile.TemporaryDirectory(prefix='columbus pre-commit ') as temp:
        root = Path(temp).resolve()
        environment['PRE_COMMIT_HOME'] = str(root / 'cache')
        repo = root / 'consumer'
        repo.mkdir()
        def run(args):
            result = subprocess.run([str(v) for v in args], cwd=repo, env=environment,
                                    capture_output=True, text=True, encoding='utf-8')
            if result.returncode:
                raise RuntimeError(f'{args}: {result.stdout}\n{result.stderr}')
            return result.stdout + result.stderr
        run(['git', 'init', '-q'])
        for key, value in [('user.name', 'Fixture'), ('user.email', 'fixture@example.invalid'),
                           ('commit.gpgsign', 'false')]:
            run(['git', 'config', key, value])
        (repo / '.gitignore').write_text('.columbus/\n', encoding='utf-8')
        # JSON is also valid YAML; quote the wheel path without shell expansion.
        config = {'repos': [{'repo': 'local', 'hooks': [{
            'id': 'columbus-sync', 'name': 'Columbus fixture', 'entry': 'columbus hook-update',
            'language': 'python', 'additional_dependencies': [str(wheel.resolve())],
            'pass_filenames': False, 'always_run': True, 'require_serial': True, 'verbose': True}]}]}
        (repo / '.pre-commit-config.yaml').write_text(json.dumps(config), encoding='utf-8')
        source = repo / 'sample.py'
        source.write_text('def staged_source():\n    return 1\n', encoding='utf-8')
        run(['git', 'add', '.'])
        source.write_text('def restored_source():\n    return 2\n', encoding='utf-8')
        run([pre_commit, 'install', '--install-hooks'])
        output = run(['git', 'commit', '-qm', 'Partial staging'])
        if 'staged_source' not in run(['git', 'show', 'HEAD:sample.py']) or 'restored_source' not in source.read_text():
            raise AssertionError('Framework altered staged or unstaged source')
        # Inspect the graph produced while pre-commit hid unstaged tracked edits.
        import sqlite3
        connection = sqlite3.connect(repo / '.columbus/index-v1.sqlite')
        names = {r[0] for r in connection.execute('SELECT name FROM symbols')}
        connection.close()
        if 'staged_source' not in names or 'restored_source' in names:
            raise AssertionError('Graph does not match the framework-visible snapshot')
        # The consumer uses the same isolated hook environment to explore again.
        candidates = list((root / 'cache').glob('repo*/py_env-*/bin/columbus'))
        candidates += list((root / 'cache').glob('repo*/py_env-*/Scripts/columbus.exe'))
        if len(candidates) != 1:
            raise AssertionError(f'Expected one isolated Columbus command: {candidates}')
        packet = json.loads(run([candidates[0], 'search', 'restored_source']))
        if not packet['hits'] or packet['hits'][0]['name'] != 'restored_source':
            raise AssertionError('Exploration did not refresh after framework restoration')
        # Deletion-only commits must run, even with no source filenames to pass.
        run(['git', 'rm', '-f', 'sample.py'])
        deletion = run(['git', 'commit', '-qm', 'Delete source'])
        if 'removed_files' not in deletion or 'visible_worktree' not in output:
            raise AssertionError('Compact hook report was not visible')
        packet = json.loads(run([candidates[0], 'search', 'restored_source', '--snapshot']))
        if packet['hits']:
            raise AssertionError('Deleted source remained searchable')
        return dict(status='passed', isolated_wheel=True, partial_staging_preserved=True,
                    framework_snapshot=True, restoration_refresh=True, deletion_only=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', required=True, type=Path)
    parser.add_argument('--pre-commit', type=Path, default=shutil.which('pre-commit'))
    args = parser.parse_args()
    if args.pre_commit is None:
        parser.error('Install the pre-commit test dependency or pass --pre-commit PATH')
    args.pre_commit = Path(args.pre_commit)
    print(json.dumps(verify(args.wheel, args.pre_commit.resolve()), indent=2))
