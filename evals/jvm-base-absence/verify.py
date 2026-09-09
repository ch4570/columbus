"""Extend the existing 84-case compiler gate with explicit-base name absence."""
from pathlib import Path
import runpy

gate = runpy.run_path(str(Path(__file__).parents[1] / 'jvm-assignment-context/verify.py'))['gate']
for name, prefix, valid, resolved in [
    ('empty_interface', 'interface API {} class C implements API', True, True),
    ('empty_class', 'class Base {} class C extends Base', True, True),
    ('transitive_interfaces', 'interface Root {} interface API extends Root {} class C implements API', True, True),
    ('base_overload', 'class Base { void hit(int n) {} } class C extends Base', True, False),
    ('interface_overload', 'interface API { void hit(int n); } abstract class C implements API', True, False),
    ('unknown_chain', 'class Base extends Missing {} class C extends Base', False, False),
    ('generic_base', 'class Base<T> {} class C extends Base<String>', True, False),
    ('cyclic_base', 'class Base extends C {} class C extends Base', False, False),
]:
    for receiver in ['', 'c.']:
        source = prefix + ' { void hit(String s) {} void run(C c) { ' + receiver + 'hit("x"); } }'
        gate.CASES.append(('base_absence_' + name + ('_receiver' if receiver else '_implicit'), valid, resolved, {'C.java': source}))
for name, body, valid in [
    ('type_receiver', 'C.hit("x");', False),
    ('shadowed_receiver', 'Object c=null; c.hit("x");', False),
    ('wrong_argument', 'hit(1);', False),
]:
    gate.CASES.append(('base_absence_' + name, valid, False, {'C.java':
        'class Base {} class C extends Base { void hit(String s) {} void run() { ' + body + ' } }'}))

if __name__ == '__main__':
    gate.main()
