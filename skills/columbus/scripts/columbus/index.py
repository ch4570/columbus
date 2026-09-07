"""Transactional SQLite graph, lexical retrieval, and bounded source context."""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import fnmatch
from pathlib import Path
import re
import sqlite3
import time
import zlib

from .discovery import digest, discover, module_name
from .languages import ANALYZER_VERSION, analyzer_fingerprint, decode_source, parse_source, resolve_files
from .sync_state import SnapshotChanged, file_stat, git_state, read_stable

SCHEMA_VERSION = "3"
READABLE_SCHEMAS = {"2", SCHEMA_VERSION}
SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, hash TEXT NOT NULL,
    size INTEGER NOT NULL, parsed BLOB NOT NULL, stat TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS configs(path TEXT PRIMARY KEY, hash TEXT NOT NULL, stat TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS symbols(id TEXT PRIMARY KEY, path TEXT NOT NULL,
    name TEXT NOT NULL, qualname TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS symbol_path ON symbols(path);
CREATE INDEX IF NOT EXISTS symbol_name ON symbols(name);
CREATE TABLE IF NOT EXISTS edges(source TEXT NOT NULL REFERENCES symbols(id),
    target TEXT NOT NULL REFERENCES symbols(id), kind TEXT NOT NULL,
    confidence TEXT NOT NULL, evidence TEXT NOT NULL, path TEXT NOT NULL, line INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS edge_source ON edges(source,kind);
CREATE INDEX IF NOT EXISTS edge_target ON edges(target,kind);
CREATE VIRTUAL TABLE IF NOT EXISTS symbol_fts USING fts5(id UNINDEXED, name, path, body);
"""


def compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def encode_parse(value: dict) -> bytes:
    """Lossless parse cache; public graph/search records remain ordinary JSON."""
    return zlib.compress(compact(value).encode("utf-8"))


def decode_parse(value: str | bytes) -> dict:
    # Schema 2 snapshots remain readable until an atomic refresh upgrades them.
    return json.loads(zlib.decompress(value) if isinstance(value, bytes) else value)


def byte_size(value) -> int:
    return len(compact(value).encode("utf-8"))


def terms(text: str) -> list[str]:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return re.findall(r"[^\W_]+", text.lower(), re.UNICODE)


class RepositoryIndex:
    def __init__(self, db: str | Path):
        self.db = Path(db).expanduser().resolve()

    @contextmanager
    def _read(self):
        if not self.db.is_file():
            raise ValueError("Index is missing. Run: columbus --db PATH index REPOSITORY")
        conn = sqlite3.connect(self.db.as_uri() + "?mode=ro", uri=True, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN")
            if self._meta(conn).get("schema_version") not in READABLE_SCHEMAS:
                raise ValueError("Unsupported index schema; choose a new --db path and rebuild (schema 2 or 3 required)")
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _meta(conn) -> dict:
        return {r[0]: json.loads(r[1]) for r in conn.execute("SELECT key,value FROM metadata")}

    def refresh(self, root: str | Path, source_root: str | None = None, fast: bool = False,
                require_complete: bool = False) -> dict:
        """Commit one working-tree snapshot atomically.

        Fast mode still enumerates and stats all eligible files. It hashes only
        metadata changes, except Git identity changes force full hashing. Full
        mode hashes all files. Changed content is reparsed; a graph change
        conservatively relinks all cached parse facts. No Git hooks/builds run.
        """
        started = time.perf_counter()
        root = Path(root).expanduser().resolve()
        if not root.is_dir():
            raise ValueError("Repository must be an existing local directory")
        self.db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            # Check existing schemas before executing CREATE TABLE statements;
            # an old database must never be destructively migrated implicitly.
            has_metadata = conn.execute("SELECT 1 FROM sqlite_master WHERE name='metadata'").fetchone()
            if has_metadata:
                current_schema = self._meta(conn).get("schema_version")
                if current_schema is not None and current_schema not in READABLE_SCHEMAS:
                    raise ValueError("Unsupported index schema; choose a new --db path and rebuild (schema 2 or 3 required)")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)
            conn.execute("BEGIN IMMEDIATE")
            old_meta = self._meta(conn)
            if old_meta.get("root", str(root)) != str(root):
                raise ValueError("This index belongs to another repository or worktree. Choose a different --db")
            source_root = source_root if source_root is not None else old_meta.get("source_root", ".")
            source_root = Path(source_root).as_posix()
            state_before = git_state(root)
            paths, inventory = discover(root, source_root)
            config_paths = inventory["config_paths"]
            language_config = inventory.get("language_config", {})
            detected_languages = inventory.get("detected_languages", {})
            actual_analyzer = analyzer_fingerprint(paths, language_config, detected_languages)
            old = {r["path"]: dict(r) for r in conn.execute("SELECT path,hash,size,stat FROM files")}
            old_configs = {r["path"]: dict(r) for r in conn.execute("SELECT * FROM configs")}
            previous_state = old_meta.get("git_state")
            git_changed = previous_state != state_before
            head_changed = previous_state is not None and previous_state.get("head") != state_before["head"]
            branch_changed = previous_state is not None and previous_state.get("branch") != state_before["branch"]
            force_hash = not fast or git_changed
            source_stats = {rel: file_stat(root, rel) for rel in paths}
            config_stats = {rel: file_stat(root, rel) for rel in config_paths}
            config_records, read_cache = [], {}
            config_hashed = config_bytes = 0
            for rel in config_paths:
                previous = old_configs.get(rel)
                if previous and not force_hash and json.loads(previous["stat"]) == config_stats[rel]:
                    content_hash = previous["hash"]
                else:
                    data, stable_stat = read_stable(root, rel, config_stats[rel], max_bytes=10_000_000)
                    content_hash = digest(data)
                    config_hashed += 1
                    config_bytes += len(data)
                    # Gradle Kotlin files can be configuration and source.
                    if rel in source_stats:
                        read_cache[rel] = (data, stable_stat, content_hash)
                config_records.append({"path": rel, "hash": content_hash, "stat": config_stats[rel]})
            config_fingerprint = digest(compact([(r["path"], r["hash"]) for r in config_records]).encode())[:20]
            config_changed = old_meta.get("config_fingerprint") != config_fingerprint
            rebuild = (old_meta.get("schema_version") != SCHEMA_VERSION
                       or old_meta.get("analyzer_fingerprint") != actual_analyzer
                       or source_root != old_meta.get("source_root", ".") or config_changed)
            records, sources = [], {}
            diagnostics = [{"path": p, "message": "excluded: file exceeds 1 MB"} for p in inventory["oversized_paths"]]
            changed = reused = bytes_read = hashed_files = metadata_reused = 0
            for rel in paths:
                previous = old.get(rel)
                current_stat = source_stats[rel]
                if previous and not rebuild and not force_hash and json.loads(previous["stat"]) == current_stat:
                    content_hash = previous["hash"]
                    parsed = None
                    reused += 1
                    metadata_reused += 1
                    size = previous["size"]
                else:
                    if rel in read_cache:
                        data, stable_stat, content_hash = read_cache[rel]
                        if stable_stat != current_stat:
                            raise SnapshotChanged(f"File changed during sync: {rel}; retry sync")
                    else:
                        data, stable_stat = read_stable(root, rel, current_stat)
                        content_hash = digest(data)
                    hashed_files += 1
                    bytes_read += len(data)
                    size = len(data)
                    if previous and previous["hash"] == content_hash and not rebuild:
                        parsed = None
                        reused += 1
                    else:
                        source = decode_source(rel, data, config=language_config, language=detected_languages.get(rel))
                        parsed = parse_source(rel, source, module_name(rel, source_root),
                                              config=language_config, language=detected_languages.get(rel))
                        sources[rel] = source
                        changed += 1
                records.append({"path": rel, "hash": content_hash, "size": size,
                                "parsed": parsed, "stat": current_stat})
            current_paths = {r["path"] for r in records}
            removed = sorted(set(old) - current_paths)
            added = sorted(current_paths - set(old))
            has_changes = bool(changed or removed or rebuild)
            cached_parses_loaded = 0
            if has_changes:
                for record in records:
                    if record["parsed"] is None:
                        record["parsed"] = decode_parse(conn.execute(
                            "SELECT parsed FROM files WHERE path=?", (record["path"],)).fetchone()[0])
                        cached_parses_loaded += 1
                    diagnostics.extend({"path": record["path"], "message": str(message)}
                                       for message in record["parsed"].get("diagnostics", []))
            else:
                # The analyzer, content and file set are identical to the committed snapshot.
                diagnostics.extend(item for item in old_meta.get("diagnostics", [])
                                   if item["path"] in current_paths)
            if require_complete and diagnostics:
                raise ValueError(f'Incomplete parse: {len(diagnostics)} diagnostics; previous index preserved')
            if has_changes:
                edges = resolve_files([r["parsed"] for r in records])
                conn.execute("DELETE FROM edges")
                conn.execute("DELETE FROM symbols")
                for rel in set(sources) | set(removed):
                    conn.execute("DELETE FROM symbol_fts WHERE path=?", (rel,))
                if rebuild:
                    conn.execute("DELETE FROM symbol_fts")
                for record in records:
                    parsed = record["parsed"]
                    source_lines = sources.get(record["path"], "").splitlines()
                    for symbol in parsed["symbols"]:
                        symbol.setdefault("language", parsed.get("language", "python"))
                        conn.execute("INSERT INTO symbols VALUES(?,?,?,?,?,?)", (
                            symbol["id"], symbol["path"], symbol["name"], symbol["qualname"], symbol["kind"], compact(symbol)))
                        if record["path"] in sources:
                            body = "\n".join(source_lines[symbol["start_line"]-1:symbol["end_line"]])
                            if symbol["kind"] != "module":
                                body = body[:12000]
                            searchable_name = " ".join(terms(symbol["qualname"]))
                            conn.execute("INSERT INTO symbol_fts VALUES(?,?,?,?)", (
                                symbol["id"], searchable_name, record["path"],
                                " ".join([symbol.get("signature", ""), symbol.get("doc", "") or "", body])))
                for edge in edges:
                    evidence = edge.get("evidence", "")
                    if not isinstance(evidence, str):
                        evidence = compact(evidence)
                    conn.execute("INSERT INTO edges VALUES(?,?,?,?,?,?,?)", (
                        edge["source"], edge["target"], edge["kind"], edge["confidence"],
                        evidence, edge.get("path", ""), edge.get("line", 0)))
            # Stat updates are necessary even if a touched file has identical bytes.
            # Internal stat maps stay in tables, never in status output.
            if has_changes:
                conn.execute("DELETE FROM files")
                conn.executemany("INSERT INTO files VALUES(?,?,?,?,?)", [
                    (r["path"], r["hash"], r["size"], encode_parse(r["parsed"]), compact(r["stat"])) for r in records])
            else:
                conn.executemany("UPDATE files SET stat=? WHERE path=?", [
                    (compact(r["stat"]), r["path"]) for r in records
                    if old[r["path"]]["stat"] != compact(r["stat"])])
            if config_changed:
                conn.execute("DELETE FROM configs")
                conn.executemany("INSERT INTO configs VALUES(?,?,?)", [
                    (r["path"], r["hash"], compact(r["stat"])) for r in config_records])
            else:
                conn.executemany("UPDATE configs SET stat=? WHERE path=?", [
                    (compact(r["stat"]), r["path"]) for r in config_records
                    if old_configs[r["path"]]["stat"] != compact(r["stat"])])
            paths_after, inventory_after = discover(root, source_root)
            if paths_after != paths or inventory_after["config_paths"] != config_paths:
                raise SnapshotChanged("Repository files changed during sync; retry sync")
            for rel, signature in {**config_stats, **source_stats}.items():
                if file_stat(root, rel) != signature:
                    raise SnapshotChanged(f"File changed during sync: {rel}; retry sync")
            if git_state(root) != state_before:
                raise SnapshotChanged("Git HEAD/branch/worktree changed during sync; retry sync")
            revision = digest(compact([SCHEMA_VERSION, actual_analyzer, source_root, state_before,
                                      config_fingerprint, [(r["path"], r["hash"]) for r in records]]).encode())[:20]
            references = [ref for record in records for ref in record["parsed"].get("references", [])] if has_changes else []
            reference_counts = ({"references": len(references),
                                 "resolved_references": sum(bool(r.get("resolved")) for r in references),
                                 "unresolved_references": sum(not r.get("resolved") for r in references)}
                                if has_changes else {key: old_meta[key] for key in
                                    ("references", "resolved_references", "unresolved_references")})
            check_mode = "content_hash_verified" if force_hash or rebuild else "metadata_checked"
            report = {"root": str(root), "source_root": source_root, "schema_version": SCHEMA_VERSION,
                      "analyzer_version": ANALYZER_VERSION, "analyzer_fingerprint": actual_analyzer,
                      "revision": revision, "git_head_at_index": state_before["head"], "git_state": state_before,
                      "config_fingerprint": config_fingerprint, "config_files": len(config_records),
                      "indexed_at": datetime.now(timezone.utc).isoformat(), "inventory": inventory,
                      "diagnostics": diagnostics, **reference_counts,
                      "indexed_bytes": sum(r["size"] for r in records),
                      "last_sync_check": check_mode,
                      "refresh": {"mode": "fast" if fast else "full", "check": check_mode,
                      "parsed_files": changed, "cached_parses_loaded": cached_parses_loaded, "reused_files": reused, "metadata_reused_files": metadata_reused,
                      "added_files": len(added), "removed_files": len(removed),
                      "hashed_files": hashed_files, "hashed_bytes": bytes_read,
                      "config_hashed_files": config_hashed, "config_hashed_bytes": config_bytes,
                      "head_changed": head_changed, "branch_changed": branch_changed,
                      "git_state_changed": git_changed, "config_changed": config_changed,
                      "global_relink": has_changes, "elapsed_seconds": round(time.perf_counter()-started, 4)}}
            for key, value in report.items():
                conn.execute("INSERT OR REPLACE INTO metadata VALUES(?,?)", (key, compact(value)))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        result = self.status()
        result["freshness"] = check_mode
        return result

    def status(self, check_files: bool = False) -> dict:
        with self._read() as conn:
            meta = self._meta(conn)
            for table in ("files", "symbols", "edges"):
                meta[table] = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            meta["freshness"] = "index_snapshot; working tree not checked"
            if check_files:
                root = Path(meta["root"])
                state_before = git_state(root)
                paths, inventory = discover(root, meta["source_root"])
                indexed = {r["path"]: r["hash"] for r in conn.execute("SELECT path,hash FROM files")}
                configs = {r["path"]: r["hash"] for r in conn.execute("SELECT path,hash FROM configs")}
                stale = set(paths) ^ set(indexed)
                config_stale = set(inventory["config_paths"]) ^ set(configs)
                checked_stats = {}
                for rel, content_hash in indexed.items():
                    if rel not in paths:
                        continue
                    try:
                        data, signature = read_stable(root, rel)
                        checked_stats[rel] = signature
                        if digest(data) != content_hash:
                            stale.add(rel)
                    except (OSError, ValueError):
                        stale.add(rel)
                for rel, content_hash in configs.items():
                    if rel not in inventory["config_paths"]:
                        continue
                    try:
                        data, signature = read_stable(root, rel, max_bytes=10_000_000)
                        checked_stats[rel] = signature
                        if digest(data) != content_hash:
                            config_stale.add(rel)
                    except (OSError, ValueError):
                        config_stale.add(rel)
                reasons = []
                if state_before != meta.get("git_state"):
                    reasons.append("git_state_changed")
                if config_stale:
                    reasons.append("configuration_changed")
                if analyzer_fingerprint(paths, inventory.get("language_config"), inventory.get("detected_languages")) != meta.get("analyzer_fingerprint"):
                    reasons.append("analyzer_or_languages_changed")
                paths_after, inventory_after = discover(root, meta["source_root"])
                if paths_after != paths or inventory_after["config_paths"] != inventory["config_paths"]:
                    reasons.append("files_changed_during_check")
                for rel, signature in checked_stats.items():
                    try:
                        if file_stat(root, rel) != signature:
                            stale.add(rel)
                    except (OSError, ValueError):
                        stale.add(rel)
                if git_state(root) != state_before:
                    reasons.append("git_changed_during_check")
                meta["freshness"] = "stale" if stale or config_stale or reasons else "checked_clean"
                meta["check"] = "content_hash_verified"
                meta["stale_paths"] = sorted(stale)
                meta["stale_config_paths"] = sorted(config_stale)
                meta["stale_reasons"] = reasons
            return meta

    @staticmethod
    def _find(conn, symbol_id: str) -> dict:
        row = conn.execute("SELECT data FROM symbols WHERE id=?", (symbol_id,)).fetchone()
        if row:
            return json.loads(row[0])
        rows = conn.execute("SELECT data FROM symbols WHERE qualname=? OR name=? LIMIT 21", (symbol_id, symbol_id)).fetchall()
        if len(rows) == 1:
            return json.loads(rows[0][0])
        if rows:
            raise ValueError("Ambiguous symbol; use an exact id: " + ", ".join(json.loads(r[0])["id"] for r in rows))
        raise ValueError("Unknown symbol; use search to find an exact symbol id")

    @staticmethod
    def _matches(symbol: dict, path: str | None = None, language: str | None = None) -> bool:
        return (not path or fnmatch.fnmatchcase(symbol['path'], path)) and (not language or symbol.get('language') == language)

    @staticmethod
    def _filter_sql(path: str | None, language: str | None) -> tuple[str, list]:
        if path is not None and (len(path) > 1024 or not path):
            raise ValueError('path must be a nonempty glob of at most 1024 characters')
        if language is not None and (len(language) > 64 or not language):
            raise ValueError('language must contain 1–64 characters')
        clauses, values = ['1=1'], []
        if path:
            clauses.append('s.path GLOB ?')
            values.append(path)
        if language:
            clauses.append("json_extract(s.data, '$.language')=?")
            values.append(language)
        return ' AND '.join(clauses), values

    def search(self, query: str, limit: int = 10, *, path: str | None = None,
               language: str | None = None) -> dict:
        if not 1 <= len(query) <= 512 or not 1 <= limit <= 50:
            raise ValueError("query must have 1–512 characters; limit must be 1–50")
        words = terms(query)[:12]
        if not words:
            raise ValueError("Query must contain a letter or number")
        expression = " OR ".join('"' + word.replace('"', '""') + '"' for word in words)
        where, values = self._filter_sql(path, language)
        with self._read() as conn:
            # IDs copied from search must not be reinterpreted as path keywords.
            # Keep filters authoritative, even for an existing exact ID.
            identified = conn.execute("SELECT s.data FROM symbols s WHERE s.id=? AND " + where,
                                      [query, *values]).fetchone()
            if identified:
                symbol = json.loads(identified["data"])
                symbol["doc"] = symbol.get("doc", "")[:400]
                symbol["signature"] = symbol.get("signature", "")[:800]
                symbol["retrieval"] = {"bm25": 0, "exact_name": False, "exact_id": True}
                meta = self._meta(conn)
                return {"query": query, "revision": meta["revision"], "freshness": "index_snapshot",
                        "hits": [symbol], "candidate_limit": 150, "truncated": False}
            rows = conn.execute("""SELECT s.data, bm25(symbol_fts,0,8,3,1) AS rank
                FROM symbol_fts JOIN symbols s ON s.id=symbol_fts.id
                WHERE symbol_fts MATCH ? AND """ + where + " ORDER BY rank LIMIT 150", [expression, *values]).fetchall()
            exact_rows = conn.execute("""SELECT s.data, 0 AS rank FROM symbols s
                WHERE (name=? COLLATE NOCASE OR qualname=? COLLATE NOCASE)
                AND """ + where + " ORDER BY id LIMIT 51", [query, query, *values]).fetchall()
            hits = []
            seen = set()
            for row in [*exact_rows, *rows]:
                symbol = json.loads(row["data"])
                if symbol["id"] in seen:
                    continue
                seen.add(symbol["id"])
                symbol["doc"] = symbol.get("doc", "")[:400]
                symbol["signature"] = symbol.get("signature", "")[:800]
                exact = symbol["name"].lower() == query.lower() or symbol["qualname"].lower() == query.lower()
                symbol["retrieval"] = {"bm25": row["rank"], "exact_name": exact}
                hits.append(symbol)
            hits.sort(key=lambda s: (not s["retrieval"]["exact_name"], s["kind"] == "module", s["retrieval"]["bm25"], s["id"]))
            meta = self._meta(conn)
            return {"query": query, "revision": meta["revision"], "freshness": "index_snapshot",
                    "hits": hits[:limit], "candidate_limit": 150,
                    "truncated": len(hits) > limit or len(rows) == 150 or len(exact_rows) == 51}

    @staticmethod
    def _source(conn, symbol: dict, max_lines: int, query: str | None = None,
                exclude_spans: list[list[int]] | None = None, receipt_file: dict | None = None) -> dict:
        meta = RepositoryIndex._meta(conn)
        record = conn.execute("SELECT hash FROM files WHERE path=?", (symbol["path"],)).fetchone()
        try:
            data, _ = read_stable(Path(meta["root"]), symbol["path"])
        except (OSError, ValueError) as exc:
            raise ValueError("Source unavailable; refresh the index") from exc
        if digest(data) != record[0]:
            raise ValueError(f"Stale source: {symbol['path']}; refresh the index before coding")
        lines = decode_source(symbol["path"], data, config=meta.get("inventory", {}).get("language_config"),
                              language=symbol.get("language")).splitlines()
        start = symbol["start_line"]
        exact_name = query and query.strip().lower() in {symbol.get('id', '').lower(), symbol.get('name', '').lower(), symbol.get('qualname', '').lower()}
        if query and not exact_name and (symbol["kind"] == "module" or symbol['end_line'] - start + 1 > max_lines):
            words = terms(query)
            # Rank only this declaration. A stronger match in a sibling must
            # not move its excerpt outside the symbol's source boundaries.
            ranked = [(sum(word in line.lower() for word in words), number)
                      for number, line in enumerate(lines[start - 1:symbol['end_line']], start)]
            score, number = max(ranked, key=lambda item: (item[0], -item[1]), default=(0, 0))
            if score:
                start = max(start, number - 3)
        from .receipts import merge_spans
        text = '\n'.join(lines)
        source_view_hash = digest(text.encode('utf-8'))
        receipt_compatible = bool(receipt_file and receipt_file.get('source_hash') == record[0]
                                  and receipt_file.get('source_view_hash') == source_view_hash)
        prior_spans = receipt_file['spans'] if receipt_compatible else []
        all_spans = merge_spans([*prior_spans, *(exclude_spans or [])])
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line) + 1)
        first = offsets[min(symbol['start_line'] - 1, len(lines))]
        last = min(len(text), offsets[min(symbol['end_line'], len(lines))])
        preferred = offsets[min(start - 1, len(lines))]
        # Spans use character offsets in newline-normalized decoded source.
        # Both raw bytes and the decoded view must match: changing a language
        # configuration can change decoding without changing any file bytes.
        available, cursor = [], first
        seen_bytes = sum(len(text[max(0, a):min(len(text), b)].encode('utf-8'))
                         for a, b in merge_spans(prior_spans))
        for a, b in all_spans:
            a, b = max(first, a), min(last, b)
            if a >= b:
                continue
            if cursor < a:
                available.append((cursor, a))
            cursor = max(cursor, b)
        if cursor < last:
            available.append((cursor, last))
        choices = [(max(a, preferred), b) for a, b in available if b > preferred]
        choices += [(a, b) for a, b in available if a < preferred]
        selected = None
        for a, b in choices:
            while a < b and text[a] == '\n':
                a += 1
            if a < b:
                selected = a, b
                break
        source_start, source_end = selected or (first, first)
        start = text.count('\n', 0, source_start) + 1
        end = min(symbol['end_line'], start + max_lines - 1, len(lines))
        source_end = min(source_end, max(source_start, offsets[end] - 1))
        excerpt = text[source_start:source_end].rstrip('\n')
        byte_truncated = len(excerpt.encode("utf-8")) > 16000
        if byte_truncated:
            excerpt = excerpt.encode("utf-8")[:16000].decode("utf-8", errors="ignore")
        source_end = source_start + len(excerpt)
        end = start + max(0, len(excerpt.splitlines()) - 1)
        partial = source_end < len(text) and text[source_end:source_end + 1] != '\n'
        result = dict(symbol)
        result["doc"] = result.get("doc", "")[:1200]
        result["signature"] = result.get("signature", "")[:800]
        result.update({"source": excerpt, "start_line": start, "excerpt_end_line": end,
                       "source_hash": record[0], "truncated": source_start > first or end < symbol["end_line"] or byte_truncated or partial,
                       "source_view_hash": source_view_hash, "receipt_compatible": receipt_compatible,
                       "last_line_may_be_partial": partial,
                       "source_start_column": source_start - offsets[min(start - 1, len(lines))] + 1,
                       "source_start_offset": source_start, "source_end_offset": source_end,
                       "seen_source_bytes": seen_bytes,
                       "freshness": "source_hash_verified", "revision": meta["revision"]})
        return result

    def symbol(self, symbol_id: str, max_lines: int = 80) -> dict:
        if not 1 <= max_lines <= 200:
            raise ValueError("max_lines must be 1–200")
        with self._read() as conn:
            result = self._source(conn, self._find(conn, symbol_id), max_lines)
            row = conn.execute("SELECT parsed FROM files WHERE path=?", (result["path"],)).fetchone()
            unresolved = [r for r in decode_parse(row[0]).get("references", [])
                          if r["source"] == result["id"] and not r.get("resolved")]
            result["unresolved_references"] = unresolved[:30]
            result["unresolved_reference_count"] = len(unresolved)
            return result

    def callers(self, query: str, budget_bytes: int = 12000, limit: int = 50) -> dict:
        """Direct caller identities and hash-verified call-site excerpts in one packet."""
        if not 1024 <= budget_bytes <= 1_000_000 or not 1 <= limit <= 200:
            raise ValueError("budget_bytes=1024–1000000 and limit=1–200 required")
        with self._read() as conn:
            matches = conn.execute("SELECT data FROM symbols WHERE id=?", (query,)).fetchall()
            if not matches:
                matches = conn.execute("SELECT data FROM symbols WHERE name=? ORDER BY id", (query,)).fetchall()
            if len(matches) != 1:
                raise ValueError("Caller target missing or ambiguous; search and use its complete symbol ID")
            target = json.loads(matches[0][0])
            meta = self._meta(conn)
            rows = conn.execute("SELECT source,MIN(line) AS line,COUNT(*) AS sites FROM edges "
                                "WHERE target=? AND kind='calls' GROUP BY source ORDER BY source LIMIT ?",
                                (target['id'], limit + 1)).fetchall()
            count = conn.execute("SELECT COUNT(DISTINCT source) FROM edges WHERE target=? AND kind='calls'",
                                 (target['id'],)).fetchone()[0]
            result = {"target": target['id'], "target_partial": target.get("partial", False), "revision": meta['revision'],
                      "freshness": "index_snapshot; included source hashes verified",
                      "semantic_complete": False, "repository_unresolved_references": meta.get('unresolved_references', 0),
                      "repository_diagnostic_count": len(meta.get('diagnostics', [])),
                      "source_policy": "Untrusted repository data; missing graph edges do not prove absence of callers.",
                      "matched_callers": count, "truncated": len(rows) > limit, "items": []}
            files = {}
            for row in rows[:limit]:
                caller = self._find(conn, row['source'])
                path = caller['path']
                if path not in files:
                    data, _ = read_stable(Path(meta['root']), path)
                    expected = conn.execute("SELECT hash FROM files WHERE path=?", (path,)).fetchone()[0]
                    if digest(data) != expected:
                        raise ValueError(f"Stale source: {path}; refresh before reading caller evidence")
                    lines = decode_source(path, data, config=meta.get('inventory', {}).get('language_config'),
                                          language=caller.get('language')).splitlines()
                    files[path] = (expected, lines)
                source_hash, lines = files[path]
                line = row['line']
                if not caller['start_line'] <= line <= min(caller['end_line'], len(lines)):
                    raise ValueError("Call site outside its indexed caller")
                start, end = max(caller['start_line'], line - 1), min(caller['end_line'], line + 2)
                result['items'].append({"id": caller['id'], "qualname": caller['qualname'], "path": path,
                    "partial": caller.get('partial', False),
                    "confidence": [r[0] for r in conn.execute("SELECT DISTINCT confidence FROM edges WHERE source=? AND target=? AND kind='calls' ORDER BY confidence", (caller['id'], target['id']))], "call_line": line, "call_sites": row['sites'],
                    "start_line": start, "end_line": end, "source_hash": source_hash,
                    "source": '\n'.join(lines[start - 1:end])})
                if byte_size(result) + 1 > budget_bytes:
                    result['items'].pop()
                    result['truncated'] = True
                    break
            if byte_size(result) + 1 > budget_bytes:
                raise ValueError("Budget too small for caller metadata")
            return result

    def neighbors(self, symbol_id: str, direction: str = "both", hops: int = 1,
                  limit: int = 50, kinds: list[str] | None = None) -> dict:
        if direction not in {"in", "out", "both"} or not 1 <= hops <= 3 or not 1 <= limit <= 200:
            raise ValueError("direction=in/out/both, hops=1–3, limit=1–200 required")
        if kinds is not None and (not kinds or any(k not in {"contains", "calls", "imports", "inherits"} for k in kinds)):
            raise ValueError("kinds must use contains/calls/imports/inherits")
        with self._read() as conn:
            first = self._find(conn, symbol_id)
            nodes, edges, seen_edges = {first["id"]: first}, [], set()
            queue, truncated = deque([(first["id"], 0)]), False
            while queue:
                node_id, depth = queue.popleft()
                if depth >= hops:
                    continue
                if direction == "in":
                    where, params = "target=?", [node_id]
                elif direction == "out":
                    where, params = "source=?", [node_id]
                else:
                    where, params = "(source=? OR target=?)", [node_id, node_id]
                if kinds:
                    where += " AND kind IN (" + ",".join("?" for _ in kinds) + ")"
                    params += kinds
                rows = conn.execute("SELECT * FROM edges WHERE " + where + " ORDER BY kind,source,target,line LIMIT 1001", params).fetchall()
                truncated |= len(rows) > 1000
                for row in rows[:1000]:
                    edge = dict(row)
                    other = edge["source"] if edge["target"] == node_id else edge["target"]
                    if other not in nodes:
                        if len(nodes) >= limit:
                            truncated = True
                            continue
                        nodes[other] = self._find(conn, other)
                        queue.append((other, depth+1))
                    key = compact(edge)
                    if key not in seen_edges:
                        if len(edges) >= 2000:
                            truncated = True
                            continue
                        seen_edges.add(key)
                        edges.append(edge)
            return {"center": first["id"], "nodes": list(nodes.values()), "edges": edges,
                    "revision": self._meta(conn)["revision"], "freshness": "index_snapshot",
                    "semantic_complete": False,
                    "repository_diagnostic_count": len(self._meta(conn).get("diagnostics", [])),
                    "repository_unresolved_references": self._meta(conn).get('unresolved_references', 0),
                    "partial_nodes": sum(bool(n.get('partial')) for n in nodes.values()),
                    "truncated": truncated, "direction": direction, "hops": hops}

    def graph(self, limit: int = 1000, *, path: str | None = None, language: str | None = None,
              kinds: list[str] | None = None, focus: str | None = None, hops: int = 2,
              direction: str = "both", level: str = "symbol") -> dict:
        from .graph_views import graph_view
        return graph_view(self, limit, path=path, language=language, kinds=kinds,
                          focus=focus, hops=hops, direction=direction, level=level)

    def context(self, query: str, budget_bytes: int = 12000, *, budget_tokens: int | None = None,
                mode: str = "snippets", exclude_ids: list[str] | None = None,
                path: str | None = None, language: str | None = None,
                output_format: str = 'json', receipt: dict | None = None) -> dict:
        from .retrieval import build_context
        return build_context(self, query, budget_bytes, budget_tokens=budget_tokens, mode=mode,
                             exclude_ids=exclude_ids, path=path, language=language, output_format=output_format,
                             receipt=receipt)

    def repo_map(self, query: str = "", budget_bytes: int = 6000, *, budget_tokens: int | None = None,
                 path: str | None = None, language: str | None = None,
                 output_format: str = 'json') -> dict:
        from .retrieval import repository_map
        return repository_map(self, query, budget_bytes, budget_tokens=budget_tokens, path=path, language=language,
                              output_format=output_format)
