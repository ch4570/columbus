import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from columbus.index import RepositoryIndex, byte_size


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/"repo"
        self.root.mkdir()
        self.index = RepositoryIndex(Path(self.temp.name)/"graph.sqlite")

    def write(self, path, source):
        file = self.root/path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(source, encoding="utf-8", newline="\n")

    def seed(self):
        self.write("payments.py", "def refund_payment(amount):\n    return amount\n")
        self.write("orders.py", "from payments import refund_payment\ndef cancel_order():\n    return refund_payment(10)\n")
        return self.index.refresh(self.root)

    def test_literal_assignment_search_tracks_reassignment_and_removal(self):
        for number, (source, signatures) in enumerate([
            ('FLAG = False\n', ['FLAG = False']),
            ('FLAG = True\n', ['FLAG = True']),
            ('FLAG = True\nFLAG = False\n', ['FLAG = True', 'FLAG = False']),
            ('FLAG = choose()\n', []),
            ('FLAG: bool\n', []),
            ('', []),
            ('FLAG = False\n', ['FLAG = False']),
        ]):
            with self.subTest(source=source):
                self.write('flags.py', source)
                self.index.refresh(self.root)
                hits = self.index.search('FLAG')['hits']
                assignments = [h for h in hits if h['kind'] == 'assignment']
                self.assertEqual(sorted(h['signature'] for h in assignments), sorted(signatures))
                fresh = RepositoryIndex(Path(self.temp.name) / ('literal-fresh-%d.sqlite' % number))
                fresh.refresh(self.root)
                self.assertEqual(self.index.graph(), fresh.graph())
                self.assertEqual(hits, fresh.search('FLAG')['hits'])

    def test_java_base_absence_is_recomputed_after_ancestor_changes(self):
        from contextlib import closing
        import sqlite3
        from columbus.index import decode_parse

        self.write('Base.java', 'class Base {}')
        self.write('Middle.java', 'class Middle extends Base {}')
        self.write('C.java', 'class C extends Middle { void hit(String s) {} void run() { hit("x"); } }')

        def snapshot(index):
            with closing(sqlite3.connect(index.db)) as conn:
                return {path: decode_parse(data) for path, data in conn.execute('SELECT path,parsed FROM files')}

        initial = None
        for number, (base, expected) in enumerate([
            ('class Base {}', True),
            ('class Base { void hit(int n) {} }', False),
            ('class Base { void broken( }', False),
            (None, False),
            ('class Base {}', True),
        ]):
            with self.subTest(base=base):
                if base is None:
                    (self.root / 'Base.java').unlink()
                else:
                    self.write('Base.java', base)
                self.index.refresh(self.root)
                facts = snapshot(self.index)
                call, = [r for r in facts['C.java']['references'] if r['kind'] == 'calls']
                self.assertEqual(call['resolved'], expected)
                fresh = RepositoryIndex(Path(self.temp.name) / ('fresh-%d.sqlite' % number))
                fresh.refresh(self.root)
                self.assertEqual(facts, snapshot(fresh))
                self.assertEqual(self.index.graph(), fresh.graph())
                if number == 0:
                    initial = facts
        self.assertEqual(facts, initial)

    def test_java_getter_loop_relinks_unchanged_consumers(self):
        from contextlib import closing
        import sqlite3
        from columbus.index import decode_parse

        for package in ('a', 'b'):
            self.write(package + '/Item.java', 'package ' + package +
                       '; public class Item { public void hit() {} }')
        self.write('c/C.java', 'package c; class C { void run(p.Source source) { '
                   'for(var item : source.items()) item.hit(); } }')

        def snapshot(index):
            with closing(sqlite3.connect(index.db)) as conn:
                return {p: decode_parse(data) for p, data in conn.execute('SELECT path,parsed FROM files')}

        initial = None
        for number, package in enumerate(('a', 'b', None, 'a')):
            with self.subTest(package=package):
                if package is None:
                    (self.root / 'p/Source.java').unlink()
                else:
                    self.write('p/Source.java', 'package p; import ' + package +
                               '.Item; public class Source { public java.util.List<Item> items() { return null; } }')
                status = self.index.refresh(self.root)
                if number:
                    self.assertEqual(status['refresh']['parsed_files'], 0 if package is None else 1)
                facts = snapshot(self.index)
                call, = [r for r in facts['c/C.java']['references'] if r['member'] == 'hit']
                expected = (package + '/Item.java::' + package + '.Item.hit:method()') if package else None
                self.assertEqual(call.get('target'), expected)
                fresh = RepositoryIndex(Path(self.temp.name) / ('getter-fresh-%d.sqlite' % number))
                fresh.refresh(self.root)
                self.assertEqual(facts, snapshot(fresh))
                self.assertEqual(self.index.graph(), fresh.graph())
                if number == 0:
                    initial = facts
        self.assertEqual(facts, initial)

    def test_exact_id_context_survives_long_path_and_noisy_overloads(self):
        path = 'src/main/java/org/example/resource/navigation/DefaultResourceLoader.java'
        self.write(path, 'package org.example.resource.navigation; class DefaultResourceLoader {\n'
                   + ''.join('void noise%d() {}\n' % n for n in range(200))
                   + 'String getResource(String location) { return "classpath:" + location; }\n'
                   + 'String getResource(int location) { return "number"; }\n}\n')
        self.index.refresh(self.root)
        candidates = self.index.search('getResource')['hits']
        target = next(s for s in candidates if s['id'].endswith('(String)'))
        result = self.index.search(target['id'])
        self.assertEqual([target['id']], [s['id'] for s in result['hits']])
        self.assertTrue(result['hits'][0]['retrieval']['exact_id'])
        context = self.index.context(target['id'], budget_bytes=6000)
        self.assertEqual(target['id'], context['items'][0]['id'])
        self.assertIn('return "classpath:"', context['items'][0]['source'])
        self.assertEqual(target['start_line'], context['items'][0]['start_line'])
        self.assertFalse(self.index.search(target['id'], path='other/*')['hits'])
        self.assertFalse(self.index.search(target['id'], language='python')['hits'])
        self.assertEqual(2, len([s for s in candidates if s['name']=='getResource']))

    def test_relink_reuses_identical_cache_but_updates_unchanged_callers(self):
        import sqlite3
        from contextlib import closing
        import zlib
        from columbus.index import decode_parse
        self.write('lib.py', 'def hit(): return 1\n')
        self.write('caller.py', 'from lib import hit\ndef run(): return hit()\n')
        self.write('other.py', 'def independent(): return "' + 'unchanged' * 50 + '"\n')
        self.index.refresh(self.root)
        with closing(sqlite3.connect(self.index.db)) as conn, conn:
            row = conn.execute("SELECT parsed FROM files WHERE path='other.py'").fetchone()[0]
            # A valid alternate compression makes recompression observable.
            preserved = zlib.compress(zlib.decompress(row), level=0)
            conn.execute("UPDATE files SET parsed=? WHERE path='other.py'", (preserved,))
            caller_before = conn.execute("SELECT parsed FROM files WHERE path='caller.py'").fetchone()[0]
        self.write('lib.py', 'def renamed(): return 1\n')
        self.index.refresh(self.root)
        with closing(sqlite3.connect(self.index.db)) as conn, conn:
            blobs = dict(conn.execute('SELECT path,parsed FROM files'))
        self.assertEqual(blobs['other.py'], preserved)
        self.assertNotEqual(blobs['caller.py'], caller_before)
        caller = decode_parse(blobs['caller.py'])
        self.assertTrue(all(not r['resolved'] for r in caller['references'] if r['kind'] == 'calls'))
        clean = RepositoryIndex(Path(self.temp.name) / 'clean-cache.sqlite')
        clean.refresh(self.root)
        with closing(sqlite3.connect(clean.db)) as conn:
            clean_facts = {p: decode_parse(b) for p, b in conn.execute('SELECT path,parsed FROM files')}
        self.assertEqual({p: decode_parse(b) for p, b in blobs.items()}, clean_facts)
        self.assertEqual(self.index.graph(), clean.graph())

    def test_incremental_delete_and_full_rebuild_equivalence(self):
        first = self.seed()
        self.assertEqual(first["refresh"]["parsed_files"], 2)
        second = self.index.refresh(self.root)
        self.assertEqual(second["refresh"]["parsed_files"], 0)
        self.assertFalse(second["refresh"]["global_relink"])
        self.assertEqual(first["revision"], second["revision"])
        self.write("payments.py", "def new_refund(amount):\n    return amount\n")
        updated = self.index.refresh(self.root)
        self.assertEqual(updated["refresh"]["parsed_files"], 1)
        self.assertEqual(updated["refresh"]["reused_files"], 1)
        graph = self.index.graph()
        self.assertFalse(any(e["kind"] == "calls" for e in graph["edges"]))
        clean = RepositoryIndex(Path(self.temp.name)/"clean.sqlite")
        clean.refresh(self.root)
        self.assertEqual(graph, clean.graph())
        (self.root/"payments.py").unlink()
        self.assertEqual(self.index.refresh(self.root)["refresh"]["removed_files"], 1)
        self.assertFalse(any(n["path"] == "payments.py" for n in self.index.graph()["nodes"]))

    def test_stale_source_fails_and_refresh_recovers(self):
        self.seed()
        before = self.index.symbol("refund_payment")
        self.write("payments.py", "def refund_payment(amount):\n    return amount * 2\n")
        with self.assertRaisesRegex(ValueError, "Stale source"):
            self.index.symbol(before["id"])
        self.assertEqual(self.index.status(True)["freshness"], "stale")
        self.index.refresh(self.root)
        self.assertIn("* 2", self.index.symbol(before["id"])["source"])

    def test_invalid_syntax_removes_old_symbols(self):
        self.seed()
        self.write("payments.py", "def refund_payment(:\n")
        report = self.index.refresh(self.root)
        self.assertTrue(report["diagnostics"])
        self.assertFalse(any(n["name"] == "refund_payment" and n["kind"] != "module" for n in self.index.graph()["nodes"]))

    def test_exact_context_budget_with_unicode_and_large_symbol(self):
        self.write("payments.py", "def refund_payment():\n" + "    # 결제 환불 데이터 😀\n"*300 + "    return 1\n")
        self.index.refresh(self.root)
        for budget in (2048, 4096, 12000):
            result = self.index.context("refund_payment", budget)
            self.assertLessEqual(byte_size(result), budget)
            self.assertEqual(result["used_bytes"], byte_size(result))
            self.assertTrue(result["items"])
        proc = subprocess.run([sys.executable, "-m", "columbus", "--db", str(self.index.db), "context", "refund_payment", "--budget-bytes", "2048"], capture_output=True, check=True)
        self.assertLessEqual(len(proc.stdout), 2048)

    def test_symlinks_ignored_and_new_repo_cannot_reuse_index(self):
        outside = Path(self.temp.name)/"outside.py"
        outside.write_text("def secret(): pass\n")
        (self.root/"linked.py").symlink_to(outside)
        self.write("secrets.py", "def secret(): pass\n")
        self.write("ignored.py", "def ignore_me(): pass\n")
        self.write(".columbusignore", "ignored.py\n")
        self.seed()
        paths = {s["path"] for s in self.index.graph()["nodes"]}
        self.assertEqual(paths, {"orders.py", "payments.py"})
        alternate = Path(self.temp.name)/"other"
        alternate.mkdir()
        with self.assertRaisesRegex(ValueError, "another repository"):
            self.index.refresh(alternate)

    def test_impact_direction_and_source_root(self):
        self.write("src/app/__init__.py", "")
        self.write("src/app/payments.py", "def refund(): return 1\n")
        self.write("src/app/orders.py", "from app.payments import refund\ndef cancel(): return refund()\n")
        self.index.refresh(self.root, source_root="src")
        impact = self.index.neighbors("refund", direction="in", kinds=["calls", "inherits"])
        self.assertIn("cancel", [n["name"] for n in impact["nodes"]])
        self.assertTrue(all(e["kind"] == "calls" for e in impact["edges"]))
        self.assertEqual(self.index.refresh(self.root)["source_root"], "src")

    def test_private_preview_runtime_is_excluded_without_modification(self):
        legacy = ".repoatlas/runtime/lib/private_module.py"
        self.write(legacy, "def old_runtime_only(): return 'preserve me'\n")
        original = (self.root / legacy).read_bytes()
        self.seed()
        self.assertEqual(self.index.search("old_runtime_only")["hits"], [])
        self.assertEqual((self.root / legacy).read_bytes(), original)

    def test_query_punctuation_and_no_matches(self):
        self.seed()
        for query in ('refund_payment OR " *', 'refund-payment', 'NEAR(refund)'):
            self.index.search(query)
        self.assertEqual(self.index.search("absentxyz")["hits"], [])
        self.assertEqual(self.index.context("absentxyz")["items"], [])

    def test_git_ignore_and_untracked_discovery(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.write(".gitignore", "private.py\n")
        self.write("private.py", "def hidden(): pass\n")
        self.write("public.py", "def visible(): pass\n")
        report = self.index.refresh(self.root)
        self.assertEqual(report["files"], 1)
        self.assertEqual(self.index.search("visible")["hits"][0]["name"], "visible")

    def test_qualified_suffix_matches_preserve_ambiguity_and_filters(self):
        for package, name in [("a", "Loader"), ("b", "Loader"), ("c", "OtherLoader")]:
            self.write(package + "/Loader.java", "package " + package + "; class " + name + " { void getResource() {} }")
        self.index.refresh(self.root)
        hits = self.index.search("Loader.getResource")["hits"]
        suffixes = [h for h in hits if h["retrieval"].get("qualified_suffix")]
        self.assertEqual({h["qualname"] for h in suffixes}, {"a.Loader.getResource", "b.Loader.getResource"})
        self.assertEqual(hits[:2], suffixes)
        self.assertTrue(all(not h["retrieval"]["exact_name"] for h in suffixes))
        filtered = self.index.search("Loader.getResource", path="b/*")["hits"]
        self.assertEqual(filtered[0]["qualname"], "b.Loader.getResource")
        exact = self.index.search("a.Loader.getResource")["hits"][0]
        self.assertTrue(exact["retrieval"]["exact_name"])

    def test_exact_match_survives_fts_candidate_cutoff(self):
        self.write("all.py", "def foo():\n" + "    # unrelated content\n"*500 + "    return 1\n" +
                   "\n".join(f"def foo_{i}(): return 1" for i in range(220)))
        self.index.refresh(self.root)
        self.assertEqual(self.index.search("foo")["hits"][0]["name"], "foo")

    def test_source_root_changes_revision(self):
        self.write("src/a.py", "def foo(): return 1\n")
        first = self.index.refresh(self.root)
        second = self.index.refresh(self.root, source_root="src")
        self.assertNotEqual(first["revision"], second["revision"])

    def test_oversized_exclusions_are_not_permanently_stale(self):
        self.write("large.py", "#"*1_000_001)
        self.seed()
        self.assertEqual(self.index.status(True)["freshness"], "checked_clean")
        self.assertIn("large.py", self.index.status()["inventory"]["oversized_paths"])

    def test_fsmonitor_repository_hook_is_not_executed(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        hook = self.root/"monitor.sh"
        hook.write_text("#!/bin/sh\ntouch executed-marker\nprintf 'token\\0'\n")
        hook.chmod(0o755)
        subprocess.run(["git", "-C", str(self.root), "config", "core.fsmonitor", str(hook)], check=True)
        self.seed()
        self.assertFalse((self.root/"executed-marker").exists())


if __name__ == "__main__":
    unittest.main()
