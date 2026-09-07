"""Exercise a versioned archive in a moved, source-free consumer via the CLI."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

parser=argparse.ArgumentParser()
parser.add_argument('--compression',choices=['gzip','xz'],default='gzip')
options=parser.parse_args()
filename='demo-v1.jsonl.'+('gz' if options.compression=='gzip' else 'xz')
engine=Path(__file__).resolve().parents[2]/'skills/columbus/scripts/columbus.py'
def run(*args,cwd):
    return subprocess.check_output([str(a) for a in args],cwd=cwd,text=True)
def cli(root,*args):
    return json.loads(run(sys.executable,engine,*args,'--repo',root,cwd=root))
with tempfile.TemporaryDirectory() as temporary:
    producer=tempfile.TemporaryDirectory(prefix='producer-',dir=temporary)
    root=Path(producer.name)
    run('git','init','-q',cwd=root)
    (root/'.gitignore').write_text('.columbus/\n')
    (root/'demo.py').write_text('def target(): return 1\ndef entry(): return target()\n')
    initial=cli(root,'sync','--summary')
    artifact=root/'codegraph'/filename
    receipt=cli(root,'archive','--output',artifact,'--compression',options.compression)
    after=cli(root,'sync','--summary')
    assert after['files']==initial['files'] and after['refresh']['parsed_files']==0
    run('git','add','.gitignore','demo.py','codegraph/'+filename,cwd=root)
    run('git','-c','user.name=Archive Fixture','-c','user.email=fixture@example.invalid','commit','-qm','Store source and graph',cwd=root)
    tracked=run('git','ls-files',cwd=root).splitlines()
    assert 'codegraph/'+filename in tracked and not any('.columbus/' in p for p in tracked)
    consumer=Path(temporary)/'consumer';consumer.mkdir()
    moved=consumer/filename;shutil.copy2(artifact,moved)
    checksum=hashlib.sha256(moved.read_bytes()).hexdigest()
    producer.cleanup()
    found=cli(consumer,'archive-search','target','--input',moved,'--budget-bytes','2048')
    target=next(n['id'] for n in found['items'] if n['name']=='target')
    related=cli(consumer,'archive-neighbors',target,'--input',moved,'--direction','in','--kinds','calls','--budget-bytes','2048')
    assert len(related['edges'])==1 and related['nodes']
    assert related['next_offset'] is None and not related['semantic_complete']
    assert {p.name for p in consumer.iterdir()}=={filename}
    assert checksum==hashlib.sha256(moved.read_bytes()).hexdigest()
    print(json.dumps({'compression':options.compression,'tracked_paths':tracked,'archive_bytes':receipt['bytes'],'archive_sha256':checksum,
                     'artifact_excluded_from_source_index':True,'producer_deleted':True,
                     'consumer_files':[filename],'search':found,'relationships':related},indent=2))
