"""Independent AST/import inventory, without importing Django or Columbus."""
import ast
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

p=argparse.ArgumentParser();p.add_argument('repo',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
result={'revision':subprocess.check_output(['git','-C',str(a.repo),'rev-parse','HEAD'],text=True).strip(),'targets':{},'runtime_executed':False}
assert result['revision']=='4ea267661b260ea0d0c87e9dcb99d70037c6f2fc'
exclusions = json.loads(Path(__file__).with_name('attribute-exclusions.json').read_text())
expected_attributes = {(x['path'], x['line'], x['quote']) for x in exclusions}
seen_attributes = set()
for target in ['force_bytes']:
    findings=[];files=0
    for path in sorted((a.repo/'django').rglob('*.py')):
        source=path.read_bytes();tree=ast.parse(source,filename=str(path));files+=1
        relative=path.relative_to(a.repo).as_posix();digest=hashlib.sha256(source).hexdigest()
        recorded=result.setdefault('production_source_manifest',{}).setdefault(relative,digest)
        assert recorded==digest, path
        imports=[n for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module=='django.utils.encoding' and any(x.name==target for x in n.names)]
        assert all(n in tree.body for n in imports), path
        aliases={x.asname or x.name for n in imports for x in n.names if x.name==target}
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == target:
                key = (relative, n.lineno, ast.get_source_segment(source.decode(), n))
                assert key in expected_attributes, key
                seen_attributes.add(key)
        definition = None
        if relative == 'django/utils/encoding.py':
            definitions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == target]
            assert len(definitions) == 1
            definition = definitions[0]
            aliases.add(target)
        if not aliases:continue
        assert not any((isinstance(n,ast.Name) and isinstance(n.ctx,(ast.Store,ast.Del)) and n.id in aliases) or (isinstance(n,ast.arg) and n.arg in aliases) or (isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.name in aliases and n is not definition) for n in ast.walk(tree)),path
        class Calls(ast.NodeVisitor):
            def __init__(self):self.stack=[];self.owner=None
            def visit_ClassDef(self,n):
                self.stack.append(n.name)
                previous=self.owner;self.owner=None
                for child in n.body:self.visit(child)
                self.owner=previous;self.stack.pop()
            def visit_FunctionDef(self,n):
                self.stack.append(n.name);previous=self.owner;self.owner=n
                for child in n.body:self.visit(child)
                self.owner=previous;self.stack.pop()
            visit_AsyncFunctionDef=visit_FunctionDef
            def visit_Call(self,n):
                if isinstance(n.func,ast.Name) and n.func.id in aliases:
                    assert self.owner is not None, (path,n.lineno)
                    findings.append({'path':path.relative_to(a.repo).as_posix(),'qualname':'.'.join(self.stack),'line':n.lineno,'end_line':n.end_lineno,'quote':ast.get_source_segment(source.decode(),n),'source_sha256':hashlib.sha256(source).hexdigest(),'owner_start':self.owner.lineno,'owner_end':self.owner.end_lineno})
                self.generic_visit(n)
        Calls().visit(tree)
    result['targets'][target]={'production_python_files':files,'calls':findings,'distinct_callers':len({(f['path'],f['qualname']) for f in findings})}
assert seen_attributes == expected_attributes
result['reviewed_attribute_exclusions'] = exclusions
a.output.write_text(json.dumps(result,indent=2)+'\n')
print({t:{'calls':len(d['calls']),'callers':d['distinct_callers']} for t,d in result['targets'].items()})
