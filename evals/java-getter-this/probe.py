"""Compiler oracle for this arguments in newly supported getter loops."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import columbus.jvm as jvm

p = argparse.ArgumentParser()
p.add_argument('--jdk', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--require-no-false', action='store_true')
a = p.parse_args()
results = []
for parameter, valid in [('C', True), ('API', True), ('Other', False)]:
    source = ('interface API {} class Other {} class Item { void hit(' + parameter +
              ' x) {} } class C implements API { Item[] items() { return null; } '
              'void run() { for(Item item : items()) item.hit(this); } }')
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / 'C.java').write_text(source, encoding='utf-8')
        compiler = subprocess.run([str(a.jdk / 'javac'), '-proc:none', str(root / 'C.java')],
                                  capture_output=True, text=True)
        assert (compiler.returncode == 0) == valid, compiler.stderr
        bytecode = subprocess.run([str(a.jdk / 'javap'), '-classpath', str(root), '-c', '-p', 'C'],
                                  capture_output=True, text=True, check=True).stdout if valid else None
        if valid:
            assert 'Method Item.hit:(L' + parameter + ';)V' in bytecode
        parsed = jvm.parse_jvm('C.java', source)
        jvm.resolve_jvm([parsed])
        call, = [r for r in parsed['references'] if r['member'] == 'hit']
        expected = 'C.java::Item.hit:method(' + parameter + ')' if valid else None
        results.append(dict(parameter=parameter, source=source,
                            source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                            javac_return_code=compiler.returncode, diagnostics=compiler.stderr,
                            javap=bytecode, expected_target=expected, actual=call))
report = dict(analyzer_sha256=hashlib.sha256(Path(jvm.__file__).read_bytes()).hexdigest(), cases=results,
              false_edges=sum(bool(r['actual'].get('target')) and r['actual'].get('target') != r['expected_target'] for r in results))
a.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print('Cases:', len(results), 'false edges:', report['false_edges'])
if a.require_no_false:
    assert report['false_edges'] == 0
