import importlib.util,json,pathlib,statistics,subprocess,sys,tempfile,time,hashlib
from columbus.index import RepositoryIndex
root=pathlib.Path(sys.argv[1]).resolve()
baseline_ref = sys.argv[2] if len(sys.argv) > 2 else '4d55a34'
with tempfile.TemporaryDirectory() as temp:
    temp=pathlib.Path(temp)
    baseline=temp/'baseline.py'
    baseline.write_bytes(subprocess.check_output(['git','show',baseline_ref + ':skills/columbus/scripts/columbus/index.py']))
    spec=importlib.util.spec_from_file_location('columbus.baseline_index',baseline)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    out={'corpus_commit':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),'os_cache':'not flushed; baseline first; shared host load uncontrolled','baseline_commit':subprocess.check_output(['git','rev-parse',baseline_ref],text=True).strip(),'after_sha256':hashlib.sha256(pathlib.Path('skills/columbus/scripts/columbus/index.py').read_bytes()).hexdigest()}
    db=temp/'index.sqlite'
    before=mod.RepositoryIndex(db);after=RepositoryIndex(db)
    initial=before.refresh(root)
    out['files']=initial['files'];out['indexed_bytes']=initial['indexed_bytes'];out['database_bytes']=db.stat().st_size
    graph_before=before.graph()
    for name,index in [('before',before),('after',after)]:
        if name == 'after':
            index.refresh(root, fast=True)  # Exclude one-time storage migration.
        rows=[]
        for _ in range(5):
            start=time.perf_counter();r=index.refresh(root,fast=True)
            rows.append({'seconds':time.perf_counter()-start,'refresh':r['refresh']})
        out[name]={'runs':rows,'median_seconds':statistics.median(r['seconds'] for r in rows)}
    graph_after=after.graph()
    graph_before.pop('revision', None); graph_after.pop('revision', None)
    out['bounded_graph_equal']=graph_before==graph_after
    print(json.dumps(out,indent=2))
