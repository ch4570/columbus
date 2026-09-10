import json
import unittest
from unittest.mock import patch
import zlib

from columbus import parse_cache


class ParseCacheTests(unittest.TestCase):
    def setUp(self):
        self.facts = {"path": "결제.py", "symbols": [{"name": "refund", "doc": "환불 😀" * 200}],
                      "references": [{"target": None, "resolved": False}], "diagnostics": []}

    def test_compressed_round_trip_is_lossless_and_smaller(self):
        encoded = parse_cache.encode_parse_cache(self.facts)
        self.assertIsInstance(encoded, bytes)
        self.assertTrue(encoded.startswith(parse_cache.MAGIC))
        self.assertEqual(parse_cache.decode_parse_cache(encoded), self.facts)
        self.assertLess(len(encoded), len(json.dumps(self.facts).encode("utf-8")))

    def test_legacy_json_text_remains_readable(self):
        self.assertEqual(parse_cache.decode_parse_cache(json.dumps(self.facts)), self.facts)

    def test_oversized_encoder_retains_legacy_json_without_loss(self):
        with patch.object(parse_cache, "MAX_DECOMPRESSED_BYTES", 32):
            encoded = parse_cache.encode_parse_cache(self.facts)
            self.assertIsInstance(encoded, str)
            self.assertEqual(parse_cache.decode_parse_cache(encoded), self.facts)

    def test_malformed_header_stream_and_trailing_payload_fail(self):
        valid = parse_cache.encode_parse_cache(self.facts)
        for value in (b"", valid[:3], b"unknown-v2" + valid, valid[:-1],
                      parse_cache.MAGIC + b"invalid zlib", valid + b"trailing",
                      valid + zlib.compress(b"{}")):
            with self.subTest(value=value[:30]):
                with self.assertRaisesRegex(ValueError, "parse cache"):
                    parse_cache.decode_parse_cache(value)

    def test_decompression_expansion_is_bounded(self):
        encoded = parse_cache.MAGIC + zlib.compress(b" " * 1_000_000)
        with patch.object(parse_cache, "MAX_DECOMPRESSED_BYTES", 1024):
            with self.assertRaisesRegex(ValueError, "parse cache.*limit"):
                parse_cache.decode_parse_cache(encoded)

    def test_invalid_json_or_non_object_facts_fail(self):
        for value in ("not json", "null", "[]", parse_cache.MAGIC + zlib.compress(b"\xff"),
                      parse_cache.MAGIC + zlib.compress(b"[]")):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "parse cache"):
                    parse_cache.decode_parse_cache(value)


if __name__ == "__main__":
    unittest.main()
