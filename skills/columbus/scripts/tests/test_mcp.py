"""Real subprocess/stdio contract test for the optional official MCP SDK."""

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


@unittest.skipUnless(importlib.util.find_spec("mcp"), "optional MCP SDK not installed")
class MCPIntegrationTests(unittest.TestCase):
    def test_stdio_initialize_discover_and_query(self):
        from columbus.index import RepositoryIndex

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            (root / "billing.py").write_text(
                "def calculate_total(price, quantity):\n"
                "    return price * quantity\n\n"
                "def checkout():\n"
                "    return calculate_total(12, 3)\n",
                encoding="utf-8",
            )
            database = Path(temporary) / "index.sqlite"
            RepositoryIndex(str(database)).refresh(str(root))
            asyncio.run(self._exercise_stdio(database))

    async def _exercise_stdio(self, database):
        from mcp.client import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        package_root = str(Path(__file__).resolve().parents[1])
        python_path = os.pathsep.join(
            [package_root] + [entry for entry in sys.path if entry]
        )
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "columbus", "--db", str(database), "serve"],
            env={"PYTHONPATH": python_path},
            cwd=package_root,
        )
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=20) as session:
                initialized = await session.initialize()
                self.assertEqual(initialized.server_info.name, "Columbus")
                self.assertIn("untrusted", initialized.instructions)
                listing = await session.list_tools()
                tools = {tool.name: tool for tool in listing.tools}
                self.assertEqual(
                    set(tools),
                    {
                        "index_status",
                        "repository_map",
                        "find_symbols",
                        "read_symbol",
                        "graph_neighbors",
                        "build_context",
                        "impact_analysis",
                    },
                )
                for tool in tools.values():
                    annotations = tool.annotations.model_dump(by_alias=True)
                    self.assertTrue(annotations["readOnlyHint"])
                    self.assertFalse(annotations["destructiveHint"])

                status = await session.call_tool("index_status", {})
                self.assertFalse(status.is_error)
                self.assertIsInstance(status.structured_content, dict)

                outline = await session.call_tool("repository_map", {"budget_tokens": 700})
                self.assertFalse(outline.is_error)
                self.assertLessEqual(outline.structured_content["estimated_tokens"], 700)
                self.assertTrue(outline.structured_content["items"])
                signatures = await session.call_tool("build_context", {
                    "query": "calculate_total", "mode": "signatures", "budget_tokens": 700})
                self.assertFalse(signatures.is_error)
                self.assertTrue(all("source" not in i for i in signatures.structured_content["items"]))

                found = await session.call_tool(
                    "find_symbols", {"query": "calculate_total", "limit": 5}
                )
                self.assertFalse(found.is_error)
                hits = found.structured_content["hits"]
                self.assertGreater(len(hits), 0)
                symbol_id = hits[0]["id"]

                page = await session.call_tool('find_symbols', {'query': 'calculate_total', 'limit': 1})
                cursor = page.structured_content['next_cursor']
                self.assertIsNotNone(cursor)
                next_page = await session.call_tool('find_symbols', {
                    'query': 'calculate_total', 'limit': 1, 'cursor': cursor})
                self.assertFalse(next_page.is_error)
                self.assertNotEqual(page.structured_content['hits'][0]['id'],
                                    next_page.structured_content['hits'][0]['id'])
                wrong_scope = await session.call_tool('find_symbols', {'query': 'checkout', 'cursor': cursor})
                self.assertTrue(wrong_scope.is_error)

                source = await session.call_tool(
                    "read_symbol", {"symbol_id": symbol_id, "max_lines": 20}
                )
                self.assertFalse(source.is_error)
                self.assertIn("return price * quantity", json.dumps(source.structured_content))

                neighbors = await session.call_tool(
                    "graph_neighbors", {"symbol_id": symbol_id, "hops": 1}
                )
                self.assertFalse(neighbors.is_error)
                impact = await session.call_tool(
                    "impact_analysis", {"symbol_id": symbol_id, "hops": 2}
                )
                self.assertFalse(impact.is_error)
                self.assertIn("checkout", json.dumps(impact.structured_content))

                context = await session.call_tool(
                    "build_context",
                    {"query": "calculate_total", "budget_bytes": 4096},
                )
                self.assertFalse(context.is_error)
                packet = json.dumps(
                    context.structured_content, ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
                self.assertLessEqual(len(packet), 4096)

                invalid = await session.call_tool(
                    "build_context", {"query": "calculate_total", "budget_bytes": 1}
                )
                self.assertTrue(invalid.is_error)
                self.assertIn("budget_bytes", invalid.content[0].text)


if __name__ == "__main__":
    unittest.main()
