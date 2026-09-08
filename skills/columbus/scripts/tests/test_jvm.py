"""Meaningful JVM navigation checks: resolution must prefer missing to false edges."""
import json
import subprocess
import sys
import textwrap
import unittest

from columbus.jvm import parse_jvm, resolve_jvm


class JVMTests(unittest.TestCase):
    def test_array_loop_bindings_preserve_scope_and_reject_conflicts(self):
        prefix = 'class Item { void hit() {} } class Wrong { void hit() {} } '
        cases = [
            ('Wrong item; void run(Item[] values) { for(Item item : values) item.hit(); item.hit(); }',
             ['C.java::Item.hit:method()', 'C.java::Wrong.hit:method()']),
            ('void run(Item[][] values) { for(Item[] row : values) for(Item item : row) item.hit(); }',
             ['C.java::Item.hit:method()']),
            ('void run(Wrong[] values) { for(Item item : values) item.hit(); }', [None]),
            ('void run(Item[] values) { Item item=null; for(Item item : values) item.hit(); }', [None]),
            ('void run(Item[] values) { for(Item item : values) {} item.hit(); }', [None]),
            ('void run(Item[] values) { for(var item : values) item.hit(); }', [None]),
            ('void run() { for(Item item : values) item.hit(); Item[] values=null; }', [None]),
            ('Item[] values; static void run() { for(Item item : values) item.hit(); }', [None]),
        ]
        for body, expected in cases:
            with self.subTest(body=body):
                parsed = parse_jvm('C.java', prefix + 'class C { ' + body + ' }')
                resolve_jvm([parsed])
                calls = [r.get('target') for r in parsed['references']
                         if r['kind'] == 'calls' and r['member'] == 'hit']
                self.assertEqual(calls, expected)

    def test_enhanced_for_iterable_uses_enclosing_scope(self):
        source = '''class C {
            C[] items() { return new C[0]; }
            void hit() {}
            void run() {
                for (C item : items()) { item.hit(); }
            }
        }'''
        parsed = parse_jvm('C.java', source)
        resolve_jvm([parsed])
        calls = {r['name']: r for r in parsed['references'] if r['kind'] == 'calls'}
        self.assertTrue(calls['items']['resolved'])
        self.assertEqual(calls['items']['target'], 'C.java::C.items:method()')
        self.assertFalse(calls['item.hit']['resolved'])
        self.assertIn('unsupported', calls['item.hit']['reason'])
        # A nested loop's iterable still belongs to the unsupported outer body.
        parsed = parse_jvm('C.java', source.replace('item.hit();',
            'for (C inner : items()) { inner.hit(); }'))
        resolve_jvm([parsed])
        items = [r for r in parsed['references'] if r['name'] == 'items']
        self.assertEqual([r['resolved'] for r in items], [True, False])

    def test_local_method_requires_complete_absence_from_base_chain(self):
        cases = [
            ('interface API {} class C implements API', True),
            ('class Base {} class C extends Base', True),
            ('interface Root {} interface API extends Root {} class C implements API', True),
            ('class Base { void hit(int n) {} } class C extends Base', False),
            ('interface API { void hit(int n); } abstract class C implements API', False),
            ('class Base extends Missing {} class C extends Base', False),
            ('class Base<T> {} class C extends Base<String>', False),
            ('class Base extends C {} class C extends Base', False),
        ]
        for prefix, expected in cases:
            for invocation in ['hit("x")', 'c.hit("x")']:
                with self.subTest(prefix=prefix, invocation=invocation):
                    file = self.parsed('C.java', prefix + ' { void hit(String s) {} void run(C c) { ' + invocation + '; } }')
                    resolve_jvm([file])
                    call, = [r for r in file['references'] if r['kind'] == 'calls']
                    self.assertEqual(call['resolved'], expected)
                    if expected:
                        self.assertIn('C.hit:method(String)', call['target'])

    def test_base_absence_keeps_partial_and_receiver_shadowing_guards(self):
        for base, body in [
            ('class Base { void broken( }', 'hit("x");'),
            ('class Base {}', 'Object c = null; c.hit("x");'),
            ('class Base {}', 'C.hit("x");'),
        ]:
            with self.subTest(base=base, body=body):
                files = [parse_jvm('Base.java', base), self.parsed('C.java',
                    'class C extends Base { void hit(String s) {} void run() { ' + body + ' } }')]
                self.assertEqual(files[0]['partial'], 'broken' in base)
                resolve_jvm(files)
                call, = [r for r in files[1]['references'] if r['kind'] == 'calls']
                self.assertFalse(call['resolved'])

    def test_assignment_context_uses_lexical_locals_and_parameters(self):
        for body,context,resolved in [
            ('void run() { String value; value=hit(1); }', 'String', False),
            ('void run() { Integer value; value=hit(1); }', 'Integer', True),
            ('void run(String value) { value=hit(1); }', 'String', False),
            ('void run(boolean b) { String value; value=b ? hit(1) : null; }', 'String', False),
            ('void run() { String value; value=hit(true) ? "a" : "b"; }', '', True),
            ('void run() { String value=""; value+=hit(1); }', '', True),
            ('void run() { { String value; } { Integer value; value=hit(1); } }', 'Integer', True),
            ('void run(Integer value) { { String other; } value=hit(1); }', 'Integer', True),
            ('void run() { Integer value[]; value=hit(1); }', 'Integer[]', False),
            ('void run(Integer value[]) { value=hit(1); }', 'Integer[]', False),
            ('void run(Integer... value) { value=hit(1); }', 'Integer[]', False),
        ]:
            with self.subTest(body=body):
                file=self.parsed('C.java','class C { static <T> T hit(T v) { return v; } '+body+' }')
                resolve_jvm([file])
                call,=[r for r in file['references'] if r['member']=='hit']
                self.assertEqual(call['expected_type'],context)
                self.assertEqual(call['resolved'],resolved)

    def test_conditional_branches_inherit_result_context_but_condition_does_not(self):
        for body,context,resolved in [
            ('String s=b ? hit(1) : null;', 'String', False),
            ('Integer s=b ? hit(1) : null;', 'Integer', True),
            ('String s=(b ? null : (b ? hit(1) : null));', 'String', False),
            ('String s=hit(true) ? "a" : "b";', '', True),
        ]:
            with self.subTest(body=body):
                file=self.parsed('C.java','class C { static <T> T hit(T v) { return v; } void run(boolean b) { '+body+' } }')
                resolve_jvm([file])
                call,=[r for r in file['references'] if r['member']=='hit']
                self.assertEqual(call['expected_type'],context)
                self.assertEqual(call['resolved'],resolved)

    def test_return_only_type_variables_retain_constraints(self):
        for declaration,context,expected in [
            ('static <T extends Number> T','String',False),
            ('static <T extends Number> T','Number',False),
            ('static <T> T','String',True),
            ('static <T> T[]','String[]',True),
            ('static <T> T[]','String',False),
        ]:
            with self.subTest(declaration=declaration,context=context):
                file=self.parsed('C.java','class C { '+declaration+' hit() { return null; } void run() { '+context+' value=hit(); } }')
                resolve_jvm([file])
                call,=[r for r in file['references'] if r['member']=='hit']
                self.assertEqual(call['resolved'],expected)
        file=self.parsed('C.java','class C<T> { T hit() { return null; } void run() { String value=hit(); } }')
        resolve_jvm([file])
        call,=[r for r in file['references'] if r['member']=='hit']
        self.assertFalse(call['resolved'])
        self.assertIn('declaring-type substitution',call['reason'])

    def test_generic_varargs_array_uses_fixed_arity_before_result_context(self):
        for result,expected in [('String[]',True),('String[][]',False),('Object[]',True)]:
            file=self.parsed('C.java','class C { static <T> T[] hit(T... x) { return x; } void run() { '+result+' value=hit(new String[0]); } }')
            resolve_jvm([file])
            call,=[r for r in file['references'] if r['member']=='hit']
            self.assertEqual(call['resolved'],expected)
        for token,value,expected in [('String','new String[0]',True),('String[]','new String[0]',True),
                                     ('Object','new int[0]',True),('String','new Object[0]',False)]:
            file=self.parsed('C.java','class C { static <T> void hit(Class<T> type,T... x) {} void run() { hit('+token+'.class,'+value+'); } }')
            resolve_jvm([file])
            call,=[r for r in file['references'] if r['member']=='hit']
            self.assertEqual(call['resolved'],expected)

    def test_array_class_token_identity_dimensions_and_shadowing(self):
        for token,value,expected in [('int[]','new int[0]',True),('int[]','new Integer[0]',False),
                ('Integer[]','new int[0]',False),('int[][]','new int[0][]',True),
                ('int[][]','new int[0]',False),('Object[]','new String[0]',True),
                ('Object[]','new int[0]',False),('Object[]','new int[0][]',True),
                ('int[]','new int[new int[0].length]',True)]:
            with self.subTest(token=token,value=value):
                file=self.parsed('C.java','class C { static <T> void hit(Class<T> type,T value) {} void run() { hit('+token+'.class,'+value+'); } }')
                resolve_jvm([file])
                call,=[r for r in file['references'] if r['member']=='hit']
                self.assertEqual(call['resolved'],expected)
        file=self.parsed('C.java','class String {} class C { static <T> void hit(Class<T> type,T value) {} void run() { hit(java.lang.String[].class,new String[0]); } }')
        resolve_jvm([file])
        call,=[r for r in file['references'] if r['member']=='hit']
        self.assertFalse(call['resolved'])

    def parsed(self, path, source):
        result = parse_jvm(path, source)
        self.assertEqual([], result["diagnostics"], result["diagnostics"])
        json.dumps(result)  # Cached parse records must round-trip through SQLite JSON.
        return result

    def test_generic_argument_constraints_check_literals_and_expressions(self):
        prefix='class Factory { static <T> void hit(Class<T> type, T value) {} } '
        for token, value, expected in [('String','"text"',True),('String','1',False),
                ('String','String.valueOf(1)',True),('String','Integer.valueOf(1)',False),
                ('CharSequence','"text"',True),('Number','1',True)]:
            with self.subTest(token=token,value=value):
                file=self.parsed('C.java',prefix+'class C { void run() { Factory.hit('+token+'.class, '+value+'); } }')
                resolve_jvm([file]);call, = [r for r in file['references'] if r['member']=='hit']
                self.assertEqual(expected,call['resolved'])
                call.pop('argument_facts')
                resolve_jvm([file])
                self.assertFalse(call['resolved'])

    def test_generic_result_context_and_unknown_constraints(self):
        for source, expected in [
            ('class C { static <T> T[] hit(T... x) { return x; } String[] run() { return hit("ok"); } }',True),
            ('class C { static <T> T[] hit(T... x) { return x; } String[] run() { return hit(1); } }',False),
            ('class C { static <T> T[] hit(T... x) { return x; } void run() { String[] x=hit(1); } }',False),
            ('class C { static <T> void hit(T x) {} void run() { C.<String>hit(1); } }',False),
            ('class C { static <T extends Number> void hit(T x) {} void run() { hit("bad"); } }',False),
            ('class C<T> { void hit(T x) {} void run() { hit(Integer.valueOf(1)); } }',False),
            ('class Filter<T> {} class C { static <T> void hit(Filter<T> f,T x) {} void run() { hit(new Filter<String>(),"ok"); } }',True),
            ('class Filter<T> {} class C { static <T> void hit(Filter<T> f,T x) {} void run() { hit(new Filter<String>(),Integer.valueOf(1)); } }',False)]:
            with self.subTest(source=source):
                file=self.parsed('C.java',source);resolve_jvm([file])
                call, = [r for r in file['references'] if r['member']=='hit']
                self.assertEqual(expected,call['resolved'])

    def test_java_type_receiver_static_requirement_is_file_layout_independent(self):
        for split in [False, True]:
            for static in [False, True]:
                with self.subTest(split=split, static=static):
                    target='class T { '+('static ' if static else '')+'void hit() {} }'
                    caller='class C { void run() { T.hit(); } }'
                    files=([self.parsed('T.java',target),self.parsed('C.java',caller)] if split
                           else [self.parsed('C.java',target+caller)])
                    resolve_jvm(files)
                    call, = [r for f in files for r in f['references'] if r['kind']=='calls']
                    self.assertEqual(static,call['resolved'])

    def test_java_reference_literal_conversions_and_shadowing(self):
        for parameter,argument,expected in [('String','1',False),('String','"ok"',True),
                ('Integer','1',True),('Long','1',False),('Object','1',True),('Number','"bad"',False),
                ('CharSequence','"ok"',True),('Custom','"bad"',False),('Custom','null',True)]:
            with self.subTest(parameter=parameter,argument=argument):
                file=self.parsed('C.java','class Custom {} class T { static void hit('+parameter+' x) {} } '
                                 'class C { void run() { T.hit('+argument+'); } }')
                resolve_jvm([file])
                call, = [r for r in file['references'] if r['member']=='hit']
                self.assertEqual(expected,call['resolved'])
        for source in [
                'class hit {} class C { void run() { hit(); } }',
                'class T { static class hit {} } class C { void run() { T.hit(); } }',
                'class String {} class T { static void hit(String x) {} void run() { hit("bad"); } }',
                'class T { static void hit() {} } class C<T> { void run() { T.hit(); } }']:
            file=self.parsed('C.java',source);resolve_jvm([file])
            call, = [r for r in file['references'] if r['member']=='hit']
            self.assertFalse(call['resolved'])
        file=self.parsed('C.java','class T { void hit() {} } class C { void run(T T) { T.hit(); } }')
        resolve_jvm([file])
        call, = [r for r in file['references'] if r['member']=='hit']
        self.assertTrue(call['resolved'])

    def test_java_package_access_checks_members_and_owner_types(self):
        cases = [
            ('public class T { void hit() {} }', 'b', False),
            ('public class T { void hit() {} }', 'a', True),
            ('public class T { protected void hit() {} }', 'b', False),
            ('public class T { protected void hit() {} }', 'a', True),
            ('public class T { public void hit() {} }', 'b', True),
            ('class T { public void hit() {} }', 'b', False),
            ('public interface T { void hit(); }', 'b', True),
        ]
        for declaration, package, expected in cases:
            with self.subTest(declaration=declaration, package=package):
                owner = self.parsed('a/T.java', 'package a; '+declaration)
                caller = self.parsed(package+'/C.java', 'package '+package+'; import a.T; class C { void run(T t) { t.hit(); } }')
                resolve_jvm([owner, caller])
                call, = [r for r in caller['references'] if r['kind']=='calls']
                self.assertEqual(expected, call['resolved'])
        for container, expected in [('class', False), ('interface', True)]:
            owner = self.parsed('a/T.java', 'package a; public '+container+' T { class Inner { public void hit() {} } }')
            caller = self.parsed('b/C.java', 'package b; import a.T.Inner; class C { void run(Inner t) { t.hit(); } }')
            resolve_jvm([owner, caller])
            call, = [r for r in caller['references'] if r['kind']=='calls']
            self.assertEqual(expected, call['resolved'])

    def test_java_inaccessible_base_remains_unresolved(self):
        for modifier, package, expected in [('', 'b', False), ('public ', 'b', True), ('', 'a', True)]:
            owner = self.parsed('a/T.java', 'package a; '+modifier+'class T {}')
            child = self.parsed(package+'/C.java', 'package '+package+'; import a.T; class C extends T {}')
            edges = resolve_jvm([owner, child])
            self.assertEqual(expected, any(e['kind']=='inherits' for e in edges))
            ref, = [r for r in child['references'] if r['kind']=='inherits']
            self.assertEqual(expected, ref['resolved'])

    def test_java_private_access_preserves_nestmates(self):
        cases = [
            ('class T { private void hit() {} } class C { void run(T item) { item.hit(); } }', False),
            ('class T { public void hit() {} } class C { void run(T item) { item.hit(); } }', True),
            ('class T { private void hit() {} static class C { void run(T item) { item.hit(); } } }', True),
        ]
        for source, valid in cases:
            with self.subTest(source=source):
                parsed = self.parsed('C.java', source)
                resolve_jvm([parsed])
                call, = [r for r in parsed['references'] if r['kind'] == 'calls']
                self.assertEqual(call['resolved'], valid)
                if not valid:
                    self.assertIn('private declaration', call['reason'])

    def test_java_implicit_instance_stops_at_static_boundaries(self):
        cases = [
            ('class T { void hit() {} static { hit(); } }', False),
            ('class T { static void hit() {} static { hit(); } }', True),
            ('class T { int hit() { return 1; } static int value = hit(); }', False),
            ('class T { int hit() { return 1; } int value = hit(); }', True),
            ('class T { static int hit() { return 1; } static int value = hit(); }', True),
            ('interface T { int hit(); int value = hit(); }', False),
            ('class T { void hit() {} static void run() { hit(); } }', False),
            ('class T { void hit() {} void run() { hit(); } }', True),
            ('class T { static void hit() {} static void run() { hit(); } }', True),
            ('class T { void hit() {} static class C { void run() { hit(); } } }', False),
            ('class T { void hit() {} class C { void run() { hit(); } } }', True),
            ('class T { static class C { void hit() {} void run() { hit(); } } }', True),
            ('class T { void hit() {} interface C { default void run() { hit(); } } }', False),
            ('class T { void hit() {} record C() { void run() { hit(); } } }', False),
            ('class T { void hit() {} enum C { ONE; void run() { hit(); } } }', False),
            ('interface T { void hit(); class C { void run() { hit(); } } }', False),
            ('class T { void hit() {} static void run(T item) { item.hit(); } }', True),
        ]
        for source, valid in cases:
            with self.subTest(source=source):
                parsed = self.parsed('C.java', source)
                resolve_jvm([parsed])
                call, = [r for r in parsed['references'] if r['kind'] == 'calls']
                self.assertEqual(call['resolved'], valid)
                if not valid:
                    self.assertIn('requires an enclosing instance', call['reason'])

    def test_large_jvm_spans_survive_native_point_reference_bug(self):
        # A subprocess contains native crashes, which cannot be caught in Python.
        # Lines >256 exercise non-cached Python integers in tree-sitter 0.26.0.
        code = textwrap.dedent("""
            import gc
            from columbus.jvm import parse_jvm
            for language in ('java', 'kotlin'):
                prefix = '// 한글\\r\\n' * 300
                if language == 'java':
                    source = prefix + 'package demo;\\nclass Large {\\n' + ''.join(
                        'void method%d() { helper(); }\\n' % i for i in range(100)) + 'void helper() {}\\n}\\n'
                else:
                    source = prefix + 'package demo\\nclass Large {\\n' + ''.join(
                        'fun method%d() { helper() }\\n' % i for i in range(100)) + 'fun helper() {}\\n}\\n'
                for _ in range(10):
                    result = parse_jvm('Large.' + ('java' if language == 'java' else 'kt'), source)
                    gc.collect()
                    assert not result['diagnostics'], result['diagnostics']
                    owner = next(s for s in result['symbols'] if s['name'] == 'Large')
                    assert (owner['start_line'], owner['end_line']) == (302, 404), owner
                    method = next(s for s in result['symbols'] if s['name'] == 'method99')
                    assert (method['start_line'], method['end_line']) == (402, 402), method
                    assert result['references'][-1]['line'] == 402
        """)
        result = subprocess.run([sys.executable, '-X', 'faulthandler', '-c', code],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_java_annotation_type_members_and_imports(self):
        annotation = self.parsed("Alias.java", '''package demo;
// @interface Fake {}
public @interface Alias {
 String value() default "@interface Fake {}";
 Class<?> target() default Object.class;
 @interface Nested { int count() default 1; }
}
''')
        client = self.parsed("Client.java", "package app; import demo.Alias; @Alias class Client {}")
        edges = resolve_jvm([annotation, client])
        symbols = {s['qualname']: s for s in annotation['symbols']}
        self.assertEqual('interface', symbols['demo.Alias']['kind'])
        self.assertEqual('method', symbols['demo.Alias.value']['kind'])
        self.assertEqual(symbols['demo.Alias']['id'], symbols['demo.Alias.value']['parent_id'])
        self.assertIn('default Object.class', symbols['demo.Alias.target']['signature'])
        self.assertEqual('method', symbols['demo.Alias.Nested.count']['kind'])
        self.assertEqual(4, symbols['demo.Alias.value']['start_line'])
        self.assertFalse(any(s['name'] == 'Fake' for s in annotation['symbols']))
        self.assertTrue(any(e['kind'] == 'imports' and e['target'] == symbols['demo.Alias']['id'] for e in edges))

    def test_kotlin_declarations_and_extension(self):
        result = self.parsed("Model.kt", '''package demo
class User(val id: Int) {
 @Deprecated("old")
 fun read(value: String): String = value
 fun String.extra() = trim()
 companion object {
  fun create() = User(1)
 }
}
interface API {
 fun fetch(): String
}
object Config {
 val name: String = "demo"
}
''')
        symbols = {s["qualname"]: s for s in result["symbols"]}
        self.assertEqual("interface", symbols["demo.API"]["kind"])
        self.assertEqual("object", symbols["demo.User.Companion"]["kind"])
        self.assertEqual("property", symbols["demo.Config.name"]["kind"])
        self.assertEqual("property", symbols["demo.User.id"]["kind"])
        self.assertEqual("String", symbols["demo.User.extra"]["receiver_type"])
        self.assertEqual(['@Deprecated("old")'], symbols["demo.User.read"]["annotations"])

    def test_java_record_constructor_enum(self):
        result = self.parsed("Model.java", '''package demo;
class User {
 public User(String name) {}
 public void read(String... words) {}
}
record Entry(String name, int id) {}
enum Color { RED, BLUE }
interface API { void get(); }
''')
        kinds = {s["kind"] for s in result["symbols"]}
        self.assertTrue({"class", "constructor", "method", "record", "enum", "interface"} <= kinds)
        read = next(s for s in result["symbols"] if s["name"] == "read")
        self.assertEqual(["String..."], read["parameter_types"])

    def test_kotlin_alias_import_to_java_typed_receiver(self):
        java = self.parsed("Service.java", "package service; public class Service { public void fetch() {} }")
        kotlin = self.parsed("Client.kt", '''package app
import service.Service as S
fun go(service: S) {
 service.fetch()
}
''')
        edges = resolve_jvm([java, kotlin])
        calls = [e for e in edges if e["kind"] == "calls"]
        self.assertEqual(1, len(calls))
        self.assertIn("service.Service.fetch", calls[0]["target"])
        self.assertEqual("heuristic", calls[0]["confidence"])
        self.assertTrue(kotlin["imports"][0]["resolved"])

    def test_java_to_kotlin_explicit_parameter(self):
        kotlin = self.parsed("Service.kt", '''package service
class Service {
 fun fetch() {}
}
''')
        java = self.parsed("Client.java", '''package app;
import service.Service;
class Client { void go(Service service) { service.fetch(); } }
''')
        resolve_jvm([java, kotlin])
        self.assertTrue(java["references"][0]["resolved"])
        self.assertIn("Service.fetch", java["references"][0]["target"])

    def test_type_parameters_never_resolve_to_same_named_concrete_type(self):
        for declaration in (
            "class C<T extends API> { void run(T item) { item.hit(); } }",
            "class C { <T extends API> void run(T item) { item.hit(); } }",
            "class C<T extends API> { class Nested { void run(T item) { item.hit(); } } }",
        ):
            with self.subTest(declaration=declaration):
                parsed = self.parsed("C.java", "class T { void hit() {} } interface API { void hit(); } " + declaration)
                edges = resolve_jvm([parsed])
                call = next(r for r in parsed["references"] if r["kind"] == "calls")
                self.assertFalse(call["resolved"], call)
                self.assertIn("type parameter", call["reason"])
                self.assertFalse([e for e in edges if e["kind"] == "calls"])

    def test_nested_type_shadows_top_level_but_value_name_does_not(self):
        parsed = self.parsed("C.java", """class T { void wrong() {} }
class C { class T { void hit() {} } void run(T item, int T) { item.hit(); } }
""")
        resolve_jvm([parsed])
        call = next(r for r in parsed["references"] if r["kind"] == "calls")
        self.assertTrue(call["resolved"], call)
        self.assertIn("C.T.hit", call["target"])

    def test_inherited_overload_cannot_assert_subclass_target(self):
        for invocation in ("hit(1)", "item.hit(1)"):
            with self.subTest(invocation=invocation):
                parsed = self.parsed("C.java", "class Base { void hit(int n) {} } "
                    "class C extends Base { void hit(String s) {} void run(C item) { " + invocation + "; } }")
                resolve_jvm([parsed])
                call = next(r for r in parsed["references"] if r["kind"] == "calls")
                self.assertFalse(call["resolved"], call)
                self.assertIn("inherited", call["reason"])

    def test_java_call_arity_rejects_false_single_targets(self):
        for parameters, arguments, resolved in (
            ("int n", "", False), ("", "1", False), ("int n", "1, 2", False),
            ("int n", "/* comment */ 1", True), ("int... ns", "", True),
            ("int n, int... ns", "", False), ("int n, int... ns", "1, 2, 3", True),
        ):
            with self.subTest(parameters=parameters, arguments=arguments):
                parsed = self.parsed("C.java", f"class C {{ void hit({parameters}) {{}} void run() {{ hit({arguments}); }} }}")
                resolve_jvm([parsed])
                call = next(r for r in parsed['references'] if r['kind']=='calls')
                self.assertEqual(call['resolved'], resolved, call)
                if not resolved:
                    self.assertIn('argument count incompatible', call['reason'])

    def test_primitive_literal_applicability_without_constant_narrowing(self):
        for parameter, argument, expected in (
            ('int', 'true', False), ('boolean', '1', False), ('int', '"x"', False),
            ('int', 'null', False), ('int', '1L', False), ('byte', '1', False),
            ('long', '1', True), ('double', '1.0f', True), ('int', "'x'", True),
            ('boolean', 'false', True), ('int...', '1, true', False),
            ('int...', '1, 2', True), ('int...', 'null', True), ('int...', '1, null', False),
        ):
            with self.subTest(parameter=parameter, argument=argument):
                parsed = self.parsed('C.java', f'class C {{ void hit({parameter} value) {{}} void run() {{ hit({argument}); }} }}')
                resolve_jvm([parsed])
                call = next(r for r in parsed['references'] if r['kind']=='calls')
                self.assertEqual(call['resolved'], expected, call)
                if not expected:
                    self.assertIn('literal argument incompatible', call['reason'])

    def test_overload_remains_unresolved_and_ids_ignore_parameter_names(self):
        original = self.parsed("A.java", '''package demo;
class A {
 void read(int id) {}
 void read(String text) {}
 void go() { read(1); }
}
''')
        renamed = self.parsed("A.java", '''package demo;
class A {
 void read(int changed) {}
 void read(String changedToo) {}
 void go() { read(1); }
}
''')
        self.assertEqual([s["id"] for s in original["symbols"]], [s["id"] for s in renamed["symbols"]])
        self.assertEqual(2, len({s["id"] for s in original["symbols"] if s["name"] == "read"}))
        resolve_jvm([original])
        self.assertFalse(original["references"][0]["resolved"])

    def test_unrelated_basename_never_resolves(self):
        service = self.parsed("Service.java", "package unrelated; class Service { void fetch() {} }")
        client = self.parsed("Client.java", "package app; class Client { void go(Service s) { s.fetch(); } }")
        resolve_jvm([service, client])
        self.assertFalse(client["references"][0]["resolved"])

    def test_same_package_top_level_and_member_calls(self):
        helper = self.parsed("Helper.kt", "package demo\nfun helper() {}\n")
        client = self.parsed("Client.kt", '''package demo
class Client {
 fun own() {}
 fun go() {
  helper()
  own()
 }
}
''')
        resolve_jvm([helper, client])
        self.assertTrue(all(r["resolved"] for r in client["references"]))
        self.assertEqual(2, len(client["references"]))

    def test_shadowing_blocks_global_callable(self):
        result = self.parsed("Client.kt", '''package demo
fun action() {}
fun go(action: () -> Unit) {
 action()
}
''')
        resolve_jvm([result])
        self.assertFalse(result["references"][0]["resolved"])
        self.assertIn("shadowed", result["references"][0]["reason"])

    def test_shadowed_receiver_does_not_reuse_field_type(self):
        java = self.parsed("Client.java", '''package demo;
class Service { void fetch() {} }
class Client {
 Service service;
 void go(Unknown service) { service.fetch(); }
}
''')
        resolve_jvm([java])
        self.assertFalse(java["references"][0]["resolved"])

    def test_extension_not_falsely_normal_method(self):
        result = self.parsed("Client.kt", '''package demo
class Service {}
fun Service.fetch() {}
fun go(s: Service) {
 s.fetch()
}
''')
        resolve_jvm([result])
        self.assertFalse(result["references"][0]["resolved"])

    def test_array_parameters_reject_scalar_literals_without_rejecting_null(self):
        cases = [('int[]', '1', False), ('String[]', '"x"', False),
                 ('Object[]', 'true', False), ('int[]...', '1', False),
                 ('int[][]', "'x'", False), ('int[]', 'null', True),
                 ('String[]', 'null', True), ('int[]...', '', True),
                 ('int[]...', 'null, null', True), ('Object...', '1', True)]
        for parameter, argument, expected in cases:
            with self.subTest(parameter=parameter, argument=argument):
                result = self.parsed('C.java', f'class C {{ void hit({parameter} p) {{}} void run() {{ hit({argument}); }} }}')
                resolve_jvm([result])
                calls = [r for r in result['references'] if r['kind'] == 'calls']
                self.assertEqual(1, len(calls))
                self.assertEqual(expected, calls[0]['resolved'])
                if not expected:
                    self.assertIn('array parameter', calls[0]['reason'])

    def test_syntax_recovery_suppresses_edges(self):
        result = parse_jvm("Bad.java", "class Bad { void run( { missing(); }")
        self.assertTrue(result["partial"])
        self.assertTrue(result["diagnostics"])
        self.assertTrue(all(s["partial"] for s in result["symbols"]))
        self.assertFalse([e for e in resolve_jvm([result]) if e["kind"] == "calls"])

    def test_lambda_and_this_dispatch_stay_unresolved(self):
        result = self.parsed("Client.kt", '''package demo
fun fetch() {}
class Client {
 fun fetch() {}
 fun go() {
  this.fetch()
  val block = { fetch() }
 }
}
''')
        resolve_jvm([result])
        self.assertEqual(2, len(result["references"]))
        self.assertFalse(any(r["resolved"] for r in result["references"]))

    def test_wildcard_does_not_invent_binding(self):
        helper = self.parsed("Helper.kt", "package helper\nfun fetch() {}\n")
        caller = self.parsed("Client.kt", "package app\nimport helper.*\nfun go() = fetch()\n")
        self.assertTrue(caller["imports"][0]["wildcard"])
        resolve_jvm([helper, caller])
        self.assertFalse(caller["references"][0]["resolved"])

    def test_inheritance_crosses_java_kotlin_without_dispatch_claim(self):
        base = self.parsed("Base.java", "package demo; interface Base { void read(); }")
        child = self.parsed("Child.kt", "package demo\nclass Child : Base {\n override fun read() {}\n}\n")
        edges = resolve_jvm([base, child])
        inherits = [e for e in edges if e["kind"] == "inherits"]
        self.assertEqual(1, len(inherits))
        self.assertIn("demo.Base:interface", inherits[0]["target"])
        self.assertEqual("heuristic", inherits[0]["confidence"])


if __name__ == "__main__":
    unittest.main()
