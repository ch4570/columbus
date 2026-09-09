"""Compiler oracle for calls newly exposed by annotated-varargs parsing."""
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from columbus.jvm import parse_jvm, resolve_jvm

assert version('tree-sitter-java') == '0.23.5+columbus.1'
javac = str(Path(sys.argv[1]) / 'javac')
cases = [('int', '1', True), ('int', '', True), ('int', '1, 2', True),
         ('long', '1', True), ('int', "'x'", True), ('int', 'null', True),
         ('int', 'true', False), ('int', '1L', False), ('int', '1, null', False),
         ('int', '"x"', False), ('byte', '1', False), ('boolean', '1', False)]
report = {'grammar_version': version('tree-sitter-java'),
          'javac_version': subprocess.check_output([javac, '-version'], text=True).strip(),
          'analyzer_sha256': hashlib.sha256(Path('skills/columbus/scripts/columbus/jvm.py').read_bytes()).hexdigest(),
          'scope': 'single local method; primitive annotated varargs and literal arguments', 'cases': []}
for parameter, argument, expected in cases:
    source = f'class C {{ void hit({parameter} @A ... values) {{}} void run() {{ hit({argument}); }} }}'
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / 'C.java').write_text(source, encoding='utf-8')
        (root / 'A.java').write_text('@java.lang.annotation.Target(java.lang.annotation.ElementType.TYPE_USE) @interface A {}', encoding='utf-8')
        compiled = subprocess.run([javac, '-proc:none', 'A.java', 'C.java'], cwd=root, capture_output=True, text=True)
    assert (compiled.returncode == 0) == expected, compiled.stderr
    parsed = parse_jvm('C.java', source)
    assert not parsed['partial']
    resolve_jvm([parsed])
    calls = [r for r in parsed['references'] if r['kind'] == 'calls']
    assert len(calls) == 1
    assert calls[0]['resolved'] == expected, calls
    report['cases'].append({'source': source, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                            'expected_valid': expected, 'javac_exit': compiled.returncode,
                            'javac_stderr': compiled.stderr, 'reference': calls[0]})
Path(sys.argv[2]).write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print('PASS: 12 newly eligible annotated-varargs calls match javac (6 valid, 6 invalid)')
