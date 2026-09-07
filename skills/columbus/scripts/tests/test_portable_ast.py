"""Real Git commit/update tests and parent-closed AST navigation contracts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from columbus.hooks import install, update
from columbus.index import RepositoryIndex
from columbus.tree import records


class PortableASTTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='columbus portable 한글 ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        # Source-suite subprocesses need the same engine as their parent.
        # Clean-wheel/pre-commit integration is verified separately.
        environment = patch.dict(os.environ, {'PYTHONPATH': str(Path(__file__).resolve().parents[1])})
        environment.start()
        self.addCleanup(environment.stop)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        (self.root / '.gitignore').write_text('.columbus/\n')
        (self.root / 'sample.py').write_text('def staged():\n    return 1\n')
        self.index = RepositoryIndex(self.root / '.columbus/index-v1.sqlite')

    def git(self, *args):
        return subprocess.check_output(['git', '-c', 'core.fsmonitor=false', '-C', str(self.root), *args],
                                       stderr=subprocess.STDOUT, text=True)

    def test_hook_plan_existing_hook_and_custom_hook_path_are_preserved(self):
        target = self.root / '.git/hooks/pre-commit'
        self.assertEqual('planned', install(self.root)['status'])
        self.assertFalse(target.exists())
        target.write_text('#!/bin/sh\nexit 0\n')
        with self.assertRaisesRegex(ValueError, 'preserved'):
            install(self.root, apply=True)
        self.assertEqual('#!/bin/sh\nexit 0\n', target.read_text())
        target.unlink()
        self.git('config', 'core.hooksPath', 'custom-hooks')
        with self.assertRaisesRegex(ValueError, 'core.hooksPath'):
            install(self.root, apply=True)
        self.assertFalse(target.exists())

    def test_native_commit_preserves_partial_staging_and_updates_visible_worktree(self):
        self.assertEqual('installed', install(self.root, apply=True)['status'])
        self.assertEqual('noop', install(self.root, apply=True)['status'])
        self.git('add', '.gitignore', 'sample.py')
        (self.root / 'sample.py').write_text('def unstaged():\n    return 2\n')
        output = self.git('commit', '-qm', 'Fixture commit')
        self.assertIn('visible_worktree', output)
        self.assertIn('staged', self.git('show', 'HEAD:sample.py'))
        self.assertNotIn('unstaged', self.git('show', 'HEAD:sample.py'))
        self.assertTrue(self.index.search('unstaged')['hits'])
        self.assertFalse(self.index.search('staged')['hits'])
        self.assertIn('sample.py', self.git('diff', '--name-only'))
        self.assertNotIn('.columbus', self.git('ls-tree', '-r', '--name-only', 'HEAD'))

    def test_delete_only_and_strict_parse_failure_preserve_snapshot(self):
        update(self.root)
        revision = self.index.status()['revision']
        (self.root / 'sample.py').write_text('def broken(:\n')
        with self.assertRaisesRegex(ValueError, 'previous index preserved'):
            update(self.root, strict=True)
        self.assertEqual(revision, self.index.status()['revision'])
        self.assertTrue(self.index.search('staged')['hits'])
        partial = update(self.root)
        self.assertFalse(partial['parse_complete'])
        self.assertGreater(partial['diagnostics'], 0)
        (self.root / 'sample.py').unlink()
        result = update(self.root)
        self.assertEqual(1, result['removed_files'])
        self.assertFalse(self.index.search('staged')['hits'])

    def test_ast_tree_label_subtree_parent_closure_and_fallback(self):
        (self.root / 'sample.py').write_text('class Owner:\n    def member(self):\n        return 1\n')
        (self.root / 'notes.txt').write_text('searchable notes')
        update(self.root)
        rows = records(self.index, label='Owner')
        self.assertEqual(1, rows[0]['matches'])
        self.assertEqual(['module', 'class', 'method'], [r['kind'] for r in rows[1:]])
        emitted = set()
        for row in rows[1:]:
            self.assertTrue(row['parent_id'] is None or row['parent_id'] in emitted)
            self.assertEqual('ast', row['fidelity'])
            self.assertEqual(64, len(row['source_hash']))
            emitted.add(row['id'])
        bounded = records(self.index, label='Owner', limit=2)
        self.assertTrue(bounded[0]['truncated'])
        self.assertEqual(2, bounded[0]['nodes'])
        self.assertFalse(any(r.get('path') == 'notes.txt' for r in records(self.index)))
        self.assertTrue(any(r.get('path') == 'notes.txt' for r in records(self.index, include_fallback=True)))
        self.assertEqual(0, records(self.index, label='missing')[0]['nodes'])

    def test_cli_jsonl_and_source_context_preserve_parse_warning(self):
        (self.root / 'C.java').write_text('class C { void run() {} void broken( { }')
        update(self.root)
        rows = records(self.index, label='C')
        self.assertTrue(any(r.get('partial') for r in rows))
        target = self.index.search('run')['hits'][0]
        packet = self.index.context(target['id'])
        self.assertTrue(packet['items'][0]['partial'])
        neighbors = self.index.neighbors(target['id'])
        self.assertFalse(neighbors['semantic_complete'])
        result = subprocess.run([sys.executable, '-m', 'columbus', 'tree', '--repo', str(self.root),
                                 '--label', 'C'], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        rendered = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual('tree', rendered[0]['record'])
        self.assertGreater(rendered[0]['diagnostics'], 0)

    def test_shared_hook_uses_committing_worktree(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'Initial')
        install(self.root, apply=True)
        linked = self.root.parent / (self.root.name + '-linked')
        self.git('worktree', 'add', '-qb', 'linked', str(linked))
        self.addCleanup(lambda: self.git('worktree', 'remove', '--force', str(linked)))
        (linked / 'sample.py').write_text('def linked_only():\n    pass\n')
        subprocess.run(['git', '-C', str(linked), 'add', 'sample.py'], check=True)
        subprocess.run(['git', '-C', str(linked), 'commit', '-qm', 'Linked change'], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        linked_index = RepositoryIndex(linked / '.columbus/index-v1.sqlite')
        self.assertTrue(linked_index.search('linked_only')['hits'])
        self.assertEqual(str(linked.resolve()), linked_index.status()['root'])
        self.assertFalse(self.index.db.exists())


if __name__ == '__main__':
    unittest.main()
