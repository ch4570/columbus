"""Compare frozen engine traversal to the independently recorded task oracle."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
output = Path(sys.argv[1])
destination = Path(sys.argv[2])
spec = importlib.util.spec_from_file_location('observe', root/'evals/exploration/observe.py')
observe = importlib.util.module_from_spec(spec); spec.loader.exec_module(observe)
sys.path.insert(0, str(output/'runtime'))
from columbus.index import RepositoryIndex
oracle = json.loads((Path(__file__).with_name('oracle.json')).read_text())
manifest = json.loads((output/'manifest.json').read_text())
engine = json.loads((output/'engine.json').read_text())
assert manifest['fixture_sha256'] == oracle['fixture_sha256']
assert manifest['source_manifest'] == oracle['source_hashes']
assert observe.manifest(output/'repository') == manifest['source_manifest']
assert observe.manifest(output/'runtime') == engine['files']
db = output/'repository/.columbus/index-v1.sqlite'
before_hash = hashlib.sha256(db.read_bytes()).hexdigest()
index = RepositoryIndex(db)
packet = index.neighbors('safe_source', direction='in', hops=3, limit=200,
                         kinds=['calls'], include_candidates=True)
assert packet['revision'] == engine['index']['revision'] and not packet['truncated']
names = {n['id']:n['qualname'] for n in packet['nodes']}
expected_methods = {f['id'] for f in oracle['findings']}
actual_methods = {n['qualname'] for n in packet['nodes'] if n['qualname'].startswith('RepositoryIndex.')}
assert actual_methods == expected_methods, (actual_methods, expected_methods)
edges = {(names[e['source']],names[e['target']],e['path'],e['line']):e for e in packet['edges']}
matched = []
for finding in oracle['findings']:
    path = []
    for edge in finding['shortest_path']:
        found = edges[(edge['owner'],edge['target'],edge['path'],edge['line'])]
        assert found['kind'] == ('candidate_calls' if edge['callee'].startswith('self.') else 'calls')
        path.append(found)
    matched.append({'id':finding['id'],'hops':finding['hops'],'edges':path})
assert hashlib.sha256(db.read_bytes()).hexdigest() == before_hash
receipt = {'source_unchanged':True,'engine_unchanged':True,'index_sha256':before_hash,
           'revision':packet['revision'],'matched':matched,'truncated':packet['truncated']}
destination.write_text(json.dumps(receipt,indent=2)+'\n')
print('Four methods and all shortest handoffs match the independent oracle; frozen inputs unchanged.')
