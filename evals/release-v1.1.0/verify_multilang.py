"""Fixed multilingual release contracts, not whole-language semantic accuracy."""
import argparse
import gzip
import hashlib
import json
import lzma
from pathlib import Path
import tempfile

from columbus.archive import archive, callers_archive, search_archive, source_archive
from columbus.index import RepositoryIndex
from columbus.languages import parse_source

SAMPLES = [
 ('main.py', 'python', 'ast', 'def helper(): pass\ndef run(): helper()\n'),
 ('Demo.java', 'java', 'ast', 'class Demo { void helper() {} void run() { helper(); } }'),
 ('main.kt', 'kotlin', 'ast', 'fun helper() {}\nfun run() { helper() }'),
 ('main.js', 'javascript', 'heuristic', 'function helper() {}\nfunction run() { helper(); }'),
 ('main.ts', 'typescript', 'heuristic', 'function helper(): void {}\nfunction run(): void { helper(); }'),
 ('main.jsx', 'javascript', 'heuristic', 'function helper() {}\nfunction run() { return <div>helper(){helper()}</div>; }'),
 ('main.tsx', 'typescript', 'heuristic', 'function helper() {}\nfunction run() { return <div>helper(){helper()}</div>; }'),
 ('main.go', 'go', 'heuristic', 'package main\nfunc helper() {}\nfunc run() { helper() }'),
 ('main.rs', 'rust', 'heuristic', 'fn helper() {}\nfn run() { helper(); }'),
 ('main.c', 'c', 'heuristic', 'void helper(void) {}\nvoid run(void) { helper(); }'),
 ('main.cpp', 'cpp', 'heuristic', 'void helper() {}\nvoid run() { helper(); }'),
 ('main.cs', 'csharp', 'heuristic', 'static void helper() {}\nstatic void run() { helper(); }'),
 ('main.php', 'php', 'heuristic', '<?php\nfunction helper() {}\nfunction run() { helper(); }'),
 ('main.swift', 'swift', 'heuristic', 'func helper() {}\nfunc run() { helper() }'),
 ('main.dart', 'dart', 'heuristic', 'void helper() {}\nvoid run() { helper(); }'),
 ('literal.jsx', 'javascript', 'heuristic', 'function helper() {}\nfunction run() { return <div>helper() function fake()</div>; }'),
 ('literal.tsx', 'typescript', 'heuristic', 'function helper() {}\nfunction run() { return <div>helper() function fake()</div>; }'),
 ('generic.tsx', 'typescript', 'heuristic', 'function helper() {}\nconst id = <T extends Foo>(value: T) => helper() || "</T>";\nfunction run() { helper(); }'),
 ('return-type.tsx', 'typescript', 'heuristic', 'function helper() {}\nconst id = <T extends object>(value: T): unknown => helper() || "</T>";\nfunction run() { helper(); }'),
 ('regex.tsx', 'typescript', 'heuristic', 'function helper() {}\nfunction run() { return <div>{true && /}/.test(value) ? helper() : null}helper()</div>; }'),
 ('notes.unknown', 'text', 'text', 'function fake()\nhelper() is documentation, not executable source.\n'),
]


def verify(path, language, fidelity, source):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / 'repo'; root.mkdir()
        (root / path).write_text(source, encoding='utf-8')
        index = RepositoryIndex(Path(directory) / 'index.sqlite')
        index.refresh(root)
        facts = parse_source(path, source)
        assert facts['language'] == language and facts['fidelity'] == fidelity
        graph = index.graph()
        nodes = graph['nodes']
        helpers = [n for n in nodes if n['name'] == 'helper']
        calls = [e for e in graph['edges'] if e['kind'] == 'calls']
        if fidelity == 'text':
            assert not calls and not helpers and len(nodes) == 1
        else:
            assert len(helpers) == 1
            expected_calls = 0 if path.startswith('literal.') else (2 if path in {'generic.tsx', 'return-type.tsx'} else 1)
            assert len(calls) == expected_calls and all(c['target'] == helpers[0]['id'] for c in calls), calls
            assert not any(n['name'] == 'fake' for n in nodes)
        assert all(n['fidelity'] == fidelity for n in nodes)
        exports = []
        for codec, opener in [('gzip', gzip.open), ('xz', lzma.open)]:
            output = Path(directory) / ('graph.' + codec)
            receipt = archive(index, output, codec)
            with opener(output, 'rt', encoding='utf-8') as stream:
                rows = [json.loads(line) for line in stream]
            archived_nodes = [r['data'] for r in rows if r['record'] == 'node']
            archived_edges = [r['data'] for r in rows if r['record'] == 'edge']
            assert sorted(archived_nodes, key=lambda n:n['id']) == sorted(nodes, key=lambda n:n['id'])
            canonical = lambda items: sorted(json.dumps(x, sort_keys=True) for x in items)
            assert canonical(archived_edges) == canonical(graph['edges'])
            if helpers:
                found = search_archive(output, 'helper')['items']
                assert any(n['id'] == helpers[0]['id'] for n in found)
                incoming = callers_archive(output, helpers[0]['id'])
                assert len(incoming['edges']) == len(calls)
                excerpt = source_archive(output, helpers[0]['id'], root)
                assert 'helper' in excerpt['source']
            exports.append({'codec': codec, 'bytes': receipt['bytes'], 'sha256': hashlib.sha256(output.read_bytes()).hexdigest()})
        changed = source.replace('helper', 'renamed')
        (root / path).write_text(changed, encoding='utf-8')
        update = index.refresh(root)
        assert update['refresh']['parsed_files'] == 1
        fresh = RepositoryIndex(Path(directory) / 'fresh.sqlite'); fresh.refresh(root)
        assert index.graph() == fresh.graph()
        return {'files':1, 'nodes':len(nodes), 'calls':len(calls), 'archives':exports, 'incremental_fresh_parity':True}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True); args=parser.parse_args()
    results=[]
    for path, language, fidelity, source in SAMPLES:
        row={'path':path,'language':language,'fidelity':fidelity,'source':source,'source_sha256':hashlib.sha256(source.encode()).hexdigest()}
        try:
            row.update(verify(path,language,fidelity,source));row['passed']=True
        except Exception as error:
            row.update(passed=False,error=repr(error))
        results.append(row)
    report={'scope':'Fixed language/fidelity, exact simple call, lossless archive and incremental parity contracts. No population precision or actual-token claim.',
            'runtime_sha256':{n:hashlib.sha256((Path(__file__).resolve().parents[2] / 'skills/columbus/scripts/columbus' / n).read_bytes()).hexdigest() for n in ('__init__.py','languages.py','parser.py','jvm.py','polyglot.py','index.py','archive.py')},
            'required_pass_rate':1.0,'passed':all(r['passed'] for r in results),'cases':results}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'cases':len(results),'failures':[{k:r[k] for k in ('path','error')} for r in results if not r['passed']]}))
    return 0 if report['passed'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
