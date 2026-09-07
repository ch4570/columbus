"""Verify pinned -> candidate -> warm candidate via the actual bootstrap installer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import bootstrap


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheelhouse', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--bundle', type=Path, help='Upgrade through this bundled-parser ZIP without --wheelhouse')
    args = parser.parse_args()
    reports = []
    with tempfile.TemporaryDirectory(prefix='columbus bootstrap upgrade ') as temporary:
        scratch = Path(temporary).resolve()
        repo = scratch/'target repository'
        repo.mkdir()
        source = repo / 'C.java'
        raw = b'class C { void hit(int @A ... values) {} void run() { hit(1); } }'
        source.write_bytes(raw)
        extracted = None
        if args.bundle:
            sys.path.insert(0, str(ROOT/'scripts'))
            from verify_distribution import verify_archive
            extracted = verify_archive(args.bundle, scratch/'extracted')
        for candidates in (None, args.wheelhouse.resolve(), args.wheelhouse.resolve()):
            install_source = ROOT
            if candidates and extracted:
                if len(reports) == 2:
                    relocated = scratch/'relocated bundle source'
                    extracted.rename(relocated)
                    extracted = relocated
                install_source = extracted
            command = [sys.executable, str(install_source/'install.py'), '--repo', str(repo)]
            if candidates and not extracted:
                command += ['--wheelhouse', str(candidates)]
            run = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8')
            python = bootstrap.interpreter(repo, repo/'.columbus/runtime')
            worker = '''
import importlib.metadata as m, json, sqlite3, sys
from columbus.index import decode_parse
with sqlite3.connect(sys.argv[1]) as db:
    parsed = decode_parse(db.execute("SELECT parsed FROM files WHERE path='C.java'").fetchone()[0])
print(json.dumps({'version': m.version('tree-sitter-java'), 'partial': parsed['partial']}))
'''
            probe = subprocess.run([str(python), '-c', worker, str(repo/'.columbus/index-v1.sqlite')],
                                   check=True, capture_output=True, text=True, encoding='utf-8',
                                   env=os.environ | {'PYTHONPATH': str(ROOT/'skills/columbus/scripts')})
            observation = json.loads(probe.stdout)
            logdir = args.output.parent / (args.output.stem + '-logs')
            logdir.mkdir(parents=True, exist_ok=True)
            (logdir / f'{len(reports)}.stdout.txt').write_text(run.stdout, encoding='utf-8')
            (logdir / f'{len(reports)}.stderr.txt').write_text(run.stderr, encoding='utf-8')
            observation.update(runtime_state=bootstrap.runtime_state(repo, repo/'.columbus/runtime'),
                               pip_ran='Install pinned dependencies' in run.stderr,
                               install_stdout_sha256=hashlib.sha256(run.stdout.encode()).hexdigest(),
                               install_stderr_sha256=hashlib.sha256(run.stderr.encode()).hexdigest())
            reports.append(observation)
            assert source.read_bytes() == raw
        assert [r['version'] for r in reports] == ['0.23.5', '0.23.5+columbus.1', '0.23.5+columbus.1'], reports
        assert [r['partial'] for r in reports] == [True, False, False], reports
        assert [r['pip_ran'] for r in reports] == [True, True, False], reports
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'source_unchanged': True, 'bundled_default': bool(args.bundle), 'bundle_sha256': hashlib.sha256(args.bundle.read_bytes()).hexdigest() if args.bundle else None, 'runs': reports}, indent=2)+'\n', encoding='utf-8')
    print('PASS: existing bootstrap environment adopts candidate; warm rerun skips pip')


if __name__ == '__main__':
    main()
