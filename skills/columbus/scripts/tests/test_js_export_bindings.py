"""Conservative JS/TS module bindings, not a runtime-dispatch parser."""
import unittest
import tracemalloc

from columbus.languages import parse_source, resolve_files
from columbus.polyglot import _js_export_bindings, mask_source


class JsExportBindingsTests(unittest.TestCase):
    def calls(self, helper, *, clause="renamed", call="renamed()", suffix="js", caller=None, extra=()):
        path = f"helper.{suffix}"
        caller = caller or f"import {clause} from './{path}';\nfunction run() {{ {call}; }}"
        files = [parse_source(f"main.{suffix}", caller, "main"), parse_source(path, helper, "helper")]
        files.extend(parse_source(name, source, name) for name, source in extra)
        edges = resolve_files(files)
        calls = [edge for edge in edges if edge["kind"] == "calls" and edge["path"] == f"main.{suffix}"]
        return files, calls

    def assert_resolves(self, helper, **kwargs):
        files, calls = self.calls(helper, **kwargs)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["target"], f"helper.{kwargs.get('suffix', 'js')}::target:function")
        self.assertEqual(calls[0]["confidence"], "heuristic")
        self.assertEqual(files[1]["fidelity"], "heuristic")

    def assert_unresolved(self, helper, **kwargs):
        _, calls = self.calls(helper, **kwargs)
        self.assertEqual(calls, [])

    def test_inline_default_is_not_a_named_export(self):
        for suffix in ("js", "ts"):
            with self.subTest(suffix=suffix):
                source = "export default function target() {}"
                self.assert_resolves(source, suffix=suffix)
                self.assert_unresolved(source, clause="{ target }", call="target()", suffix=suffix)

    def test_separate_default_only_unique_function_declaration(self):
        for suffix in ("js", "ts"):
            for source in ("function target() {}\nexport default target;",
                           "export default target;\nfunction target() {}",
                           "function target() {}; export /* comment */ default\n target /* comment */;"):
                with self.subTest(suffix=suffix, source=source):
                    self.assert_resolves(source, suffix=suffix)
                    self.assert_unresolved(source, clause="{ target }", call="target()", suffix=suffix)

    def test_named_and_separate_default_can_coexist(self):
        source = "export function target() {}\nexport default target;"
        self.assert_resolves(source)
        self.assert_resolves(source, clause="{ target as renamed }")

    def test_multiline_and_comment_separated_inline_declarations(self):
        for source in ("export\n/* a */ default\n/* b */ function target() {}",
                       "export default async /* comment */ function target() {}",
                       "export default function * target() {}"):
            with self.subTest(source=source):
                self.assert_resolves(source)
        self.assert_resolves("export\n/* comment */ function target() {}", clause="{ target as renamed }")

    def test_simple_ts_returns_work_but_type_braces_are_not_function_bodies(self):
        for annotation in ("number", "Thing[]", "namespace.Thing"):
            self.assert_resolves(f"export default function target(): {annotation} {{ return value; }}", suffix="ts")
        for declaration in ("function target(): { x: number };",
                            "function target(): Promise<{ x: number }>;",
                            "function target(): keyof { x: number };",
                            "function target<T extends {x: number}>(): T;",
                            "function target<T extends {x: number}>(): T { return value; }",
                            "function target(): { x: number } { return value; }"):
            with self.subTest(declaration=declaration):
                self.assert_unresolved("export default " + declaration, suffix="ts")
                self.assert_unresolved(declaration + " export default target;", suffix="ts")

    def test_existing_named_arrow_and_unnamed_function_bindings(self):
        for declaration in ("const target = () => {};", "const target = () => 1;",
                            "const target = function() {};", "const target = async () => {};"):
            with self.subTest(declaration=declaration):
                self.assert_resolves("export " + declaration, clause="{ target as renamed }")
                self.assert_unresolved(declaration + " export default target;")

    def test_constructor_identifier_does_not_resolve_receiver_methods(self):
        source = "function target() {}\nexport default target;"
        self.assert_resolves(source, call="new renamed()")
        self.assert_resolves(source, call="new renamed().method()")
        for call in ("renamed.method()", "renamed?.method()", "renamed . method()"):
            self.assert_unresolved(source, call=call)

    def test_literal_and_comment_text_cannot_export_a_function(self):
        for prefix in ("/* export default */", "// export default\n", "const s = 'export default';",
                       'const s = "export default";', "const s = `export default`;",
                       "const pattern = /export default/;", "const node = <x>export default</x>;"):
            with self.subTest(prefix=prefix):
                self.assert_unresolved(prefix + " function target() {}")
                self.assert_unresolved(prefix + " function target() {}", clause="{ target as renamed }")

    def test_same_line_export_does_not_taint_following_declaration(self):
        self.assert_unresolved("export function first() {} function target() {}", clause="{ target as renamed }")
        self.assert_unresolved("export default function first() {} function target() {}", clause="{ target as renamed }")

    def test_nested_block_conditional_and_expression_declarations_are_not_module_bindings(self):
        for source in ("{ function target() {} }", "if (condition) { function target() {} }",
                       "if (condition) function target() {}", "function outer() { function target() {} }",
                       "const value = function target() {};", "(function target() {});",
                       "const object = { method: function target() {} };",
                       "label: function target() {}", "class Holder { method() { function target() {} } }"):
            with self.subTest(source=source):
                self.assert_unresolved(source + "\nexport default target;")
        self.assert_unresolved("function target() {}\n{ export default target; }")
        self.assert_unresolved("{ export default function target() {} }")
        self.assert_unresolved("{ export function target() {} }", clause="{ target as renamed }")

    def test_non_declaration_and_unsupported_default_expressions_stay_unresolved(self):
        for statement in ("export default target + other;", "export default target();",
                          "export default target\n(other);", "export default (target);",
                          "export default target satisfies T;", "export default {target};",
                          "export { target as default };", "export default target"):
            with self.subTest(statement=statement):
                self.assert_unresolved("function target() {}\n" + statement)
        for source in ("export default function() {}", "export default () => {};",
                       "export default class target {}", "declare function target(): void; export default target;"):
            self.assert_unresolved(source, suffix="ts")

    def test_duplicate_declarations_and_defaults_are_ambiguous(self):
        for source in ("function target() {} function target() {} export default target;",
                       "function target() {} class target {} export default target;",
                       "function target() {} const target = other; export default target;",
                       "function target() {} export default target; export default target;",
                       "export default function target() {} export default other;",
                       "export default function target() {} export default {};",
                       "export default function target() {} export { other as default };",
                       "export default function target() {} export * as default from './other.js';",
                       'export default function target() {} export { other as "default" };',
                       'export default function target() {} export * as "default" from "./other.js";'):
            with self.subTest(source=source):
                self.assert_unresolved(source)

    def test_exporter_writes_are_conservatively_rejected_before_or_after_value_export(self):
        for mutation in ("target = other;", "target += other;", "target &&= other;", "target **= other;",
                         "target++;", "++target;", "[target] = other;", "({target} = other);",
                         "({key: target} = other);", "function later() { target = other; }",
                         "for (target of values) {}", "for ({target} of values) {}",
                         "for ({key: target} in values) {}", "for ([target] of values) {}",
                         "for await (target of values) {}", "for await ({target} of values) {}",
                         "(target) = other;", "((target)) += other;", "++(target);", "(target)++;",
                         "const node = <x>{target = other}</x>;"):
            for source in (f"function target() {{}} {mutation} export default target;",
                           f"function target() {{}} export default target; {mutation}",
                           f"export default function target() {{}} {mutation}"):
                with self.subTest(source=source):
                    self.assert_unresolved(source)
            self.assert_unresolved(f"export function target() {{}} {mutation}", clause="{ target as renamed }")

    def test_exporter_dynamic_scope_and_hidden_template_expressions_reject_bindings(self):
        for statement in ("eval(code);", "(eval)(code);", "((eval))(code);", "with (object) {}",
                          "const s = `${target = other}`;", "const s = `${eval(code)}`;",
                          "const s = `${with(code)}`;", "const s = `${eval /* comment */ (code)}`;",
                          "const s = `${(eval)('tar' + 'get = other')}`;"):
            with self.subTest(statement=statement):
                self.assert_unresolved(f"function target() {{}} {statement} export default target;")
                self.assert_unresolved(f"export function target() {{}} {statement}", clause="{ target as renamed }")
        self.assert_resolves("function target() {} const s = `${unrelated}`; export default target;")
        self.assert_resolves("function target() {} const s = 'target = other; eval(code)'; export default target;")

    def test_own_and_unrelated_scope_shadows_are_conservative_false_negatives(self):
        for source in ("function target(target) {}", "function target() { const target = other; }",
                       "function target() {} function unrelated(target) {}"):
            self.assert_unresolved(source + " export default target;")

    def test_inline_variable_mutations_are_not_mistaken_for_initializer(self):
        for mutation in ("target = other;", "++target;", "target++;", "[target] = other;",
                         "function later() { target = other; }"):
            self.assert_unresolved("export const target = () => {}; " + mutation, clause="{ target as renamed }")

    def test_importer_shadowing_dynamic_scope_and_namespace_stay_unresolved(self):
        helper = "function target() {} export default target;"
        for caller in ("import renamed from './helper.js'; function run(renamed) { renamed(); }",
                       "import renamed from './helper.js'; function run() { const renamed = other; renamed(); }",
                       "import renamed from './helper.js'; function run() { eval(code); renamed(); }",
                       "import * as renamed from './helper.js'; function run() { renamed.target(); }",
                       "import renamed from 'helper.js'; function run() { renamed(); }",
                       "const renamed = require('./helper.js'); function run() { renamed(); }"):
            with self.subTest(caller=caller):
                self.assert_unresolved(helper, caller=caller)

    def test_module_ambiguity_import_binding_collision_and_reexport_stay_unresolved(self):
        self.assert_unresolved("export default function target() {}",
                               caller="import renamed from './helper'; function run() { renamed(); }",
                               extra=(("helper.ts", "export default function target() {}"),))
        self.assert_unresolved("import target from './other.js'; function target() {} export default target;")
        self.assert_unresolved("export { default } from './other.js';",
                               extra=(("other.js", "export default function target() {}"),))

    def test_unbalanced_exporter_and_missing_target_reset_resolution(self):
        self.assert_unresolved("export default function target() {}\n{")
        files, calls = self.calls("function target() {} export default target;")
        self.assertEqual(len(calls), 1)
        self.assertEqual([edge for edge in resolve_files(files[:1]) if edge["kind"] == "calls"], [])
        self.assertNotIn("target", files[0]["references"][0])

    def test_unsupported_export_tokens_do_not_retain_quadratic_prefix_copies(self):
        source = "export " * 4000
        tracemalloc.start()
        try:
            _js_export_bindings(source, [], [], [], {}, [], False)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        # The 28 KB malformed input previously implied ~56 MB of repeated
        # prefix strings. This permits ample platform overhead for offsets.
        self.assertLess(peak, 8_000_000)

    def test_arrow_regex_and_unrelated_regexp_template_keep_named_export(self):
        # Exact relevant shapes from pinned Axios bin/helpers/parser.js: the
        # unrelated template has ordinary regex escapes, not identifier escapes.
        helper = r"""export const parseSection = (body, name, cb) => {
  matchAll(body, new RegExp(`^(#+)\\s+${name}?(.*?)^\\1\\s+\\w+`, 'gims'), cb);
}
export const parseVersion = (rawVersion) => /^v?(\d+).(\d+).(\d+)/.exec(rawVersion);
"""
        _, calls = self.calls(helper, clause="{ parseVersion }", call="parseVersion(value)")
        self.assertEqual([edge["target"] for edge in calls], ["helper.js::parseVersion:function"])
        masked, literals = mask_source(helper, "javascript")
        self.assertNotIn(r"\d", masked)
        self.assertIn(r"/^v?(\d+).(\d+).(\d+)/", [literal["text"] for literal in literals])

    def test_arrow_regex_comments_are_masked_but_literals_do_not_hide_later_division(self):
        for gap in (" ", " /* comment */ ", " // comment\n "):
            source = f"const regex = () =>{gap}/export default function phantom()|target = other|eval(code)/g;\n"
            source += "function target() {} export default target;"
            self.assert_resolves(source)
            files, _ = self.calls(source)
            self.assertNotIn("phantom", {symbol["name"] for symbol in files[1]["symbols"]})
        for expression in ("value", "'text'", "'=> '", "`text`", "/text/", "<x/>"):
            with self.subTest(expression=expression):
                self.assert_unresolved(f"function target() {{}} const value = () => {expression} / (target = other) / 2; export default target;")

    def test_template_unicode_identifier_escapes_stay_unsupported(self):
        for expression in (r"\u0074arget = other", r"\u{74}arget = other", r"\u0065val(code)"):
            self.assert_unresolved("function target() {} const text = `${" + expression + "}`; export default target;")
        self.assert_unresolved(r"function target() {} t\u0061rget = other; export default target;")

    def test_completed_constructor_arrow_initializer_allows_newline_export(self):
        # Exact boundary shape from pinned Axios test/helpers/server.js: the
        # expression-bodied arrow ends in }) without a semicolon.
        helper = """export const makeEchoStream = (echo) => new WritableStream({
  write(chunk) {
    echo && console.log(`Echo chunk`, chunk);
  }
})

export const startTestServer = async (port) => {
  return await startHTTPServer(port);
}
"""
        _, calls = self.calls(helper, clause="{ startTestServer }", call="startTestServer(port)")
        self.assertEqual([edge["target"] for edge in calls], ["helper.js::startTestServer:function"])
        for previous in ("const prior = Factory()", "const prior = new Factory()",
                         "const prior = value => Factory(value)", "export const prior = () => Factory()"):
            for gap in ("\n", "\r\n", " /* comment\n */ ", " // comment\n"):
                self.assert_resolves(previous + gap + "export default function target() {}")

    def test_asi_boundary_does_not_reset_controls_properties_or_unfinished_expressions(self):
        for previous in ("if (condition)", "while (condition)", "for (;;)",
                         "const prior = condition ? Factory()", "const prior = condition && Factory()",
                         "const prior = object.Factory()", "const prior = Factory() + other()",
                         "const prior = Factory().", "const prior = Factory() +",
                         "const prior = (() => Factory())()", "const prior = Factory(",
                         "const prior = object.", "const prior = ()"):
            with self.subTest(previous=previous):
                self.assert_unresolved(previous + "\nexport default function target() {}")
                self.assert_unresolved(previous + "\nexport const target = () => {};", clause="{ target as renamed }")
        self.assert_unresolved("const prior = Factory() export default function target() {}")
        self.assert_unresolved("const prior = Factory() /* no newline */ export default function target() {}")
        self.assert_unresolved("function outer() { const prior = Factory()\nexport default function target() {} }")


if __name__ == "__main__":
    unittest.main()
