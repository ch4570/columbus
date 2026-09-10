"""Tree-sitter JVM navigation facts, never compiler or runtime equivalence.

No builds, annotation processors, class loading or LLM calls. Explicitly typed
receivers may point to a declared member with heuristic confidence. Declared
generic bases, bounds, return types and standard collection elements provide
bounded navigation; overload selection, extension dispatch, implicit lambda
receivers and this/super dispatch remain unresolved. Block locals are conservatively
collected at function scope: shadowing can suppress a valid edge, never justify it.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any

TYPE_NODES = {"user_type", "nullable_type", "function_type", "parenthesized_type",
              "type_identifier", "scoped_type_identifier", "generic_type",
              "integral_type", "floating_point_type", "boolean_type", "array_type",
              "annotated_type", "void_type", "dynamic"}
CLASS_NODES = {"class_declaration", "interface_declaration", "enum_declaration",
               "record_declaration", "object_declaration", "companion_object",
               "annotation_type_declaration"}
FUNCTION_NODES = {"function_declaration", "method_declaration",
                  "constructor_declaration", "secondary_constructor",
                  "annotation_type_element_declaration"}
CLASS_KINDS = {"class", "interface", "enum", "record", "object"}
CALLABLE_KINDS = {"function", "method", "constructor"}


def _children(node, kinds):
    return [c for c in node.named_children if c.type in kinds]


def _first(node, kinds):
    return next(iter(_children(node, kinds)), None)


def _walk(node):
    yield node
    for child in node.named_children:
        yield from _walk(child)


class _Parser:
    def __init__(self, path, source, module, language):
        self.path, self.source = path, source.encode("utf-8")
        self.module, self.language, self.package = module, language, ""
        # Avoid native Point properties: tree-sitter 0.26.0 row/column getters
        # return borrowed references. Byte offsets also preserve UTF-8 spans.
        self.line_starts = [0] + [i + 1 for i, byte in enumerate(self.source) if byte == 10]
        self.symbols, self.references, self.imports = [], [], []
        self.scopes, self.counts = {}, defaultdict(int)
        self.annotation_cache = {}
        self.current = f"{path}::module"
        self.scope(self.current, None, "module", "")
        self.symbols.append(dict(id=self.current, path=path, module=module,
            name=PurePosixPath(path).name, qualname=module, kind="module",
            start_line=1, end_line=max(1, len(source.splitlines())),
            signature="", doc="", parent_id=None, language=language))

    def line(self, byte_offset):
        return bisect_right(self.line_starts, byte_offset)

    def text(self, node):
        return self.source[node.start_byte:node.end_byte].decode("utf-8") if node else ""

    def normalized(self, node):
        return "".join(self.text(node).split())

    def scope(self, key, parent, kind, qualname):
        self.scopes[key] = dict(id=key, parent=parent, kind=kind,
                                qualname=qualname, bindings={}, type_parameters={}, type_aliases=[])

    def bind(self, name, type_text="", *, reason="local", target=None, expression=None):
        if name:
            self.scopes[self.current]["bindings"].setdefault(name, []).append(
                dict(type=type_text, reason=reason, target=target,
                     scope_id=self.current, expression=expression))

    def type_parameters(self, node):
        container = node.child_by_field_name("type_parameters") or _first(node, {"type_parameters"})
        result = {}
        for parameter in container.named_children if container else []:
            name = _first(parameter, {"identifier", "type_identifier"})
            bound = _first(parameter, {"type_bound"})
            bounds = _children(bound or parameter, TYPE_NODES)
            result[self.text(name)] = [self.normalized(b) for b in bounds if b != name]
        return result

    def parameters(self, node):
        container = node.child_by_field_name("parameters") or _first(node, {
            "function_value_parameters", "class_parameters", "formal_parameters"})
        if not container:
            primary = _first(node, {"primary_constructor"})
            container = _first(primary, {"class_parameters"}) if primary else None
        values = []
        for parameter in container.named_children if container else []:
            if parameter.type not in {"parameter", "formal_parameter", "spread_parameter", "class_parameter"}:
                continue
            name = parameter.child_by_field_name("name") or _first(parameter, {"identifier"})
            if not name:
                variable = _first(parameter, {"variable_declarator"})
                name = variable.child_by_field_name("name") if variable else None
            type_node = parameter.child_by_field_name("type") or _first(parameter, TYPE_NODES)
            type_text = self.normalized(type_node)
            vararg = parameter.type == "spread_parameter" or "vararg" in [self.text(c) for c in parameter.children]
            values.append(dict(name=self.text(name), type=type_text,
                               signature=type_text + ("..." if vararg else "")))
        return values

    def annotations(self, node):
        return [annotation["text"] for annotation in self.annotation_details(node)]

    def annotation_details(self, node):
        return self.annotation_facts(node)["details"]

    def detached_annotation_spans(self, node, depth=0):
        """Accept only an annotation prefix, including the grammar's split args."""
        if node.type != "annotated_expression" or depth > 16:
            return None
        children = node.named_children
        if len(children) > 64:
            return None
        spans, index, position = [], 0, node.start_byte
        while index < len(children):
            child = children[index]
            if self.source[position:child.start_byte].strip():
                return None
            end_byte = child.end_byte
            if child.type == "annotation":
                # The pinned grammar can read @Route("/api") as @Route plus
                # a parenthesized expression. Rejoin only adjacent arguments.
                if (index + 1 < len(children) and children[index + 1].type == "parenthesized_expression"
                        and children[index + 1].start_byte == end_byte):
                    index += 1
                    end_byte = children[index].end_byte
                spans.append((child, end_byte))
            elif child.type == "annotated_expression":
                nested = self.detached_annotation_spans(child, depth + 1)
                if not nested:
                    return None
                spans.extend(nested)
            elif child.type not in {"line_comment", "block_comment", "multiline_comment"}:
                return None
            position = end_byte
            index += 1
        return spans if not self.source[position:node.end_byte].strip() else None

    def annotation_facts(self, node):
        key = (node.start_byte, node.end_byte, node.type)
        if key in self.annotation_cache:
            return self.annotation_cache[key]
        mods = _first(node, {"modifiers"})
        prefix, start_byte, previous, complete = [], node.start_byte, node.prev_named_sibling, True
        if self.language == "kotlin" and node.type in CLASS_NODES | FUNCTION_NODES:
            cursor, boundary, count = previous, node.start_byte, 0
            while cursor and count < 64:
                if self.source[cursor.end_byte:boundary].strip():
                    break
                if node.start_byte - cursor.start_byte > 16384:
                    complete = False
                    break
                count += 1
                if cursor.type in {"line_comment", "block_comment", "multiline_comment"}:
                    boundary, cursor = cursor.start_byte, cursor.prev_named_sibling
                    continue
                if cursor.type != "annotated_expression":
                    break
                spans = self.detached_annotation_spans(cursor)
                if not spans:
                    complete = False
                    break
                prefix = spans + prefix
                start_byte, previous = cursor.start_byte, cursor.prev_named_sibling
                boundary, cursor = cursor.start_byte, cursor.prev_named_sibling
            if count == 64:
                complete = False
        annotations = prefix + [(annotation, annotation.end_byte) for annotation in _walk(mods)
                                if annotation.type in {"annotation", "marker_annotation"}] if mods else prefix
        details = []
        for annotation, end_byte in annotations:
            raw = self.source[annotation.start_byte:end_byte].decode("utf-8")
            name = annotation.child_by_field_name("name") or _first(annotation, {
                "user_type", "identifier", "scoped_identifier", "constructor_invocation"})
            if name and name.type == "constructor_invocation":
                name = _first(name, {"user_type"})
            details.append(dict(name=self.normalized(name), text=raw[:300],
                                start_line=self.line(annotation.start_byte),
                                end_line=self.line(end_byte), truncated=len(raw) > 300))
        facts = dict(details=details, start_byte=start_byte, previous=previous, complete=complete)
        self.annotation_cache[key] = facts
        return facts

    def declaration_modifiers(self, node):
        modifiers = _first(node, {"modifiers"})
        keywords = {"public", "private", "protected", "internal", "static", "abstract",
                    "final", "override", "open", "sealed", "non-sealed", "default", "native",
                    "synchronized", "strictfp", "transient", "volatile", "data", "inner",
                    "inline", "crossinline", "noinline", "tailrec", "operator", "infix",
                    "const", "lateinit", "external", "expect", "actual", "reified", "value",
                    "suspend", "vararg"}

        def tokens(current):
            if current.type in {"annotation", "marker_annotation"}:
                return
            if not current.children:
                if current.type in keywords:
                    yield current.type
                return
            for child in current.children:
                yield from tokens(child)

        return sorted(set(tokens(modifiers))) if modifiers else []

    def declaration(self, node):
        parent = self.scopes[self.current]
        name_node = node.child_by_field_name("name")
        name = self.text(name_node)
        is_class = node.type in CLASS_NODES
        if is_class:
            kind = {"interface_declaration": "interface", "annotation_type_declaration": "interface", "enum_declaration": "enum",
                    "record_declaration": "record", "object_declaration": "object",
                    "companion_object": "object"}.get(node.type, "class")
            words = self.text(node).split("{", 1)[0].split()
            if self.language == "kotlin" and "interface" in words:
                kind = "interface"
            elif self.language == "kotlin" and "enum" in words:
                kind = "enum"
            if node.type == "companion_object" and not name:
                name = "Companion"
        else:
            kind = "constructor" if "constructor" in node.type else (
                "method" if parent["kind"] in CLASS_KINDS else "function")
            if kind == "constructor":
                name = "<init>"
        if not name:
            return
        params = self.parameters(node)
        receiver = ""
        if node.type == "function_declaration" and name_node:
            before_name = [c for c in node.named_children if c.end_byte <= name_node.start_byte and c.type in TYPE_NODES]
            if before_name:
                receiver = self.normalized(before_name[-1])
        prefix = parent["qualname"]
        qualname = f"{prefix}.{name}" if prefix else name
        signature_types = ",".join(p["signature"] for p in params)
        suffix = (f"({signature_types})" if not is_class else "") + (f"@{receiver}" if receiver else "")
        base = f"{self.path}::{qualname}:{kind}{suffix}"
        self.counts[base] += 1
        key = base + (f"#duplicate{self.counts[base]}" if self.counts[base] > 1 else "")
        body = node.child_by_field_name("body") or _first(node, {
            "class_body", "enum_class_body", "function_body", "block"})
        header_end = body.start_byte if body else node.end_byte
        annotation_facts = self.annotation_facts(node)
        annotation_details = annotation_facts["details"]
        declaration_start = annotation_facts["start_byte"]
        signature = " ".join(self.source[declaration_start:header_end].decode().split())[:600]
        previous = annotation_facts["previous"]
        doc = self.text(previous) if previous and previous.type in {"block_comment", "multiline_comment"} else ""
        symbol = dict(id=key, path=self.path, module=self.module, name=name,
            qualname=qualname, kind=kind, start_line=self.line(declaration_start),
            end_line=self.line(node.end_byte), signature=signature, doc=doc[:3000],
            parent_id=self.current, language=self.language, package=self.package,
            parameter_types=[p["signature"] for p in params], receiver_type=receiver,
            annotations=[a["text"] for a in annotation_details], annotation_details=annotation_details,
            annotation_metadata_version=2, annotation_metadata_complete=annotation_facts["complete"],
            declaration_modifiers=self.declaration_modifiers(node),
            local=parent["kind"] in CALLABLE_KINDS)
        return_node = node.child_by_field_name("type")
        if node.type == "function_declaration":
            return_node = next((c for c in node.named_children
                                if c.type in TYPE_NODES and c.start_byte > name_node.end_byte), None)
        symbol["return_type"] = self.normalized(return_node) if not is_class else ""
        symbol["type_parameters"] = self.type_parameters(node)
        self.symbols.append(symbol)
        self.bind(name, reason="declaration", target=key)
        previous_scope = self.current
        self.scope(key, previous_scope, kind, qualname)
        self.scopes[key]["type_parameters"] = symbol["type_parameters"]
        self.current = key
        for parameter in params:
            self.bind(parameter["name"], parameter["type"], reason="parameter")
        if is_class:
            self.inheritance(node)
            primary = _first(node, {"primary_constructor"})
            for item in _walk(primary) if primary else []:
                if item.type == "class_parameter" and any(c.type in {"val", "var"} for c in item.children):
                    property_name = self.text(_first(item, {"identifier"}))
                    property_type = self.normalized(_first(item, TYPE_NODES))
                    property_annotations = self.annotation_details(item)
                    self.symbols.append(dict(id=f"{key}.{property_name}:property", path=self.path,
                        module=self.module, name=property_name, qualname=f"{qualname}.{property_name}",
                        kind="property", start_line=self.line(item.start_byte),
                        end_line=self.line(item.end_byte), signature=self.text(item), doc="",
                        parent_id=key, language=self.language, package=self.package,
                        declared_type=property_type, annotations=[a["text"] for a in property_annotations],
                        annotation_details=property_annotations,
                        annotation_metadata_version=2, annotation_metadata_complete=True,
                        declaration_modifiers=self.declaration_modifiers(item)))
        # Primary-constructor parameters participate in conservative class scope.
        for child in node.named_children:
            if child.type not in {"modifiers", "function_value_parameters", "formal_parameters", "primary_constructor"}:
                self.visit(child)
        self.current = previous_scope

    def inheritance(self, node):
        for clause in _children(node, {"superclass", "super_interfaces", "extends_interfaces", "delegation_specifiers"}):
            # Outermost type nodes avoid inventing inheritance for generic args.
            def types(current):
                if current.type in TYPE_NODES:
                    yield current
                elif current.type not in {"value_arguments", "argument_list", "expression"}:
                    for child in current.named_children:
                        yield from types(child)
            for type_node in types(clause):
                name = self.normalized(type_node)
                self.references.append(dict(source=self.current, scope_id=self.current,
                    kind="inherits", name=name, member=name, receiver="", constructor=False,
                    path=self.path, line=self.line(type_node.start_byte),
                    evidence=self.text(clause)[:240], resolved=False))

    def property(self, node):
        type_node = node.child_by_field_name("type")
        variables = _children(node, {"variable_declaration", "variable_declarator"})
        for variable in variables:
            name_node = variable.child_by_field_name("name") or _first(variable, {"identifier"})
            name = self.text(name_node)
            value_type = self.normalized(type_node or _first(variable, TYPE_NODES))
            initializer = variable.child_by_field_name("value")
            if initializer is None and node.type == "property_declaration":
                initializer = next((c for c in node.named_children if c.start_byte > variable.end_byte), None)
            immutable = any(c.type == "val" for c in node.children)
            self.bind(name, value_type, reason="variable",
                      expression=self.expression(initializer) if immutable else None)
            scope = self.scopes[self.current]
            if scope["kind"] in CLASS_KINDS | {"module"}:
                property_annotations = self.annotation_details(node)
                qualname = ".".join(filter(None, [scope["qualname"], name]))
                base = f"{self.path}::{qualname}:property"
                self.counts[base] += 1
                key = base + (f"#duplicate{self.counts[base]}" if self.counts[base] > 1 else "")
                self.symbols.append(dict(id=key, path=self.path, module=self.module,
                    name=name, qualname=qualname, kind="property",
                    start_line=self.line(node.start_byte), end_line=self.line(node.end_byte),
                    signature=f"{name}: {value_type or '<inferred>'}", doc="",
                    parent_id=self.current, language=self.language, package=self.package,
                    declared_type=value_type, annotations=[a["text"] for a in property_annotations],
                    annotation_details=property_annotations,
                    annotation_metadata_version=2, annotation_metadata_complete=True,
                    declaration_modifiers=self.declaration_modifiers(node)))
        for child in node.named_children:
            self.visit(child)

    def expression(self, node, depth=0):
        """Small JSON-safe expression facts; unsupported syntax carries no type."""
        if node is None or depth > 24:
            return None
        if node.type == "identifier":
            return dict(kind="name", name=self.text(node))
        if node.type in {"call_expression", "method_invocation", "object_creation_expression"}:
            return dict(kind="call", **self.call_parts(node, depth + 1))
        if node.type in {"navigation_expression", "field_access"}:
            parts = node.named_children
            if len(parts) == 2 and parts[1].type == "identifier":
                return dict(kind="property", receiver=self.expression(parts[0], depth + 1),
                            member=self.text(parts[1]))
        if node.type == "index_expression" and node.named_children:
            return dict(kind="index", receiver=self.expression(node.named_children[0], depth + 1),
                        argument_count=len(node.named_children) - 1)
        if node.type == "binary_expression" and any(c.type == "?:" for c in node.children):
            # Only a terminating fallback preserves the left-hand declared type.
            right = node.child_by_field_name("right")
            if right and right.type in {"return_expression", "throw_expression", "continue_expression", "break_expression"}:
                return self.expression(node.child_by_field_name("left"), depth + 1)
        return None

    def call_parts(self, node, depth=0):
        receiver, name, construct = "", "", False
        receiver_node = None
        if node.type == "method_invocation":
            name = self.text(node.child_by_field_name("name"))
            receiver_node = node.child_by_field_name("object")
            receiver = self.text(receiver_node)
        elif node.type == "object_creation_expression":
            name = self.normalized(node.child_by_field_name("type"))
            construct = True
        else:
            callee = node.named_children[0] if node.named_children else None
            if callee and callee.type == "identifier":
                name = self.text(callee)
            elif callee and callee.type == "navigation_expression":
                parts = callee.named_children
                if len(parts) == 2 and parts[1].type == "identifier":
                    receiver, name = self.text(parts[0]), self.text(parts[1])
                    receiver_node = parts[0]
        arguments = node.child_by_field_name("arguments") or _first(node, {"value_arguments", "argument_list"})
        argument_count = len(arguments.named_children) if arguments else 0
        argument_count += sum(c.type == "annotated_lambda" for c in node.named_children)
        return dict(member=name, receiver=receiver, constructor=construct, argument_count=argument_count,
                    receiver_expression=self.expression(receiver_node, depth + 1))

    def call(self, node):
        parts = self.call_parts(node)
        receiver, name = parts["receiver"], parts["member"]
        if name:
            self.references.append(dict(source=self.current, scope_id=self.current,
                kind="calls", name=f"{receiver}.{name}" if receiver else name,
                **parts,
                path=self.path, line=self.line(node.start_byte),
                evidence=" ".join(self.text(node).split())[:240], resolved=False))
        for child in node.named_children:
            self.visit(child)

    def visit(self, node):
        if node.type == "annotated_expression":
            following, count = node.next_named_sibling, 0
            while following and count < 64 and following.type in {
                    "annotated_expression", "line_comment", "block_comment", "multiline_comment"}:
                following, count = following.next_named_sibling, count + 1
            if following and following.type in CLASS_NODES | FUNCTION_NODES:
                if self.annotation_facts(following)["start_byte"] <= node.start_byte:
                    # Recovered annotation arguments are metadata, not executable calls.
                    return
        if node.type == "type_alias":
            name = self.text(node.child_by_field_name("type"))
            if name:
                self.scopes[self.current]["type_aliases"].append(name)
                self.bind(name, reason="unsupported type alias")
            return
        if node.type in CLASS_NODES | FUNCTION_NODES:
            self.declaration(node)
            return
        if node.type in {"property_declaration", "field_declaration", "local_variable_declaration"}:
            self.property(node)
            return
        if node.type in {"call_expression", "method_invocation", "object_creation_expression"}:
            self.call(node)
            return
        # Only verified standard collection lambdas expose lexical element types.
        # Receiver lambdas, loops/catches and anonymous classes remain opaque.
        if node.type in {"lambda_literal", "lambda_expression", "anonymous_function",
                         "object_literal", "enhanced_for_statement", "for_statement",
                         "catch_block", "catch_clause"}:
            previous = self.current
            key = f"{previous}::opaque:{node.start_byte}"
            self.scope(key, previous, "lambda" if node.type == "lambda_literal" else "opaque",
                       self.scopes[previous]["qualname"])
            self.current = key
            if node.type == "lambda_literal":
                outer = node.parent
                if outer and outer.type == "annotated_lambda":
                    outer = outer.parent
                invocation = self.call_parts(outer) if outer and outer.type == "call_expression" else None
                self.scopes[key]["lambda_call"] = invocation
                parameters = _first(node, {"lambda_parameters"})
                if parameters is None:
                    self.bind("it", reason="implicit lambda parameter",
                              expression=dict(kind="element", call=invocation))
                for parameter in parameters.named_children if parameters else []:
                    variables = parameter.named_children if parameter.type == "multi_variable_declaration" else [parameter]
                    for index, variable in enumerate(variables):
                        name = _first(variable, {"identifier"})
                        self.bind(self.text(name), self.normalized(_first(variable, TYPE_NODES)),
                                  reason="lambda parameter", expression=dict(kind="element", call=invocation,
                                      component=index if parameter.type == "multi_variable_declaration" else None))
            for child in node.named_children:
                self.visit(child)
            # References need a real symbol as their graph source.
            for ref in self.references:
                if ref["source"] == key:
                    ref["source"] = previous
            self.current = previous
            return
        for child in node.named_children:
            self.visit(child)


