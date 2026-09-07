"""Show that a bundled local-version constraint prevents upstream fallback."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheelhouse', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    candidate = next(args.wheelhouse.glob('tree_sitter_java-0.23.5+columbus.1-*.whl'))
    with tempfile.TemporaryDirectory(prefix='columbus unavailable parser ') as temporary:
        root = Path(temporary)
        subprocess.run([sys.executable, '-m', 'pip', '--isolated', 'download', '--no-deps',
                                '--only-binary=:all:', '--dest', str(root), 'tree-sitter-java==0.23.5'],
                               check=True, capture_output=True, text=True, encoding='utf-8')
        # Deliberately use a platform tag unsupported by every target machine.
        shutil.copyfile(candidate, root/'tree_sitter_java-0.23.5+columbus.1-cp39-abi3-columbus_unavailable.whl')
        constraint = root/'constraints.txt'
        constraint.write_text('tree-sitter-java==0.23.5+columbus.1\n', encoding='ascii')
        command = [sys.executable, '-m', 'pip', '--isolated', 'install', '--dry-run', '--ignore-installed',
                   '--no-deps', '--no-index', '--find-links', str(root), 'tree-sitter-java==0.23.5']
        baseline = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        constrained = subprocess.run([*command, '--constraint', str(constraint)],
                                     capture_output=True, text=True, encoding='utf-8')
        assert baseline.returncode == 0, baseline.stderr
        assert 'tree-sitter-java-0.23.5' in baseline.stdout, baseline.stdout
        assert constrained.returncode != 0, constrained.stdout
        assert '0.23.5+columbus.1' in constrained.stdout + constrained.stderr
        result = {'unavailable_candidate_tag': 'columbus_unavailable', 'runtime_mutated': False,
                  'upstream_wheels': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in root.glob('tree_sitter_java-0.23.5-*.whl')},
                  'without_constraint': {'exit_code': baseline.returncode, 'stdout': baseline.stdout, 'stderr': baseline.stderr},
                  'with_constraint': {'exit_code': constrained.returncode, 'stdout': constrained.stdout, 'stderr': constrained.stderr}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('PASS: incompatible candidate fails instead of selecting available upstream wheel')


if __name__ == '__main__':
    main()
