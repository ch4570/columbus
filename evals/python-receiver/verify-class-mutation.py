"""Compare a literal runtime counterexample against two parser revisions."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[2]
relative = 'skills/columbus/scripts/columbus/parser.py'
source = '''class C:
    def helper(self): events.append('original')
    def run(self): self.helper()
C.helper = lambda self: events.append('replacement')
C().run()
'''
events = []
exec(compile(source, 'fixture.py', 'exec'), {'events': events})
assert events == ['replacement']
rows = {}
with tempfile.TemporaryDirectory() as tmp:
    before = Path(tmp) / 'before.py'
    before.write_bytes(subprocess.check_output(['git', 'show', 'e1f1d09:' + relative], cwd=repo))
    for label, path in [('before', before), ('after', repo / relative)]:
        spec = importlib.util.spec_from_file_location(label, path)
        parser = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(parser)
        parsed = parser.parse_source('fixture.py', source, 'fixture')
        edges = parser.resolve_files([parsed])
        ref = next(r for r in parsed['references'] if r['name'] == 'self.helper')
        assert not ref['resolved']
        assert not any(e['evidence'] == 'self.helper' for e in edges)
        assert bool(ref.get('retrieval_candidates')) == (label == 'before')
        rows[label] = {'parser_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'reference': ref}
result = {'baseline_commit': 'e1f1d09', 'source': source, 'runtime_events': events, 'observations': rows,
          'scope': 'Literal generated fixture only; does not execute repository source or prove general mutation analysis.'}
(repo / 'evals/python-receiver/class-mutation.json').write_text(json.dumps(result, indent=2) + '\n')
print('Reproduced old misleading candidate and verified its suppression; stored calls unchanged.')
