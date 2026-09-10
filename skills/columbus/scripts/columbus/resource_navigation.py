"""Bounded discovery of declared JVM resources, without runtime dispatch claims."""
from __future__ import annotations

import base64
import hashlib
import json
import re

from .parse_cache import decode_parse_cache
from .retrieval import envelope, fits, limits

CANDIDATE_LIMIT = 200
_HTTP = {"RequestMapping": None, "GetMapping": "GET", "PostMapping": "POST",
         "PutMapping": "PUT", "DeleteMapping": "DELETE", "PatchMapping": "PATCH"}
_REGISTRY = {"org.springframework.web.bind.annotation." + name: "http" for name in _HTTP}
_REGISTRY.update({"org.springframework.kafka.annotation.KafkaListener": "kafka",
                  "jakarta.persistence.Table": "table", "javax.persistence.Table": "table"})
_REGISTRY.update({"org.springframework.cache.annotation." + name: "cache"
                  for name in ("Cacheable", "CachePut", "CacheEvict")})
_SHORT = {name.rsplit(".", 1)[-1]: kind for name, kind in _REGISTRY.items()}
_LIMITATIONS = [
    "Declarations only; no live HTTP registration, DI, broker, SQL access or cache execution verified.",
    "Indirect/meta-annotations, annotation containers, inheritance, external configuration and framework defaults are not expanded.",
]


def _encode(binding, after):
    return base64.urlsafe_b64encode(json.dumps([1, binding, after], separators=(",", ":")).encode()).decode().rstrip("=")


def _decode(cursor, binding):
    try:
        if not isinstance(cursor, str) or not 1 <= len(cursor) <= 16000 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
            raise ValueError
        value = json.loads(base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True))
        if not isinstance(value, list) or len(value) != 3 or value[:2] != [1, binding]:
            raise ValueError
        after = value[2]
        if (not isinstance(after, list) or len(after) != 3
                or any(not isinstance(v, str) or len(v) > 4096 for v in after[:2])
                or type(after[2]) is not int or after[2] < 0):
            raise ValueError
        return after
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ValueError("Invalid resource cursor or different revision, repository, query or filter scope") from exc


def _annotation(value, symbol):
    if isinstance(value, dict):
        return value
    raw = str(value)
    match = re.match(r"@(?:[\w]+:)?([\w.]+)", raw)
    return dict(name=match[1] if match else "", text=raw, start_line=symbol["start_line"],
                end_line=symbol["start_line"], truncated=len(raw) >= 300, legacy=True)


def _annotations(symbol):
    return [_annotation(value, symbol) for value in symbol.get("annotation_details", symbol.get("annotations", []))]


def _identity(annotation, file_info):
    name = annotation.get("name", "")
    if name in _REGISTRY:
        return name, _REGISTRY[name], []
    if "." in name:
        return None
    imported = [i for i in file_info["imports"] if not i.get("wildcard") and i.get("alias") == name]
    if imported:
        qualified = imported[0].get("qualified", "")
        if len(imported) != 1:
            return (name, _SHORT[name], ["Conflicting annotation imports."]) if name in _SHORT else None
        if qualified not in _REGISTRY:
            return None
        if name in file_info["types"]:
            return qualified, _REGISTRY[qualified], ["Local declaration shadows the annotation name."]
        reason = ["Annotation import alias is not resolved as a framework declaration."] if imported[0].get("name") != name else []
        return qualified, _REGISTRY[qualified], reason
    if name in file_info["types"] or name not in _SHORT:
        return None
    return name, _SHORT[name], ["Annotation has no unambiguous fully qualified name or explicit import; wildcard imports are not resolved."]


def _split(raw):
    """Split only top-level arguments; nested expressions stay opaque data."""
    parts, start, stack, quoted, escaped = [], 0, [], False, False
    pairs = {")": "(", "]": "[", "}": "{"}
    for offset, char in enumerate(raw):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "([{":
            stack.append(char)
        elif char in ")]}":
            if not stack or stack.pop() != pairs[char]:
                return None
        elif char == "," and not stack:
            parts.append(raw[start:offset].strip())
            start = offset + 1
    if quoted or stack:
        return None
    parts.append(raw[start:].strip())
    return [p for p in parts if p]


