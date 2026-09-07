"""Meaningful JVM navigation checks: resolution must prefer missing to false edges."""
import json
import unittest

from repoatlas.jvm import parse_jvm, resolve_jvm


class JVMTests(unittest.TestCase):
    def parsed(self, path, source):
        result = parse_jvm(path, source)
        self.assertEqual([], result["diagnostics"], result["diagnostics"])
        json.dumps(result)  # Cached parse records must round-trip through SQLite JSON.
        return result

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
