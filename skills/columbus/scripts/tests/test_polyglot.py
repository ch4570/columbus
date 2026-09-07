"""Polyglot navigation contracts, including conservative non-resolution."""
import json
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from columbus.discovery import discover, load_config
from columbus.languages import analyzer_fingerprint, language_for, parse_source, resolve_files
from columbus.polyglot import mask_source


def parsed(path, source, **kwargs):
    return parse_source(path, textwrap.dedent(source).lstrip("\n"), Path(path).stem, **kwargs)


def edges(files, kind):
    return [e for e in resolve_files(files) if e["kind"] == kind]


class DetectionTests(unittest.TestCase):
    def test_extensions_names_shebang_and_unknown(self):
        expected = {"a.TSX": "typescript", "a.C": "cpp", "a.rs": "rust", "a.go": "go",
                    "Dockerfile": "dockerfile", "Gemfile": "ruby", "go.mod": "go-module",
                    "a.fs": "fsharp", "a.ex": "elixir", "a.sol": "solidity", "a.unknown": "text"}
        for path, language in expected.items():
            with self.subTest(path=path):
                self.assertEqual(language_for(path), language)
        self.assertEqual(language_for("bin/job", "#!/usr/bin/env -S python3.14 -u\n"), "python")
        self.assertEqual(language_for("bin/build", "#!/bin/bash\n"), "shell")
        self.assertEqual(language_for("a.mod", config={"extensions": {".mod": "custom"}}), "custom")

    def test_discovery_fallback_and_safety_in_non_git_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, data in {"app.ts": b"export function run() {}", "logic.odd": b"routine answer",
                               "README.md": b"architecture reference", "picture.odd": b"\0binary",
                               "late_binary.odd": b"a" * 9000 + b"\0", "secret.key": b"private",
                               ".env.local": b"PASSWORD=123", ".gitignore": b"unused\n",
                               "large.odd": b"a" * 1_000_001, "tool": b"#!/usr/bin/env ruby\ndef run; end"}.items():
                (root / name).write_bytes(data)
            (root / ".omx").mkdir()
            (root / ".omx" / "state.ts").write_text("function secret() {}")
            (root / "link.ts").symlink_to(root / "app.ts")
            paths, inventory = discover(root)
            self.assertEqual(set(paths), {"app.ts", "logic.odd", "README.md", "tool"})
            self.assertEqual(inventory["detected_languages"]["tool"], "ruby")
            self.assertEqual(inventory["detected_languages"]["logic.odd"], "text")
            self.assertIn(".gitignore", inventory["config_paths"])
            self.assertIn("large.odd", inventory["oversized_paths"])
            self.assertEqual(set(inventory["binary_paths"]), {"picture.odd", "late_binary.odd"})
            self.assertEqual(inventory["probe_files"], 4)

    def test_extensionless_python_honors_encoding_cookie(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tool").write_bytes(b"#!/usr/bin/python3\n# coding: latin-1\ndef caf\xe9(): pass\n")
            paths, inventory = discover(root)
            self.assertEqual(paths, ["tool"])
            self.assertEqual(inventory["detected_languages"]["tool"], "python")

    def test_known_languages_need_no_discovery_content_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.ts").write_text("function run() {}")
            (root / "main.py").write_bytes(b"\xff invalid python")
            with patch.object(Path, "open", side_effect=AssertionError("unexpected content read")):
                paths, inventory = discover(root)
            self.assertEqual(set(paths), {"main.ts", "main.py"})
            self.assertEqual(inventory["probe_files"], 0)
            self.assertEqual(inventory["probe_bytes"], 0)

    def test_declarative_custom_language_and_include_exclude(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {"include": ["**/*.custom"], "exclude": ["ignored*"],
                      "extensions": {".custom": "domain"}, "declarations": {"domain": ["routine"]}}
            (root / ".columbus.json").write_text(json.dumps(config))
            (root / "main.custom").write_text("routine calculate\nresult = 42\n")
            (root / "ignored.custom").write_text("routine wrong")
            (root / "other.js").write_text("function wrong() {}")
            paths, inventory = discover(root)
            self.assertEqual(paths, ["main.custom"])
            self.assertIn(".columbus.json", inventory["config_paths"])
            file = parsed(paths[0], (root / paths[0]).read_text(), config=inventory["language_config"])
            self.assertEqual(file["language"], "domain")
            self.assertEqual(file["symbols"][1]["name"], "calculate")
            self.assertEqual(file["symbols"][1]["fidelity"], "heuristic")
            a = analyzer_fingerprint(paths, inventory["language_config"], inventory["detected_languages"])
            config["declarations"]["domain"] = ["task"]
            b = analyzer_fingerprint(paths, config, inventory["detected_languages"])
            self.assertNotEqual(a, b)

    def test_config_rejects_code_regex_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for config in ({"plugin": "execute.py"}, {"declarations": {"custom": ["(a+)+$"]}},
                           {"include": "*.ts"}, {"extensions": {"ts": "typescript"}}):
                (root / ".columbus.json").write_text(json.dumps(config))
                with self.assertRaises(ValueError):
                    load_config(root)
            (root / ".columbus.json").unlink()
            (root / "config").write_text("{}")
            (root / ".columbus.json").symlink_to(root / "config")
            with self.assertRaises(ValueError):
                load_config(root)


class PolyglotParserTests(unittest.TestCase):
    def test_mainstream_declaration_and_direct_calls(self):
        samples = {
            "main.js": "export function helper() {}\nexport function run() { helper(); }",
            "main.ts": "export function helper(): void {}\nexport function run(): void { helper(); }",
            "main.go": "package main\nfunc helper() {}\nfunc run() { helper() }",
            "main.rs": "fn helper() {}\nfn run() { helper(); }",
            "main.c": "void helper(void) {}\nvoid run(void) { helper(); }",
            "main.cpp": "void helper() {}\nvoid run() { helper(); }",
            "main.cs": "static void helper() {}\nstatic void run() { helper(); }",
            "main.php": "<?php\nfunction helper() {}\nfunction run() { helper(); }",
            "main.swift": "func helper() {}\nfunc run() { helper() }",
            "main.dart": "void helper() {}\nvoid run() { helper(); }",
        }
        for path, source in samples.items():
            with self.subTest(path=path):
                file = parsed(path, source)
                self.assertEqual({s["name"] for s in file["symbols"][1:]}, {"helper", "run"})
                calls = edges([file], "calls")
                self.assertEqual([(c["source"], c["target"]) for c in calls],
                                 [(f"{path}::run:function", f"{path}::helper:function")])
                self.assertEqual({e["confidence"] for e in resolve_files([file])}, {"heuristic"})
                self.assertEqual(file["fidelity"], "heuristic")

    def test_additional_language_declarations(self):
        samples = {"a.rb": "class Store\n  def save\n  end\nend", "a.sh": "run() { echo hi; }",
                   "a.lua": "function run()\nend", "a.ex": "defmodule Store do\n def save() do\n end\nend",
                   "a.scala": "class Store { def save() = {} }", "a.nim": "proc run() = discard",
                   "a.sql": "CREATE TABLE orders (id int);", "a.proto": "message Order { string id = 1; }",
                   "a.graphql": "type Order { id: ID! }", "a.jl": "function run()\nend"}
        for path, source in samples.items():
            with self.subTest(path=path):
                file = parsed(path, source)
                self.assertGreater(len(file["symbols"]), 1)
                self.assertTrue(all(s["fidelity"] == "heuristic" for s in file["symbols"]))

    def test_comments_strings_templates_raw_strings_and_regex_are_not_code(self):
        samples = {
            "a.js": r'''// function fake1() {}
                const a = "function fake2() { hidden(); }";
                const b = `function fake3() { ${hidden()} }`;
                const c = /function fake4\(\) { hidden\(\); }/;
                /* function fake5() { hidden(); } */
                function real() {}
            ''',
            "a.rs": '''/* fn fake1() {} /* fn fake2() {} */ */
                let a = r###"fn fake3() { hidden(); }"###;
                fn real() {}
            ''',
            "a.cpp": '''const char *a = R"text(void fake() { hidden(); })text";
                void real() {}
            ''',
            "a.rb": '''# def fake1
                value = <<~TEXT
                def fake2
                TEXT
                def real
                end
            ''',
        }
        for path, source in samples.items():
            with self.subTest(path=path):
                file = parsed(path, source)
                self.assertEqual([s["name"] for s in file["symbols"][1:]], ["real"])
                self.assertFalse(any("hidden" in r["name"] for r in file["references"]))
                masked, _ = mask_source(textwrap.dedent(source).lstrip("\n"), file["language"])
                self.assertEqual(masked.count("\n"), textwrap.dedent(source).lstrip("\n").count("\n"))

    def test_relative_import_call_and_file_dependency(self):
        helper = parsed("lib/helper.ts", "export function help() {}")
        main = parsed("main.ts", "import { help as assist } from './lib/helper';\nfunction run() { assist(); }")
        calls = edges([main, helper], "calls")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["target"], "lib/helper.ts::help:function")
        self.assertEqual(edges([main, helper], "imports")[0]["target"], "lib/helper.ts::module")
        self.assertTrue(main["imports"][0]["resolved"])
        self.assertEqual(edges([main], "calls"), [])
        self.assertNotIn("target", main["references"][0])

    def test_ambiguous_import_and_nonexport_do_not_link_calls(self):
        main = parsed("main.ts", "import { help } from './helper';\nfunction run() { help(); }")
        one = parsed("helper.ts", "export function help() {}")
        two = parsed("helper.js", "export function help() {}")
        self.assertEqual(edges([main, one, two], "calls"), [])
        self.assertEqual(edges([main, one, two], "imports"), [])
        hidden = parsed("helper.ts", "function help() {}")
        self.assertEqual(edges([main, hidden], "calls"), [])
        self.assertEqual(len(edges([main, hidden], "imports")), 1)

    def test_shadowed_parameters_assignments_duplicates_and_receivers_stay_unknown(self):
        file = parsed("main.ts", '''
            function help() {}
            function parameter(help) { help(); }
            function assigned() { let help = other; help(); }
            function ordinary() { help(); }
            function receiver(client) { client.help(); unknown.help(); }
            function callback() { values.map((help) => help()); }
            function destructured() { const {help} = callbacks; help(); }
            function caught() { try {} catch(help) { help(); } }
            function spaced(client) { client . help(); client?.help(); }
        ''')
        calls = edges([file], "calls")
        self.assertEqual([(c["source"], c["target"]) for c in calls],
                         [("main.ts::ordinary:function", "main.ts::help:function")])
        duplicate = parsed("main.ts", "function help() {}\nfunction help() {}\nfunction run() { help(); }")
        self.assertEqual(edges([duplicate], "calls"), [])
        self.assertEqual(len({s["id"] for s in duplicate["symbols"]}), len(duplicate["symbols"]))

    def test_no_cross_file_basename_matching_or_cross_language_calls(self):
        main = parsed("main.rs", "fn run() { help(); }")
        helper = parsed("helper.rs", "fn help() {}")
        foreign = parsed("helper.go", "func help() {}")
        self.assertEqual(edges([main, helper, foreign], "calls"), [])

    def test_c_ruby_dart_rust_relative_module_edges(self):
        samples = [("main.cpp", '#include "helper.h"', "helper.h", "struct Helper {};"),
                   ("main.rb", "require_relative 'helper'", "helper.rb", "def help\nend"),
                   ("main.dart", "import './helper.dart';", "helper.dart", "void help() {}"),
                   ("src/main.rs", "mod helper;", "src/helper.rs", "fn help() {}")]
        for path, source, helper_path, helper_source in samples:
            with self.subTest(path=path):
                result = edges([parsed(path, source), parsed(helper_path, helper_source)], "imports")
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]["target"], helper_path + "::module")

    def test_methods_are_nested_and_never_become_global_functions(self):
        sources = {
            "main.ts": "class Store { save() {} run() { this.save(); } }\nfunction run() { save(); }",
            "main.go": "type Store struct {}\nfunc (s Store) save() {}\nfunc run() { save() }",
            "main.rs": "struct Store {}\nimpl Store { fn save(&self) {} }\nfn run() { save(); }",
        }
        for path, source in sources.items():
            with self.subTest(path=path):
                file = parsed(path, source)
                save = next(s for s in file["symbols"] if s["name"] == "save")
                self.assertEqual(save["kind"], "method")
                self.assertEqual(edges([file], "calls"), [])
                if path.endswith((".ts", ".rs")):
                    self.assertNotEqual(save["parent_id"], path + "::module")

    def test_perl_namespace_is_not_a_second_file_module(self):
        file = parsed("Foo.pm", "package Foo;\nsub run { return 1; }\n1;\n")
        self.assertEqual([s["id"] for s in file["symbols"] if s["kind"] == "module"], ["Foo.pm::module"])
        self.assertEqual(next(s for s in file["symbols"] if s["name"] == "Foo" and s["parent_id"])["kind"], "namespace")

    def test_zero_argument_arrow_and_spaced_receivers(self):
        file = parsed("main.ts", "function refund() {}\nconst cancel = () => refund();")
        calls = edges([file], "calls")
        self.assertEqual([(e["source"], e["target"]) for e in calls],
                         [("main.ts::cancel:function", "main.ts::refund:function")])
        for path, source in {
            "main.ts": "function refund() {}\nfunction run(obj) { obj?.refund(); obj . refund(); }",
            "main.cpp": "void refund() {}\nvoid run() { obj . refund(); obj -> refund(); ns :: refund(); }",
        }.items():
            with self.subTest(path=path):
                self.assertEqual(edges([parsed(path, source)], "calls"), [])

    def test_multiline_named_import_and_commonjs_module_edge(self):
        helper = parsed("helper.ts", "export function help() {}")
        caller = parsed("main.ts", "import {\n help as assist,\n} from './helper';\nfunction run() { assist(); }")
        self.assertEqual(len(edges([caller, helper], "calls")), 1)
        commonjs = parsed("main.js", "const helpers = require('./helper');")
        self.assertEqual(len(edges([commonjs, helper], "imports")), 1)

    def test_unknown_text_has_module_and_no_invented_semantics(self):
        file = parsed("logic.unseen", "unusual start\nfunction imagined() { imagined(); }\n")
        self.assertEqual(file["symbols"][0]["id"], "logic.unseen::module")
        self.assertEqual(file["fidelity"], "text")
        self.assertEqual(len(file["symbols"]), 1)
        self.assertEqual(resolve_files([file]), [])
        json.dumps(file)


if __name__ == "__main__":
    unittest.main()
