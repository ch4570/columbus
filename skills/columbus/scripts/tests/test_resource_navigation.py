"""Declared resource discovery preserves provenance and uncertain framework evidence."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from columbus.index import RepositoryIndex
from columbus.presentation import render
from columbus.resource_navigation import resources


class ResourceNavigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.index = RepositoryIndex(Path(self.temp.name) / "graph.sqlite")

    def seed(self, files):
        for path, source in files.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(textwrap.dedent(source))
        self.index.refresh(self.root)

    def test_existing_flow_has_four_declarations_without_runtime_claims(self):
        fixture = Path(__file__).resolve().parents[4] / "evals/real-repository/fixtures/Flow.kt"
        self.seed({"Flow.kt": fixture.read_text()})
        packet = resources(self.index, budget_bytes=16000)
        self.assertEqual("resources", packet["mode"])
        self.assertFalse(packet["semantic_complete"])
        self.assertEqual({"http", "kafka", "table", "cache"}, {i["resource_kind"] for i in packet["items"]})
        declarations = {i["resource_kind"]: i for i in packet["items"]}
        self.assertEqual(["/synthetic/items"], declarations["http"]["http"]["paths"])
        self.assertEqual(["synthetic-events"], declarations["kafka"]["kafka"]["topics"])
        self.assertEqual("demo", declarations["table"]["table"]["schema"])
        self.assertTrue(declarations["cache"]["cache"]["all_entries"])
        for item in packet["items"]:
            self.assertEqual("literal", item["resolution"])
            self.assertFalse(item["runtime_verified"])
            self.assertFalse(item["semantic_complete"])
            self.assertTrue(item["source_hash"])
            self.assertTrue(item["owner_id"])
            self.assertGreaterEqual(item["end_line"], item["start_line"])

    def test_http_class_method_literal_combinations_and_query_filter(self):
        self.seed({"Controller.java": '''
            import org.springframework.web.bind.annotation.RequestMapping;
            import org.springframework.web.bind.annotation.GetMapping;
            @RequestMapping(path = {"/api", "/v2"})
            class Controller {
                @GetMapping({"/items", "/all"}) void list() {}
            }
        '''})
        packet = resources(self.index, "/v2/items", kind="http", path="*.java")
        self.assertEqual(1, len(packet["items"]))
        item = packet["items"][0]
        self.assertEqual(["/api/items", "/api/all", "/v2/items", "/v2/all"], item["http"]["paths"])
        self.assertEqual(["GET"], item["http"]["methods"])
        self.assertEqual("literal", item["resolution"])
        self.assertEqual(2, len(item["evidence"]))
        self.assertFalse(resources(self.index, kind="kafka")["items"])

    def test_dynamic_and_disabled_declarations_are_not_literal_resources(self):
        self.seed({"Bindings.kt": '''
            import org.springframework.web.bind.annotation.GetMapping
            import org.springframework.web.bind.annotation.RequestMapping
            import org.springframework.kafka.annotation.KafkaListener
            import org.springframework.cache.annotation.Cacheable
            @RequestMapping("${base}")
            class Bindings {
                @GetMapping("/items") fun route() {}
                @KafkaListener(topics = ["${topic}"], groupId = "#{group}", autoStartup = "false")
                fun consume() {}
                @Cacheable(cacheNames = ["items"], key = "#id") fun cache(id: Int) {}
            }
        '''})
        items = resources(self.index, budget_bytes=14000)["items"]
        self.assertEqual(3, len(items))
        self.assertTrue(all(i["resolution"] == "dynamic" for i in items))
        kafka = next(i for i in items if i["resource_kind"] == "kafka")
        self.assertTrue(kafka["kafka"]["declared_disabled"])
        self.assertEqual("false", kafka["kafka"]["auto_startup"])
        http = next(i for i in items if i["resource_kind"] == "http")
        self.assertEqual([], http["http"]["paths"])
        self.assertIn("${base}", json.dumps(http))

    def test_custom_annotations_are_rejected_and_wildcard_alias_stay_incomplete(self):
        self.seed({
            "Custom.kt": '''
                import my.framework.GetMapping
                class Custom { @GetMapping("/wrong") fun route() {} }
            ''',
            "Local.kt": '''
                annotation class Table(val name: String)
                @Table(name = "wrong") class Local
            ''',
            "Wildcard.kt": '''
                import org.springframework.web.bind.annotation.*
                class Wildcard { @GetMapping("/uncertain") fun route() {} }
            ''',
            "Alias.kt": '''
                import org.springframework.web.bind.annotation.GetMapping as Route
                class Alias { @Route("/alias") fun route() {} }
            ''',
            "Qualified.kt": '''
                class Qualified {
                    @org.springframework.web.bind.annotation.GetMapping("/qualified") fun route() {}
                }
            ''',
        })
        items = resources(self.index, budget_bytes=16000)["items"]
        by_path = {i["path"]: i for i in items}
        self.assertEqual({"Wildcard.kt", "Alias.kt", "Qualified.kt"}, set(by_path))
        self.assertEqual("literal", by_path["Qualified.kt"]["resolution"])
        self.assertEqual("incomplete", by_path["Wildcard.kt"]["resolution"])
        self.assertEqual("incomplete", by_path["Alias.kt"]["resolution"])
        self.assertTrue(by_path["Wildcard.kt"]["limitations"])

    def test_annotation_truncation_and_legacy_fallback_are_explicit(self):
        self.seed({"Long.kt": '''
            import org.springframework.kafka.annotation.KafkaListener
            class Long {
                @KafkaListener(topics = ["events"], properties = ["''' + "x" * 340 + '''"])
                fun consume() {}
            }
        '''})
        item = resources(self.index)["items"][0]
        self.assertEqual("incomplete", item["resolution"])
        self.assertIn("truncated", " ".join(item["limitations"]))
        with closing(sqlite3.connect(self.index.db)) as conn, conn:
            for symbol_id, data in conn.execute("SELECT id,data FROM symbols").fetchall():
                symbol = json.loads(data)
                symbol.pop("annotation_details", None)
                conn.execute("UPDATE symbols SET data=? WHERE id=?", (json.dumps(symbol), symbol_id))
        legacy = resources(self.index)["items"][0]
        self.assertEqual("incomplete", legacy["resolution"])
        self.assertIn("legacy", " ".join(legacy["limitations"]))

    def test_budget_pagination_binding_and_snapshot_hash(self):
        self.seed({"Routes.java": '''
            import org.springframework.web.bind.annotation.GetMapping;
            class Routes {
        ''' + "\n".join(f'@GetMapping("/items/{n}") void route{n}() {{}}' for n in range(12)) + "\n}"})
        cursor, ids = None, []
        for _ in range(20):
            packet = resources(self.index, limit=2, cursor=cursor, budget_bytes=4500)
            self.assertEqual(len(render(packet).encode()), packet["used_bytes"])
            self.assertLessEqual(packet["used_bytes"], 4500)
            ids.extend(i["id"] for i in packet["items"])
            cursor = packet["next_cursor"]
            if cursor is None:
                break
            for changed in ({"query": "items"}, {"path": "*.java"}, {"kind": "http"}):
                with self.assertRaisesRegex(ValueError, "cursor"):
                    resources(self.index, cursor=cursor, **changed)
        self.assertEqual(12, len(ids))
        self.assertEqual(len(ids), len(set(ids)))
        first = resources(self.index, limit=1)
        before_hash = first["items"][0]["source_hash"]
        (self.root / "Routes.java").write_text("class Routes {}")
        self.assertEqual(before_hash, resources(self.index, limit=1)["items"][0]["source_hash"])
        self.index.refresh(self.root)
        with self.assertRaisesRegex(ValueError, "cursor"):
            resources(self.index, cursor=first["next_cursor"])

    def test_candidate_scan_and_per_file_cache_decode_are_bounded(self):
        self.seed({f"C{n}.java": '''
            import org.springframework.web.bind.annotation.GetMapping;
            class C { @GetMapping("/items") void route() {} }
        ''' for n in range(8)})
        from columbus.parse_cache import decode_parse_cache
        with patch("columbus.resource_navigation.CANDIDATE_LIMIT", 3), patch(
                "columbus.resource_navigation.decode_parse_cache", wraps=decode_parse_cache) as decode:
            first = resources(self.index, "missing")
        self.assertEqual([], first["items"])
        self.assertTrue(first["truncated"])
        self.assertIsNotNone(first["next_cursor"])
        self.assertEqual(3, first["scanned_candidates"])
        self.assertLessEqual(decode.call_count, 3)
        next_page = resources(self.index, "missing", cursor=first["next_cursor"])
        self.assertIsNone(next_page["next_cursor"])

    def test_invalid_inputs_and_text_budget(self):
        self.seed({"C.java": '''class C {
            @org.springframework.web.bind.annotation.GetMapping("/items") void route() {}
        }'''})
        for bad in ({"kind": "sql"}, {"limit": True}, {"limit": 0}, {"cursor": "!"}, {"query": "x" * 2001}):
            with self.assertRaises(ValueError):
                resources(self.index, **bad)
        packet = resources(self.index, output_format="text", budget_bytes=2048)
        self.assertIn("/items", render(packet, "text"))
        self.assertLessEqual(len(render(packet, "text").encode()), 2048)

    def test_nested_annotation_is_not_reported_as_a_literal_binding(self):
        self.seed({"Nested.java": '''
            import org.springframework.cache.annotation.CacheEvict;
            class Nested {
                @Unrelated(metadata = @CacheEvict("items")) void run() {}
            }
        '''})
        item = resources(self.index)["items"][0]
        self.assertEqual("incomplete", item["resolution"])
        self.assertIn("nested", " ".join(item["limitations"]))

    def test_multiple_declarations_in_one_file_decode_cache_once(self):
        self.seed({"Many.java": '''
            import org.springframework.web.bind.annotation.GetMapping;
            import java.util.*;
            class Many {
                @GetMapping("/a") void first() {}
                @GetMapping("/b") void second() {}
            }
        '''})
        from columbus.parse_cache import decode_parse_cache
        with patch("columbus.resource_navigation.decode_parse_cache", wraps=decode_parse_cache) as decode:
            packet = resources(self.index, budget_bytes=12000, budget_tokens=1800)
        self.assertEqual(1, decode.call_count)
        self.assertEqual(2, len(packet["items"]))
        self.assertTrue(all(i["resolution"] == "literal" for i in packet["items"]))
        self.assertLessEqual(packet["used_bytes"], 5400)

    def test_missing_class_mapping_metadata_does_not_invent_root_route(self):
        self.seed({"QueryController.kt": '''
            import org.springframework.web.bind.annotation.RequestMapping
            import org.springframework.web.bind.annotation.GetMapping
            import example.Tag
            @RequestMapping("/v1/api/items")
            @Tag(name = "Items")
            class QueryController {
                @GetMapping
                fun list() {}
            }
        '''})
        # Kotlin may detach leading annotations into a separate AST expression
        # without a syntax diagnostic. Freeze that observed old-cache shape.
        with closing(sqlite3.connect(self.index.db)) as conn, conn:
            row = conn.execute("SELECT id,data FROM symbols WHERE name='QueryController'").fetchone()
            owner = json.loads(row[1])
            owner["annotations"] = ['@Tag(name = "Items")']
            owner["annotation_details"] = [detail for detail in owner["annotation_details"] if detail["name"] == "Tag"]
            owner["partial"] = False
            conn.execute("UPDATE symbols SET data=? WHERE id=?", (json.dumps(owner), row[0]))
        item = resources(self.index, kind="http")["items"][0]
        self.assertEqual("incomplete", item["resolution"])
        self.assertEqual([], item["http"]["paths"])
        self.assertNotEqual("GET /", item["signature"])
        self.assertIn("explicit HTTP path", " ".join(item["limitations"]))

    def test_missing_enclosing_type_metadata_keeps_explicit_method_path_unresolved(self):
        self.seed({"Controller.java": '''
            import org.springframework.web.bind.annotation.GetMapping;
            class Controller { @GetMapping("/items") void list() {} }
        '''})
        with closing(sqlite3.connect(self.index.db)) as conn, conn:
            row = conn.execute("SELECT id,data FROM symbols WHERE name='list'").fetchone()
            method = json.loads(row[1])
            method["parent_id"] = "missing-owner"
            conn.execute("UPDATE symbols SET data=? WHERE id=?", (json.dumps(method), row[0]))
        item = resources(self.index)["items"][0]
        self.assertEqual("incomplete", item["resolution"])
        self.assertEqual([], item["http"]["paths"])
        self.assertEqual(["/items"], item["http"]["declared_paths"])

    def test_legacy_or_ambiguous_class_prefix_keeps_method_suffix_unresolved(self):
        self.seed({"Controller.java": '''
            import org.springframework.web.bind.annotation.RequestMapping;
            import org.springframework.web.bind.annotation.GetMapping;
            @RequestMapping("/api")
            class Controller { @GetMapping("/items") void list() {} }
        '''})
        with closing(sqlite3.connect(self.index.db)) as conn, conn:
            row = conn.execute("SELECT id,data FROM symbols WHERE name='Controller'").fetchone()
            original = json.loads(row[1])
            for metadata in ({}, {"annotation_metadata_version": 2, "annotation_metadata_complete": False},
                             {"annotation_metadata_version": 1, "annotation_metadata_complete": True}):
                with self.subTest(metadata=metadata):
                    owner = dict(original, annotations=[], annotation_details=[])
                    owner.pop("annotation_metadata_version", None)
                    owner.pop("annotation_metadata_complete", None)
                    owner.update(metadata)
                    conn.execute("UPDATE symbols SET data=? WHERE id=?", (json.dumps(owner), row[0]))
                    conn.commit()
                    item = resources(self.index)["items"][0]
                    self.assertEqual("incomplete", item["resolution"])
                    self.assertEqual([], item["http"]["paths"])
                    self.assertEqual(["/items"], item["http"]["declared_paths"])
                    self.assertIn("metadata", " ".join(item["limitations"]))

    def test_explicit_root_path_remains_literal(self):
        self.seed({"Controller.java": '''
            import org.springframework.web.bind.annotation.GetMapping;
            class Controller { @GetMapping("/") void root() {} }
        '''})
        item = resources(self.index)["items"][0]
        self.assertEqual("literal", item["resolution"])
        self.assertEqual(["/"], item["http"]["paths"])

    def test_detached_kotlin_class_annotations_preserve_the_http_prefix(self):
        self.seed({"Controller.kt": '''
            import org.springframework.web.bind.annotation.RestController
            import org.springframework.web.bind.annotation.RequestMapping
            import org.springframework.web.bind.annotation.GetMapping
            import example.Tag
            import example.ApiResponses
            @RestController
            @RequestMapping("/api")
            @Tag(name="catalog")
            class Controller(
            ) {
             /**
             */
             @ApiResponses(
             value = [
             ApiResponse(
             ),
             ],
             )
             @GetMapping
             fun list() {
             }
            }
            /** tail */
        '''})
        item = resources(self.index, kind="http")["items"][0]
        self.assertEqual(["/api"], item["http"]["paths"])
        self.assertEqual("literal", item["resolution"])
        self.assertTrue(any(evidence["text"] == '@RequestMapping("/api")' for evidence in item["evidence"]))


if __name__ == "__main__":
    unittest.main()
