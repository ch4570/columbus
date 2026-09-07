"""Compare Java access/static-context call gates with javac and frozen failures."""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from columbus.jvm import parse_jvm, resolve_jvm

HERE = Path(__file__).resolve().parent
EXTRA = [
    ("static_initializer_instance", False, "class T { void hit() {} static { hit(); } }"),
    ("static_initializer_static", True, "class T { static void hit() {} static { hit(); } }"),
    ("static_field_instance", False, "class T { int hit() { return 1; } static int value = hit(); }"),
    ("instance_field_instance", True, "class T { int hit() { return 1; } int value = hit(); }"),
    ("static_field_static", True, "class T { static int hit() { return 1; } static int value = hit(); }"),
    ("interface_field_instance", False, "interface T { int hit(); int value = hit(); }"),
    ('outer_instance_from_static_nested', False, 'class T { void hit() {} static class C { void run() { hit(); } } }'),
    ('outer_instance_from_inner', True, 'class T { void hit() {} class C { void run() { hit(); } } }'),
    ('own_instance_in_static_nested', True, 'class T { static class C { void hit() {} void run() { hit(); } } }'),
    ('outer_instance_from_nested_interface', False, 'class T { void hit() {} interface C { default void run() { hit(); } } }'),
    ('outer_instance_from_record', False, 'class T { void hit() {} record C() { void run() { hit(); } } }'),
    ('outer_instance_from_enum', False, 'class T { void hit() {} enum C { ONE; void run() { hit(); } } }'),
    ('outer_instance_from_interface_member', False, 'interface T { void hit(); class C { void run() { hit(); } } }'),
    ('explicit_value_from_static', True, 'class T { void hit() {} static void run(T item) { item.hit(); } }'),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('jdk', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    prior = json.loads((HERE/'results/access-discovery/value-receivers.json').read_text())
    cases = [(c['name'], c['compiler_valid'], c['source']) for c in prior['cases']] + EXTRA
    compiler = subprocess.check_output([str(args.jdk/'javac'), '-version'], text=True).strip()
    rows = []
    with tempfile.TemporaryDirectory(prefix='columbus access oracle ') as temporary:
        for name, valid, source in cases:
            root = Path(temporary)/name
            root.mkdir()
            path = root/'C.java'
            path.write_text(source, encoding='utf-8')
            run = subprocess.run([str(args.jdk/'javac'), '-proc:none', '-d', str(root), str(path)],
                                 capture_output=True, text=True, encoding='utf-8')
            assert (run.returncode == 0) == valid, (name, run.stderr)
            parsed = parse_jvm('C.java', source)
            assert not parsed['partial'], name
            edges = resolve_jvm([parsed])
            calls = [r for r in parsed['references'] if r['kind'] == 'calls' and r['member'] == 'hit']
            passed = len(calls) == 1 and calls[0]['resolved'] == valid
            rows.append({'name': name, 'source': source, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                         'compiler_valid': valid, 'compiler_exit': run.returncode, 'compiler_stderr': run.stderr,
                         'references': calls, 'call_edges': [e for e in edges if e['kind'] == 'calls'], 'passed': passed})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'compiler': compiler,
        'versions': {name: version(name) for name in ('tree-sitter', 'tree-sitter-java', 'tree-sitter-kotlin')},
        'analyzer_sha256': hashlib.sha256((HERE.parents[1]/'skills/columbus/scripts/columbus/jvm.py').read_bytes()).hexdigest(),
        'cases': rows, 'passed': all(r['passed'] for r in rows)}, indent=2)+'\n', encoding='utf-8')
    assert all(r['passed'] for r in rows), [(r['name'], r['references']) for r in rows if not r['passed']]
    print(f'PASS: {len(rows)} compiler-backed access/static-context cases')


if __name__ == '__main__':
    main()