def parse_jvm(path: str, source: str, module: str = "") -> dict[str, Any]:
    """Parse Kotlin/Java text into JSON-safe facts using pinned grammar packages."""
    language = "java" if path.endswith(".java") else "kotlin"
    parser = _Parser(path, source, module, language)
    diagnostics = []
    try:
        from tree_sitter import Language, Parser
        if language == "java":
            import tree_sitter_java as grammar
        else:
            import tree_sitter_kotlin as grammar
        tree = Parser(Language(grammar.language())).parse(source.encode("utf-8"))
        root = tree.root_node
        for node in root.named_children:
            if node.type in {"package_header", "package_declaration"}:
                package_node = _first(node, {"qualified_identifier", "scoped_identifier", "identifier"})
                parser.package = parser.text(package_node)
        parser.scopes[parser.current]["qualname"] = parser.package
        for node in root.named_children:
            if node.type in {"import", "import_declaration"}:
                full_node = _first(node, {"qualified_identifier", "scoped_identifier", "identifier"})
                full_name = parser.text(full_node)
                wildcard = any(c.type in {"*", "asterisk"} for c in node.children)
                alias_node = next((c for c in node.named_children if c.type == "identifier" and c != full_node), None)
                parser.imports.append(dict(id=f"{path}::import:{len(parser.imports)+1}",
                    source=parser.current, scope_id=parser.current, path=path,
                    line=parser.line(node.start_byte), evidence=parser.text(node),
                    module=full_name.rpartition(".")[0], name=full_name.rpartition(".")[2],
                    qualified=full_name, alias=parser.text(alias_node) or full_name.rpartition(".")[2],
                    wildcard=wildcard, static=any(c.type == "static" for c in node.children),
                    level=0, resolved=False))
            elif node.type not in {"package_header", "package_declaration"}:
                parser.visit(node)
        if root.has_error:
            errors = [n for n in _walk(root) if n.type == "ERROR" or n.is_missing]
            diagnostics = [f"Tree-sitter {language} syntax recovery at line {parser.line(n.start_byte)}: {n.type}"
                           for n in errors[:20]] or ["Tree-sitter syntax recovery"]
    except ImportError as exc:
        diagnostics = [f"JVM parser dependency unavailable: {exc.name}; install pinned requirements"]
    except (RecursionError, ValueError) as exc:
        diagnostics = [f"JVM parser failed: {type(exc).__name__}: {exc}"]
    partial = bool(diagnostics)
    for symbol in parser.symbols:
        symbol["partial"] = partial
    return dict(path=path, module=module, language=language, package=parser.package,
                symbols=parser.symbols, references=parser.references, imports=parser.imports,
                diagnostics=diagnostics, partial=partial, _scopes=parser.scopes)