def _attributes(annotation):
    raw = annotation.get("text", "")
    if annotation.get("truncated"):
        return {}, ["Annotation evidence was truncated; trailing arguments may change the declaration."]
    if "(" not in raw:
        return {}, []
    if not raw.rstrip().endswith(")"):
        return {}, ["Incomplete annotation argument syntax."]
    parts = _split(raw[raw.index("(") + 1:raw.rfind(")")])
    if parts is None:
        return {}, ["Unsupported or incomplete annotation arguments."]
    attrs = {}
    for part in parts:
        match = re.match(r"^(\w+)\s*=\s*(.*)$", part, re.S)
        key, value = (match[1], match[2]) if match else ("value", part)
        if key in attrs:
            return attrs, ["Repeated annotation argument or unsupported positional arguments."]
        attrs[key] = value
    return attrs, []


def _strings(raw):
    if raw is None:
        return [], False
    value = raw.strip()
    if value.startswith(("[", "{")) and value.endswith(("]", "}")):
        parts = _split(value[1:-1])
        if parts is None:
            return [value], True
        results, dynamic = [], False
        for part in parts:
            parsed, uncertain = _strings(part)
            results.extend(parsed)
            dynamic |= uncertain
        return results, dynamic
    try:
        parsed = json.loads(value)
        if isinstance(parsed, str):
            return [parsed], bool(re.search(r"\$\{|\$[A-Za-z_]|#", parsed))
    except (ValueError, TypeError):
        pass
    return [value], True


def _single(attrs, name):
    values, dynamic = _strings(attrs.get(name))
    return (values[0] if values else None), dynamic or len(values) > 1


def _bool(attrs, name):
    value = attrs.get(name)
    if value in ("true", "false"):
        return value == "true", False
    return (None, value is not None)


def _alias(attrs, name, default="value"):
    values, dynamic = _strings(attrs.get(name, attrs.get(default)))
    return values, dynamic, ([f"Both {name} and {default} are declared; alias conflict is not evaluated."]
                             if name in attrs and default in attrs else [])


def _http(annotation, attrs, symbol, file_info, conn):
    paths, dynamic, reasons = _alias(attrs, "path")
    paths = paths or [""]
    short = annotation["name"].rsplit(".", 1)[-1]
    method = _HTTP.get(short)
    methods = [method] if method else ["ANY"]
    if "method" in attrs:
        raw = attrs["method"].strip().strip("{}[]")
        tokens = _split(raw)
        if tokens and all(re.fullmatch(r"(?:org\.springframework\.web\.bind\.annotation\.)?RequestMethod\.(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS|TRACE)", t) for t in tokens):
            methods = [t.rsplit(".", 1)[-1] for t in tokens]
        else:
            methods, dynamic = [attrs["method"]], True
    bases, evidence = [""], []
    parent_row = conn.execute("SELECT data FROM symbols WHERE id=? AND path=?", (symbol.get("parent_id"), symbol["path"])).fetchone()
    if parent_row:
        parent = json.loads(parent_row[0])
        version = parent.get("annotation_metadata_version")
        if (type(version) is not int or version < 2 or parent.get("annotation_metadata_complete") is not True
                or parent.get("partial") or not any(key in parent for key in ("annotation_details", "annotations"))):
            reasons.append("Enclosing type annotation metadata is legacy, missing or incomplete; sync before resolving the full HTTP path.")
        class_mappings = []
        for detail in _annotations(parent):
            identity = _identity(detail, file_info)
            if identity and identity[1] == "http":
                class_mappings.append((detail, identity))
        if len(class_mappings) > 1:
            reasons.append("Multiple class mappings are not combined.")
        for detail, identity in class_mappings[:1]:
            evidence.append(detail)
            parent_attrs, errors = _attributes(detail)
            parent_paths, uncertain, conflicts = _alias(parent_attrs, "path")
            bases = parent_paths or [""]
            dynamic |= uncertain
            reasons.extend(identity[2] + errors + conflicts)
            if "method" in parent_attrs:
                reasons.append("Class-level HTTP method conditions are not combined.")
    else:
        reasons.append("Enclosing type metadata is missing; the full HTTP path is unknown.")
    if not any(paths + bases):
        reasons.append("No explicit HTTP path is available; class mapping metadata may be missing and a root route is not inferred.")
    combined = []
    if not dynamic and not reasons:
        for base in bases:
            for suffix in paths:
                combined.append((base.rstrip("/") + "/" + suffix.lstrip("/")) if base and suffix else base or suffix)
                if len(combined) >= 64 and len(bases) * len(paths) > 64:
                    reasons.append("Literal path combinations exceed the 64-path extraction bound.")
                    break
            if reasons:
                break
    return dict(methods=methods, paths=combined, declared_paths=paths, class_paths=bases), dynamic, reasons, evidence


