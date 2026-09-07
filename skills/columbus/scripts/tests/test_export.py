"""Export correctness and hostile-repository-string regression tests."""

import json
import re
import unittest
from xml.etree import ElementTree as ET

from columbus.export import HTML_NODE_LIMIT, render_graph


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.hostile = '</script><img src=x onerror="alert(1)"> & " ] --> injected'
        self.graph = {
            "revision": "abc123",
            "nodes": [
                {"id": self.hostile, "name": self.hostile, "kind": "function", "path": "src/a&b.py", "start_line": 3, "end_line": 9},
                {"id": "target", "name": "target", "kind": "function", "path": "src/target.py", "start_line": 7},
            ],
            "edges": [{"source": self.hostile, "target": "target", "kind": "calls", "confidence": "heuristic", "evidence": self.hostile, "path": "src/a&b.py", "line": 6}],
        }

    def test_html_cannot_close_data_script_or_interpolate_repository_html(self):
        html = render_graph(self.graph, "html")
        match = re.search(r'<script id="columbus-data" type="application/json">(.*?)</script>', html, re.S)
        self.assertIsNotNone(match)
        data = json.loads(match.group(1))
        self.assertEqual(data["nodes"][0]["id"], self.hostile)
        self.assertEqual(data["edges"][0]["evidence"], self.hostile)
        self.assertNotIn(self.hostile, html)
        self.assertEqual(html.count("</script>"), 2)
        self.assertNotIn("innerHTML", html)
        self.assertNotRegex(html, r"<(?:script|link)[^>]+(?:src|href)=")
        self.assertIn("Source files are not embedded", html)
        self.assertIn('<h1><span>Columbus</span></h1>', html)

    def test_graphml_is_parseable_preserves_keys_evidence_and_endpoint_ids(self):
        root = ET.fromstring(render_graph(self.graph, "graphml"))
        ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
        keys = {key.attrib["id"]: (key.attrib["for"], key.attrib["attr.name"]) for key in root.findall("g:key", ns)}
        nodes = root.findall("g:graph/g:node", ns)
        edges = root.findall("g:graph/g:edge", ns)
        self.assertEqual(len(nodes), 2)
        values = {keys[data.attrib["key"]][1]: data.text for data in nodes[0].findall("g:data", ns)}
        self.assertEqual(values["id"], self.hostile)
        self.assertEqual(values["path"], "src/a&b.py")
        self.assertEqual(edges[0].attrib["source"], nodes[0].attrib["id"])
        self.assertEqual(edges[0].attrib["target"], nodes[1].attrib["id"])
        evidence = next(data.text for data in edges[0].findall("g:data", ns) if keys[data.attrib["key"]] == ("edge", "evidence"))
        self.assertEqual(evidence, self.hostile)

    def test_invalid_xml_controls_are_replaced(self):
        self.graph["nodes"][0]["name"] = "a\x00b\x08c"
        xml = render_graph(self.graph, "graphml")
        ET.fromstring(xml)
        self.assertIn("a\ufffdb\ufffdc", xml)

    def test_mermaid_uses_generated_ids_and_escaped_labels(self):
        text = render_graph(self.graph, "mermaid")
        self.assertNotIn(self.hostile, text)
        self.assertNotIn("</script>", text)
        self.assertIn("#34;", text)
        self.assertIn('n0 -.->|"calls · heuristic"| n1', text)

    def test_html_caps_data_and_preserves_total_counts_without_source_bodies(self):
        graph = {"nodes": [{"id": str(index), "name": "name", "source": "do_not_export_source()"} for index in range(HTML_NODE_LIMIT + 1)], "edges": [{"source": "0", "target": str(HTML_NODE_LIMIT), "kind": "calls"}]}
        html = render_graph(graph, "html")
        data = json.loads(re.search(r'type="application/json">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(len(data["nodes"]), HTML_NODE_LIMIT)
        self.assertEqual(data["total_nodes"], HTML_NODE_LIMIT + 1)
        self.assertEqual(data["total_edges"], 1)
        self.assertEqual(data["edges"], [])
        self.assertNotIn("do_not_export_source()", html)

    def test_dangling_edges_are_omitted_and_counted(self):
        self.graph["edges"].append({"source": "target", "target": "missing"})
        root = ET.fromstring(render_graph(self.graph, "graphml"))
        ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
        self.assertEqual(len(root.findall("g:graph/g:edge", ns)), 1)
        metadata = json.loads(root.find("g:graph/g:data", ns).text)
        self.assertEqual(metadata["omitted_dangling_edges"], 1)

    def test_html_preserves_upstream_truncation_revision_freshness_and_center(self):
        self.graph.update({"truncated": True, "freshness": "stale", "indexed_at": "2026-09-07T10:00:00Z", "center": "target"})
        html = render_graph(self.graph, "html")
        data = json.loads(re.search(r'type="application/json">(.*?)</script>', html, re.S).group(1))
        for key in ("truncated", "revision", "freshness", "indexed_at", "center"):
            self.assertEqual(data[key], self.graph[key])
        self.assertIn("The input graph was truncated before export", html)
        self.assertIn("The index reports stale source files", html)
        self.assertIn('id="snapshot"', html)

    def test_empty_graph_and_format_validation(self):
        for format in ["html", "graphml", "mermaid"]:
            self.assertTrue(render_graph({"nodes": [], "edges": []}, format))
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            render_graph({}, "svg")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            render_graph({"nodes": [{"id": "a"}, {"id": "a"}]}, "html")


if __name__ == "__main__":
    unittest.main()