class _Resolver:
    def __init__(self, files):
        self.files = files
        self.by_path = {f["path"]: f for f in files}
        self.symbols = {s["id"]: s for f in files for s in f["symbols"]}
        self.scopes = {k: v for f in files for k, v in f.get("_scopes", {}).items()}
        self.type_aliases = {".".join(filter(None, [scope["qualname"], name]))
                             for scope in self.scopes.values() for name in scope.get("type_aliases", [])}
        self.qualified, self.members = defaultdict(list), defaultdict(list)
        for symbol in self.symbols.values():
            if symbol["kind"] != "module" and not symbol.get("partial") and not symbol.get("local"):
                self.qualified[symbol["qualname"]].append(symbol)
                self.members[(symbol["parent_id"], symbol["name"])].append(symbol)
        self.bases = defaultdict(list)
        for file in files:
            if file.get("partial"):
                continue
            for ref in file["references"]:
                if ref["kind"] == "inherits":
                    bases = self.types(file, ref["member"], ref["scope_id"])
                    if len(bases) == 1:
                        self.bases[ref["source"]].append(bases[0]["id"])

    def binding(self, scope_id, name):
        while scope_id:
            scope = self.scopes[scope_id]
            if scope["kind"] == "opaque":
                return [dict(type="", reason="unsupported scope")]
            if name in scope["bindings"]:
                return scope["bindings"][name]
            scope_id = scope["parent"]
        return None

    def candidates(self, file, name, *, type_only=False):
        # Never search globally by basename. Qualified imports and this package
        # are the only supported visibility paths; wildcard imports stay unknown.
        names = []
        aliases = [i for i in file["imports"] if not i["wildcard"] and i["alias"] == name.split(".")[0]]
        if aliases:
            if len(aliases) != 1:
                return []
            names = [aliases[0]["qualified"] + ("." + name.split(".", 1)[1] if "." in name else "")]
        elif "." in name:
            names = [name, ".".join(filter(None, [file["package"], name]))]
        else:
            if any(i["wildcard"] for i in file["imports"]):
                return []
            names = [".".join(filter(None, [file["package"], name]))]
        candidates = {s["id"]: s for full in names for s in self.qualified.get(full, [])}
        return [s for s in candidates.values() if not type_only or s["kind"] in CLASS_KINDS]

    @staticmethod
    def type_parts(type_name):
        """Erase only well-shaped outer generic arguments, preserving their text."""
        text = type_name.rstrip("?")
        if not text or any(c in text for c in "()[]&"):
            return "", []
        base, opening, tail = text.partition("<")
        if not all(part.isidentifier() for part in base.split(".")):
            return "", []
        if not opening:
            return base, []
        if not tail.endswith(">"):
            return "", []
        args, start, depth = [], 0, 0
        body = tail[:-1]
        for index, char in enumerate(body):
            depth += (char == "<") - (char == ">")
            if depth < 0:
                return "", []
            if char == "," and depth == 0:
                args.append(body[start:index])
                start = index + 1
        return (base, args + [body[start:]]) if depth == 0 else ("", [])

    def types(self, file, type_name, scope_id, seen=frozenset()):
        name, _ = self.type_parts(type_name)
        if not name or (scope_id, name) in seen:
            return []
        current = scope_id
        while current:
            scope = self.scopes.get(current, {})
            params = scope.get("type_parameters", {})
            if name in params:
                bounds = params[name]
                return self.types(file, bounds[0], current, seen | {(scope_id, name)}) if len(bounds) == 1 else []
            if name in scope.get("type_aliases", []):
                return []
            declarations = [self.symbols[b["target"]] for b in scope.get("bindings", {}).get(name, [])
                            if b.get("target") in self.symbols and self.symbols[b["target"]]["kind"] in CLASS_KINDS]
            if declarations:
                return [s for s in declarations if not s.get("partial")]
            current = scope.get("parent")
        if self.type_alias_visible(file, name, scope_id):
            return []
        return self.candidates(file, name, type_only=True)

    def type_alias_visible(self, file, name, scope_id):
        current = scope_id
        while current:
            scope = self.scopes.get(current, {})
            if name in scope.get("type_aliases", []):
                return True
            current = scope.get("parent")
        aliases = [i for i in file["imports"] if not i["wildcard"] and i["alias"] == name.split(".")[0]]
        if aliases:
            suffix = "." + name.split(".", 1)[1] if "." in name else ""
            return any(i["qualified"] + suffix in self.type_aliases for i in aliases)
        return name in self.type_aliases or ".".join(filter(None, [file["package"], name])) in self.type_aliases

    def parameter_identity(self, symbol):
        """Compare declaration types only; never choose applicable overloads."""
        file = self.by_path[symbol["path"]]
        identities = []
        for parameter in symbol.get("parameter_types", []):
            if not all(part.isidentifier() for part in parameter.split(".")):
                return None
            types = self.types(file, parameter, symbol["id"])
            if len(types) == 1:
                identities.append(types[0]["id"])
            elif "." in parameter or (file["language"] == "java" and parameter in {
                    "int", "long", "short", "byte", "float", "double", "char", "boolean"}):
                identities.append(parameter)
            else:
                return None
        return tuple(identities)

    def declared_members(self, owner, member, seen=frozenset()):
        if owner in seen:
            return []
        direct = self.members.get((owner, member), [])
        signatures = {self.parameter_identity(s) for s in direct if s["kind"] in CALLABLE_KINDS}
        signatures.discard(None)
        result = {s["id"]: s for s in direct}
        for base in self.bases.get(owner, []):
            for inherited in self.declared_members(base, member, seen | {owner}):
                if "private" in inherited.get("declaration_modifiers", []) or self.parameter_identity(inherited) in signatures:
                    continue
                if "declaration_modifiers" not in inherited:
                    # Legacy facts still participate in ambiguity checks, but
                    # cannot justify an inherited target with unknown visibility.
                    inherited = dict(inherited, _unknown_inherited_modifiers=True)
                result[inherited["id"]] = inherited
        return list(result.values())

    def standard_collection(self, file, type_name, scope_id):
        name, args = self.type_parts(type_name)
        standard = {"List", "MutableList", "Collection", "Iterable", "Set", "MutableSet", "Map", "MutableMap"}
        simple = name.rsplit(".", 1)[-1]
        if simple not in standard:
            return None
        if self.type_alias_visible(file, name, scope_id):
            return None
        if "." in name:
            return (simple, args) if name == "kotlin.collections." + simple else None
        if self.types(file, name, scope_id) or any(i["wildcard"] or i["alias"] == name for i in file["imports"]):
            return None
        current = scope_id
        while current:
            scope = self.scopes.get(current, {})
            if name in scope.get("type_parameters", {}):
                return None
            current = scope.get("parent")
        return simple, args

    def collection_operation(self, file, member, scope_id):
        current = scope_id
        while current:
            scope = self.scopes.get(current, {})
            if scope.get("kind") in CLASS_KINDS and self.declared_members(current, member):
                return False
            current = scope.get("parent")
        return (file["language"] == "kotlin" and not self.candidates(file, member)
                and self.binding(scope_id, member) is None
                and not any(i["wildcard"] or i["alias"] == member for i in file["imports"]))

    def lambda_element(self, file, call, scope_id, depth, component=None):
        if not call or call["member"] != "forEach" or call.get("argument_count") != 1 or file["language"] != "kotlin":
            return None
        # Unknown or locally provided extension functions may have receiver lambdas.
        if not self.collection_operation(file, "forEach", scope_id):
            return None
        receiver = self.expression_type(file, call.get("receiver_expression"), scope_id, depth + 1)
        if receiver:
            type_name, context, context_scope = receiver
            collection = self.standard_collection(context, type_name, context_scope)
            if collection and collection[0] not in {"Map", "MutableMap"} and len(collection[1]) == 1:
                return (collection[1][0], context, context_scope) if component is None else None
            if collection and collection[0] in {"Map", "MutableMap"} and len(collection[1]) == 2:
                if component in {0, 1}:
                    return collection[1][component], context, context_scope
                if component is None:
                    return "kotlin.collections.Map.Entry<" + ",".join(collection[1]) + ">", context, context_scope
        return None

    def expression_type(self, file, expression, scope_id, depth=0):
        if not expression or depth > 24:
            return None
        kind = expression["kind"]
        if kind == "name":
            name = expression["name"]
            bindings = self.binding(scope_id, name)
            if bindings is not None:
                if len(bindings) != 1:
                    return None
                binding = bindings[0]
                context_scope = binding.get("scope_id", scope_id)
                if binding.get("type"):
                    return binding["type"], file, context_scope
                if binding.get("expression"):
                    return self.expression_type(file, binding["expression"], context_scope, depth + 1)
                target = self.symbols.get(binding.get("target"), {})
                if target.get("kind") in CLASS_KINDS:
                    return target["qualname"], self.by_path[target["path"]], target["id"]
                return None
            types = self.types(file, name, scope_id)
            return (types[0]["qualname"], self.by_path[types[0]["path"]], types[0]["id"]) if len(types) == 1 else None
        if kind == "element":
            return self.lambda_element(file, expression.get("call"), self.scopes[scope_id]["parent"],
                                       depth + 1, expression.get("component"))
        if kind == "index":
            if expression.get("argument_count") != 1 or not self.collection_operation(file, "get", scope_id):
                return None
            receiver = self.expression_type(file, expression.get("receiver"), scope_id, depth + 1)
            if receiver:
                type_name, context, context_scope = receiver
                collection = self.standard_collection(context, type_name, context_scope)
                if collection and collection[0] in {"Map", "MutableMap"} and len(collection[1]) == 2:
                    return collection[1][1], context, context_scope
            return None
        if kind == "property":
            receiver = self.expression_type(file, expression.get("receiver"), scope_id, depth + 1)
            if not receiver:
                return None
            type_name, context, context_scope = receiver
            owners = self.types(context, type_name, context_scope)
            candidates = self.declared_members(owners[0]["id"], expression["member"]) if len(owners) == 1 else []
            if (len(candidates) == 1 and candidates[0].get("declared_type")
                    and not candidates[0].get("_unknown_inherited_modifiers")):
                target = candidates[0]
                return target["declared_type"], self.by_path[target["path"]], target["parent_id"]
            return None
        if kind == "call":
            if (expression["member"] == "groupBy" and expression.get("argument_count") == 1
                    and self.collection_operation(file, "groupBy", scope_id)):
                receiver = self.expression_type(file, expression.get("receiver_expression"), scope_id, depth + 1)
                if receiver:
                    type_name, context, context_scope = receiver
                    collection = self.standard_collection(context, type_name, context_scope)
                    if collection and collection[0] not in {"Map", "MutableMap"} and len(collection[1]) == 1:
                        # The selector's key type is unknown; the declared element
                        # type survives grouping without evaluating the selector.
                        return "kotlin.collections.Map<*,kotlin.collections.List<" + collection[1][0] + ">>", context, context_scope
            reference = dict(expression, kind="calls", scope_id=scope_id)
            target_id, _ = self.resolve(file, reference, depth + 1)
            target = self.symbols.get(target_id, {})
            if target.get("kind") in CLASS_KINDS:
                return target["qualname"], self.by_path[target["path"]], target["id"]
            if target.get("return_type"):
                return target["return_type"], self.by_path[target["path"]], target["id"]
        return None

    def owner(self, scope_id):
        while scope_id:
            scope = self.scopes[scope_id]
            if scope["kind"] in CLASS_KINDS:
                return scope_id
            scope_id = scope["parent"]
        return None

    def resolve(self, file, ref, depth=0):
        if depth > 24:
            return None, "expression type recursion limit"
        if file.get("partial"):
            return None, "syntax recovery: partial file"
        scope_id, member, receiver = ref["scope_id"], ref["member"], ref["receiver"]
        if ref["kind"] == "inherits":
            candidates = self.types(file, member, scope_id)
            return (candidates[0]["id"], "unique declared base; compiler unverified") if len(candidates) == 1 else (
                None, "base type external, generic, ambiguous or unknown")
        scope = self.scopes.get(scope_id, {})
        while scope:
            if scope.get("kind") == "opaque":
                return None, "lambda, loop, catch or anonymous scope unsupported"
            if scope.get("kind") == "lambda" and not self.lambda_element(file, scope.get("lambda_call"), scope.get("parent"), depth + 1):
                return None, "lambda receiver or element type unsupported"
            symbol = self.symbols.get(scope.get("id"), {})
            if symbol.get("receiver_type"):
                return None, "extension receiver dispatch unsupported"
            scope = self.scopes.get(scope.get("parent"), {})
        if receiver:
            if receiver in {"this", "super"}:
                return None, "this or super receiver unsupported"
            expression = ref.get("receiver_expression") or (dict(kind="name", name=receiver) if receiver.isidentifier() else None)
            resolved_type = self.expression_type(file, expression, scope_id, depth + 1)
            if not resolved_type:
                return None, "receiver shadowed, inferred, complex or ambiguous"
            type_name, context, context_scope = resolved_type
            types = self.types(context, type_name, context_scope)
            if len(types) != 1:
                return None, "receiver type external, ambiguous or unknown"
            candidates = self.declared_members(types[0]["id"], member)
        else:
            bindings = self.binding(scope_id, member)
            if bindings is not None:
                if any(not b.get("target") for b in bindings):
                    return None, "callable shadowed by local or parameter"
                candidates = [self.symbols[b["target"]] for b in bindings]
                owner = self.owner(scope_id)
                if owner and all(s["parent_id"] == owner and s["kind"] in CALLABLE_KINDS for s in candidates):
                    candidates = self.declared_members(owner, member)
            else:
                owner = self.owner(scope_id)
                candidates = self.declared_members(owner, member) if owner else []
                if not candidates:
                    candidates = self.candidates(file, member)
        candidates = [s for s in candidates if s["kind"] in CLASS_KINDS | CALLABLE_KINDS]
        if any(s.get("receiver_type") for s in candidates):
            return None, "extension dispatch unsupported"
        if len(candidates) != 1:
            return None, "overloaded, external, ambiguous or unknown declaration"
        target = candidates[0]
        if target.get("_unknown_inherited_modifiers"):
            return None, "inherited declaration modifiers missing; refresh required"
        if target.get("partial"):
            return None, "target file has syntax recovery"
        return target["id"], "unique syntax candidate; runtime dispatch unverified"


