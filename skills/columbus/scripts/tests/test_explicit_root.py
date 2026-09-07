from pathlib import Path
import subprocess
import tempfile
import unittest

from columbus.discovery import discover
from columbus.index import RepositoryIndex


class ExplicitRootTests(unittest.TestCase):
    def test_explicit_directory_ignored_by_enclosing_repo_uses_filesystem(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            subprocess.run(['git','init','-q',str(parent)],check=True)
            (parent/'.gitignore').write_text('ignored/\n')
            root = parent/'ignored/project'
            root.mkdir(parents=True)
            (root/'app.py').write_text('def useful(): return 1\n')
            paths, inventory = discover(root)
            self.assertEqual(paths,['app.py'])
            self.assertIn('explicit',inventory['enumeration'])
            index=RepositoryIndex(root/'.columbus/index.sqlite')
            self.assertEqual(index.refresh(root)['files'],1)
            self.assertEqual(index.search('useful')['hits'][0]['name'],'useful')

    def test_all_ignored_files_in_selected_git_root_stay_excluded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            subprocess.run(['git','init','-q',str(root)],check=True)
            (root/'.gitignore').write_text('*.py\n')
            (root/'private.py').write_text('def hidden(): return 1\n')
            paths,_=discover(root)
            self.assertEqual(paths,[])


if __name__ == '__main__': unittest.main()
