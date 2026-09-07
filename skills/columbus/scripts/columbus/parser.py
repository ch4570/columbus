"""Conservative, non-executing Python syntax indexing and static name resolution.

This is a navigation aid, not a Python type checker. Dynamic dispatch, star imports,
monkey patching, runtime module paths and values assigned to variables are not
resolved. Unresolved references remain available in the returned parse records.
"""

from __future__ import annotations

import ast
from pathlib import PurePosixPath
from typing import Any


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


class _Declarations(ast.NodeVisitor):
    """Find declarations in this scope, including its conditional blocks."""

    def __init__(self) -> None:
        self.globals: set[str] = set()
        self.nonlocals: set[str] = set()

    def visit_Global(self, node: ast.Global) -> None:
        self.globals.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.nonlocals.update(node.names)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        pass

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        pass

    def visit_Lambda(self, node: ast.Lambda) -> None:
        pass


class _Parser(ast.NodeVisitor):
    def __init__(self, path: str, source: str, module: str) -> None:
        self.path, self.source, self.module = path, source, module
        self.symbols: list[dict[str, Any]] = []
        self.references: list[dict[str, Any]] = []
        self.imports: list[dict[str, Any]] = []
        self.scopes: dict[str, dict[str, Any]] = {}
        self.counts: dict[str, int] = {}
        self.nonlocal_bindings: list[tuple[str, str, dict[str, Any]]] = []
        self.current = f"{path}::module"
        self._scope(self.current, None, "module", "", self.current, [])
        self.symbols.append({
            "id": self.current, "path": path, "module": module,
            "name": module.rsplit(".", 1)[-1], "qualname": module,
            "kind": "module", "start_line": 1,
            "end_line": max(1, len(source.splitlines())),
            "signature": "", "doc": "", "parent_id": None,
        })

    def _scope(self, key: str, parent: str | None, kind: str,
               qualname: str, owner: str, body: list[ast.stmt]) -> None:
        declarations = _Declarations()
        for statement in body:
            declarations.visit(statement)
        self.scopes[key] = {
            "id": key, "parent": parent, "kind": kind,
            "qualname": qualname, "owner": owner, "bindings": {},
            "globals": sorted(declarations.globals),
            "nonlocals": sorted(declarations.nonlocals),
        }

    def _bind(self, name: str, binding: dict[str, Any]) -> None:
        scope = self.scopes[self.current]
        if name in scope["globals"]:
            scope = self.scopes[f"{self.path}::module"]
        elif name in scope["nonlocals"]:
            # The binding may be several functions out, or declared later in
            # source order. Finish these writes after collecting every scope.
            self.nonlocal_bindings.append((self.current, name, binding))
            return
        scope["bindings"].setdefault(name, []).append(binding)

    def finish_bindings(self) -> None:
        for scope_id, name, binding in self.nonlocal_bindings:
            parent = self.scopes[scope_id]["parent"]
            while parent is not None:
                candidate = self.scopes[parent]
                if candidate["kind"] == "function" and name in candidate["bindings"]:
                    candidate["bindings"][name].append(binding)
                    break
                parent = candidate["parent"]

    def _evidence(self, node: ast.AST) -> str:
        value = ast.get_source_segment(self.source, node) or ast.unparse(node)
        return " ".join(value.split())[:240]

    def _reference(self, node: ast.AST, kind: str,
                   source: str | None = None) -> None:
        self.references.append({
            "source": source or self.scopes[self.current]["owner"],
            "scope_id": self.current, "kind": kind, "name": _dotted(node),
            "path": self.path, "line": getattr(node, "lineno", 1),
            "evidence": self._evidence(node), "resolved": False,
        })

    def _definition(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        parent = self.scopes[self.current]
        prefix = parent["qualname"]
        qualname = f"{prefix}.{node.name}" if prefix else node.name
        kind = "class" if isinstance(node, ast.ClassDef) else (
            "method" if parent["kind"] == "class" else "function")
        base = f"{self.path}::{qualname}:{kind}"
        ordinal = self.counts.get(base, 0) + 1
        self.counts[base] = ordinal
        key = base if ordinal == 1 else f"{base}#{ordinal}"
        if isinstance(node, ast.ClassDef):
            signature = f"class {node.name}({', '.join(ast.unparse(b) for b in node.bases)})"
        else:
            prefix_text = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            signature = f"{prefix_text} {node.name}({ast.unparse(node.args)})"
            if node.returns is not None:
                signature += f" -> {ast.unparse(node.returns)}"
        self.symbols.append({
            "id": key, "path": self.path, "module": self.module,
            "name": node.name, "qualname": qualname, "kind": kind,
            "start_line": node.lineno, "end_line": node.end_lineno or node.lineno,
            "signature": signature, "doc": ast.get_docstring(node) or "",
            "parent_id": parent["owner"],
            "decorators": [ast.unparse(d) for d in node.decorator_list],
        })
        self._bind(node.name, {"kind": "symbol", "target": key})
        for decorator in node.decorator_list:
            self.visit(decorator)
        if isinstance(node, ast.ClassDef):
            for base_node in node.bases:
                self._reference(base_node, "inherits", source=key)
                self.visit(base_node)
            for keyword in node.keywords:
                self.visit(keyword.value)
        else:
            for default in [*node.args.defaults, *node.args.kw_defaults]:
                if default is not None:
                    self.visit(default)
        previous = self.current
        self._scope(key, previous, "class" if kind == "class" else "function",
                    qualname, key, node.body)
        self.current = key
        if isinstance(node, ast.ClassDef):
            self.scopes[key]['receiver_mutations'] = []
            self.scopes[key]['dynamic_class'] = bool(node.bases or node.keywords or node.decorator_list)
        elif kind == 'method' and not node.decorator_list:
            positional = [*node.args.posonlyargs, *node.args.args]
            if positional:
                self.scopes[key]['instance_receiver'] = {'name': positional[0].arg, 'owner': previous}
        if not isinstance(node, ast.ClassDef):
            self._arguments(node.args)
        for statement in node.body:
            self.visit(statement)
        self.current = previous

    visit_FunctionDef = _definition
    visit_AsyncFunctionDef = _definition
    visit_ClassDef = _definition

    def _arguments(self, arguments: ast.arguments) -> None:
        args = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
        if arguments.vararg:
            args.append(arguments.vararg)
        if arguments.kwarg:
            args.append(arguments.kwarg)
        for arg in args:
            self._bind(arg.arg, {"kind": "local", "reason": "parameter"})

    def receiver_owner(self, name):
        scope = self.scopes[self.current]
        while scope:
            receiver = scope.get('instance_receiver')
            if receiver and receiver['name'] == name:
                return receiver['owner']
            if name in scope['bindings']:
                return None
            scope = self.scopes.get(scope['parent'])
        return None

    def record_member_write(self, value: ast.AST, member: str) -> None:
        name = _dotted(value)
        if name:
            self.scopes[self.current].setdefault("member_writes", []).append(
                {"name": name, "scope_id": self.current, "member": member})

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.record_member_write(node.value, node.attr)
        if isinstance(node.ctx, (ast.Store, ast.Del)) and isinstance(node.value, ast.Name):
            owner = self.receiver_owner(node.value.id)
            if owner:
                mutations = self.scopes[owner]['receiver_mutations']
                if node.attr not in mutations:
                    mutations.append(node.attr)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if (isinstance(node.ctx, (ast.Store, ast.Del)) and isinstance(node.value, ast.Attribute)
                and node.value.attr == "__dict__" and isinstance(node.value.value, ast.Name)):
            owner = self.receiver_owner(node.value.value.id)
            if owner:
                self.scopes[owner]["receiver_mutations"].append("*")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self._bind(node.id, {"kind": "local", "reason": "assignment"})

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        previous = self.current
        # Assignment expressions in a comprehension bind in its containing
        # scope; otherwise a later call could incorrectly resolve a global.
        while self.scopes[self.current]["kind"] == "comprehension":
            self.current = self.scopes[self.current]["parent"]
        self.visit(node.target)
        self.current = previous

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self._bind(node.name, {"kind": "local", "reason": "exception target"})
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name:
            self._bind(node.name, {"kind": "local", "reason": "pattern target"})
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self._bind(node.name, {"kind": "local", "reason": "pattern target"})

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest:
            self._bind(node.rest, {"kind": "local", "reason": "pattern target"})
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (isinstance(node.func, ast.Name) and node.func.id in {"setattr", "delattr"}
                and node.args):
            member = (node.args[1].value if len(node.args) > 1 and isinstance(node.args[1], ast.Constant)
                      and isinstance(node.args[1].value, str) else "*")
            self.record_member_write(node.args[0], member)
        if (isinstance(node.func, ast.Name) and node.func.id in {"setattr", "delattr"}
                and node.args and isinstance(node.args[0], ast.Name)):
            owner = self.receiver_owner(node.args[0].id)
            if owner:
                self.scopes[owner]["receiver_mutations"].append("*")
        self._reference(node.func, "calls")
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._import(node, alias.name, None, alias.asname or alias.name.split(".")[0], 0,
                         bound_module=alias.name if alias.asname else alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self._import(node, node.module or "", alias.name,
                         alias.asname or alias.name, node.level)

    def _import(self, node: ast.AST, module: str, name: str | None,
                alias: str, level: int, bound_module: str | None = None) -> None:
        key = f"{self.path}::import:{len(self.imports) + 1}"
        self.imports.append({
            "id": key, "source": self.scopes[self.current]["owner"],
            "scope_id": self.current, "module": module, "name": name,
            "alias": alias, "level": level, "bound_module": bound_module,
            "path": self.path, "line": getattr(node, "lineno", 1),
            "evidence": self._evidence(node), "resolved": False,
        })
        if name != "*":
            self._bind(alias, {"kind": "import", "import_id": key})
        else:
            self.scopes[self.current]["star_import"] = True

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                self.visit(default)
        previous = self.current
        parent = self.scopes[previous]
        key = f"{previous}::lambda:{node.lineno}:{node.col_offset}"
        self._scope(key, previous, "function", parent["qualname"], parent["owner"], [])
        self.current = key
        self._arguments(node.args)
        self.visit(node.body)
        self.current = previous

    def _comprehension(self, node: ast.AST) -> None:
        generators = node.generators  # type: ignore[attr-defined]
        # Python evaluates the first iterable in the enclosing scope.
        self.visit(generators[0].iter)
        previous = self.current
        parent = self.scopes[previous]
        key = f"{previous}::comprehension:{node.lineno}:{node.col_offset}"  # type: ignore[attr-defined]
        self._scope(key, previous, "comprehension", parent["qualname"], parent["owner"], [])
        self.current = key
        for i, generator in enumerate(generators):
            if i:
                self.visit(generator.iter)
            self.visit(generator.target)
            for condition in generator.ifs:
                self.visit(condition)
        if isinstance(node, ast.DictComp):
            self.visit(node.key)
            self.visit(node.value)
        else:
            self.visit(node.elt)  # type: ignore[attr-defined]
        self.current = previous

    visit_ListComp = _comprehension
    visit_SetComp = _comprehension
    visit_DictComp = _comprehension
    visit_GeneratorExp = _comprehension


def parse_source(path: str, source: str, module: str) -> dict[str, Any]:
    """Parse text without importing or executing it; all returned values are JSON safe."""
    parser = _Parser(path, source, module)
    diagnostics: list[str] = []
    try:
        tree = ast.parse(source, filename=path)
        parser.symbols[0]["doc"] = ast.get_docstring(tree) or ""
        for statement in tree.body:
            parser.visit(statement)
        parser.finish_bindings()
    except (SyntaxError, ValueError, RecursionError) as exc:
        # Never expose partial symbols when a parse fails.
        parser = _Parser(path, source, module)
        line = getattr(exc, "lineno", None)
        diagnostics.append(f"{type(exc).__name__}{f' at line {line}' if line else ''}: {exc}")
    return {
        "path": path, "module": module, "symbols": parser.symbols,
        "references": parser.references, "imports": parser.imports,
        "diagnostics": diagnostics, "_scopes": parser.scopes,
    }


class _Resolver:
    def __init__(self, files: list[dict[str, Any]]) -> None:
        self.files = files
        self.symbols = {s["id"]: s for f in files for s in f["symbols"]}
        self.scopes = {k: v for f in files for k, v in f.get("_scopes", {}).items()}
        self.imports = {i["id"]: (f, i) for f in files for i in f["imports"]}
        self.modules: dict[str, list[dict[str, Any]]] = {}
        for file in files:
            self.modules.setdefault(file["module"], []).append(file)
        self.receiver_bases = {target for file in files for ref in file["references"]
                               if ref["kind"] == "inherits" and (target := self.reference(ref))}
        self.class_mutations: dict[str, set[str]] = {}
        for scope in self.scopes.values():
            for write in scope.get("member_writes", []):
                target = self.reference({**write, "kind": "inherits"})
                if target and self.symbols[target]["kind"] == "class":
                    self.class_mutations.setdefault(target, set()).add(write["member"])


    def module_file(self, module: str) -> dict[str, Any] | None:
        candidates = self.modules.get(module, [])
        return candidates[0] if len(candidates) == 1 else None

    def absolute_module(self, file: dict[str, Any], imported: dict[str, Any]) -> str | None:
        if not imported["level"]:
            return imported["module"]
        package = file["module"].split(".")
        if PurePosixPath(file["path"]).name != "__init__.py":
            package = package[:-1]
        up = imported["level"] - 1
        if up >= len(package):
            return None
        if up:
            package = package[:-up]
        return ".".join([*package, *([imported["module"]] if imported["module"] else [])])

    def imported(self, import_id: str, seen: set[str]) -> tuple[str, str] | None:
        if import_id in seen:
            return None
        file, item = self.imports[import_id]
        module = self.absolute_module(file, item)
        if module is None or item["name"] == "*":
            return None
        seen = seen | {import_id}
        if item["name"] is None:
            return ("module", item["bound_module"] or module)
        # Prefer a statically declared package export to a same-named submodule.
        base = self.module_file(module)
        if base:
            scope = self.scopes.get(f"{base['path']}::module", {})
            if scope.get("star_import"):
                return None
            if item["name"] in scope.get("bindings", {}):
                return self.binding(scope["bindings"][item["name"]], seen)
        child = f"{module}.{item['name']}" if module else item["name"]
        if self.module_file(child):
            return ("module", child)
        return None

    def binding(self, bindings: list[dict[str, Any]], seen: set[str]) -> tuple[str, str] | None:
        if len(bindings) != 1:
            return None
        binding = bindings[0]
        if binding["kind"] == "symbol":
            return ("symbol", binding["target"])
        if binding["kind"] == "import":
            return self.imported(binding["import_id"], seen)
        return None

    def name(self, scope_id: str, name: str) -> tuple[str, str] | None:
        scope = self.scopes[scope_id]
        if name in scope["globals"]:
            while scope["parent"] is not None:
                scope = self.scopes[scope["parent"]]
        elif name in scope["nonlocals"]:
            parent = scope["parent"]
            while parent is not None and self.scopes[parent]["kind"] != "function":
                parent = self.scopes[parent]["parent"]
            if parent is None:
                return None
            scope = self.scopes[parent]
        while True:
            if scope.get("star_import"):
                return None
            bindings = scope["bindings"].get(name)
            if bindings is not None:
                return self.binding(bindings, set())
            parent = scope["parent"]
            # Class namespaces do not form a lexical closure for nested scopes.
            while parent is not None and self.scopes[parent]["kind"] == "class":
                parent = self.scopes[parent]["parent"]
            if parent is None:
                return None
            scope = self.scopes[parent]

    def attribute(self, value: tuple[str, str], parts: list[str]) -> tuple[str, str] | None:
        while parts:
            head, parts = parts[0], parts[1:]
            kind, target = value
            if kind == "module":
                module_file = self.module_file(target)
                bindings = None
                if module_file:
                    scope = self.scopes.get(f"{module_file['path']}::module", {})
                    if scope.get("star_import"):
                        return None
                    bindings = scope.get("bindings", {}).get(head)
                if bindings is not None:
                    resolved = self.binding(bindings, set())
                    if resolved is None:
                        return None
                    value = resolved
                else:
                    candidate = f"{target}.{head}"
                    # Intermediate namespace packages may have no __init__.py.
                    if not any(m == candidate or m.startswith(candidate + ".") for m in self.modules):
                        return None
                    value = ("module", candidate)
            elif self.symbols[target]["kind"] == "class":
                scope = self.scopes.get(target, {})
                bindings = scope.get("bindings", {}).get(head)
                if bindings is None:
                    return None
                resolved = self.binding(bindings, set())
                if resolved is None:
                    return None
                value = resolved
            else:
                return None
        return value

    def receiver_candidate(self, reference):
        """A navigation hint only: receiver dispatch is not a proven call edge."""
        parts = (reference.get('name') or '').split('.')
        if reference['kind'] != 'calls' or len(parts) != 2:
            return None
        name, member = parts
        scope = self.scopes[reference['scope_id']]
        while scope:
            if name in scope['globals'] or name in scope['nonlocals']:
                return None
            bindings = scope['bindings'].get(name)
            if bindings is not None:
                receiver = scope.get('instance_receiver')
                if (not receiver or receiver['name'] != name
                        or bindings != [{'kind': 'local', 'reason': 'parameter'}]):
                    return None
                owner = receiver['owner']
                break
            scope = self.scopes.get(scope['parent'])
        else:
            return None
        cls = self.scopes[owner]
        if (cls.get('dynamic_class') or owner in self.receiver_bases
                or {member, '*', '__class__', '__dict__'} & set(cls.get('receiver_mutations', []))
                or {'__getattr__', '__getattribute__'} & cls['bindings'].keys()
                or {member, '*', '__bases__', '__getattr__', '__getattribute__'}
                   & self.class_mutations.get(owner, set())):
            return None
        resolved = self.binding(cls['bindings'].get(member, []), set())
        if not resolved or resolved[0] != 'symbol':
            return None
        target = self.symbols[resolved[1]]
        if target['kind'] != 'method' or target.get('decorators') not in ([], ['staticmethod']):
            return None
        if target.get('decorators'):
            current = cls
            while current:
                if 'staticmethod' in current['bindings']:
                    return None
                current = self.scopes.get(current['parent'])
        return target['id']

    def reference(self, reference: dict[str, Any]) -> str | None:
        name = reference["name"]
        if not name:
            return None
        parts = name.split(".")
        value = self.name(reference["scope_id"], parts[0])
        if value is None:
            return None
        value = self.attribute(value, parts[1:])
        if value is None or value[0] != "symbol":
            return None
        target = self.symbols[value[1]]
        if reference["kind"] == "inherits" and target["kind"] != "class":
            return None
        return target["id"]


def resolve_files(parsed_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build edges across parsed modules, retaining unresolved references in-place.

    ``resolved_static`` means an unambiguous lexical/import syntax match. It is
    not proof of runtime identity. Attribute calls are labeled ``heuristic``.
    """
    resolver = _Resolver(parsed_files)
    edges: list[dict[str, Any]] = []
    for file in parsed_files:
        for symbol in file["symbols"]:
            if symbol["parent_id"]:
                edges.append({
                    "source": symbol["parent_id"], "target": symbol["id"],
                    "kind": "contains", "confidence": "syntactic",
                    "evidence": symbol["signature"], "path": file["path"],
                    "line": symbol["start_line"],
                })
        for imported in file["imports"]:
            imported.pop("target", None)
            imported["resolved"] = False
            value = resolver.imported(imported["id"], set())
            # An import edge targets the full module loaded, while its local
            # binding may be just a root package (``import package.module``).
            if imported["name"] is None:
                value = ("module", resolver.absolute_module(file, imported) or "")
            target = None
            if value:
                if value[0] == "symbol":
                    target = value[1]
                else:
                    module_file = resolver.module_file(value[1])
                    if module_file:
                        target = f"{module_file['path']}::module"
            if target:
                imported.update(resolved=True, target=target)
                edges.append({
                    "source": imported["source"], "target": target,
                    "kind": "imports", "confidence": "resolved_static",
                    "evidence": imported["evidence"], "path": file["path"],
                    "line": imported["line"],
                })
        for reference in file["references"]:
            reference.pop("target", None)
            reference.pop("confidence", None)
            reference.pop("retrieval_candidates", None)
            target = resolver.reference(reference)
            reference["resolved"] = target is not None
            if target is None:
                reference["reason"] = "dynamic, external, shadowed, ambiguous or unknown name"
                candidate = resolver.receiver_candidate(reference)
                if candidate:
                    reference["retrieval_candidates"] = [{"target": candidate, "confidence": "retrieval_only",
                        "reason": "lexical instance-receiver member; runtime dispatch and external mutation unverified"}]
                continue
            reference.pop("reason", None)
            confidence = "heuristic" if "." in reference["name"] else "resolved_static"
            reference.update(target=target, confidence=confidence)
            edges.append({
                "source": reference["source"], "target": target,
                "kind": reference["kind"], "confidence": confidence,
                "evidence": reference["evidence"], "path": file["path"],
                "line": reference["line"],
            })
    # Preserve distinct call sites, but avoid duplicate edges from identical input.
    unique = {tuple(edge[k] for k in ("source", "target", "kind", "path", "line")): edge for edge in edges}
    return sorted(unique.values(), key=lambda e: (e["path"], e["line"], e["kind"], e["source"], e["target"]))