def resolve_jvm(parsed_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Relink all JVM facts deterministically; no edge claims semantic exactness."""
    files = [f for f in parsed_files if f.get("language") in {"kotlin", "java"}]
    resolver, edges = _Resolver(files), []
    for file in files:
        for symbol in file["symbols"]:
            if symbol["parent_id"] in resolver.symbols:
                edges.append(dict(source=symbol["parent_id"], target=symbol["id"],
                    kind="contains", confidence="syntactic", evidence=symbol["signature"],
                    path=file["path"], line=symbol["start_line"]))
        for imported in file["imports"]:
            imported.pop("target", None)
            imported["resolved"] = False
            candidates = resolver.qualified.get(imported["qualified"], [])
            if not file.get("partial") and not imported["wildcard"] and len(candidates) == 1:
                imported.update(resolved=True, target=candidates[0]["id"])
                edges.append(dict(source=imported["source"], target=candidates[0]["id"],
                    kind="imports", confidence="syntactic", evidence=imported["evidence"],
                    path=file["path"], line=imported["line"]))
        for ref in file["references"]:
            ref.pop("target", None)
            ref.pop("confidence", None)
            target, reason = resolver.resolve(file, ref)
            ref.update(resolved=bool(target), reason=reason)
            if target:
                ref.update(target=target, confidence="heuristic")
                edges.append(dict(source=ref["source"], target=target, kind=ref["kind"],
                    confidence="heuristic", evidence=ref["evidence"],
                    path=ref["path"], line=ref["line"]))
    unique = {tuple(e[k] for k in ("source", "target", "kind", "path", "line")): e for e in edges}
    return sorted(unique.values(), key=lambda e: (e["path"], e["line"], e["kind"], e["source"], e["target"]))
