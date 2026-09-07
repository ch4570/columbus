"""Exercise real package-version cache invalidation across fresh processes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('candidate_target', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
engine = Path(__file__).resolve().parents[2] / 'skills/columbus/scripts'
worker = '''
import json, sys
from columbus.index import RepositoryIndex, decode_parse
from contextlib import closing
import sqlite3
index = RepositoryIndex(sys.argv[2])
report = index.refresh(sys.argv[1], fast=True)
with closing(sqlite3.connect(index.db)) as conn:
    parsed = decode_parse(conn.execute('SELECT parsed FROM files').fetchone()[0])
print(json.dumps({'version': report['analyzer_fingerprint']['versions']['tree-sitter-java'],
                  'refresh': report['refresh'], 'revision': report['revision'],
                  'partial': parsed['partial']}))
'''
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    source = root / 'C.java'
    raw = b'class C { void hit(int @A ... values) {} void run() { hit(1); } }'
    source.write_bytes(raw)
    reports = []
    for candidate in (False, True, True, False):
        env = dict(os.environ)
        env['PYTHONPATH'] = os.pathsep.join(([str(args.candidate_target.resolve())] if candidate else []) + [str(engine)])
        result = subprocess.run([sys.executable, '-c', worker, str(root), str(root / '.columbus/index.sqlite')],
                                env=env, check=True, capture_output=True, text=True)
        reports.append(json.loads(result.stdout))
        assert source.read_bytes() == raw
    assert [r['version'] for r in reports] == ['0.23.5', '0.23.5+columbus.1', '0.23.5+columbus.1', '0.23.5']
    assert [r['partial'] for r in reports] == [True, False, False, True]
    assert [r['refresh']['parsed_files'] for r in reports] == [1, 1, 0, 1]
    assert reports[1]['revision'] == reports[2]['revision']
    assert reports[0]['revision'] != reports[1]['revision']
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps({'source_unchanged': True, 'runs': reports}, indent=2) + '\n', encoding='utf-8')
print('PASS: pinned -> candidate -> warm candidate -> pinned rebuilds only when required')
