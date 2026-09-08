"""Tree-sitter JVM navigation facts, never compiler or runtime equivalence.

No builds, annotation processors, class loading or LLM calls. Explicitly typed
receivers may point to a declared member with heuristic confidence. Overloads,
inheritance, inferred types, extension dispatch, implicit lambda receivers and
this/super dispatch are deliberately unresolved. Block locals are conservatively
collected at function scope: shadowing can suppress a valid edge, never justify it.
"""
from __future__ import annotations

import re

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
            if not is_class:
                symbol["return_type"] = self.normalized(node.child_by_field_name("type"))
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
        if "return_type" in symbol:
            self.scopes[key]["return_type"] = symbol["return_type"]
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

    def assignment_type(self, assignment):
        left = assignment.child_by_field_name("left")
        if left is None or left.type != "identifier":
            return ""
        name = self.text(left)
        ancestor = assignment.parent
        while ancestor:
            if ancestor.type == "block":
                # Only declarations in an enclosing block can bind this name.
                # The extractor's function bindings also include completed sibling blocks.
                for declaration in reversed(ancestor.named_children):
                    if declaration.start_byte >= assignment.start_byte or declaration.type != "local_variable_declaration":
                        continue
                    for variable in _children(declaration, {"variable_declarator"}):
                        if self.text(variable.child_by_field_name("name")) == name:
                            return (self.normalized(declaration.child_by_field_name("type"))
                                    + self.normalized(variable.child_by_field_name("dimensions")))
            if ancestor.type in FUNCTION_NODES:
                parameters = ancestor.child_by_field_name("parameters")
                for parameter in parameters.named_children if parameters else []:
                    variable = _first(parameter, {"variable_declarator"})
                    identifier = parameter.child_by_field_name("name") or (variable.child_by_field_name("name") if variable else None)
                    if self.text(identifier) == name:
                        return (self.normalized(parameter.child_by_field_name("type") or _first(parameter, TYPE_NODES))
                                + self.normalized(parameter.child_by_field_name("dimensions"))
                                + ("[]" if parameter.type == "spread_parameter" else ""))
                return ""  # Field/inherited member lookup needs declaration-scope typing.
            if ancestor.type in CLASS_NODES:
                return ""
            ancestor = ancestor.parent
        return ""

    def invocation_context(self, node):
        parent = node.parent
        while parent:
            if parent.type == "parenthesized_expression":
                node, parent = parent, parent.parent
            elif self.language == "java" and parent.type == "ternary_expression" and node in (
                    parent.child_by_field_name("consequence"), parent.child_by_field_name("alternative")):
                node, parent = parent, parent.parent
            else:
                break
        if (self.language == "java" and parent and parent.type == "assignment_expression"
                and node == parent.child_by_field_name("right")
                and self.text(parent.child_by_field_name("operator")) == "="):
            return self.assignment_type(parent)
        if parent and parent.type == "variable_declarator" and parent.parent:
            return self.normalized(parent.parent.child_by_field_name("type"))
        if parent and parent.type == "return_statement":
            scope = self.scopes[self.current]
            while scope:
                if "return_type" in scope:
                    return scope["return_type"]
                scope = self.scopes.get(scope["parent"])
        return ""

    def argument_fact(self, node):
        if node.type == 'array_creation_expression':
            dimensions = sum(1 if c.type == 'dimensions_expr' else
                             sum(part.type == '[' for part in c.children)
                             for c in node.named_children if c.type in {'dimensions_expr', 'dimensions'})
            if dimensions:
                return {'kind': 'new', 'type': self.normalized(node.child_by_field_name('type')) + '[]' * dimensions}
        if node.type == "identifier":
            return {"kind": "name", "name": self.text(node)}
        if node.type in {"class_literal", "object_creation_expression"}:
            type_node = node.child_by_field_name("type") or _first(node, TYPE_NODES)
            return {"kind": "class_literal" if node.type == "class_literal" else "new",
                    "type": self.normalized(type_node)}
        if node.type == "method_invocation" and self.text(node.child_by_field_name("name")) == "valueOf":
            receiver = self.text(node.child_by_field_name("object"))
            args = node.child_by_field_name("arguments")
            values = [_literal_argument_type(n.type, self.text(n)) for n in args.named_children
                      if n.type not in {"line_comment", "block_comment"}] if args else []
            if receiver and len(values) == 1 and values[0] is not None:
                return {"kind": "value_of", "receiver": receiver, "literal": values[0]}
        return {}

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
                argument_facts=[self.argument_fact(n) for n in arguments.named_children
                                if n.type not in {"line_comment", "block_comment"}] if arguments else [],
                expected_type=self.invocation_context(node),
                explicit_type_arguments=bool(node.child_by_field_name("type_arguments") or _first(node, {"type_arguments"})),
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
        # Receiver lambdas, anonymous classes and unsupported bindings stay opaque.
        # Array loops have explicit bindings guarded by the resolver.
        if node.type in {"lambda_literal", "lambda_expression", "anonymous_function",
                         "object_literal", "enhanced_for_statement", "for_statement",
                         "catch_block", "catch_clause"}:
            # The iterable is evaluated before the Java loop binding exists.
            # Loop bindings are validated independently before resolving body calls.
            iterable = (node.child_by_field_name("value")
                        if self.language == "java" and node.type == "enhanced_for_statement" else None)
            if iterable is not None:
                self.visit(iterable)
            previous = self.current
            loop = self.language == "java" and node.type == "enhanced_for_statement"
            kind = "array_loop" if loop else "opaque"
            key = f"{previous}::{kind}:{node.start_byte}"
            self.scope(key, previous, kind, self.scopes[previous]["qualname"])
            self.current = key
            if loop:
                name = self.text(node.child_by_field_name("name"))
                declared = self.normalized(node.child_by_field_name("type"))
                declared += self.normalized(node.child_by_field_name("dimensions"))
                self.bind(name, declared, reason="loop variable")
                self.scopes[key]["loop_variable"] = name
                self.scopes[key]["iterable_fact"] = self.argument_fact(iterable) if iterable else {}
            for child in node.named_children:
                if child != iterable:
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
        self.files_by_path = {f["path"]: f for f in files}
        self.declared_type_names = {s["qualname"] for f in files for s in f["symbols"] if s["kind"] in CLASS_KINDS}
        self.symbols = {s["id"]: s for f in files for s in f["symbols"]}
        self.scopes = {k: v for f in files for k, v in f.get("_scopes", {}).items()}
        self.scope_files = {k: f for f in files for k in f.get("_scopes", {})}
        self.inherited_owners = {r["source"] for f in files for r in f["references"] if r["kind"] == "inherits"}
        self.base_references = defaultdict(list)
        for file in files:
            for ref in file["references"]:
                if ref["kind"] == "inherits":
                    self.base_references[ref["source"]].append((file, ref))
        self.inherited_absence = {}
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
                bindings = scope["bindings"][name]
                if (scope["kind"] == "array_loop" and len(bindings) == 1
                        and bindings[0].get("reason") == "loop variable" and bindings[0].get("type") == "var"):
                    array = self.loop_element_binding(scope)
                    if array:
                        return [dict(bindings[0], type=array["element_type"])]
                return bindings
            scope_id = scope["parent"]
        return None

    def loop_element_binding(self, scope):
        fact = scope.get("iterable_fact", {})
        bindings = self.binding(scope["parent"], fact.get("name", "")) if fact.get("kind") == "name" else None
        if not bindings or len(bindings) != 1 or bindings[0].get("reason") not in {"parameter", "loop variable"}:
            return None
        declared = bindings[0].get("type", "")
        if declared.endswith("[]"):
            element = declared[:-2]
        else:
            match = re.fullmatch(r"([\w.$]+)<([\w.$]+(?:\[\])*)>", declared)
            if not match:
                return None
            file = self.scope_files[scope["id"]]
            identity = self.reference_type_name(file, scope["parent"], match[1])
            if identity not in {"java.lang.Iterable", "java.util.Collection", "java.util.List", "java.util.Set"}:
                return None
            element = match[2]
        if bindings[0]["reason"] == "parameter":
            origin = self.scopes.get(scope["parent"], {})
            while origin and fact["name"] not in origin["bindings"]:
                origin = self.scopes.get(origin["parent"], {})
            for type_name in re.findall(r"[A-Za-z_$][\w.$]*", declared):
                for binding in origin.get("type_bindings", {}).get(type_name.split('.')[0], []):
                    target = self.symbols.get(binding.get("target"), {})
                    if target.get("parent_id") == origin.get("id"):
                        return None  # A body-local class cannot type a formal parameter.
        return dict(bindings[0], element_type=element)

    def loop_reason(self, file, scope):
        """Require a known iterable element identity before using loop bindings."""
        name = scope.get("loop_variable")
        outer = self.scopes.get(scope["parent"], {})
        while outer and outer["kind"] not in CLASS_KINDS | {"module"}:
            if name in outer["bindings"]:
                return "loop variable conflicts with an enclosing local"
            outer = self.scopes.get(outer["parent"], {})
        array = self.loop_element_binding(scope)
        if array is None:
            return "loop iterable element type unsupported"
        own = scope["bindings"].get(name, [])
        if len(own) != 1:
            return "ambiguous loop variable"
        element = self.reference_type_name(file, scope["parent"], array["element_type"])
        declared_type = array["element_type"] if own[0]["type"] == "var" else own[0]["type"]
        declared = self.reference_type_name(file, scope["id"], declared_type)
        if not element or not declared or element != declared:
            return "loop element assignment unsupported or incompatible"
        return None

    def inherited_member_absent(self, owner, member, visiting=frozenset()):
        """Prove a name absent from every explicit base before local lookup.

        This does not select inherited overloads or collapse overrides. Unknown,
        partial, generic and cyclic base chains retain the conservative gate.
        """
        key = (owner, member)
        if owner in visiting:
            return False
        if key in self.inherited_absence:
            return self.inherited_absence[key]
        absent = True
        for file, ref in self.base_references.get(owner, []):
            bases = self.candidates(file, ref["member"], type_only=True, scope_id=ref["scope_id"])
            if len(bases) != 1 or bases[0].get("language") != "java":
                absent = False
                break
            base = bases[0]
            if (self.java_access_reason(file, ref["scope_id"], base)
                    or self.members.get((base["id"], member))
                    or not self.inherited_member_absent(base["id"], member, visiting | {owner})):
                absent = False
                break
        self.inherited_absence[key] = absent
        return absent

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

    def reference_type_name(self, file, scope_id, name):
        """Resolve identity only; no generic erasure or basename matching."""
        if (name or '').endswith('[]'):
            component = name[:-2]
            identity = ('primitive:' + component if component in _PRIMITIVE_WIDENING
                        else self.reference_type_name(file, scope_id, component))
            return 'array:' + identity if identity else None
        if not re.fullmatch(r"[A-Za-z_$][\w.$]*", name or ""):
            return None
        primitive_boxes = {"int": "Integer", "long": "Long", "short": "Short", "byte": "Byte",
                           "float": "Float", "double": "Double", "char": "Character", "boolean": "Boolean"}
        if name in primitive_boxes:
            return "java.lang." + primitive_boxes[name]
        bindings = self.type_binding(scope_id, name.split(".")[0])
        if bindings is not None:
            if len(bindings) != 1 or not bindings[0].get("target"):
                return None
        candidates = self.candidates(file, name, type_only=True, scope_id=scope_id)
        if len(candidates) == 1:
            return "source:" + candidates[0]["id"]
        if candidates or any(i["wildcard"] for i in file["imports"]):
            return None
        aliases = [i for i in file["imports"] if i["alias"] == name.split(".")[0]]
        if aliases:
            return aliases[0]["qualified"] + name[len(aliases[0]["alias"]):] if len(aliases) == 1 else None
        if "." in name:
            return name
        local_name = ".".join(filter(None, [file["package"], name]))
        if local_name in self.declared_type_names:
            return None
        if name in {"Object", "String", "Class", "CharSequence", "Number", "Comparable", "Cloneable", *primitive_boxes.values()}:
            return "java.lang." + name
        return None

    @staticmethod
    def reference_assignable(actual, expected):
        if actual == "null" or actual == expected or expected == "java.lang.Object":
            return True
        if actual.startswith('array:'):
            if expected in {'java.lang.Cloneable', 'java.io.Serializable'}:
                return True
            if expected.startswith('array:'):
                left, right = actual[6:], expected[6:]
                if left.startswith('primitive:') or right.startswith('primitive:'):
                    return False
                return _Resolver.reference_assignable(left, right)
        if actual == "java.lang.String" and expected in {"java.lang.CharSequence", "java.lang.Comparable", "java.io.Serializable"}:
            return True
        wrappers = {"java.lang." + n for n in ("Boolean", "Byte", "Short", "Integer", "Long", "Float", "Double", "Character")}
        if actual in wrappers:
            return expected in {"java.lang.Comparable", "java.io.Serializable"} or (expected == "java.lang.Number" and actual not in {"java.lang.Boolean", "java.lang.Character"})
        return False

    def argument_reference_type(self, file, ref, literal, fact):
        if literal == "null":
            return "null"
        if literal == "reference_literal":
            return "java.lang.String"
        if literal in _PRIMITIVE_WIDENING:
            return self.reference_type_name(file, ref["scope_id"], literal)
        if fact.get("kind") == "name":
            bindings = self.binding(ref["scope_id"], fact["name"])
            if bindings is None or len(bindings) != 1:
                return None
            return self.reference_type_name(file, ref["scope_id"], bindings[0].get("type", ""))
        if fact.get("kind") == "new":
            return self.reference_type_name(file, ref["scope_id"], fact["type"])
        if fact.get("kind") == "value_of":
            receiver = fact["receiver"]
            if self.binding(ref["scope_id"], receiver.split(".")[0]) is not None:
                return None
            owner = self.reference_type_name(file, ref["scope_id"], receiver)
            value = fact["literal"]
            if owner == "java.lang.String" and value != "null":
                return owner
            primitives = {"java.lang." + n: p for p,n in {"int":"Integer", "long":"Long", "short":"Short", "byte":"Byte", "float":"Float", "double":"Double", "char":"Character", "boolean":"Boolean"}.items()}
            if owner in primitives and (primitives[owner] in _PRIMITIVE_WIDENING.get(value, set())
                    or (value == "reference_literal" and owner != "java.lang.Character")):
                return owner
        return None

    def generic_argument_check(self, file, ref, target, parameters):
        target_scope = self.scopes.get(target["id"], {})
        returned = target.get("return_type", "")
        constrained_types = [*parameters, returned]
        variables = {name: bindings for name, bindings in target_scope.get("type_bindings", {}).items()
                     if any(b.get("reason") == "type parameter" for b in bindings)}
        scope, shadowed = target_scope, set(variables)
        while scope:
            for name, bindings in scope.get("type_bindings", {}).items():
                if name not in shadowed and any(b.get("reason") == "type parameter" for b in bindings):
                    if any(re.search(r"\b" + re.escape(name) + r"\b", p) for p in constrained_types):
                        return set(), "generic declaring-type substitution requires semantic analysis"
                shadowed.add(name)
            scope = self.scopes.get(scope.get("parent"))
        if not variables:
            return set(), None
        used = {v for v in variables if any(re.search(r"\b" + re.escape(v) + r"\b", p) for p in constrained_types)}
        if not used:
            return set(), None
        if ref.get("explicit_type_arguments") or any(len(variables[v]) != 1 or variables[v][0].get("declaration") != v for v in used):
            return set(), "generic bounds or explicit type arguments require semantic analysis"
        target_file = self.files_by_path[target["path"]]
        facts = ref.get("argument_facts", [])
        literals = ref.get("argument_types", [])
        if len(facts) != len(literals):
            return set(), "generic argument facts unavailable"
        anchors, values, handled = {}, [], set()
        array_vararg_index = None
        for i,(literal,fact) in enumerate(zip(literals,facts)):
            parameter = parameters[min(i,len(parameters)-1)].removesuffix("...")
            if parameter in used:
                actual = self.argument_reference_type(file,ref,literal,fact)
                if actual is None:
                    return set(), "generic value type requires semantic analysis"
                values.append((parameter,actual));handled.add(i)
                if (i == len(parameters) - 1 and len(facts) == len(parameters)
                        and parameters[-1].endswith('...') and actual.startswith('array:')
                        and not actual[6:].startswith('primitive:')):
                    array_vararg_index = len(values) - 1
                continue
            match = re.fullmatch(r"([\w.$]+)<([\w$]+)>",parameter)
            if match and match[2] in used:
                formal = self.reference_type_name(target_file,target["id"],match[1])
                if formal == "java.lang.Class" and fact.get("kind") == "class_literal":
                    concrete = self.reference_type_name(file,ref["scope_id"],fact["type"])
                else:
                    actual_type = fact.get("type", "") if fact.get("kind") == "new" else ""
                    if fact.get("kind") == "name":
                        bindings = self.binding(ref["scope_id"],fact["name"])
                        if bindings and len(bindings)==1:
                            actual_type = bindings[0].get("type", "")
                    actual = re.fullmatch(r"([\w.$]+)<([\w.$]+)>", actual_type)
                    if not actual or not formal or formal != self.reference_type_name(file,ref["scope_id"],actual[1]):
                        return set(), "generic invariant argument requires semantic analysis"
                    concrete = self.reference_type_name(file,ref["scope_id"],actual[2])
                if concrete is None or (match[2] in anchors and anchors[match[2]] != concrete):
                    return set(), "generic invariant type constraints conflict or are unknown"
                anchors[match[2]]=concrete;handled.add(i)
            elif any(re.search(r"\b"+re.escape(v)+r"\b",parameter) for v in used):
                return set(), "generic parameter shape requires semantic analysis"
        # An applicable fixed-arity array argument wins before target-type inference.
        # Primitive components cannot instantiate T, so primitive arrays stay values.
        if array_vararg_index is not None:
            variable, actual = values[array_vararg_index]
            component = actual[6:]
            if variable not in anchors or self.reference_assignable(component, anchors[variable]):
                values[array_vararg_index] = (variable, component)
        context = ref.get("expected_type", "")
        if context and context != "var":
            for variable in used:
                if returned not in {variable, variable + "[]"}:
                    continue
                expected = context
                if returned.endswith("[]"):
                    if self.reference_type_name(file, ref["scope_id"], context) in {
                            "java.lang.Object", "java.lang.Cloneable", "java.io.Serializable"}:
                        continue
                    if not context.endswith("[]"):
                        return set(), "generic array result context requires semantic analysis"
                    expected = context[:-2]
                upper = self.reference_type_name(file, ref["scope_id"], expected)
                actuals = [anchors[variable]] if variable in anchors else [a for v,a in values if v == variable]
                if upper is None or any(not self.reference_assignable(a,upper) for a in actuals):
                    return set(), "generic result context incompatible or unverified"
        for variable,actual in values:
            if variable in anchors and not self.reference_assignable(actual,anchors[variable]):
                return set(), "generic argument type constraints incompatible or unverified"
        return handled, None

    def literal_reference_compatible(self, target, expected, actual):
        """Known String/boxing conversions only; None means semantic work remains."""
        file = self.files_by_path[target["path"]]
        if self.type_binding(target["id"], expected) is not None:
            return None
        declared = expected if "." in expected else ".".join(filter(None, [file["package"], expected]))
        if declared in self.declared_type_names:
            return False
        aliases = [i for i in file["imports"] if i["alias"] == expected]
        if aliases:
            if len(aliases) != 1:
                return None
            qualified = aliases[0]["qualified"]
        elif "." in expected:
            qualified = expected
        elif any(i["wildcard"] for i in file["imports"]):
            return None
        else:
            qualified = "java.lang." + expected
        if qualified in self.declared_type_names:
            return False
        boxed = {"boolean": "Boolean", "byte": "Byte", "short": "Short", "char": "Character",
                 "int": "Integer", "long": "Long", "float": "Float", "double": "Double"}
        if qualified == "java.lang.Object":
            return True
        if qualified == "java.lang.Number":
            return actual in {"byte", "short", "int", "long", "float", "double"}
        if qualified in {"java.lang.String", "java.lang.CharSequence"}:
            return actual == "reference_literal"
        if qualified in {"java.io.Serializable", "java.lang.Comparable"}:
            return True
        if qualified in {"java.lang." + name for name in boxed.values()}:
            return qualified == "java.lang." + boxed.get(actual, "")
        return None

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
            if scope.get("kind") == "array_loop":
                reason = self.loop_reason(file, scope)
                if reason:
                    return None, reason
            symbol = self.symbols.get(scope.get("id"), {})
            if symbol.get("receiver_type"):
                return None, "extension receiver dispatch unsupported"
            scope = self.scopes.get(scope.get("parent"), {})
        type_receiver = False
        if receiver:
            if not receiver.isidentifier() or receiver in {"this", "super"}:
                return None, "complex, this or super receiver unsupported"
            bindings = self.binding(scope_id, receiver)
            declared_type = (file["language"] == "java" and bindings is not None and len(bindings) == 1
                             and self.symbols.get(bindings[0].get("target"), {}).get("kind") in CLASS_KINDS)
            if declared_type:
                # A lexical class is also recorded in value bindings. Re-enter
                # type lookup so nearer type parameters still shadow it.
                types = self.candidates(file, receiver, type_only=True, scope_id=scope_id)
                type_receiver = True
            elif bindings is not None:
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
                type_receiver = file["language"] == "java"
            if len(types) != 1:
                return None, "receiver type external, ambiguous or unknown"
            if (types[0]["id"] in self.inherited_owners
                    and not (file["language"] == "java" and types[0].get("language") == "java"
                             and self.members.get((types[0]["id"], member))
                             and self.inherited_member_absent(types[0]["id"], member))):
                return None, "inherited candidate set and argument applicability required"
            candidates = self.members.get((types[0]["id"], member), [])
        else:
            if (not ref["constructor"] and self.owner(scope_id) in self.inherited_owners
                    and not (file["language"] == "java"
                             and self.members.get((self.owner(scope_id), member))
                             and self.inherited_member_absent(self.owner(scope_id), member))):
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
            if not ref["constructor"] and target["kind"] in CLASS_KINDS:
                return None, "Java class invocation requires constructor syntax"
            if type_receiver and target["kind"] == "method" and "static" not in target.get("modifiers", []):
                return None, "instance method requires a value receiver, not a type name"
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
            generic_handled, generic_reason = self.generic_argument_check(file, ref, target, parameters)
            if generic_reason:
                return None, generic_reason
            for number, actual in enumerate(ref.get("argument_types", [])):
                if number in generic_handled:
                    continue
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
                if (actual is not None and actual != "null" and expected not in _PRIMITIVE_WIDENING
                        and not expected.endswith("[]")):
                    compatible = self.literal_reference_compatible(target, expected, actual)
                    if compatible is not True:
                        return None, ("literal argument incompatible with reference parameter" if compatible is False
                                      else "literal reference conversion requires semantic analysis")
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
