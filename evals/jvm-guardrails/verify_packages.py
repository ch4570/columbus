"""Compiler-backed Java package/member accessibility fixtures."""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import tempfile
from columbus.jvm import parse_jvm, resolve_jvm

CASES = [
    ('package_method_foreign', False, False, {'a/T.java':'package a; public class T { void hit() {} }', 'b/C.java':'package b; import a.T; class C { void run(T t) { t.hit(); } }'}),
    ('package_method_same', True, True, {'a/T.java':'package a; public class T { void hit() {} }', 'a/C.java':'package a; class C { void run(T t) { t.hit(); } }'}),
    ('public_method_foreign', True, True, {'a/T.java':'package a; public class T { public void hit() {} }', 'b/C.java':'package b; import a.T; class C { void run(T t) { t.hit(); } }'}),
    ('protected_method_foreign', False, False, {'a/T.java':'package a; public class T { protected void hit() {} }', 'b/C.java':'package b; import a.T; class C { void run(T t) { t.hit(); } }'}),
    ('protected_method_same', True, True, {'a/T.java':'package a; public class T { protected void hit() {} }', 'a/C.java':'package a; class C { void run(T t) { t.hit(); } }'}),
    ('package_class_foreign', False, False, {'a/T.java':'package a; class T { public void hit() {} }', 'b/C.java':'package b; import a.T; class C { void run(T t) { t.hit(); } }'}),
    ('package_class_same', True, True, {'a/T.java':'package a; class T { public void hit() {} }', 'a/C.java':'package a; class C { void run(T t) { t.hit(); } }'}),
    ('public_interface_method', True, True, {'a/T.java':'package a; public interface T { void hit(); }', 'b/C.java':'package b; import a.T; class C { void run(T t) { t.hit(); } }'}),
    ('nested_package_class_foreign', False, False, {'a/T.java':'package a; public class T { static class Inner { public void hit() {} } }', 'b/C.java':'package b; import a.T.Inner; class C { void run(Inner t) { t.hit(); } }'}),
    ('nested_public_class_foreign', True, True, {'a/T.java':'package a; public class T { public static class Inner { public void hit() {} } }', 'b/C.java':'package b; import a.T.Inner; class C { void run(Inner t) { t.hit(); } }'}),
    ('interface_implicit_public_nested', True, True, {'a/T.java':'package a; public interface T { class Inner { public void hit() {} } }', 'b/C.java':'package b; import a.T.Inner; class C { void run(Inner t) { t.hit(); } }'}),
    ('private_owner_foreign', False, False, {'a/T.java':'package a; public class T { private static class Inner { public void hit() {} } }', 'a/C.java':'package a; import a.T.Inner; class C { void run(Inner t) { t.hit(); } }'}),
    ('package_base_foreign', False, False, {'a/T.java':'package a; class T {}', 'b/C.java':'package b; import a.T; class C extends T {}'}),
    ('package_base_same', True, True, {'a/T.java':'package a; class T {}', 'a/C.java':'package a; class C extends T {}'}),
    ('public_base_foreign', True, True, {'a/T.java':'package a; public class T {}', 'b/C.java':'package b; import a.T; class C extends T {}'}),
    ('protected_subclass_valid_unresolved', True, False, {'a/T.java':'package a; public class T { protected void hit() {} }', 'b/C.java':'package b; import a.T; class C extends T { void run(C c) { c.hit(); } }'}),
]


def main():
    p=argparse.ArgumentParser(); p.add_argument('jdk',type=Path); p.add_argument('output',type=Path); p.add_argument('--observe',action='store_true'); args=p.parse_args()
    rows=[]
    with tempfile.TemporaryDirectory(prefix='columbus package oracle ') as temp:
        for name, valid, resolved, sources in CASES:
            root=Path(temp)/name; paths=[]; parsed=[]
            for relative,source in sources.items():
                path=root/relative; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(source)
                paths.append(str(path)); parsed.append(parse_jvm(relative,source))
            assert all(not f['partial'] for f in parsed), name
            compile_result=subprocess.run([str(args.jdk/'javac'),'-proc:none','-d',str(root/'classes'),*paths],capture_output=True,text=True)
            assert (compile_result.returncode==0)==valid,(name,compile_result.stderr)
            edges=resolve_jvm(parsed)
            refs=[r for f in parsed for r in f['references'] if r['kind']=='calls' and r['member']=='hit']
            if not refs:
                refs=[r for f in parsed for r in f['references'] if r['kind']=='inherits']
            assert len(refs)==1
            rows.append({'name':name,'sources':sources,'source_hashes':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in sources.items()},
                         'compiler_valid':valid,'compiler_exit':compile_result.returncode,'compiler_stderr':compile_result.stderr,
                         'expected_resolved':resolved,'reference':refs[0],'edges':[e for e in edges if e['kind']==refs[0]['kind']],
                         'passed':refs[0]['resolved']==resolved})
    result={'compiler':subprocess.check_output([str(args.jdk/'javac'),'-version'],text=True).strip(),
            'versions':{n:version(n) for n in ['tree-sitter','tree-sitter-java','tree-sitter-kotlin']},
            'analyzer_sha256':hashlib.sha256(Path(__file__).resolve().parents[2].joinpath('skills/columbus/scripts/columbus/jvm.py').read_bytes()).hexdigest(),
            'cases':rows,'passed':all(r['passed'] for r in rows)}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({r['name']:r['passed'] for r in rows}))
    if not args.observe: assert result['passed']

if __name__=='__main__': main()
