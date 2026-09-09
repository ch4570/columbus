"""Verify optional navigation on the frozen source without running its code."""
import hashlib
import json
import sys
from pathlib import Path
import tempfile
import time
import zipfile
from columbus.index import RepositoryIndex

repo = Path(__file__).resolve().parents[2]
fixture = repo / 'evals/exploration/fixtures/columbus-source-c67b20a.zip'
with tempfile.TemporaryDirectory() as tmp:
    with zipfile.ZipFile(fixture) as archive:
        archive.extractall(tmp)
    root = Path(tmp) / 'columbus-source'
    index = RepositoryIndex(Path(tmp) / 'index.sqlite')
    status = index.refresh(root)
    prefix = 'skills/columbus/scripts/columbus/'
    start = prefix + 'index.py::RepositoryIndex.symbol:method'
    end = prefix + 'discovery.py::safe_source:function'
    expected = [(start, prefix + 'index.py::RepositoryIndex._source:method', 'candidate_calls'),
                (prefix + 'index.py::RepositoryIndex._source:method', prefix + 'sync_state.py::read_stable:function', 'calls'),
                (prefix + 'sync_state.py::read_stable:function', end, 'calls')]
    observations = {}
    for enabled in (False, True):
        before = time.perf_counter()
        packet = index.neighbors(end, direction='in', hops=3, limit=200, kinds=['calls'], include_candidates=enabled)
        elapsed = time.perf_counter() - before
        triples = {(e['source'], e['target'], e['kind']) for e in packet['edges']}
        present = [edge in triples for edge in expected]
        assert present == ([True, True, True] if enabled else [False, True, True]), present
        observations[str(enabled)] = {'elapsed_seconds': elapsed, 'expected_path_present': present,
                                     'nodes': len(packet['nodes']), 'edges': len(packet['edges']),
                                     'truncated': packet['truncated'],
                                     'path_edges': [e for e in packet['edges'] if (e['source'], e['target'], e['kind']) in expected]}
    assert not any(e['kind'] == 'candidate_calls' for e in index.graph()['edges'])
    result = {'fixture_sha256': hashlib.sha256(fixture.read_bytes()).hexdigest(),
              'analyzer_sha256': hashlib.sha256((repo / 'skills/columbus/scripts/columbus/parser.py').read_bytes()).hexdigest(),
              'observations': observations,
              'scope': 'Source-reviewed three-hop navigation path; first hop remains an uncertain candidate. No model token trial.'}
(Path(sys.argv[1]) if len(sys.argv) > 1 else repo / 'evals/python-receiver/candidate-path.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: {key: value for key, value in v.items() if key != 'path_edges'} for k, v in observations.items()}))
