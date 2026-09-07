"""Tree-sitter JVM navigation facts, never compiler or runtime equivalence.

No builds, annotation processors, class loading or LLM calls. Explicitly typed
receivers may point to a declared member with heuristic confidence. Overloads,
inheritance, inferred types, extension dispatch, implicit lambda receivers and
this/super dispatch are deliberately unresolved. Block locals are conservatively
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


# Method invocation permits primitive identity/widening, not constant narrowing.
_PRIMITIVE_WIDENING = {
    "boolean": {"boolean"}, "byte": {"byte", "short", "int", "long", "float", "double"},
    "short": {"short", "int", "long", "float", "double"},
    "char": {"char", "int", "long", "float", "double"},
    "int": {"int", "long", "float", "double"}, "long": {"long", "float", "double"},
    "float": {"float", "double"}, "double": {"double"},
}


def _literal_argument_type(kind, text):
    if kind in {"true", "false"}:
        return "boolean"
    if kind == "null_literal":
        return "null"
    if kind == "string_literal":
        return "reference_literal"
    if kind == "character_literal":
        return "char"
    if kind == "decimal_integer_literal":
        value = text.replace("_", "")
        is_long = value.endswith(("l", "L"))
        digits = value[:-1] if is_long else value
        significant = digits.lstrip("0") or "0"
        if digits.isdecimal() and len(significant) <= 19 and int(significant) <= (2**63 - 1 if is_long else 2**31 - 1):
            return "long" if is_long else "int"
    if kind == "decimal_floating_point_literal":
        return "float" if text.endswith(("f", "F")) else "double"
    return None


class _Parser:
    def __init__(self, path, source, module, language):
        self.path, self.source = path, source.encode("utf-8")
        self.module, self.language, self.package = module, language, ""
        # Avoid native Point properties: tree-sitter 0.26.0 row/column getters
        # return borrowed references. Byte offsets also preserve UTF-8 spans.
        self.line_starts = [0] + [i + 1 for i, byte in enumerate(self.source) if byte == 10]
        self.symbols, self.references, self.imports = [], [], []
        self.scopes, self.counts = {}, defaultdict(int)
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
                                qualname=qualname, bindings={}, type_bindings={})

    def bind(self, name, type_text="", *, reason="local", target=None):
        if name:
            self.scopes[self.current]["bindings"].setdefault(name, []).append(
                dict(type=type_text, reason=reason, target=target))

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
        mods = _first(node, {"modifiers"})
        return [self.text(n)[:300] for n in _walk(mods)
                if n.type in {"annotation", "marker_annotation"}] if mods else []

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
        signature = " ".join(self.source[node.start_byte:header_end].decode().split())[:600]
        previous = node.prev_named_sibling
        doc = self.text(previous) if previous and previous.type in {"block_comment", "multiline_comment"} else ""
        symbol = dict(id=key, path=self.path, module=self.module, name=name,
            qualname=qualname, kind=kind, start_line=self.line(node.start_byte),
            end_line=self.line(node.end_byte), signature=signature, doc=doc[:3000],
            parent_id=self.current, language=self.language, package=self.package,
            parameter_types=[p["signature"] for p in params], receiver_type=receiver,
            annotations=self.annotations(node), local=parent["kind"] in CALLABLE_KINDS)
        if self.language == "java":
            modifiers = _first(node, {"modifiers"})
            symbol["modifiers"] = sorted(self.text(child) for child in modifiers.children
                                         if child.type not in {"annotation", "marker_annotation"}) if modifiers else []
        self.symbols.append(symbol)
        self.bind(name, reason="declaration", target=key)
        if is_class:
            self.scopes[self.current]["type_bindings"].setdefault(name, []).append(
                dict(reason="declaration", target=key))
        previous_scope = self.current
        self.scope(key, previous_scope, kind, qualname)
        self.current = key
        type_parameters = node.child_by_field_name("type_parameters") or _first(node, {"type_parameters"})
        for parameter in type_parameters.named_children if type_parameters else []:
            if parameter.type == "type_parameter":
                identifier = parameter.child_by_field_name("name") or _first(parameter, {"type_identifier", "identifier"})
                self.scopes[key]["type_bindings"].setdefault(self.text(identifier), []).append(
                    dict(reason="type parameter", target=None, declaration=self.text(parameter)))
        for parameter in params:
            self.bind(parameter["name"], parameter["type"], reason="parameter")
        if is_class:
            self.inheritance(node)
            primary = _first(node, {"primary_constructor"})
            for item in _walk(primary) if primary else []:
                if item.type == "class_parameter" and any(c.type in {"val", "var"} for c in item.children):
                    property_name = self.text(_first(item, {"identifier"}))
                    property_type = self.normalized(_first(item, TYPE_NODES))
                    self.symbols.append(dict(id=f"{key}.{property_name}:property", path=self.path,
                        module=self.module, name=property_name, qualname=f"{qualname}.{property_name}",
                        kind="property", start_line=self.line(item.start_byte),
                        end_line=self.line(item.end_byte), signature=self.text(item), doc="",
                        parent_id=key, language=self.language, package=self.package,
                        declared_type=property_type, annotations=self.annotations(item)))
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
            self.bind(name, value_type, reason="variable")
            scope = self.scopes[self.current]
            if scope["kind"] in CLASS_KINDS | {"module"}:
                qualname = ".".join(filter(None, [scope["qualname"], name]))
                base = f"{self.path}::{qualname}:property"
                self.counts[base] += 1
                key = base + (f"#duplicate{self.counts[base]}" if self.counts[base] > 1 else "")
                self.symbols.append(dict(id=key, path=self.path, module=self.module,
                    name=name, qualname=qualname, kind="property",
                    start_line=self.line(node.start_byte), end_line=self.line(node.end_byte),
                    signature=f"{name}: {value_type or '<inferred>'}", doc="",
                    parent_id=self.current, language=self.language, package=self.package,
                    declared_type=value_type, annotations=self.annotations(node)))
        for child in node.named_children:
            self.visit(child)

    def static_initialization(self, node):
        if self.language != "java":
            return False
        parent = node.parent
        while parent and parent.type not in CLASS_NODES | FUNCTION_NODES:
            if parent.type in {"static_initializer", "constant_declaration"}:
                return True
            if parent.type == "field_declaration":
                modifiers = _first(parent, {"modifiers"})
                if modifiers and any(child.type == "static" for child in modifiers.children):
                    return True
                owner = parent.parent
                while owner and owner.type not in CLASS_NODES:
                    owner = owner.parent
                return bool(owner and owner.type in {"interface_declaration", "annotation_type_declaration"})
            parent = parent.parent
        return False

    def call(self, node):
        receiver, name, construct = "", "", False
        if node.type == "method_invocation":
            name = self.text(node.child_by_field_name("name"))
            receiver = self.text(node.child_by_field_name("object"))
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
        arguments = node.child_by_field_name("arguments") if self.language == "java" else None
        argument_count = (len([child for child in arguments.named_children
                               if child.type not in {"line_comment", "block_comment"}])
                          if arguments is not None else None)
        argument_types = ([_literal_argument_type(child.type, self.text(child))
                           for child in arguments.named_children
                           if child.type not in {"line_comment", "block_comment"}]
                          if arguments is not None else [])
        if name:
            self.references.append(dict(source=self.current, scope_id=self.current,
                kind="calls", name=f"{receiver}.{name}" if receiver else name,
                member=name, receiver=receiver, constructor=construct, argument_count=argument_count, argument_types=argument_types,
                static_context=self.static_initialization(node),
                path=self.path, line=self.line(node.start_byte),
                evidence=" ".join(self.text(node).split())[:240], resolved=False))
        for child in node.named_children:
            self.visit(child)

    def visit(self, node):
        if node.type in CLASS_NODES | FUNCTION_NODES:
            self.declaration(node)
            return
        if node.type in {"property_declaration", "field_declaration", "local_variable_declaration"}:
            self.property(node)
            return
        if node.type in {"call_expression", "method_invocation", "object_creation_expression"}:
            self.call(node)
            return
        # Receiver lambdas, anonymous classes and loop/catch bindings need scopes
        # beyond this v1 extractor; retain calls as unresolved in an opaque scope.
        if node.type in {"lambda_literal", "lambda_expression", "anonymous_function",
                         "object_literal", "enhanced_for_statement", "for_statement",
                         "catch_block", "catch_clause"}:
            previous = self.current
            key = f"{previous}::opaque:{node.start_byte}"
            self.scope(key, previous, "opaque", self.scopes[previous]["qualname"])
            self.current = key
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
        self.symbols = {s["id"]: s for f in files for s in f["symbols"]}
        self.scopes = {k: v for f in files for k, v in f.get("_scopes", {}).items()}
        self.inherited_owners = {r["source"] for f in files for r in f["references"] if r["kind"] == "inherits"}
        self.qualified, self.members = defaultdict(list), defaultdict(list)
        for symbol in self.symbols.values():
            if symbol["kind"] != "module" and not symbol.get("partial") and not symbol.get("local"):
                self.qualified[symbol["qualname"]].append(symbol)
                self.members[(symbol["parent_id"], symbol["name"])].append(symbol)

    def binding(self, scope_id, name):
        while scope_id:
            scope = self.scopes[scope_id]
            if scope["kind"] == "opaque":
                return [dict(type="", reason="unsupported scope")]
            if name in scope["bindings"]:
                return scope["bindings"][name]
            scope_id = scope["parent"]
        return None

    def type_binding(self, scope_id, name):
        while scope_id:
            scope = self.scopes[scope_id]
            bindings = scope.get("type_bindings", {}).get(name)
            if bindings is not None:
                return bindings
            scope_id = scope["parent"]
        return None

    def candidates(self, file, name, *, type_only=False, scope_id=None):
        if type_only and scope_id:
            bindings = self.type_binding(scope_id, name.split(".")[0])
            if bindings is not None:
                if len(bindings) != 1 or not bindings[0].get("target"):
                    return []
                target = self.symbols[bindings[0]["target"]]
                if "." not in name:
                    return [target]
                return self.qualified.get(target["qualname"] + "." + name.split(".", 1)[1], [])
        # Never search globally by basename. Qualified imports and this package
        # are the only supported visibility paths; wildcard imports stay unknown.
        if any(i["wildcard"] for i in file["imports"]):
            return []
        names = []
        aliases = [i for i in file["imports"] if i["alias"] == name.split(".")[0]]
        if aliases:
            if len(aliases) != 1:
                return []
            names = [aliases[0]["qualified"] + ("." + name.split(".", 1)[1] if "." in name else "")]
        elif "." in name:
            names = [name, ".".join(filter(None, [file["package"], name]))]
        else:
            names = [".".join(filter(None, [file["package"], name]))]
        candidates = {s["id"]: s for full in names for s in self.qualified.get(full, [])}
        return [s for s in candidates.values() if not type_only or s["kind"] in CLASS_KINDS]

    def owner(self, scope_id):
        while scope_id:
            scope = self.scopes[scope_id]
            if scope["kind"] in CLASS_KINDS:
                return scope_id
            scope_id = scope["parent"]
        return None

    def enclosing_type(self, scope_id):
        """The top-level Java declaration defines private nestmate access."""
        outer = None
        while scope_id:
            scope = self.scopes[scope_id]
            if scope["kind"] in CLASS_KINDS:
                outer = scope_id
            scope_id = scope["parent"]
        return outer

    def java_access_reason(self, file, scope_id, target):
        """Check the declaration and enclosing types without inventing subtype access."""
        declaration = target
        while declaration and declaration.get("kind") != "module":
            modifiers = declaration.get("modifiers", [])
            parent = self.symbols.get(declaration.get("parent_id"), {})
            if "private" in modifiers:
                if self.enclosing_type(scope_id) != self.enclosing_type(declaration.get("parent_id")):
                    return "private declaration outside the enclosing top-level type"
            elif ("public" not in modifiers and parent.get("kind") != "interface"
                  and file.get("package", "") != declaration.get("package", "")):
                if "protected" in modifiers:
                    return "protected declaration across packages requires subtype and receiver analysis"
                return "package-private declaration outside its package"
            declaration = parent
        return None

    def implicit_instance(self, scope_id, owner):
        while scope_id:
            if scope_id == owner:
                return True
            symbol = self.symbols.get(scope_id, {})
            parent = self.symbols.get(symbol.get("parent_id"), {})
            if ("static" in symbol.get("modifiers", [])
                    or symbol.get("kind") in {"interface", "enum", "record"}
                    or (symbol.get("kind") in CLASS_KINDS and parent.get("kind") == "interface")):
                return False
            scope_id = self.scopes[scope_id]["parent"]
        return False

    def resolve(self, file, ref):
        if file.get("partial"):
            return None, "syntax recovery: partial file"
        scope_id, member, receiver = ref["scope_id"], ref["member"], ref["receiver"]
        if ref["kind"] == "inherits":
            candidates = self.candidates(file, member, type_only=True, scope_id=scope_id)
            if len(candidates) != 1:
                return None, "base type external, generic, ambiguous or unknown"
            if file["language"] == "java" and candidates[0].get("language") == "java":
                access_reason = self.java_access_reason(file, scope_id, candidates[0])
                if access_reason:
                    return None, access_reason
            return candidates[0]["id"], "unique declared base; compiler unverified"
        scope = self.scopes.get(scope_id, {})
        while scope:
            if scope.get("kind") == "opaque":
                return None, "lambda, loop, catch or anonymous scope unsupported"
            symbol = self.symbols.get(scope.get("id"), {})
            if symbol.get("receiver_type"):
                return None, "extension receiver dispatch unsupported"
            scope = self.scopes.get(scope.get("parent"), {})
        if receiver:
            if not receiver.isidentifier() or receiver in {"this", "super"}:
                return None, "complex, this or super receiver unsupported"
            bindings = self.binding(scope_id, receiver)
            if bindings is not None:
                if len(bindings) != 1 or not bindings[0].get("type"):
                    return None, "receiver shadowed, inferred or ambiguous"
                type_name = bindings[0]["type"]
                # Generics and nullable syntax are not type resolution.
                if any(char in type_name for char in "<>()[]?*"):
                    return None, "receiver type requires semantic analysis"
                type_bindings = self.type_binding(scope_id, type_name.split(".")[0])
                if type_bindings and any(b["reason"] == "type parameter" for b in type_bindings):
                    return None, "type parameter receiver: bound and applicability analysis required"
                types = self.candidates(file, type_name, type_only=True, scope_id=scope_id)
            else:
                types = self.candidates(file, receiver, type_only=True, scope_id=scope_id)
            if len(types) != 1:
                return None, "receiver type external, ambiguous or unknown"
            if types[0]["id"] in self.inherited_owners:
                return None, "inherited candidate set and argument applicability required"
            candidates = self.members.get((types[0]["id"], member), [])
        else:
            if not ref["constructor"] and self.owner(scope_id) in self.inherited_owners:
                return None, "inherited candidate set and argument applicability required"
            bindings = self.binding(scope_id, member)
            if bindings is not None:
                if any(not b.get("target") for b in bindings):
                    return None, "callable shadowed by local or parameter"
                candidates = [self.symbols[b["target"]] for b in bindings]
            else:
                candidates = self.candidates(file, member)
        candidates = [s for s in candidates if s["kind"] in CLASS_KINDS | CALLABLE_KINDS]
        if any(s.get("receiver_type") for s in candidates):
            return None, "extension dispatch unsupported"
        if len(candidates) != 1:
            return None, "overloaded, external, ambiguous or unknown declaration"
        target = candidates[0]
        if file["language"] == "java" and target.get("language") == "java":
            target_owner = self.owner(target.get("parent_id"))
            access_reason = self.java_access_reason(file, scope_id, target)
            if access_reason:
                return None, access_reason
            if (target["kind"] == "method" and not receiver
                    and "static" not in target.get("modifiers", [])
                    and (ref.get("static_context") or not self.implicit_instance(scope_id, target_owner))):
                return None, "instance method requires an enclosing instance in this context"
        if (file["language"] == "java" and target.get("language") == "java"
                and target["kind"] in CALLABLE_KINDS and ref.get("argument_count") is not None):
            parameters = target.get("parameter_types", [])
            varargs = bool(parameters and parameters[-1].endswith("..."))
            count = ref["argument_count"]
            if (varargs and count < len(parameters) - 1) or (not varargs and count != len(parameters)):
                return None, "argument count incompatible with declared parameters"
            for number, actual in enumerate(ref.get("argument_types", [])):
                parameter = parameters[min(number, len(parameters) - 1)] if parameters else ""
                expected = parameter.removesuffix("...") if varargs else parameter
                # A lone null in the final position may denote the varargs array.
                if varargs and actual == "null" and number == len(parameters) - 1 and count == len(parameters):
                    continue
                # Boxing a primitive or a String literal cannot produce an array.
                # Null and unknown expressions may still denote an array value.
                if expected.endswith("[]") and (actual in _PRIMITIVE_WIDENING or actual == "reference_literal"):
                    return None, "literal argument incompatible with array parameter"
                if (expected in _PRIMITIVE_WIDENING and actual is not None
                        and expected not in _PRIMITIVE_WIDENING.get(actual, set())):
                    return None, "literal argument incompatible with primitive parameter"
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
