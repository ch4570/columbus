import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from columbus.archive import archive
from columbus.index import RepositoryIndex
from preflight import digest, file_manifest, verify

class ArchivePreflightTests(unittest.TestCase):
    def test_both_codecs_and_independent_failure_controls(self):
        for codec in ['gzip','xz']:
            with self.subTest(codec=codec), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);repo=root/'repo';repo.mkdir();runtime=root/'runtime';runtime.mkdir()
                (repo/'demo.py').write_text('def target(): pass\ndef entry(): target()\n')
                (runtime/'engine.py').write_text('# frozen runtime\n')
                index=RepositoryIndex(repo/'.columbus/index.sqlite');index.refresh(repo)
                artifact=root/'graph';receipt=archive(index,artifact,compression=codec)
                shutil.rmtree(repo/'.columbus')
                expected={'source_manifest':file_manifest(repo),'runtime_manifest':file_manifest(runtime),
                          'archive_sha256':digest(artifact),'revision':receipt['revision'],
                          'counts':{key:receipt[key] for key in ['files','nodes','scopes','edges','references','imports','diagnostics']}}
                self.assertTrue(verify(repo,runtime,artifact,expected)['passed'])
                (repo/'.columbus').mkdir()
                with self.assertRaisesRegex(ValueError,'local index'):verify(repo,runtime,artifact,expected)
                (repo/'.columbus').rmdir()
                old=(repo/'demo.py').read_bytes();(repo/'demo.py').write_bytes(old+b'# changed\n')
                with self.assertRaisesRegex(ValueError,'source or runtime'):verify(repo,runtime,artifact,expected)
                stale=copy.deepcopy(expected);stale['source_manifest']=file_manifest(repo)
                with self.assertRaisesRegex(ValueError,'Archive source hash'):verify(repo,runtime,artifact,stale)
                (repo/'demo.py').write_bytes(old)
                (runtime/'engine.py').write_text('# changed runtime\n')
                with self.assertRaisesRegex(ValueError,'source or runtime'):verify(repo,runtime,artifact,expected)
                (runtime/'engine.py').write_text('# frozen runtime\n')
                wrong=copy.deepcopy(expected);wrong['counts']['edges']+=1
                with self.assertRaisesRegex(ValueError,'counts'):verify(repo,runtime,artifact,wrong)
                original=artifact.read_bytes();artifact.write_bytes(original[:-8])
                with self.assertRaisesRegex(ValueError,'checksum'):verify(repo,runtime,artifact,expected)
                artifact.write_bytes(original)
                self.assertTrue(verify(repo,runtime,artifact,expected)['passed'])

if __name__=='__main__':unittest.main()
