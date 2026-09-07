"""Reproduce and correct a hash-verified excerpt whose Unicode line count was wrong."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASELINE = '5b24630df7ef3a647ee2b27d7d08f3cd9a8b4bc1'
worker = '''
import json,sys
from pathlib import Path
from columbus.index import RepositoryIndex
from columbus.presentation import render
root=Path(sys.argv[1]);index=RepositoryIndex(root/'.columbus/index.sqlite');sync=index.refresh(root)
p=index.callers('target',output_format='text')
print(json.dumps({'caller':p,'text':render(p,'text','callers'),'symbol':index.symbol('caller'),'refresh':sync['refresh']}))
'''
with tempfile.TemporaryDirectory() as temporary:
    scratch = Path(temporary)
    old = scratch/'old/columbus'
    shutil.copytree(ROOT/'skills/columbus/scripts/columbus', old, ignore=shutil.ignore_patterns('__pycache__'))
    for name in ('index.py', 'languages.py', 'presentation.py', 'retrieval.py'):
        (old/name).write_bytes(subprocess.check_output(['git', '-C', str(ROOT), 'show', BASELINE+':skills/columbus/scripts/columbus/'+name]))
    repo = scratch/'repo'
    repo.mkdir()
    raw = 'def target(): pass\ndef caller():\n    value = "a\u2028b"\n    target()\n'.encode()
    source = repo/'x.py'
    source.write_bytes(raw)
    rows = []
    for engine in (old.parent, ROOT/'skills/columbus/scripts'):
        rows.append(json.loads(subprocess.check_output([sys.executable, '-c', worker, str(repo)],
            env=os.environ | {'PYTHONPATH': str(engine)}, text=True, encoding='utf-8')))
        assert source.read_bytes() == raw
    before, after = rows
    assert 'target()' not in before['caller']['items'][0]['source']
    item = after['caller']['items'][0]
    assert item['call_line'] == 4 and item['source'].split('\n')[1] == '    target()'
    assert '\u2028' in item['source'] and '4|     target()' in after['text']
    assert item['source_hash'] == before['caller']['items'][0]['source_hash'] == hashlib.sha256(raw).hexdigest()
    assert after['symbol']['source_view_hash'] != before['symbol']['source_view_hash']
    result = {'baseline_revision': BASELINE, 'source': raw.decode(), 'source_unchanged': True,
              'before': before, 'after': after,
              'interpretation': 'Raw hash equality did not prove the old excerpt matched its cited lines. The corrected decoded-view hash invalidates old receipt spans.'}
output = Path(sys.argv[1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
print('PASS: raw source preserved, wrong excerpt corrected, receipt view fingerprint changed')
