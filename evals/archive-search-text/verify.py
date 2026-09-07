"""Recheck the unsupported CLI command, without replaying a model trial."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
p=argparse.ArgumentParser();p.add_argument('artifact',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
checksum=hashlib.sha256(a.artifact.read_bytes()).hexdigest()
cli=Path(__file__).parents[2]/'skills/columbus/scripts/columbus.py'
base=[sys.executable,str(cli),'archive-search','urlencode','--input',str(a.artifact),'--budget-bytes','6000']
plain=json.loads(subprocess.check_output(base,text=True))
text=subprocess.check_output([*base,'--format','text'],text=True)
lines=text.splitlines();metadata=json.loads(lines[1][9:]);items=[json.loads(line) for line in lines[3:]]
assert dict(metadata,items=items)==plain
assert len(text.encode())<=6000
assert hashlib.sha256(a.artifact.read_bytes()).hexdigest()==checksum
a.output.write_text(json.dumps({'archive_sha256':checksum,'text_bytes':len(text.encode()),'matched_nodes':plain['matched_nodes'],'returned_nodes':len(items),'packet_parity':True,'archive_unchanged':True,'model_trial':False},indent=2)+'\n')
