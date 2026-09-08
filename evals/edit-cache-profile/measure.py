"""Profile a one-file edit in an isolated full source copy; retain no source changes."""
import argparse,cProfile,hashlib,json,pstats,shutil,tempfile
from pathlib import Path
from columbus.index import RepositoryIndex
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
with tempfile.TemporaryDirectory(prefix='columbus edit profile ') as directory:
 root=Path(directory)/'source';shutil.copytree(a.source,root,ignore=shutil.ignore_patterns('.git','.columbus','__pycache__'))
 index=RepositoryIndex(Path(directory)/'index.sqlite');before=index.refresh(root)
 target=root/'django/utils/encoding.py';original=target.read_bytes();target.write_bytes(original+b'\n# isolated profiling edit\n')
 profile=cProfile.Profile();profile.enable();edited=index.refresh(root,fast=True);profile.disable()
 stats=pstats.Stats(profile);rows=[]
 for (filename,line,name),(cc,nc,tt,ct,callers) in sorted(stats.stats.items(),key=lambda x:x[1][3],reverse=True)[:30]:rows.append({'file':Path(filename).name,'line':line,'name':name,'calls':nc,'own_seconds':tt,'cumulative_seconds':ct})
 target.write_bytes(original);restored=index.refresh(root,fast=True)
 assert [before[k] for k in ('files','symbols','edges')]==[restored[k] for k in ('files','symbols','edges')]
 result={'files':before['files'],'symbols':before['symbols'],'edges':before['edges'],'edit':edited['refresh'],'profile':rows,'restored_counts_equal':True,'scope':'Instrumented one-edit diagnosis, temporary copy, unflushed caches; no latency speedup or complete graph parity claim.'}
a.output.write_text(json.dumps(result,indent=2)+'\n');print(rows[:8])
