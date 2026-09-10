"""Source-shaped JVM regressions, with synthetic names and negative targets."""
import json
import textwrap
import unittest

from columbus.jvm import parse_jvm, resolve_jvm


class JVMNavigationTests(unittest.TestCase):
    def graph(self, sources):
        files = [parse_jvm(path, textwrap.dedent(source)) for path, source in sources.items()]
        for file in files:
            self.assertEqual([], file["diagnostics"], file["diagnostics"])
            json.dumps(file)
        edges = resolve_jvm(files)
        symbols = {s["id"]: s for f in files for s in f["symbols"]}
        calls = {(symbols[e["source"]]["qualname"], symbols[e["target"]]["qualname"])
                 for e in edges if e["kind"] == "calls"}
        return files, calls

    def test_explicit_import_survives_unrelated_wildcard_and_multiline_call(self):
        _, calls = self.graph({
            "Port.kt": """package ports
                interface Port {
                    fun execute(): String
                }
            """,
            "Client.kt": """package app
                import ports.Port
                import java.util.*
                class Client(private val port: Port) {
                    fun run() = port
                        .execute()
                }
            """,
        })
        self.assertIn(("app.Client.run", "ports.Port.execute"), calls)

    def test_constructor_and_declared_return_chain_keep_declaration_context(self):
        _, calls = self.graph({
            "Port.kt": """package ports
                interface Port {
                    fun execute()
                }
                class Registry {
                    fun lookup(): Port = TODO()
                }
            """,
            "Client.kt": """package app
                import ports.Registry
                class Port {
                    fun execute() {}
                }
                fun runReturn(registry: Registry) {
                    registry.lookup().execute()
                }
                fun runConstructor() {
                    Registry().lookup().execute()
                }
                fun runLocal(registry: Registry) {
                    val port = registry.lookup()
                    port.execute()
                }
            """,
        })
        for method in ("runReturn", "runConstructor", "runLocal"):
            self.assertIn(("app." + method, "ports.Port.execute"), calls)
            self.assertNotIn(("app." + method, "app.Port.execute"), calls)

    def test_generic_base_exposes_unique_inherited_member(self):
        files, calls = self.graph({"Workflow.kt": """package sample
            abstract class Workflow<P, C> {
                fun runPhases(phases: List<P>, context: C) {}
            }
            class Concrete : Workflow<String, Int>() {
                fun execute(phases: List<String>, context: Int) {
                    runPhases(phases, context)
                }
            }
        """})
        self.assertIn(("sample.Concrete.execute", "sample.Workflow.runPhases"), calls)
        self.assertTrue(next(r for r in files[0]["references"] if r["kind"] == "inherits")["resolved"])

    def test_inherited_overload_is_not_false_unique_local_target(self):
        files, calls = self.graph({"C.java": """package sample;
            class Base { void hit(int n) {} }
            class C extends Base {
                void hit(String s) {}
                void run() { hit(1); }
                void explicit(C other) { other.hit(1); }
            }
        """})
        self.assertFalse(calls)
        self.assertTrue(all("overload" in r["reason"] for r in files[0]["references"] if r["kind"] == "calls"))

    def test_same_spelling_from_different_packages_is_not_an_override(self):
        _, calls = self.graph({
            "left/Value.java": "package left; public class Value {}",
            "right/Value.java": "package right; public class Value {}",
            "Base.java": """package sample; import left.Value;
                class Base { void hit(Value value) {} }
            """,
            "C.java": """package sample; import right.Value;
                class C extends Base {
                    void hit(Value value) {}
                    void run(left.Value value) { hit(value); }
                }
            """,
        })
        self.assertNotIn(("sample.C.run", "sample.C.hit"), calls)

    def test_declared_override_preserves_unique_navigation(self):
        _, calls = self.graph({"C.kt": """package sample
            interface Port {
                fun execute()
            }
            class C : Port {
                override fun execute() {}
                fun run() = execute()
            }
        """})
        self.assertIn(("sample.C.run", "sample.C.execute"), calls)
        self.assertNotIn(("sample.C.run", "sample.Port.execute"), calls)

    def test_type_parameter_bound_shadows_same_named_class(self):
        _, calls = self.graph({"C.java": """package sample;
            class T { void hit() {} }
            interface API { void hit(); }
            class C<T extends API> { void run(T item) { item.hit(); } }
            class Unknown<T> { void run(T item) { item.hit(); } }
        """})
        self.assertIn(("sample.C.run", "sample.API.hit"), calls)
        self.assertNotIn(("sample.C.run", "sample.T.hit"), calls)
        self.assertFalse(any(source == "sample.Unknown.run" for source, _ in calls))

    def test_generic_receiver_and_type_parameter_method_shadow(self):
        _, calls = self.graph({"C.kt": """package sample
            class Box<T> {
                fun hit() {}
            }
            class T {
                fun hit() {}
            }
            fun run(box: Box<String>) = box.hit()
            fun <T> unknown(value: T) = value.hit()
        """})
        self.assertIn(("sample.run", "sample.Box.hit"), calls)
        self.assertFalse(any(source == "sample.unknown" for source, _ in calls))

    def test_explicitly_typed_map_lookup_reaches_declared_value_contract(self):
        _, calls = self.graph({"Registry.kt": """package sample
            interface Processor {
                fun process()
            }
            class Registry(private val processors: Map<String, Processor>) {
                fun run(key: String) {
                    val processor = processors[key] ?: return
                    processor.process()
                }
            }
        """})
        self.assertIn(("sample.Registry.run", "sample.Processor.process"), calls)

    def test_typed_collection_lambda_has_element_contract(self):
        _, calls = self.graph({"Workflow.kt": """package sample
            interface Processor<T> {
                fun process(context: T)
            }
            class Workflow<C> {
                fun run(processors: List<Processor<C>>, context: C) {
                    processors.forEach { processor -> processor.process(context) }
                }
            }
        """})
        self.assertIn(("sample.Workflow.run", "sample.Processor.process"), calls)

    def test_implicit_lambda_parameter_shadows_captured_it(self):
        _, calls = self.graph({"C.kt": """package sample
            interface Processor {
                fun process()
            }
            class Other {
                fun process() {}
            }
            fun run(processors: List<Processor>, it: Other) {
                processors.forEach { it.process() }
            }
        """})
        self.assertIn(("sample.run", "sample.Processor.process"), calls)
        self.assertNotIn(("sample.run", "sample.Other.process"), calls)

    def test_grouped_registry_lambda_keeps_value_type_without_di_dispatch(self):
        _, calls = self.graph({"Registry.kt": """package sample
            class Event(val site: String, val phases: List<String>)
            interface Workflow {
                fun execute(phases: List<String>)
            }
            class Concrete : Workflow {
                override fun execute(phases: List<String>) {}
            }
            class Registry(private val workflows: Map<String, Workflow>) {
                fun run(events: List<Event>) {
                    events.groupBy { it.site }.forEach { (site, siteEvents) ->
                        val workflow = workflows[site]
                        if (workflow == null) return@forEach
                        siteEvents.groupBy { it.phases }.forEach { (phases, phaseEvents) ->
                            workflow.execute(phases)
                        }
                    }
                }
            }
        """})
        self.assertIn(("sample.Registry.run", "sample.Workflow.execute"), calls)
        self.assertNotIn(("sample.Registry.run", "sample.Concrete.execute"), calls)

    def test_collection_extension_conflict_does_not_enable_lambda_dispatch(self):
        _, calls = self.graph({"C.kt": """package sample
            interface Processor {
                fun process()
            }
            fun List<Processor>.forEach(block: Processor.() -> Unit) {}
            fun run(processors: List<Processor>) {
                processors.forEach { processor -> processor.process() }
            }
        """})
        self.assertNotIn(("sample.run", "sample.Processor.process"), calls)

    def test_grouping_value_transform_does_not_reuse_original_element_type(self):
        _, calls = self.graph({"C.kt": """package sample
            interface Processor {
                fun process()
            }
            class Other {
                fun process() {}
            }
            fun run(processors: List<Processor>) {
                processors.groupBy({ 0 }, { Other() }).forEach { (_, items) ->
                    items.forEach { item -> item.process() }
                }
            }
        """})
        self.assertNotIn(("sample.run", "sample.Processor.process"), calls)

    def test_member_extension_does_not_infer_standard_collection_contract(self):
        _, calls = self.graph({"C.kt": """package sample
            interface Processor {
                fun process()
            }
            class Other {
                fun process() {}
            }
            class C {
                fun List<Processor>.forEach(block: (Other) -> Unit) {}
                fun run(processors: List<Processor>) {
                    processors.forEach { item -> item.process() }
                }
            }
        """})
        self.assertNotIn(("sample.C.run", "sample.Processor.process"), calls)

    def test_inherited_member_extension_blocks_standard_collection_inference(self):
        _, calls = self.graph({"C.kt": """package sample
            interface Processor {
                fun process()
            }
            class Other {
                fun process() {}
            }
            open class Base {
                fun List<Processor>.forEach(block: (Other) -> Unit) {}
            }
            class C : Base() {
                fun run(processors: List<Processor>) {
                    processors.forEach { item -> item.process() }
                }
            }
        """})
        self.assertNotIn(("sample.C.run", "sample.Processor.process"), calls)

    def test_annotation_text_cannot_hide_inherited_extension_conflict(self):
        _, calls = self.graph({"C.kt": """package sample
            interface Processor {
                fun process()
            }
            class Other {
                fun process() {}
            }
            open class Base {
                @Tag("x private y")
                public fun List<Processor>.forEach(block: (Other) -> Unit) {}
            }
            class C : Base() {
                fun run(processors: List<Processor>) {
                    processors.forEach { item -> item.process() }
                }
            }
        """})
        self.assertNotIn(("sample.C.run", "sample.Processor.process"), calls)

    def test_missing_modifier_metadata_cannot_hide_inherited_conflicts(self):
        files, _ = self.graph({"C.kt": """package sample
            interface Processor {
                fun process()
            }
            class Other {
                fun process() {}
            }
            open class Base {
                @Tag("x private y")
                public fun List<Processor>.forEach(block: (Other) -> Unit) {}
                private fun hidden() {}
            }
            class C : Base() {
                fun run(processors: List<Processor>) {
                    processors.forEach { item -> item.process() }
                    hidden()
                }
            }
        """})
        for file in files:
            for symbol in file["symbols"]:
                symbol.pop("declaration_modifiers", None)
        edges = resolve_jvm(files)
        self.assertFalse(any(edge["kind"] == "calls" for edge in edges))

    def test_visible_get_extension_blocks_standard_map_value_inference(self):
        _, calls = self.graph({"C.kt": """package sample
            interface Processor {
                fun process()
            }
            class Other {
                fun process() {}
            }
            operator fun Map<String, Processor>.get(key: Int): Other = Other()
            fun run(values: Map<String, Processor>) = values[0].process()
        """})
        self.assertNotIn(("sample.run", "sample.Processor.process"), calls)

    def test_multi_index_get_does_not_infer_single_key_map_contract(self):
        _, calls = self.graph({"C.kt": """package sample
            interface Processor {
                fun process()
            }
            class Other {
                fun process() {}
            }
            operator fun Map<String, Processor>.get(first: Int, second: Int): Other = Other()
            fun run(values: Map<String, Processor>) = values[0, 1].process()
        """})
        self.assertNotIn(("sample.run", "sample.Processor.process"), calls)

    def test_same_package_type_alias_does_not_become_standard_map(self):
        _, calls = self.graph({
            "Aliases.kt": """package sample
                typealias Map<K, V> = CustomMap<K, V>
                class CustomMap<K, V> {
                    operator fun get(key: K): Other = Other()
                }
            """,
            "C.kt": """package sample
                interface Processor {
                    fun process()
                }
                class Other {
                    fun process() {}
                }
                fun run(values: Map<String, Processor>) = values["key"].process()
            """,
        })
        self.assertNotIn(("sample.run", "sample.Processor.process"), calls)

    def test_nested_type_does_not_reuse_same_package_type(self):
        _, calls = self.graph({"C.kt": """package sample
            class Port {
                fun execute() {}
            }
            class C {
                class Port {
                    fun execute() {}
                }
                fun run(port: Port) = port.execute()
            }
        """})
        self.assertIn(("sample.C.run", "sample.C.Port.execute"), calls)
        self.assertNotIn(("sample.C.run", "sample.Port.execute"), calls)

    def test_receiver_lambda_and_untyped_shadow_remain_unresolved(self):
        _, calls = self.graph({"C.kt": """package sample
            class Port {
                fun execute() {}
            }
            class C(private val port: Port) {
                fun run(unknown: External) {
                    unknown.apply { port.execute() }
                    val callback = { port: External -> port.execute() }
                }
            }
        """})
        self.assertNotIn(("sample.C.run", "sample.Port.execute"), calls)

    def test_custom_collection_name_does_not_infer_standard_map_value(self):
        _, calls = self.graph({"C.kt": """package sample
            class Port {
                fun execute() {}
            }
            class Map<K, V>
            fun run(values: Map<String, Port>) {
                val port = values["key"]
                port.execute()
            }
        """})
        self.assertNotIn(("sample.run", "sample.Port.execute"), calls)

    def test_annotation_details_keep_spans_and_truncation(self):
        source = 'package sample\n@sample.Route(\n "' + 'x' * 320 + '"\n)\nclass C\n'
        files, _ = self.graph({"C.kt": source})
        symbol = next(s for s in files[0]["symbols"] if s["name"] == "C")
        detail = symbol["annotation_details"][0]
        self.assertEqual("sample.Route", detail["name"])
        self.assertEqual((2, 4), (detail["start_line"], detail["end_line"]))
        self.assertTrue(detail["truncated"])
        self.assertEqual(300, len(detail["text"]))
        self.assertEqual([detail["text"]], symbol["annotations"])

    def test_detached_annotation_prefix_keeps_complete_arguments_and_source_span(self):
        files, _ = self.graph({"C.kt": '''\
            @RestController
            @RequestMapping("/api")
            @Tag(name = "catalog")
            class C(
            ) {
                /**
                 */
                @ApiResponses(
                    value = [
                        ApiResponse(
                        ),
                    ],
                )
                fun run() {
                }
            }
            /** tail */
        '''})
        owner = next(s for s in files[0]["symbols"] if s["name"] == "C")
        details = owner["annotation_details"]
        self.assertEqual(["RestController", "RequestMapping", "Tag"], [d["name"] for d in details])
        self.assertEqual('@RequestMapping("/api")', details[1]["text"])
        self.assertEqual((2, 2), (details[1]["start_line"], details[1]["end_line"]))
        self.assertEqual(1, owner["start_line"])
        self.assertTrue(owner["signature"].startswith('@RestController @RequestMapping("/api")'))
        self.assertEqual(2, owner.get("annotation_metadata_version"))
        self.assertIs(True, owner.get("annotation_metadata_complete"))

    def test_detached_annotation_does_not_cross_executable_expression_or_separator(self):
        for prefix in ('@Marker consume()', '@Marker consume() + other()', '@Marker("old");'):
            with self.subTest(prefix=prefix):
                files, _ = self.graph({"C.kt": prefix + '\nclass C {}\n'})
                owner = next(s for s in files[0]["symbols"] if s["name"] == "C")
                self.assertEqual([], owner["annotation_details"])
                self.assertEqual(2, owner["start_line"])

    def test_detached_annotation_recovery_allows_only_intervening_trivia(self):
        files, _ = self.graph({"C.kt": '''\
            @RestController
            @RequestMapping("/api")
            // A comment between the route and the declaration.

            @Tag(name = "catalog")
            class C(
            ) {
                /**
                 */
                @ApiResponses(
                    value = [
                        ApiResponse(
                        ),
                    ],
                )
                fun run() {
                }
            }
            /** tail */
        '''})
        owner = next(s for s in files[0]["symbols"] if s["name"] == "C")
        self.assertEqual(["RestController", "RequestMapping", "Tag"],
                         [a["name"] for a in owner["annotation_details"]])
        self.assertEqual(1, owner["start_line"])
        self.assertIs(True, owner["annotation_metadata_complete"])

    def test_annotation_prefix_does_not_cross_previous_declaration(self):
        files, _ = self.graph({"C.kt": '''\
            @Route("/previous")
            class Previous {}
            // A separate declaration has no route.
            class C {}
        '''})
        owner = next(s for s in files[0]["symbols"] if s["name"] == "C")
        self.assertEqual([], owner["annotation_details"])

    def test_kotlin_declaration_modifiers_exclude_annotation_strings(self):
        files, _ = self.graph({"C.kt": """package sample
            @Tag("private static final")
            internal open class C(private val value: String) {
                @Tag("private route")
                protected open fun run() {}
                private suspend fun execute() {}
            }
        """})
        symbols = {s["qualname"]: s for s in files[0]["symbols"]}
        self.assertEqual(["internal", "open"], symbols["sample.C"].get("declaration_modifiers"))
        self.assertEqual(["private"], symbols["sample.C.value"].get("declaration_modifiers"))
        self.assertEqual(["open", "protected"], symbols["sample.C.run"].get("declaration_modifiers"))
        self.assertEqual(["private", "suspend"], symbols["sample.C.execute"].get("declaration_modifiers"))

    def test_java_declaration_modifiers_exclude_annotation_strings(self):
        files, _ = self.graph({"C.java": """package sample;
            @Tag("private static route") public abstract class C {
                @Tag("public route") protected static final void run() {}
                public abstract void execute();
            }
        """})
        symbols = {s["qualname"]: s for s in files[0]["symbols"]}
        self.assertEqual(["abstract", "public"], symbols["sample.C"].get("declaration_modifiers"))
        self.assertEqual(2, symbols["sample.C"].get("annotation_metadata_version"))
        self.assertIs(True, symbols["sample.C"].get("annotation_metadata_complete"))
        self.assertEqual(["final", "protected", "static"], symbols["sample.C.run"].get("declaration_modifiers"))
        self.assertEqual(["abstract", "public"], symbols["sample.C.execute"].get("declaration_modifiers"))


if __name__ == "__main__":
    unittest.main()
