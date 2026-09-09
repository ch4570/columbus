"""Compare full Django facts and storage, then query the saved literal flag."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import zlib
from columbus.index import RepositoryIndex
from columbus.archive import archive, search_archive

p = argparse.ArgumentParser()
p.add_argument('repo', type=Path)
p.add_argument('before', type=Path)
p.add_argument('after', type=Path)
p.add_argument('artifacts', type=Path)
p.add_argument('output', type=Path)
a = p.parse_args()
a.artifacts.mkdir(exist_ok=False)
records = []
for db in [a.before, a.after]:
    with closing(sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True)) as c:
        hashes = dict(c.execute('SELECT path,hash FROM files'))
        facts = {p: json.loads(zlib.decompress(d)) for p, d in c.execute('SELECT path,parsed FROM files')}
        edges = set(c.execute('SELECT source,target,kind,path,line,confidence,evidence FROM edges'))
        fts = dict((row[0], row[1:]) for row in c.execute('SELECT id,name,path,body FROM search_documents'))
    assert all(hashlib.sha256((a.repo / p).read_bytes()).hexdigest() == h for p, h in hashes.items())
    records.append((hashes, facts, edges, fts))
old, new = records
assert old[0] == new[0]
assignments = []
for path, previous in old[1].items():
    current = new[1][path]
    added = [s for s in current['symbols'] if s['kind'] == 'assignment']
    assert previous == dict(current, symbols=[s for s in current['symbols'] if s['kind'] != 'assignment']), path
    assignments.extend(added)
assert not old[2] - new[2]
assert {e[1] for e in new[2] - old[2]} == {s['id'] for s in assignments}
assert all(e[2] == 'contains' for e in new[2] - old[2])
assert all(new[3][key] == value for key, value in old[3].items())
exports = []
for name, db in [('before', a.before), ('after', a.after)]:
    target = a.artifacts / (name + '.xz')
    result = archive(RepositoryIndex(db), target, 'xz')
    exports.append({'name': name, 'sqlite_bytes': db.stat().st_size,
                    'archive_bytes': target.stat().st_size,
                    'archive_sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
query = 'django.contrib.gis.gdal.raster.const.VSI_DELETE_BUFFER_ON_READ'
assert search_archive(a.artifacts / 'before.xz', query)['items'] == []
found = search_archive(a.artifacts / 'after.xz', query)['items']
assert len(found) == 1 and found[0]['kind'] == 'assignment'
assert found[0]['signature'] == 'VSI_DELETE_BUFFER_ON_READ = False'
result = {'files': len(old[0]), 'added_assignment_nodes': len(assignments),
          'source_manifest_sha256': hashlib.sha256(json.dumps(old[0], sort_keys=True).encode()).hexdigest(),
          'all_previous_facts_except_added_symbols_equal': True,
          'all_non_contains_edges_equal': True, 'all_previous_fts_documents_equal': True,
          'storage': exports, 'saved_flag_search': found,
          'model_trial': False, 'runtime_value_or_immutability_claimed': False}
a.output.write_text(json.dumps(result, indent=2) + '\n')
print({k: v for k, v in result.items() if k != 'saved_flag_search'})
