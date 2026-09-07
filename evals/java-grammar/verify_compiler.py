"""Check grammar fixture validity with javac, not either grammar as oracle."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

base = Path(__file__).resolve().parent
pinned = json.loads((base / 'results/pinned.json').read_text())
javac = str(Path(sys.argv[1]) / 'javac')
report = {'javac_version': subprocess.run([javac, '-version'], check=True, capture_output=True, text=True).stdout.strip(), 'cases': {}}
for name, fixture in pinned['fixtures'].items():
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        (directory / 'C.java').write_text(fixture['source'])
        for annotation in ('A', 'B'):
            (directory / (annotation + '.java')).write_text('@java.lang.annotation.Target(java.lang.annotation.ElementType.TYPE_USE) @interface ' + annotation + ' {}')
        completed = subprocess.run([javac, '-proc:none', 'A.java', 'B.java', 'C.java'], cwd=directory,
                                   capture_output=True, text=True)
        expected = name != 'invalid_after_ellipsis'
        assert (completed.returncode == 0) == expected, completed.stderr
        report['cases'][name] = {'source_sha256': fixture['sha256'], 'expected_valid': expected,
                                'returncode': completed.returncode, 'stdout': completed.stdout, 'stderr': completed.stderr}
(base / 'results/compiler.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS: javac accepts three legal annotation forms and rejects after-ellipsis annotation')
