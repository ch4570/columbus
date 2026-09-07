"""Negative call-edge gate with javac/javap evidence, no project build executed."""
import hashlib
import importlib.util
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from columbus.jvm import parse_jvm, resolve_jvm

base = Path(__file__).resolve().parent
jdk = Path(sys.argv[1])
output = Path(sys.argv[2]) if len(sys.argv) > 2 else base / 'results'
output.mkdir(parents=True, exist_ok=True)
compiler_version = subprocess.run([str(jdk / 'javac'), '-version'], capture_output=True, text=True, check=True)
report = {'javac_version': (compiler_version.stdout + compiler_version.stderr).strip(),
          'analyzer_sha256': hashlib.sha256(Path('skills/columbus/scripts/columbus/jvm.py').read_bytes()).hexdigest(),
          'versions': {name: version(name) for name in ('columbus', 'tree-sitter', 'tree-sitter-java', 'tree-sitter-kotlin')},
          'baseline_commit': '4d55a3438f375aada7ca063aa3dba434bc1a3725', 'cases': []}
with tempfile.TemporaryDirectory() as directory:
    directory = Path(directory)
    baseline = directory / 'baseline.py'
    baseline.write_bytes(subprocess.check_output(['git', 'show', report['baseline_commit'] + ':skills/columbus/scripts/columbus/jvm.py']))
    spec = importlib.util.spec_from_file_location('baseline_jvm', baseline)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    for name, expected_instruction in [('Generic', 'InterfaceMethod API.hit:()V'), ('Inherited', 'Method hit:(I)V')]:
        source_path = base / 'fixtures' / (name + '.java')
        source = source_path.read_text()
        subprocess.run([str(jdk / 'javac'), '-proc:none', '-d', str(directory), str(source_path)], check=True, capture_output=True)
        bytecode = subprocess.run([str(jdk / 'javap'), '-c', '-p', '-classpath', str(directory), name],
                                  check=True, capture_output=True, text=True).stdout
        (output / (name + '.javap.txt')).write_text(bytecode)
        assert expected_instruction in bytecode, bytecode
        case = {'name': name, 'source_sha256': hashlib.sha256(source_path.read_bytes()).hexdigest(),
                'compiler_expected_instruction': expected_instruction}
        for label, parse, resolve in [('before', old.parse_jvm, old.resolve_jvm), ('after', parse_jvm, resolve_jvm)]:
            parsed = parse(source_path.name, source)
            assert not parsed['diagnostics'], parsed['diagnostics']
            edges = resolve([parsed])
            calls = [r for r in parsed['references'] if r['kind'] == 'calls']
            case[label] = {'references': calls, 'call_edges': [e for e in edges if e['kind'] == 'calls']}
        assert case['before']['call_edges'], case
        assert not case['after']['call_edges'], case
        assert all(not r['resolved'] and r['reason'] for r in case['after']['references'])
        report['cases'].append(case)
(output / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS: compiler-backed false-edge gate for both issue #8 fixtures')
