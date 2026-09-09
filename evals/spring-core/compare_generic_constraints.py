"""Same-source graph comparison, allowing only additive syntax facts."""
from pathlib import Path
import argparse,copy,json,sqlite3,hashlib
from columbus.index import RepositoryIndex,decode_parse
p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
oldroot=args.baseline;out=args.output;out.mkdir(parents=True,exist_ok=False);root=args.repo
index=RepositoryIndex(out/'index.sqlite');status=index.refresh(root)
def load(db):
 with sqlite3.connect(db) as c:
  facts={r[0]:decode_parse(r[1]) for r in c.execute('select path,parsed from files')}
  calls={(r[0],r[1],r[2],r[3]) for r in c.execute("select source,target,path,line from edges where kind='calls'")}
  hashes={r[0]:r[1] for r in c.execute('select path,hash from files')}
 return facts,calls,hashes
before,old,oldhash=load(oldroot/'index.sqlite');after,new,newhash=load(out/'index.sqlite');assert oldhash==newhash
for path in before:
 def core(f):
  f=copy.deepcopy(f)
  for ref in f['references']:
   for k in ['resolved','target','reason','confidence','retrieval_candidates','argument_facts','explicit_type_arguments','expected_type']:ref.pop(k,None)
  for i in f['imports']:
   for k in ['resolved','target','confidence']:i.pop(k,None)
  for s in f['symbols']:s.pop('return_type',None)
  for s in f.get('_scopes',{}).values():s.pop('return_type',None)
  return f
 assert core(before[path])==core(after[path]),path
assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in newhash.items())
recovered={tuple([r['edge'][k] for k in ['source','target','path','line']]) for r in [json.loads(l) for l in (oldroot/'removed.jsonl').read_text().splitlines()]}
refs={(r['source'],r['path'],r['line'],r.get('evidence')):r for f in after.values() for r in f['references']}
with sqlite3.connect(oldroot/'index.sqlite') as c:
 evidence={(r[0],r[1],r[2],r[3]):r[4] for r in c.execute("select source,target,path,line,evidence from edges where kind='calls'")}
result={'before_calls':len(old),'after_calls':len(new),'added':len(new-old),'removed':len(old-new),'recovered_previous_32':len(recovered&new),
        'source_unchanged':True,'base_syntax_facts_unchanged':True,
        'removed_edges':[{'source':e[0],'target':e[1],'path':e[2],'line':e[3],'reason':refs.get((e[0],e[2],e[3],evidence[e]),{}).get('reason')} for e in sorted(old-new)],
        'added_edges':[{'source':e[0],'target':e[1],'path':e[2],'line':e[3]} for e in sorted(new-old)],
        'fingerprint':status['analyzer_fingerprint']}
(out/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
print({k:v for k,v in result.items() if k not in ['removed_edges','added_edges','fingerprint']})
