#!/usr/bin/env python3
"""Model-free, source-checked spring-core CLI observation. Never builds Spring."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import platform
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

PIN = '4c8c6409a27a62ab163d3b6196ad862b7c835440'
RESOURCE = 'src/main/java/org/springframework/core/io/'
ANNOTATION = 'src/main/java/org/springframework/core/annotation/'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True, help='spring-core module')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline-db', type=Path, help='Optional crash-only-fixed snapshot for annotation comparison')
    args = parser.parse_args()
    root = args.repo.resolve()
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if head != PIN:
        parser.error(f'Expected Spring commit {PIN}, got {head}')
    dirty = subprocess.check_output(['git', '-C', str(root), 'diff', '--', '.'], text=True)
    if dirty:
        parser.error('Spring module must have no tracked modifications')
    if args.output.exists():
        parser.error('Choose a new output directory to preserve observations')
    args.output.mkdir(parents=True)
    records, cases = [], []
    def run(label, command):
        start = time.perf_counter()
        result = subprocess.run(command, capture_output=True)
        elapsed = time.perf_counter() - start
        (args.output / (label + '.stdout')).write_bytes(result.stdout)
        (args.output / (label + '.stderr')).write_bytes(result.stderr)
        records.append(dict(label=label, command=command, seconds=round(elapsed, 6),
                            returncode=result.returncode, output_bytes=len(result.stdout),
                            estimated_tokens=math.ceil(len(result.stdout)/3)))
        if result.returncode:
            raise RuntimeError(f'{label}: {result.stderr.decode(errors="replace")}')
        return result.stdout
    def check(name, passed, evidence):
        cases.append(dict(name=name, passed=bool(passed), evidence=evidence))
    def cli(label, *tail, db=None):
        return run(label, [sys.executable, '-m', 'columbus', '--repo', str(root), '--db', str(db or database), *tail])
    with tempfile.TemporaryDirectory(prefix='columbus-spring-observation-') as temp:
        work = Path(temp)
        syncs = []
        for n in range(3):
            database = work / f'index-{n}.sqlite'
            cold = json.loads(cli(f'cold-{n}', 'sync'))
            warm = json.loads(cli(f'warm-{n}', 'sync'))
            syncs.append(dict(cold=cold['refresh'], warm=warm['refresh'], db_bytes=database.stat().st_size))
        check('unchanged refresh parses and hashes zero files', all(s['warm']['parsed_files']==s['warm']['hashed_files']==0 for s in syncs), 'warm-{0,1,2}.stdout')
        connection = sqlite3.connect(database)
        symbols = [json.loads(row[0]) for row in connection.execute('select data from symbols')]
        def symbol(qualname):
            return next(s for s in symbols if s['qualname']==qualname)
        method = symbol('org.springframework.core.io.DefaultResourceLoader.getResource')
        resource = symbol('org.springframework.core.io.ClassPathResource')
        alias_query = ['search', 'AliasFor', '--snapshot', '--limit', '3']
        if args.baseline_db:
            before = json.loads(cli('annotation-before', *alias_query, db=args.baseline_db.resolve()))
        else:
            before = None
        after = json.loads(cli('annotation-after', *alias_query))
        check('AliasFor exact declaration ranks first', after['hits'][0]['qualname']=='org.springframework.core.annotation.AliasFor', 'annotation-after.stdout')
        aliases = [s for s in symbols if s['qualname'].startswith('org.springframework.core.annotation.AliasFor.')]
        check('AliasFor members have their annotation owner', {'value','attribute','annotation'} <= {s['name'] for s in aliases}, [s['id'] for s in aliases])
        imports = connection.execute('select count(*) from edges where kind="imports" and target=?', (after['hits'][0]['id'],)).fetchone()[0]
        check('AliasFor incoming imports exist', imports > 0, {'incoming_import_edges':imports})
        found = json.loads(cli('resource-search', 'search', method['qualname'], '--snapshot', '--limit','3'))
        check('resource entry point ranks first', found['hits'][0]['id']==method['id'], 'resource-search.stdout')
        source = json.loads(cli('resource-source', 'symbol', method['id'], '--snapshot','--max-lines','80'))
        actual_lines = (root / method['path']).read_text().splitlines()
        expected = '\n'.join(actual_lines[method['start_line']-1:method['end_line']])
        # Source rendering can include a final newline; compare contiguous lines.
        check('resource source matches original contiguous lines', source['source'].rstrip('\n')==expected.rstrip('\n'), 'resource-source.stdout')
        check('resource routing branches available in source', all(t in source['source'] for t in ['getProtocolResolvers()', 'CLASSPATH_URL_PREFIX', 'CLASSPATH_ALL_URL_PREFIX', 'ResourceUtils.toURL(location)', 'getResourceByPath(location)']), 'resource-source.stdout')
        cli('resource-calls', 'neighbors', method['id'], '--snapshot','--direction','out','--hops','1','--kinds','calls','--format','text')
        targets = [r[0] for r in connection.execute('select target from edges where source=? and kind="calls"',(method['id'],))]
        check('resource factory calls reach ClassPathResource and toURL', resource['id'] in targets and any('ResourceUtils.toURL:' in t for t in targets), 'resource-calls.stdout')
        cli('resource-inheritance','neighbors',resource['id'],'--snapshot','--direction','out','--hops','3','--kinds','inherits','--format','text')
        chain=['org.springframework.core.io.'+n for n in ['ClassPathResource','AbstractFileResolvingResource','AbstractResource','Resource']]
        check('three-hop Resource inheritance chain exists', all(connection.execute('select 1 from edges where source=? and target=? and kind="inherits"',(symbol(a)['id'],symbol(b)['id'])).fetchone() for a,b in zip(chain,chain[1:])), 'resource-inheritance.stdout')
        cli('resource-impact','impact',resource['id'],'--snapshot','--hops','1','--format','text')
        # Exact source comparison with ordinary bounded reads: no model savings claim.
        run('ordinary-search',['rg','-n','public Resource getResource',str(root / method['path'])])
        run('ordinary-source',[sys.executable,'-c','from pathlib import Path; import sys; print("\\n".join(Path(sys.argv[1]).read_text().splitlines()[int(sys.argv[2])-1:int(sys.argv[3])]))',str(root / method['path']),str(method['start_line']),str(method['end_line'])])
        receipt = work / 'receipt.json'
        for n in range(3):
            cli(f'receipt-{n}', 'context', method['id'],'--snapshot','--budget-bytes','6000','--format','json','--receipt',str(receipt))
            cli(f'no-receipt-{n}', 'context',method['id'],'--snapshot','--budget-bytes','6000','--format','json')
        delivered = []
        for n in range(3):
            response = json.loads((args.output / f'receipt-{n}.stdout').read_text())
            check(f'receipt response {n} fits 6000-byte budget', (args.output / f'receipt-{n}.stdout').stat().st_size <= 6001, f'receipt-{n}.stdout')
            if n == 0:
                check('exact-ID context returns intended routing source first',
                      bool(response.get('items')) and response['items'][0]['id']==method['id']
                      and 'CLASSPATH_URL_PREFIX' in response['items'][0].get('source',''),
                      'receipt-0.stdout')
            for item in response.get('items', []):
                if not item.get('source'):
                    continue
                span=(item['path'],item['source_start_offset'],item['source_end_offset'])
                check(f'receipt range {len(delivered)} does not repeat', not any(span[0]==old[0] and span[1]<old[2] and old[1]<span[2] for old in delivered), f'receipt-{n}.stdout')
                delivered.append(span)
        for fmt in ['json','html','mermaid','graphml']:
            cli('graph-'+fmt,'graph','--snapshot','--focus',resource['id'],'--level','symbol','--hops','2','--limit','100','--format',fmt,'--output',str(args.output / ('resource-graph.'+fmt)))
        parsed = [json.loads(r[0]) for r in connection.execute('select parsed from files')]
        refs = [r for p in parsed for r in p.get('references',[])]
        from collections import Counter
        graph = dict(files=len(parsed), symbols=len(symbols), source_bytes=sum(r[0] for r in connection.execute('select size from files')),
                     edges=dict(connection.execute('select kind,count(*) from edges group by kind')),
                     references=len(refs),resolved=sum(bool(r['resolved']) for r in refs),
                     unresolved_reasons=dict(Counter(r.get('reason','other') for r in refs if not r['resolved'])),
                     partial_files=[dict(path=p['path'],diagnostics=p['diagnostics']) for p in parsed if p.get('partial')])
        check('partial ResolvableType remains flagged (known grammar limitation)', any('ResolvableType.java' in p['path'] for p in graph['partial_files']), graph['partial_files'])
        check('ambiguous overloads stay unresolved', any(not r['resolved'] and r.get('member')=='notNull' for r in refs), 'unresolved reference census; no compiler dispatch claim')
        connection.close()
        target = root / method['path']; original=target.read_bytes()
        try:
            target.write_bytes(original+b'\n// Columbus incremental benchmark\n')
            edit=json.loads(cli('one-file-edit','sync'))
            check('one-file edit reparses exactly one file',edit['refresh']['parsed_files']==1,'one-file-edit.stdout')
        finally:
            target.write_bytes(original)
        cli('restore','sync')
        manifest={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file() and '.columbus' not in p.parts}
        result=dict(spring_commit=head,python=sys.version,platform=platform.platform(),model_calls=0,model_billed_cost_usd=0,
                    model_tokens=None,notes='Fresh databases; OS caches not cleared. Timings include CLI startup. Payload bytes/3 are not model tokens. Includes production, tests, JMH and resources.',
                    syncs=syncs,graph=graph,cases=cases,commands=records,
                    baseline_alias_exact=bool(before and before['hits'] and before['hits'][0]['qualname']=='org.springframework.core.annotation.AliasFor'))
        (args.output/'source-sha256.json').write_text(json.dumps(manifest,indent=2)+'\n')
        (args.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(dict(cases=len(cases),passed=sum(c['passed'] for c in cases),graph=graph,syncs=syncs),indent=2))
        return 0 if all(c['passed'] for c in cases) else 1

if __name__=='__main__':
    raise SystemExit(main())