def _details(kind, annotation, attrs, symbol, file_info, conn):
    if kind == "http":
        return _http(annotation, attrs, symbol, file_info, conn)
    info, dynamic, reasons = {}, False, []
    if kind == "kafka":
        info["topics"], dynamic = _strings(attrs.get("topics"))
        for argument, key in (("topicPattern", "topic_pattern"), ("groupId", "group_id"), ("autoStartup", "auto_startup")):
            info[key], uncertain = _single(attrs, argument)
            dynamic |= uncertain
        if attrs.get("autoStartup") in ("true", "false"):
            info["auto_startup"] = attrs["autoStartup"]
            # Booleans are accepted as declaration evidence even though Spring uses String.
            dynamic = any(_strings(attrs.get(k))[1] for k in ("topics", "topicPattern", "groupId"))
        info["declared_disabled"] = info["auto_startup"] == "false"
        if "topicPartitions" in attrs:
            reasons.append("Explicit topicPartitions are preserved in evidence but not expanded.")
        if not info["topics"] and not info["topic_pattern"]:
            reasons.append("No literal topic or topic pattern is available.")
    elif kind == "table":
        for name in ("name", "schema", "catalog"):
            info[name], uncertain = _single(attrs, name)
            dynamic |= uncertain
        if not info["name"]:
            reasons.append("Implicit entity table names and naming strategies are not inferred.")
    else:
        info["operation"] = annotation["name"].rsplit(".", 1)[-1]
        info["names"], dynamic, reasons = _alias(attrs, "cacheNames")
        for argument, key in (("key", "key"), ("condition", "condition"), ("unless", "unless")):
            info[key], uncertain = _single(attrs, argument)
            dynamic |= uncertain
        for argument, key in (("allEntries", "all_entries"), ("beforeInvocation", "before_invocation")):
            info[key], uncertain = _bool(attrs, argument)
            dynamic |= uncertain
        if not info["names"]:
            reasons.append("Inherited cache names and cache resolver results are not inferred.")
    return info, dynamic, reasons, []


def _item(annotation, symbol, identity, file_info, source_hash, annotation_index, conn):
    qualified, kind, reasons = identity
    if kind == "http" and symbol["kind"] not in {"method", "function"}:
        return None
    attrs, errors = _attributes(annotation)
    reasons = list(reasons) + errors
    if any(detail.get("text") != annotation.get("text")
           and annotation.get("text", "") in detail.get("text", "")
           for detail in _annotations(symbol)):
        reasons.append("Annotation is nested inside another annotation; container semantics are not expanded.")
    if annotation.get("legacy"):
        reasons.append("legacy annotation metadata has approximate source lines and no explicit truncation flag.")
    if symbol.get("partial"):
        reasons.append("File parsing was partial; related declarations may be missing.")
    canonical = dict(annotation, name=qualified)
    info, dynamic, extra, parent_evidence = _details(kind, canonical, attrs, symbol, file_info, conn)
    reasons.extend(extra)
    if reasons and kind == "http":
        info["paths"] = []
    resolution = "incomplete" if reasons else "dynamic" if dynamic else "literal"
    if dynamic:
        reasons.append("Expressions, placeholders or SpEL are preserved as declaration text and are not evaluated.")
    summary = {"http": lambda: " ".join(info["methods"]) + " " + (", ".join(info["paths"] or info["declared_paths"]) or "<unresolved path>"),
               "kafka": lambda: "subscribe " + ", ".join(info["topics"] or [info["topic_pattern"] or "<unresolved>"]) + (" disabled" if info["declared_disabled"] else ""),
               "table": lambda: ".".join(v for v in (info["schema"], info["name"]) if v) or "<implicit table>",
               "cache": lambda: info["operation"] + " " + ", ".join(info["names"])}[kind]()
    return dict(id=f"{symbol['id']}::resource:{annotation_index}", path=symbol["path"],
                start_line=annotation.get("start_line", symbol["start_line"]),
                end_line=annotation.get("end_line", symbol["end_line"]), kind="resource", resource_kind=kind,
                signature=summary[:500], owner_id=symbol["id"], language=symbol.get("language"),
                resolution=resolution, source_hash=source_hash, runtime_verified=False, semantic_complete=False,
                limitations=list(dict.fromkeys(reasons)), evidence=parent_evidence + [annotation], **{kind: info})


