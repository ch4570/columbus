"""Runtime-traced generated fixtures for a missing Python receiver path.

Only these literal fixtures execute; no target repository/application code runs.
"""
import hashlib
import json
from pathlib import Path
import sys
from columbus.parser import parse_source, resolve_files

CASES = {
    'instance': '''class C:
    def helper(self): events.append('C.helper')
    def run(self): self.helper()
C().run()
''',
    'static_target': '''class C:
    @staticmethod
    def helper(): events.append('C.helper')
    def run(self): self.helper()
C().run()
''',
    'reassigned_receiver': '''class D:
    def helper(self): events.append('D.helper')
class C:
    def helper(self): events.append('C.helper')
    def run(self):
        self = D()
        self.helper()
C().run()
''',
    'overridden_receiver': '''class C:
    def helper(self): events.append('C.helper')
    def run(self): self.helper()
class D(C):
    def helper(self): events.append('D.helper')
D().run()
''',
    'assigned_attribute': '''class C:
    def helper(self): events.append('C.helper')
    def run(self):
        self.helper = lambda: events.append('replacement')
        self.helper()
C().run()
''',
    'static_parameter': '''class D:
    def helper(self): events.append('D.helper')
class C:
    def helper(self): events.append('C.helper')
    @staticmethod
    def run(self): self.helper()
C.run(D())
''',
    'decorated_target': '''def replace(fn):
    return lambda self: events.append('replacement')
class C:
    @replace
    def helper(self): events.append('C.helper')
    def run(self): self.helper()
C().run()
''',
    'nested_capture': '''class C:
    @staticmethod
    def helper(): events.append('C.helper')
    def run(self):
        def inner(): self.helper()
        inner()
C().run()
''',
}
EXPECTED = {'instance': 'C.helper', 'static_target': 'C.helper', 'reassigned_receiver': 'D.helper',
            'overridden_receiver': 'D.helper', 'assigned_attribute': 'replacement',
            'static_parameter': 'D.helper', 'decorated_target': 'replacement', 'nested_capture': 'C.helper'}
rows = []
for name, source in CASES.items():
    events = []
    exec(compile(source, name+'.py', 'exec'), {'events': events})
    assert events == [EXPECTED[name]], (name, events)
    parsed = parse_source(name+'.py', source, name)
    resolve_files([parsed])
    references = [r for r in parsed['references'] if r['name'] == 'self.helper']
    assert len(references) == 1
    rows.append({'name': name, 'source': source, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                 'runtime_events': events, 'receiver_reference': references[0]})
output = Path(sys.argv[1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({'python': sys.version,
    'analyzer_sha256': hashlib.sha256(Path(__file__).resolve().parents[2].joinpath('skills/columbus/scripts/columbus/parser.py').read_bytes()).hexdigest(),
    'cases': rows, 'scope': 'Eight literal generated fixtures; these executions do not prove general dispatch completeness.'}, indent=2)+'\n')
print('Observed eight runtime traces and graph receiver references')
