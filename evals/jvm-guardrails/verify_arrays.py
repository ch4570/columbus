"""Compiler-backed array literal applicability gate, with baseline traces."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from columbus.jvm import parse_jvm, resolve_jvm

cases = [
    ('int[]', '1', False), ('String[]', '"x"', False), ('Object[]', 'true', False),
    ('int[]...', '1', False), ('int[][]', "'x'", False), ('Object[]', '1.0', False),
    ('int[]', 'null', True), ('String[]', 'null', True), ('int[]...', '', True),
    ('int[]...', 'null, null', True), ('Object...', '1', True), ('int[]...', '(int[]) null', True),
]

output = Path(sys.argv[2])
output.mkdir(parents=True, exist_ok=True)
javac = str(Path(sys.argv[1]) / 'javac')
report = {'baseline_commit': '9d190fa', 'compiler': subprocess.run([javac, '-version'], check=True, capture_output=True, text=True).stdout.strip(),
          'analyzer_sha256': hashlib.sha256(Path('skills/columbus/scripts/columbus/jvm.py').read_bytes()).hexdigest(), 'cases': []}
with tempfile.TemporaryDirectory() as directory:
    directory = Path(directory)
    old = directory / 'old.py'
    old.write_bytes(subprocess.check_output(['git', 'show', report['baseline_commit'] + ':skills/columbus/scripts/columbus/jvm.py']))
    spec = importlib.util.spec_from_file_location('old_jvm', old)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for parameter, argument, expected in cases:
        source = f'class C {{ void hit({parameter} value) {{}} void run() {{ hit({argument}); }} }}'
        (directory / 'C.java').write_text(source)
        compiler = subprocess.run([javac, '-proc:none', 'C.java'], cwd=directory, capture_output=True, text=True)
        assert (compiler.returncode == 0) == expected, compiler.stderr
        case = {'source': source, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(), 'expected_valid': expected,
                'compiler_exit': compiler.returncode, 'compiler_stderr': compiler.stderr}
        for label, parse, resolve in [('before', module.parse_jvm, module.resolve_jvm), ('after', parse_jvm, resolve_jvm)]:
            parsed = parse('C.java', source)
            assert not parsed['partial'], parsed['diagnostics']
            resolve([parsed])
            case[label] = next(r for r in parsed['references'] if r['kind'] == 'calls')
        assert case['after']['resolved'] == expected, case
        report['cases'].append(case)
(output / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS: 12 array/varargs cases match javac')
