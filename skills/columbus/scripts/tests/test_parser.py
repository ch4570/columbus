import json
import textwrap
import unittest

from columbus.parser import parse_source, resolve_files


def parsed(module, source, path=None):
    return parse_source(path or module.replace(".", "/") + ".py",
                        textwrap.dedent(source).lstrip("\n"), module)


def relations(files, kind="calls"):
    return [edge for edge in resolve_files(files) if edge["kind"] == kind]


class ParserTests(unittest.TestCase):
    def test_absolute_import_alias_and_module_alias(self):
        helpers = parsed("pkg.helpers", "def work(): pass")
        caller = parsed("pkg.main", """
            from pkg.helpers import work as do_work
            import pkg.helpers as h
            def run():
                do_work()
                h.work()
        """)
        calls = relations([caller, helpers])
        self.assertEqual(len(calls), 2)
        self.assertEqual({e["target"] for e in calls}, {"pkg/helpers.py::work:function"})
        self.assertEqual({e["confidence"] for e in calls}, {"resolved_static", "heuristic"})
        self.assertTrue(all(r["resolved"] for r in caller["references"]))
        self.assertEqual(len(relations([caller, helpers], "imports")), 2)

    def test_relative_import_levels_and_package_init(self):
        helpers = parsed("pkg.helpers", "class Base: pass\ndef work(): pass")
        inner = parsed("pkg.sub.main", """
            from ..helpers import work
            from .. import helpers as h
            from ..helpers import Base
            class Child(Base): pass
            def run():
                work()
                h.work()
        """)
        package = parsed("pkg", "from .helpers import work", "pkg/__init__.py")
        consumer = parsed("client", "from pkg import work\nwork()")
        files = [helpers, inner, package, consumer]
        self.assertEqual(len(relations(files)), 3)
        inheritance = relations(files, "inherits")
        self.assertEqual(len(inheritance), 1)
        self.assertEqual(inheritance[0]["target"], "pkg/helpers.py::Base:class")

    def test_parameters_and_assignments_prevent_false_global_calls(self):
        file = parsed("main", """
            def target(): pass
            def parameter(target):
                target()
            def assigned():
                target()
                target = object()
            def imported():
                import external as target
                target()
            def ordinary():
                target()
        """)
        calls = relations([file])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["source"], "main.py::ordinary:function")
        self.assertGreaterEqual(sum(not r["resolved"] for r in file["references"]), 4)

    def test_nested_lexical_function_and_class_scope(self):
        file = parsed("main", """
            def helper(): pass
            def outer():
                def helper(): pass
                class Inner:
                    def helper(self): pass
                    def run(self):
                        helper()
                        self.helper()
                def nested():
                    helper()
                return nested
            class Outer:
                def helper(self): pass
                class Inner:
                    def run(self):
                        helper()
        """)
        calls = relations([file])
        pairs = {(e["source"], e["target"]) for e in calls}
        self.assertEqual(pairs, {
            ("main.py::outer.Inner.run:method", "main.py::outer.helper:function"),
            ("main.py::outer.nested:function", "main.py::outer.helper:function"),
            ("main.py::Outer.Inner.run:method", "main.py::helper:function"),
        })
        self.assertFalse(next(r for r in file["references"] if r["name"] == "self.helper")["resolved"])

    def test_duplicate_definitions_have_unique_ids_and_are_ambiguous(self):
        file = parsed("main", """
            def same():
                def child(): pass
            def same():
                def child(): pass
            same()
        """)
        ids = [symbol["id"] for symbol in file["symbols"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("main.py::same:function#2", ids)
        self.assertIn("main.py::same.child:function#2", ids)
        self.assertEqual(relations([file]), [])
        child = next(s for s in file["symbols"] if s["id"].endswith("child:function#2"))
        self.assertEqual(child["parent_id"], "main.py::same:function#2")

    def test_parse_failure_never_keeps_partial_symbols(self):
        file = parsed("main", "def good(): pass\ndef broken(:\n")
        self.assertTrue(file["diagnostics"])
        self.assertEqual([s["kind"] for s in file["symbols"]], ["module"])
        self.assertEqual(file["references"], [])
        self.assertEqual(resolve_files([file]), [])
        json.dumps(file)

    def test_no_global_last_name_matching(self):
        file = parsed("main", """
            def save(): pass
            def run(client):
                client.save()
                unknown.save()
                make_client().save()
        """)
        self.assertEqual(relations([file]), [])
        self.assertEqual(len(file["references"]), 4)

    def test_namespace_import_without_package_init(self):
        helper = parsed("company.pkg.helper", "def run(): pass")
        caller = parsed("main", "import company.pkg.helper\ncompany.pkg.helper.run()")
        self.assertEqual(len(relations([helper, caller])), 1)
        imports = relations([helper, caller], "imports")
        self.assertEqual(imports[0]["target"], "company/pkg/helper.py::module")

    def test_comprehension_and_lambda_parameters_are_local(self):
        file = parsed("main", """
            def target(): pass
            def run(values):
                result = [target() for target in values]
                fn = lambda target: target()
                target()
        """)
        calls = relations([file])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["line"], 5)

    def test_walrus_in_comprehension_shadows_containing_scope(self):
        file = parsed("main", """
            def target(): pass
            def run(values):
                result = [(target := value) for value in values]
                target()
        """)
        self.assertEqual(relations([file]), [])

    def test_pattern_and_exception_targets_are_local(self):
        file = parsed("main", """
            def target(): pass
            def pattern(value):
                match value:
                    case {'callback': target}:
                        target()
            def handler():
                try:
                    pass
                except Exception as target:
                    target()
        """)
        self.assertEqual(relations([file]), [])

    def test_explicit_global_and_nonlocal_resolution(self):
        file = parsed("main", """
            def target(): pass
            def global_call():
                global target
                target()
            def outer():
                def target(): pass
                def inner():
                    nonlocal target
                    target()
        """)
        calls = relations([file])
        self.assertEqual({e["target"] for e in calls}, {
            "main.py::target:function", "main.py::outer.target:function"})

    def test_cyclic_reexports_do_not_recurse_forever(self):
        a = parsed("a", "from b import thing\nthing()")
        b = parsed("b", "from a import thing")
        self.assertEqual(relations([a, b]), [])

    def test_nonlocal_rebinding_reaches_actual_enclosing_binding(self):
        file = parsed("main", """
            def outer():
                def middle():
                    def inner(value):
                        nonlocal target
                        target = value
                def target(): pass
                def sibling():
                    target()
        """)
        self.assertEqual(relations([file]), [])

    def test_resolution_can_be_repeated_without_stale_target(self):
        helper = parsed("helper", "def work(): pass")
        caller = parsed("main", "from helper import work\nwork()")
        self.assertEqual(len(relations([helper, caller])), 1)
        self.assertEqual(relations([caller]), [])
        self.assertNotIn("target", caller["references"][0])
        self.assertFalse(caller["imports"][0]["resolved"])

    def test_duplicate_modules_are_ambiguous(self):
        a = parsed("helper", "def work(): pass", "a/helper.py")
        b = parsed("helper", "def work(): pass", "b/helper.py")
        caller = parsed("main", "from helper import work\nwork()")
        self.assertEqual(relations([a, b, caller]), [])

    def test_class_attribute_and_inheritance_are_navigable(self):
        file = parsed("main", """
            class Base:
                @staticmethod
                def work(): pass
            class Child(Base): pass
            Base.work()
        """)
        self.assertEqual(relations([file])[0]["target"], "main.py::Base.work:method")
        self.assertEqual(relations([file])[0]["confidence"], "heuristic")
        self.assertEqual(len(relations([file], "inherits")), 1)

    def test_star_import_prevents_unjustified_resolution(self):
        file = parsed("main", "def target(): pass\nfrom external import *\ntarget()")
        self.assertEqual(relations([file]), [])


if __name__ == "__main__":
    unittest.main()
