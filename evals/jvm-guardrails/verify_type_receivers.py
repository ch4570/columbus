"""Reuse the javac gate for type/value receiver classification."""
import verify_packages as gate

gate.CASES=[]
for split in [False,True]:
    for static in [False,True]:
        target='public class T { public '+('static ' if static else '')+'void hit() {} }'
        caller='class C { void run() { T.hit(); } }'
        sources={'T.java':target,'C.java':caller} if split else {'T.java':target+caller}
        gate.CASES.append(('split_'+str(split)+'_static_'+str(static),static,static,sources))
gate.CASES += [
    ('typed_value_named_T',True,True,{'T.java':'class T { void hit() {} } class C { void run(T T) { T.hit(); } }'}),
    ('unknown_value_shadows_T',False,False,{'T.java':'class T { static void hit() {} } class C { void run() { Object T = new Object(); T.hit(); } }'}),
    ('type_parameter_shadows_T',False,False,{'T.java':'class T { static void hit() {} } class C<T> { void run() { T.hit(); } }'}),
    ('private_static_foreign',False,False,{'T.java':'class T { private static void hit() {} } class C { void run() { T.hit(); } }'}),
    ('private_static_nestmate',True,True,{'T.java':'class T { private static void hit() {} static class C { void run() { T.hit(); } } }'}),
    ('inherited_static_unresolved',True,False,{'T.java':'class Base { static void hit() {} } class T extends Base {} class C { void run() { T.hit(); } }'}),
]

for parameter, argument, valid, resolved in [
    ('String','1',False,False), ('String','"ok"',True,True),
    ('Object','1',True,True), ('Number','1',True,True), ('Number','"bad"',False,False),
    ('Integer','1',True,True), ('Long','1',False,False), ('CharSequence','"ok"',True,True),
    ('Custom','"bad"',False,False), ('Custom','null',True,True),
    ('java.lang.String','1',False,False), ('java.lang.String','"ok"',True,True),
]:
    source='class Custom {} class T { static void hit('+parameter+' x) {} } class C { void run() { T.hit('+argument+'); } }'
    gate.CASES.append(('literal_'+str(len(gate.CASES)),valid,resolved,{'C.java':source}))

gate.CASES += [
    ('nested_class_is_not_method',False,False,{'C.java':'class T { static class hit {} } class C { void run() { T.hit(); } }'}),
    ('class_is_not_function',False,False,{'C.java':'class hit {} class C { void run() { hit(); } }'}),
]

if __name__=='__main__': gate.main()