def resources(index, query="", *, kind=None, path=None, limit=30, cursor=None,
              budget_bytes=6000, budget_tokens=None, output_format="json"):
    """Return a bounded snapshot page of resource declarations and explicit uncertainties."""
    budget = limits(budget_bytes, budget_tokens)
    if not isinstance(query, str) or len(query) > 2000:
        raise ValueError("query must contain at most 2000 characters")
    if kind is not None and kind not in {"http", "kafka", "table", "cache"}:
        raise ValueError("kind must be http, kafka, table or cache")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be 1–100")
    where, values = index._filter_sql(path, None)
    with index._read() as conn:
        meta = index._meta(conn)
        binding = hashlib.sha256(json.dumps(["resources/v1", meta.get("root"), meta["revision"], query, path, kind]).encode()).hexdigest()
        after = _decode(cursor, binding) if cursor is not None else None
        if after:
            where += " AND (s.path,s.id,CAST(a.key AS INTEGER)) > (?,?,?)"
            values.extend(after)
        rows = conn.execute("""SELECT s.data,s.id,s.path,f.hash,a.key AS annotation_index,a.value AS annotation
            FROM symbols s JOIN files f ON f.path=s.path,
            json_each(COALESCE(json_extract(s.data,'$.annotation_details'),json_extract(s.data,'$.annotations'),'[]')) a
            WHERE """ + where + " ORDER BY s.path,s.id,CAST(a.key AS INTEGER) LIMIT ?", [*values, CANDIDATE_LIMIT + 1]).fetchall()
        packet = envelope(meta, query, "resources", budget, budget_tokens, output_format)
        packet.update(semantic_complete=False, runtime_verified=False, limitations=list(_LIMITATIONS),
                      next_cursor=None, candidate_limit=CANDIDATE_LIMIT, scanned_candidates=0,
                      omitted_candidates_exact=False)
        file_cache, positions = {}, []
        previous, pending = after, None
        for row_number, row in enumerate(rows[:CANDIDATE_LIMIT]):
            position = [row["path"], row["id"], row["annotation_index"]]
            symbol = json.loads(row["data"])
            annotation = _annotation(json.loads(row["annotation"]) if row["annotation"].startswith("{") else row["annotation"], symbol)
            if row["path"] not in file_cache:
                parsed = decode_parse_cache(conn.execute("SELECT parsed FROM files WHERE path=?", (row["path"],)).fetchone()[0])
                file_cache[row["path"]] = {"imports": parsed.get("imports", []),
                    "types": {s["name"] for s in parsed.get("symbols", []) if s["kind"] in {"class", "interface", "object", "enum", "record"}}}
            file_info = file_cache[row["path"]]
            identity = _identity(annotation, file_info)
            packet["scanned_candidates"] += 1
            item = _item(annotation, symbol, identity, file_info, row["hash"], row["annotation_index"], conn) if identity and (kind is None or identity[1] == kind) else None
            if item and query.casefold() not in json.dumps(item, ensure_ascii=False).casefold():
                item = None
            if item:
                packet["items"].append(item)
                packet["next_cursor"] = _encode(binding, position) if row_number + 1 < len(rows) else None
                packet["truncated"] = packet["next_cursor"] is not None
                if not fits(packet):
                    packet["items"].pop()
                    pending = previous
                    if not packet["items"]:
                        raise ValueError("Budget too small for one resource item and metadata; increase budget_bytes or narrow the query")
                    break
                positions.append(previous)
            previous = position
            if len(packet["items"]) >= limit:
                pending = position if row_number + 1 < len(rows) else None
                break
        else:
            pending = previous if len(rows) > CANDIDATE_LIMIT else None
        packet["next_cursor"] = _encode(binding, pending) if pending is not None else None
        packet["truncated"] = packet["next_cursor"] is not None
        packet["omitted_candidates"] = int(packet["truncated"])
        packet["omitted_candidates_exact"] = not packet["truncated"]
        evicted = False
        while not fits(packet) and packet["items"]:
            packet["items"].pop()
            evicted = True
            pending = positions.pop()
            packet.update(next_cursor=_encode(binding, pending) if pending is not None else None,
                          truncated=True, omitted_candidates=1, omitted_candidates_exact=False)
        if not fits(packet) or (evicted and not packet["items"]):
            raise ValueError("Budget too small for resource response metadata; increase budget_bytes")
        return packet
