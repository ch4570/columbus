"""Conservative lexical graph facts for languages without an installed AST parser.

All declarations and links from this module are heuristic. Strings/comments are
masked first. Only unique, visible direct function calls are linked; receiver,
macro, overload and runtime/package resolution remain explicitly unresolved.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from pathlib import PurePosixPath
import posixpath
import re

from .language_profiles import fidelity_for

IDENT = r"[A-Za-z_$][\w$]*"
HASH_COMMENTS = {"ruby", "shell", "powershell", "r", "julia", "elixir", "perl", "nim",
                 "crystal", "terraform", "nix", "yaml", "toml", "make", "cobol"}
CALL_LANGUAGES = {"javascript", "typescript", "go", "rust", "c", "cpp", "csharp", "php",
                  "swift", "dart", "zig", "d", "solidity", "v", "apex"}
CONTROL_WORDS = {"if", "for", "while", "switch", "catch", "with", "match", "when", "sizeof",
                 "typeof", "return", "throw", "new", "function", "func", "fn", "def", "class",
                 "interface", "struct", "enum", "import", "require", "super", "this", "assert",
                 "synchronized", "foreach", "using", "lock", "checked", "unchecked", "delete"}


def _jsx_start(source: str, offset: int) -> bool:
    cursor = offset - 1
    while cursor >= 0 and source[cursor].isspace():
        cursor -= 1
    if cursor < 0 or source[cursor] in '=(:,![{;?&|>+-*/%^~':
        return True
    end = cursor + 1
    while cursor >= 0 and (source[cursor].isalnum() or source[cursor] in '_$'):
        cursor -= 1
    return source[cursor + 1:end] in {'return', 'yield', 'case', 'throw'}


def _generic_arrow_start(source: str, start: int) -> bool:
    """Disambiguate constrained TSX arrows before looking for JSX close tags."""
    if not re.match(r'<' + IDENT + r'\s+(?:extends\b)', source[start:]):
        return False

    def opaque_end(cursor):
        if source.startswith(('//', '/*'), cursor):
            block = source.startswith('/*', cursor)
            stop = source.find('*/' if block else '\n', cursor + 2)
            return len(source) if stop < 0 else stop + (2 if block else 1)
        if source[cursor] in '\"\'`':
            quote = source[cursor]
            cursor += 1
            while cursor < len(source):
                if source[cursor] == '\\':
                    cursor += 2
                elif source[cursor] == quote:
                    return cursor + 1
                else:
                    cursor += 1
            return len(source)
        return None

    def balanced_end(cursor, opening, closing):
        if cursor >= len(source) or source[cursor] != opening:
            return None
        nesting = 1
        cursor += 1
        while cursor < len(source):
            opaque = opaque_end(cursor)
            if opaque is not None:
                cursor = opaque
                continue
            if source[cursor] == opening:
                nesting += 1
            elif source[cursor] == closing and not (closing == '>' and source[cursor - 1] == '='):
                nesting -= 1
                if not nesting:
                    return cursor + 1
            cursor += 1
        return None

    cursor = balanced_end(start, '<', '>')
    if cursor is None:
        return False
    while cursor < len(source) and source[cursor].isspace():
        cursor += 1
    cursor = balanced_end(cursor, '(', ')')
    if cursor is None:
        return False
    while cursor < len(source) and source[cursor].isspace():
        cursor += 1
    if source.startswith(':', cursor):
        # Return annotations can contain objects, tuples, generics and arrow
        # types. They are code even when a later string looks like </T>.
        cursor += 1
        seen_type = False
        while cursor < len(source):
            opaque = opaque_end(cursor)
            if opaque is not None:
                seen_type |= source[cursor] in '\"\'`'
                cursor = opaque
                continue
            if source.startswith('=>', cursor):
                return seen_type
            token = source[cursor]
            if token in '({[<':
                closing = {'(': ')', '{': '}', '[': ']', '<': '>'}[token]
                cursor = balanced_end(cursor, token, closing)
                if cursor is None:
                    return False
                seen_type = True
                continue
            if token in ')}]>;':
                return False
            seen_type |= not token.isspace()
            cursor += 1
        return False
    return source.startswith('=>', cursor)


def _jsx_regions(source: str, start: int, depth: int = 0) -> tuple[int, list[tuple[int, int]]] | None:
    """Recognize a complete JSX element and return only its non-code spans.

    Requiring a matching close (or a self-closing tag) avoids treating ordinary
    TypeScript generic headers and comparison operators as JSX. Braced values
    retain their JavaScript, including nested JSX values; this is still a
    lexical mask, not JSX name resolution or a syntax validator.
    """
    if depth > 128 or _generic_arrow_start(source, start):
        return None
    size = len(source)
    regions = []

    def expression(cursor):
        nesting = 1
        cursor += 1
        while cursor < size:
            if source.startswith(('//', '/*'), cursor):
                block = source.startswith('/*', cursor)
                stop = source.find('*/' if block else '\n', cursor + 2)
                if stop < 0:
                    return None
                cursor = stop + (2 if block else 1)
                continue
            character = source[cursor]
            if character in '\"\'`':
                quote = character
                cursor += 1
                while cursor < size:
                    if source[cursor] == '\\':
                        cursor += 2
                    elif source[cursor] == quote:
                        cursor += 1
                        break
                    else:
                        cursor += 1
                continue
            if character == '/':
                prefix = source[:cursor].rstrip()
                if not prefix or prefix[-1] in '=(:,![{;?&|' or re.search(r'\b(?:return|yield|case)\s*$', prefix):
                    regex_cursor, in_class = cursor + 1, False
                    while regex_cursor < size and source[regex_cursor] != '\n':
                        token = source[regex_cursor]
                        if token == '\\':
                            regex_cursor += 2
                            continue
                        if token == '[':
                            in_class = True
                        elif token == ']':
                            in_class = False
                        elif token == '/' and not in_class:
                            cursor = regex_cursor + 1
                            break
                        regex_cursor += 1
                    else:
                        cursor += 1
                    continue
            if character == '<' and _jsx_start(source, cursor):
                nested = _jsx_regions(source, cursor, depth + 1)
                if nested:
                    cursor, spans = nested
                    regions.extend(spans)
                    continue
            if character == '{':
                nesting += 1
            elif character == '}':
                nesting -= 1
                if not nesting:
                    return cursor + 1
            cursor += 1
        return None

    opening = re.match(r'<(?P<name>[A-Za-z_$][\w$.:\-]*)(?=[\s/>])|<(?=>)', source[start:])
    if not opening:
        return None
    name = opening.group('name') or ''
    cursor, chunk = start + opening.end(), start
    while cursor < size:
        character = source[cursor]
        if character in '\"\'':
            stop = source.find(character, cursor + 1)
            if stop < 0:
                return None
            cursor = stop + 1
        elif character == '{':
            regions.append((chunk, cursor))
            stop = expression(cursor)
            if stop is None:
                return None
            cursor = chunk = stop
        elif source.startswith('/>', cursor):
            regions.append((chunk, cursor + 2))
            return cursor + 2, regions
        elif character == '>':
            cursor += 1
            regions.append((chunk, cursor))
            break
        else:
            cursor += 1
    else:
        return None
    chunk = cursor
    while cursor < size:
        if source.startswith('</', cursor):
            closing = re.match(r'</' + re.escape(name) + r'\s*>', source[cursor:])
            if not closing:
                return None
            cursor += closing.end()
            regions.append((chunk, cursor))
            return cursor, regions
        if source[cursor] == '<':
            regions.append((chunk, cursor))
            nested = _jsx_regions(source, cursor, depth + 1)
            if not nested:
                return None
            cursor, spans = nested
            regions.extend(spans)
            chunk = cursor
        elif source[cursor] == '{':
            regions.append((chunk, cursor))
            stop = expression(cursor)
            if stop is None:
                return None
            cursor = chunk = stop
        else:
            cursor += 1
    return None


def mask_source(source: str, language: str, *, jsx: bool = True) -> tuple[str, list[dict]]:
    """Blank comments and literal bodies, preserving offsets and line numbers.

    Interpolated string expressions are deliberately omitted too: resolving
    them without a language grammar would manufacture misleading call facts.
    """
    chars, literals, size, i = list(source), [], len(source), 0
    expression_end = 0
    jsx_regions = {}

    def blank(start, end):
        for offset in range(start, end):
            if chars[offset] not in "\r\n":
                chars[offset] = " "

    while i < size:
        if i in jsx_regions:
            end = jsx_regions[i]
            blank(i, end)
            expression_end = end
            i = end
            continue
        if jsx and source[i] == '<' and language in {'javascript', 'typescript'} and _jsx_start(source, i):
            element = _jsx_regions(source, i)
            if element:
                jsx_regions.update((start, end) for start, end in element[1] if start < end)
                continue
        start, end, literal = i, None, False
        if source.startswith("/*", i) and language not in {"ruby", "shell", "lua", "haskell"}:
            # Nested block comments occur in Rust, Swift, Kotlin and several DSLs.
            cursor, depth = i + 2, 1
            while cursor < size and depth:
                if source.startswith("/*", cursor) and language in {"rust", "swift", "scala", "d"}:
                    depth, cursor = depth + 1, cursor + 2
                elif source.startswith("*/", cursor):
                    depth, cursor = depth - 1, cursor + 2
                else:
                    cursor += 1
            end = cursor
        elif source.startswith("//", i) and language not in {"ruby", "shell", "lua", "haskell", "elixir", "r"}:
            end = source.find("\n", i)
        elif source[i] == "#" and (language in HASH_COMMENTS or language == "php"):
            end = source.find("\n", i)
        elif source.startswith("--", i) and language in {"lua", "sql", "haskell", "ada"}:
            if language == "lua" and source.startswith("--[[", i):
                stop = source.find("]]", i + 4)
                end = size if stop < 0 else stop + 2
            else:
                end = source.find("\n", i)
        elif source[i] == ";" and language in {"clojure", "lisp"}:
            end = source.find("\n", i)
        elif source[i] == "%" and language in {"erlang", "fortran"}:
            end = source.find("\n", i)
        elif source.startswith("=begin", i) and language == "ruby" and (i == 0 or source[i - 1] == "\n"):
            stop = source.find("\n=end", i)
            end = size if stop < 0 else source.find("\n", stop + 1)
        elif source.startswith("<#", i) and language == "powershell":
            stop = source.find("#>", i + 2)
            end = size if stop < 0 else stop + 2
        elif source.startswith("<!--", i):
            stop = source.find("-->", i + 4)
            end = size if stop < 0 else stop + 3
        elif language == "rust" and source[i] in "rb" and (raw := re.match(r'(?:br|r)(#+)?"', source[i:])):
            terminator = '"' + (raw.group(1) or "")
            stop = source.find(terminator, i + raw.end())
            end, literal = (size if stop < 0 else stop + len(terminator)), True
        elif language == "cpp" and source[i] == "R" and (raw := re.match(r'R"([^ ()\\\t\r\n]{0,16})\(', source[i:])):
            terminator = ")" + raw.group(1) + '"'
            stop = source.find(terminator, i + raw.end())
            end, literal = (size if stop < 0 else stop + len(terminator)), True
        elif source.startswith("<<", i) and language in {"ruby", "shell", "php", "perl"}:
            heredoc = re.match(r"<<<[ \t]*['\"]?(\w+)['\"]?[ \t]*\n" if language == "php"
                               else r"<<[-~]?[ \t]*['\"]?(\w+)['\"]?[ \t]*\n", source[i:])
            if heredoc:
                stop = re.search(r"(?m)^\s*" + re.escape(heredoc.group(1)) + r";?\s*$", source[i + heredoc.end():])
                end = size if stop is None else i + heredoc.end() + stop.end()
                literal = True
        if end is None and source[i] in "\"'`":
            quote = source[i]
            # Rust lifetimes and Lisp quote operators are not string starts.
            if quote == "'" and ((language == "rust" and re.match(r"'[A-Za-z_]\w*(?!')", source[i:])
                                   and not re.match(r"'[^'\n]{1,8}'", source[i:]))
                                  or language in {"lisp", "clojure", "haskell", "ocaml"}):
                i += 1
                continue
            delimiter = quote * 3 if source.startswith(quote * 3, i) else quote
            cursor = i + len(delimiter)
            while cursor < size:
                if source[cursor] == "\\":
                    cursor += 2
                elif source.startswith(delimiter, cursor):
                    # C#/SQL doubled quotes escape their quote character.
                    if len(delimiter) == 1 and source.startswith(quote * 2, cursor) and language in {"csharp", "sql"}:
                        cursor += 2
                    else:
                        cursor += len(delimiter)
                        break
                else:
                    cursor += 1
            end, literal = min(cursor, size), True
        if end is None and language in {"javascript", "typescript"} and source[i] == "/":
            # A regex literal can contain apparent declarations/calls. Recognize
            # expression-start positions; division remains ordinary source.
            prefix = source[:i].rstrip()
            previous = i - 1
            while previous >= 0 and chars[previous].isspace():
                previous -= 1
            # Comments may intervene after =>, but an already masked literal
            # or JSX expression must not turn later division into a regex.
            after_arrow = (previous >= 1 and chars[previous - 1:previous + 1] == ["=", ">"]
                           and previous - 1 >= expression_end)
            if (not prefix or prefix[-1] in "=(:,![{;?&|" or after_arrow
                    or re.search(r"\b(?:return|yield|case)\s*$", prefix)):
                cursor, in_class = i + 1, False
                while cursor < size and source[cursor] != "\n":
                    if source[cursor] == "\\":
                        cursor += 2
                        continue
                    if source[cursor] == "[":
                        in_class = True
                    elif source[cursor] == "]":
                        in_class = False
                    elif source[cursor] == "/" and not in_class:
                        end, literal = cursor + 1, True
                        break
                    cursor += 1
        if end is not None:
            end = size if end < 0 else end
            if literal:
                literals.append({"start": start, "end": end, "text": source[start:end]})
                expression_end = end
            blank(start, end)
            i = end
        else:
            i += 1
    return "".join(chars), literals


def _patterns(language: str, config: dict) -> list[tuple[str, str]]:
    name = rf"(?P<name>{IDENT})"
    kinds = []
    if language in {"javascript", "typescript"}:
        kinds += [("class", rf"\bclass\s+{name}"), ("interface", rf"\binterface\s+{name}"),
                  ("enum", rf"\benum\s+{name}"), ("type", rf"\btype\s+{name}(?:\s*<[^;{{}}\n]*>)?\s*="),
                  ("function", rf"\bfunction\s*\*?\s*{name}\s*(?:<[^;{{}}\n]*>)?\s*\("),
                  ("function", rf"\b(?:const|let|var)\s+{name}\s*=\s*(?:async\s+)?function\s*\("),
                  ("function", rf"\b(?:const|let|var)\s+{name}\s*=\s*(?:async\s+)?(?:\([^;{{}}]*\)|{IDENT})\s*(?::[^=\n]+)?=>")]
    elif language == "go":
        kinds += [("function", rf"\bfunc\s+(?:\([^()\n]+\)\s*)?{name}\s*(?:\[[^\]\n]+\])?\s*\("),
                  ("type", rf"\btype\s+{name}\s+(?:struct|interface)\b")]
    elif language in {"rust", "zig", "v"}:
        kinds += [("function", rf"\bfn\s+{name}\s*(?:<[^;{{}}\n]+>)?\s*\("),
                  ("struct", rf"\bstruct\s+{name}"), ("enum", rf"\benum\s+{name}"),
                  ("trait", rf"\btrait\s+{name}"), ("type", rf"\btype\s+{name}\s*=")]
        if language == "rust":
            kinds += [("implementation", rf"\bimpl\s*(?:<[^;{{}}\n]+>)?\s*{name}(?:\s*<[^;{{}}\n]+>)?\s*(?=\{{)")]
    elif language in {"ruby", "crystal", "elixir"}:
        kinds += [("class", rf"\b(?:class|defmodule|module)\s+{name}"),
                  ("function", rf"\b(?:def|defp|defmacro)\s+(?:self\.)?{name}[!?=]?")]
    elif language in {"swift", "scala", "groovy", "php", "dart", "csharp", "c", "cpp", "d", "solidity", "apex"}:
        kinds += [("class", rf"\b(?:class|actor|object)\s+{name}"),
                  ("struct", rf"\bstruct\s+{name}"), ("interface", rf"\b(?:interface|protocol|trait)\s+{name}"),
                  ("enum", rf"\benum\s+{name}")]
        if language == "swift":
            kinds += [("function", rf"\bfunc\s+{name}\s*(?:<[^;{{}}\n]*>)?\s*\(")]
        elif language in {"scala", "groovy"}:
            kinds += [("function", rf"\bdef\s+{name}\s*(?:\[[^\]\n]+\])?\s*\(")]
        elif language in {"php", "solidity"}:
            kinds += [("function", rf"\bfunction\s*&?\s*{name}\s*\(")]
        if language not in {"swift", "scala", "php", "solidity"}:
            # A typed header at a statement boundary, followed by a body. Calls
            # and prototypes cannot satisfy this declaration expression.
            kinds += [("function", rf"(?:^|(?<=[;{{}}]))[ \t]*(?:(?:{IDENT})(?:[\w<>,.?:\[\]*& \t]*?)[ \t*&]+){name}\s*\([^;{{}}]*\)\s*(?:const\s*)?(?:noexcept\s*)?(?:->[^{{;\n]+)?\s*(?=\{{)")]
    elif language in {"shell", "powershell"}:
        kinds += [("function", rf"\bfunction\s+{name}"),
                  ("function", rf"^\s*{name}\s*\(\s*\)\s*(?=\{{)")]
    elif language in {"lua", "julia", "r"}:
        kinds += [("function", rf"\bfunction\s+{name}"),
                  ("function", rf"\b{name}\s*(?:<-|=)\s*function\s*\(")]
    elif language in {"clojure", "lisp"}:
        kinds += [("function", rf"\(\s*(?:defn|defun|define|defmacro)\s+\(?{name}")]
    elif language == "perl":
        kinds += [("function", rf"\bsub\s+{name}"), ("namespace", rf"\bpackage\s+{name}")]
    elif language in {"nim", "pascal", "ada", "fortran", "cobol"}:
        kinds += [("function", rf"\b(?:proc|procedure|function|subroutine|PROGRAM-ID\.)\s+{name}")]
    elif language in {"haskell", "ocaml", "fsharp", "erlang", "odin", "nix"}:
        kinds += [("function", rf"^\s*(?:(?:let|rec|pub)\s+)*{name}\s*(?:::|:\s*proc|\([^\n]*\)\s*->|[^=\n]+\s*=)")]
    elif language == "sql":
        kinds += [("table", rf"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?{name}"),
                  ("function", rf"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s+{name}")]
    elif language in {"graphql", "protobuf", "terraform"}:
        kinds += [("type", rf"\b(?:type|input|interface|enum|message|service)\s+{name}")]
    for keyword in config.get("declarations", {}).get(language, []):
        kinds.append(("declaration", rf"(?<!\w){re.escape(keyword)}\s+{name}"))
    return kinds


def _braces(masked: str) -> dict[int, int]:
    stack, pairs = [], {}
    for offset, char in enumerate(masked):
        if char == "{":
            stack.append(offset)
        elif char == "}" and stack:
            pairs[stack.pop()] = offset + 1
    return pairs


def _js_export_bindings(masked, literals, symbols, spans, scopes, imports, dynamic_scope):
    """Recognize a small, conservative subset of module export bindings.

    Separate ``export default identifier;`` exports a value, not a general
    live alias. We deliberately reject writes even after that statement, and
    shadows in unrelated scopes, rather than infer evaluation order. This is
    still lexical evidence: no re-exports, expression/receiver dispatch or
    named function-expression bindings are inferred.
    """
    # Literals are not whitespace between syntax tokens. Their contents must
    # stay masked, but their presence must prevent matching an export prefix.
    chars = list(masked)
    for literal in literals:
        chars[literal["start"]] = "\0"
    code = "".join(chars)
    export_tokens = list(re.finditer(r"\bexport\b", code))
    if not export_tokens:
        return
    positions = {span["name_start"] for span in spans} | {m.start() for m in export_tokens}
    prefixes, empty_prefixes, stack, start, only_space, pattern_writes = {}, set(), [], 0, True, set()
    assignment = re.compile(r"\s*(?:=(?!=|>)|(?:\*\*|&&|\|\||\?\?|>>>|>>|<<|[+*/%&|^~-])=|\+\+|--)")
    loop_binding = re.compile(r"\s*(?:in|of)\b")
    # A deliberately small ASI boundary: a complete top-level variable
    # initializer consisting of a direct call, optionally an identifier-only
    # arrow returning that call. No controls, chains or conditional expressions.
    parameters = rf"(?:{IDENT}(?:\s*,\s*{IDENT})*)?"
    asi_call = re.compile(rf"\s*(?:export\s+)?(?:const|let|var)\s+{IDENT}\s*=\s*"
                          rf"(?:(?:async[ \t]+)?(?:{IDENT}|\(\s*{parameters}\s*\))\s*=>\s*)?"
                          rf"(?:new\s+)?{IDENT}\s*\(")
    for offset, char in enumerate(code):
        if offset in positions and not stack:
            # Retain offsets, not repeated source-prefix copies (which can be
            # quadratic on many unsupported export tokens in one statement).
            prefixes[offset] = start
            if only_space:
                empty_prefixes.add(offset)
        if not char.isspace():
            only_space = False
        if char in "({[":
            stack.append((char, offset))
        elif char in ")}]":
            if not stack or stack[-1][0] != {")": "(", "}": "{", "]": "["}[char]:
                return
            _, begin = stack.pop()
            previous = begin - 1
            while previous >= 0 and code[previous].isspace():
                previous -= 1
            if (assignment.match(code, offset + 1)
                    or loop_binding.match(code, offset + 1)
                    or code[max(0, previous - 1):previous + 1] in {"++", "--"}):
                pattern_writes.update(re.findall(IDENT, code[begin:offset]))
            if not stack and char == "}":
                start, only_space = offset + 1, True
            elif not stack and char == ")":
                following = offset + 1
                while following < len(code) and code[following].isspace():
                    following += 1
                if (any(c in "\r\n" for c in code[offset + 1:following])
                        and re.match(r"export\b", code[following:following + 7])):
                    initializer = asi_call.match(code, start, begin + 1)
                    if initializer and initializer.end() == begin + 1:
                        start, only_space = offset + 1, True
        elif char == ";" and not stack:
            start, only_space = offset + 1, True
    # Even parenthesized/aliased eval can hide exporter writes. Reject the
    # lexical name conservatively; proving whether it is shadowed is outside
    # this subset (as are escaped identifiers).
    if stack or dynamic_scope or "\\" in code or re.search(r"\b(?:eval|with)\b", code):
        return
    templates = [literal["text"] for literal in literals
                 if literal["text"].startswith("`") and "${" in literal["text"]]
    # The shared masker intentionally omits executable template expressions.
    # Do not let hidden writes or computed eval bypass the export guard.
    # Ordinary template escapes (e.g. RegExp's \\s) cannot spell identifiers.
    # Unicode escapes can hide binding names, so they remain unsupported even
    # when they might instead belong to harmless literal text.
    if any(re.search(r"\b(?:eval|with)\b|\\u(?:[0-9a-fA-F]{4}|\{)", text) for text in templates):
        return
    blocked = pattern_writes | {name for scope in scopes.values() for name in scope["blocked"]}
    for imported in imports:
        blocked.update(imported.get("names", {}))
        if imported.get("alias"):
            blocked.add(imported["alias"])
    blocked.update(re.findall(rf"(?:\+\+|--)\s*({IDENT})", code))
    blocked.update(re.findall(rf"\bfor\s+await\s*\(\s*({IDENT})\s+(?:in|of)\b", code))
    scope_blocked = blocked.copy()
    writes = rf"(?<![\w$])(?P<name>{IDENT})\s*(?:=(?!=|>)|(?:\*\*|&&|\|\||\?\?|>>>|>>|<<|[+*/%&|^~-])=|\+\+|--)"
    write_occurrences = defaultdict(list)
    for match in re.finditer(writes, code):
        write_occurrences[match.group("name")].append(match)
        blocked.add(match.group("name"))
    # Initializers belong to inline callable variable declarations, but later
    # writes to the same name do not. Simple assignment guards above therefore
    # exclude those declarations below, unless their initializer is the only
    # write and the existing scope guards agree.
    by_name = defaultdict(list)
    by_id = {symbol["id"]: symbol for symbol in symbols}
    for symbol in symbols:
        if symbol["parent_id"] == f"{symbol['path']}::module":
            by_name[symbol["name"]].append(symbol)
    declarations = {}
    inline_defaults = []
    function_prefix = re.compile(r"\s*(?:(?P<export>export)\s+(?:(?P<default>default)\s+)?)?"
                                 r"(?:async[ \t]+)?function\s*\*?\s*")
    variable_prefix = re.compile(r"\s*export\s+(?:const|let|var)\s*")
    for span in spans:
        symbol = by_id[span["id"]]
        if span["name_start"] not in prefixes:
            continue
        begin, end = prefixes[span["name_start"]], span["name_start"]
        genuine = function_prefix.fullmatch(code, begin, end)
        inline_variable = variable_prefix.fullmatch(code, begin, end)
        if symbol["kind"] != "function" or len(by_name[symbol["name"]]) != 1:
            continue
        header = code[span["name_start"]:span["header_end"]]
        # The shared body finder can mistake a TS return-type object for a
        # function body. Only no annotation or a simple named/array return type
        # is accepted here; complex valid return types are false negatives.
        parameter_end = header.rfind(")")
        return_type = header[parameter_end + 1:]
        simple_type = rf"(?!(?:keyof|typeof|readonly|unique|infer|asserts)\b){IDENT}"
        supported_return = parameter_end >= 0 and re.fullmatch(rf"\s*(?::\s*{simple_type}(?:\.{IDENT})*(?:\s*\[\s*\])*)?\s*", return_type)
        if genuine and span["body"] is not None and supported_return:
            declarations[symbol["name"]] = symbol
            if genuine.group("default"):
                inline_defaults.append(symbol)
            elif genuine.group("export"):
                symbol["exported"] = True
        elif inline_variable:
            # Preserve the existing explicit named arrow/function binding path.
            symbol["exported"] = True
            name = symbol["name"]
            occurrences = write_occurrences[name]
            if (len(occurrences) == 1 and occurrences[0].start("name") == span["name_start"]
                    and name not in scope_blocked):
                blocked.discard(name)
    default_prefix = re.compile(r"export\s+(?:default\b|\{[^;{}]*(?:\bdefault\b|\0)|\*\s+as\s+(?:default\b|\0))")
    defaults = [m for m in export_tokens if m.start() in empty_prefixes and default_prefix.match(code, m.start())]
    if len(defaults) == 1:
        match = re.compile(rf"export\s+default\s+({IDENT})\s*;").match(code, defaults[0].start())
        if match and match.group(1) in declarations:
            declarations[match.group(1)]["default_export"] = True
        elif len(inline_defaults) == 1:
            inline_defaults[0]["default_export"] = True
    for symbol in symbols:
        if not (symbol.get("exported") or symbol.get("default_export")):
            continue
        name = symbol["name"]
        if name in blocked or any(re.search(rf"(?<![\w$]){re.escape(name)}(?![\w$])", text) for text in templates):
            symbol["exported"] = symbol["default_export"] = False


def parse_polyglot(path: str, source: str, module: str, language: str, config: dict | None = None) -> dict:
    config = config or {}
    fidelity = fidelity_for(language, config)
    line_starts = [0] + [m.end() for m in re.finditer("\n", source)]
    line = lambda offset: bisect_right(line_starts, offset)
    module_id = f"{path}::module"
    symbols = [dict(id=module_id, path=path, module=module, name=module.rsplit(".", 1)[-1],
                    qualname=module, kind="module", start_line=1, end_line=max(1, len(source.splitlines())),
                    signature="", doc="", parent_id=None, language=language, fidelity=fidelity,
                    confidence="text" if fidelity == "text" else "heuristic")]
    result = dict(path=path, module=module, language=language, fidelity=fidelity,
                  symbols=symbols, imports=[], references=[], scopes={}, diagnostics=[])
    if fidelity == "text":
        result["analysis_note"] = "Text module only; declaration and call semantics are unavailable."
        return result
    result["analysis_note"] = "Lexical heuristics; receiver dispatch, macros, overloads and external packages are unresolved."
    # TypeScript only permits JSX in .tsx; angle assertions in .ts/.mts/.cts
    # must remain ordinary code even if a later string resembles a close tag.
    masked, literals = mask_source(source, language,
                                   jsx=language != 'typescript' or PurePosixPath(path).suffix.lower() == '.tsx')
    braces = _braces(masked)
    candidates, seen = [], set()
    for kind, pattern in _patterns(language, config):
        flags = re.MULTILINE | (re.IGNORECASE if language in {"sql", "cobol", "fortran", "pascal", "ada"} else 0)
        for match in re.finditer(pattern, masked, flags):
            name = match.group("name")
            name_start = match.start("name")
            if name_start in seen or name in CONTROL_WORDS:
                continue
            seen.add(name_start)
            header_end = masked.find("\n", match.end())
            header_end = len(masked) if header_end < 0 else header_end
            # Find a body through balanced multiline parameter lists. A type
            # alias or prototype ends at its semicolon and does not own a body.
            cursor, parentheses, body = match.end(), match.group().count("(") - match.group().count(")"), None
            while cursor < len(masked) and cursor - match.end() < 2000:
                char = masked[cursor]
                if char == "(":
                    parentheses += 1
                elif char == ")":
                    parentheses -= 1
                elif char == "{" and parentheses <= 0:
                    body = cursor
                    break
                elif char == ";" and parentheses <= 0:
                    break
                elif char == "\n" and parentheses <= 0:
                    # A brace may start the following line; do not consume a
                    # later unrelated declaration or statement as this body.
                    next_nonspace = cursor + 1
                    while next_nonspace < len(masked) and masked[next_nonspace].isspace():
                        next_nonspace += 1
                    if next_nonspace < len(masked) and masked[next_nonspace] == "{":
                        body = next_nonspace
                    break
                cursor += 1
            end = braces.get(body, header_end) if body is not None else header_end
            if body is None and language in {"ruby", "crystal", "elixir", "lua", "julia"}:
                closing = re.search(r"(?m)^\s*end\b", masked[header_end:])
                if closing:
                    end = header_end + closing.end()
            candidates.append(dict(name=name, kind=kind, start=match.start(), name_start=name_start,
                                   header_end=body if body is not None else (match.end() if "=>" in match.group() else header_end),
                                   body=body, end=max(end, match.end())))
    if language in {"javascript", "typescript"}:
        method_pattern = rf"(?:^|(?<=[;{{}}]))[ \t]*(?:(?:public|private|protected|static|async|get|set|abstract|override)\s+)*(?P<name>{IDENT})\s*(?:<[^;{{}}\n]*>)?\s*\([^;{{}}]*\)\s*(?::[^{{;\n]+)?\s*(?=\{{)"
        for match in re.finditer(method_pattern, masked, re.MULTILINE):
            name_start, name = match.start("name"), match.group("name")
            containers = [c for c in candidates if c["body"] is not None and c["body"] < name_start < c["end"]]
            parent = min(containers, key=lambda c: c["end"] - c["start"]) if containers else None
            if (name_start in seen or name in CONTROL_WORDS or not parent
                    or parent["kind"] not in {"class", "interface"}):
                continue
            body = masked.find("{", match.end())
            if body not in braces:
                continue
            seen.add(name_start)
            candidates.append(dict(name=name, kind="function", start=match.start(), name_start=name_start,
                                   header_end=body, body=body, end=braces[body]))
    candidates.sort(key=lambda c: (c["name_start"], -c["end"]))
    counts, spans = defaultdict(int), []
    for candidate in candidates:
        parents = [s for s in spans if s["body_start"] <= candidate["name_start"] < s["end"]]
        parent = min(parents, key=lambda s: s["end"] - s["start"]) if parents else None
        parent_id = parent["id"] if parent else module_id
        prefix = parent["qualname"] + "." if parent else ""
        kind = candidate["kind"]
        if kind == "function" and parent and parent["kind"] in {"class", "struct", "interface", "trait", "implementation"}:
            kind = "method"
        if language == "go" and kind == "function" and re.search(r"\bfunc\s*\(", masked[candidate["start"]:candidate["name_start"]]):
            kind = "method"
        qualname = prefix + candidate["name"]
        base = f"{path}::{qualname}:{kind}"
        counts[base] += 1
        key = base + (f"#{counts[base]}" if counts[base] > 1 else "")
        signature = " ".join(source[candidate["start"]:candidate["header_end"]].split())[:300]
        symbol = dict(id=key, path=path, module=module, name=candidate["name"], qualname=qualname,
                      kind=kind, parent_id=parent_id, start_line=line(candidate["name_start"]),
                      end_line=line(max(candidate["name_start"], candidate["end"] - 1)),
                      signature=signature, doc="", language=language, fidelity="heuristic", confidence="heuristic")
        # JS export bindings are checked after lexical scopes/imports exist.
        declaration_line = source[line_starts[line(candidate["name_start"]) - 1]:candidate["name_start"]]
        symbol["exported"] = language not in {"javascript", "typescript"} and bool(re.search(r"\bexport\b", declaration_line))
        symbol["default_export"] = language not in {"javascript", "typescript"} and bool(re.search(r"\bexport\s+default\b", declaration_line))
        symbols.append(symbol)
        spans.append(dict(candidate, id=key, qualname=qualname, kind=kind,
                          body_start=(candidate["body"] + 1) if candidate["body"] is not None else candidate["header_end"]))

    def owner(offset):
        containing = [span for span in spans if span["body_start"] <= offset < span["end"]]
        return min(containing, key=lambda span: span["end"] - span["start"])["id"] if containing else module_id

    scopes = {s["id"]: {"parent": s["parent_id"], "blocked": []} for s in symbols}
    blocked = defaultdict(set)
    for span in spans:
        if span["kind"] in {"function", "method"}:
            header = masked[span["name_start"] + len(span["name"]):span["header_end"]]
            if "(" in header:
                parameters = header[header.find("(") + 1:header.rfind(")")]
                blocked[span["id"]].update(re.findall(IDENT, parameters))
            elif "=>" in header:
                blocked[span["id"]].update(re.findall(IDENT, header.split("=>")[0]))
    # Assignment and local bindings conservatively shadow within their owner.
    binding_pattern = rf"\b(?:let|const|var|val|auto|local|catch)\s+(?:mut\s+)?(?P<name>{IDENT})|\b(?P<assigned>{IDENT})\s*(?::=|=(?!=|>))"
    for match in re.finditer(binding_pattern, masked):
        name = match.group("name") or match.group("assigned")
        # A named arrow declaration is itself the callable binding.
        if any(s["name_start"] == match.start(match.lastgroup) for s in spans):
            continue
        blocked[owner(match.start())].add(name)
    for match in re.finditer(r"\(([^(){};]*)\)\s*=>|\b([A-Za-z_$][\w$]*)\s*=>", masked):
        blocked[owner(match.start())].update(re.findall(IDENT, match.group(1) or match.group(2) or ""))
    for match in re.finditer(r"\b(?:int|char|bool|float|double|string|String|long|short|size_t)\s+([A-Za-z_$][\w$]*)\s*(?:[;=,)]|\[)", masked):
        blocked[owner(match.start())].add(match.group(1))
    # Destructuring/pattern bindings, catch parameters and loop variables can
    # hide an outer function without a simple identifier assignment.
    for match in re.finditer(r"\b(?:let|const|var|for|catch)\s*[({]([^;{}\n]+)[)}]|\bfor\s+(\w+)\s+in\b|\b([A-Za-z_$][\w$]*(?:\s*,\s*[A-Za-z_$][\w$]*)+)\s*:=", masked):
        binding = next(group for group in match.groups() if group is not None)
        blocked[owner(match.start())].update(re.findall(IDENT, binding))
    for key in scopes:
        scopes[key]["blocked"] = sorted(blocked[key])
    result["scopes"] = scopes
    imports = _imports(path, source, masked, literals, language, module_id, line)
    result["imports"] = imports
    if language in CALL_LANGUAGES:
        for match in re.finditer(rf"\b(?P<name>{IDENT}(?:(?:\.|::|->){IDENT})*)\s*\(", masked):
            name = match.group("name")
            previous = match.start() - 1
            while previous >= 0 and masked[previous].isspace():
                previous -= 1
            prefix = masked[max(0, previous - 1):previous + 1]
            if prefix.endswith((".", "::", "->", "$")):
                name = "<receiver>." + name
            if name in CONTROL_WORDS or match.start("name") in seen:
                continue
            # Parameter type expressions and declaration headers are not calls.
            if any(s["start"] <= match.start() < s["body_start"] for s in spans):
                continue
            result["references"].append(dict(source=owner(match.start()), scope_id=owner(match.start()),
                                             kind="calls", name=name, path=path, line=line(match.start()),
                                             evidence=" ".join(source[match.start():min(len(source), match.end()+100)].split())[:180],
                                             resolved=False))
    if re.search(r"\b(?:eval|with)\s*\(", masked):
        result["dynamic_scope"] = True
    if language in {"javascript", "typescript"}:
        _js_export_bindings(masked, literals, symbols, spans, scopes, imports, result.get("dynamic_scope", False))
    return result


def _imports(path, source, masked, literals, language, module_id, line):
    imports = []
    for literal in literals:
        text = literal["text"]
        if not text.startswith(("'", '"')) or text[:1] != text[-1:] or "\n" in text:
            continue
        target = text[1:-1]
        # Only import syntax outside strings/comments may introduce a link.
        start = max(masked.rfind(";", 0, literal["start"]), masked.rfind("\n", 0, literal["start"])) + 1
        prefix = masked[start:literal["start"]].strip()
        if language in {"javascript", "typescript"}:
            window_start = max(0, literal["start"] - 2000)
            starters = list(re.finditer(r"\b(?:import|export)\b", masked[window_start:literal["start"]]))
            if starters:
                proposed = window_start + starters[-1].start()
                if ";" not in masked[proposed:literal["start"]]:
                    start, prefix = proposed, masked[proposed:literal["start"]].strip()
        binding, names = None, {}
        valid = False
        if language in {"javascript", "typescript"}:
            valid = bool(re.match(r"(?:import|export)\b", prefix) and (re.search(r"\bfrom\s*$", prefix) or prefix == "import"))
            if not valid and re.search(r"\brequire\s*\(\s*$", prefix):
                valid = True
            if valid and prefix.startswith("import"):
                clause = re.sub(r"^import\s+|\s+from\s*$", "", prefix)
                if brace := re.search(r"\{([^{}]+)\}", clause):
                    for item in brace.group(1).split(","):
                        entry = re.fullmatch(r"\s*(?:type\s+)?(\w+)(?:\s+as\s+(\w+))?\s*", item)
                        if entry:
                            names[entry.group(2) or entry.group(1)] = entry.group(1)
                if namespace := re.search(r"\*\s+as\s+(\w+)", clause):
                    binding = namespace.group(1)
                if default := re.match(r"([A-Za-z_$][\w$]*)\s*(?:,|$)", clause):
                    names[default.group(1)] = "default"
        elif language in {"c", "cpp", "objective-c"}:
            valid = bool(re.fullmatch(r"#\s*(?:include|import)", prefix))
        elif language in {"ruby", "crystal"}:
            valid = bool(re.search(r"\brequire_relative\s*\(?\s*$", prefix))
        elif language == "php":
            valid = bool(re.search(r"\b(?:require|include)(?:_once)?\s*\(?\s*$", prefix))
        elif language == "dart":
            valid = bool(re.match(r"(?:import|export|part)\s*$", prefix))
        elif language == "go":
            valid = bool(re.match(r"import\s+(?:\w+\s+)?$", prefix + " "))
            if not valid:
                before = masked[:literal["start"]]
                opening = before.rfind("import")
                valid = opening >= 0 and bool(re.fullmatch(r"import\s*\([^)]*", before[opening:], re.DOTALL))
        if valid:
            imports.append(dict(source=module_id, path=path, line=line(literal["start"]),
                                module=target, names=names, alias=binding, resolved=False,
                                evidence=" ".join(source[start:literal["end"]].split())[:240]))
    if language == "rust":
        for match in re.finditer(r"\bmod\s+(\w+)\s*;", masked):
            imports.append(dict(source=module_id, path=path, line=line(match.start()),
                                module=match.group(1), rust_mod=True, names={}, alias=None,
                                resolved=False, evidence=match.group()))
    namespace_pattern = {"rust": r"\buse\s+([A-Za-z_][\w:]*)\s*;",
                         "swift": r"\bimport\s+([A-Za-z_][\w.]*)",
                         "csharp": r"\busing\s+(?:static\s+)?([A-Za-z_][\w.]*)\s*;"}.get(language)
    if namespace_pattern:
        for match in re.finditer(namespace_pattern, masked):
            imports.append(dict(source=module_id, path=path, line=line(match.start()),
                                module=match.group(1), namespace=True, names={}, alias=None,
                                resolved=False, evidence=match.group()))
    for number, imported in enumerate(imports, 1):
        imported["id"] = f"{path}::import:{number}"
    return imports


def _module_target(file, imported, files):
    target, path = imported["module"], PurePosixPath(file["path"])
    language = file["language"]
    if imported.get("namespace"):
        return None
    if language in {"javascript", "typescript", "dart"} and not target.startswith("."):
        return None
    if language == "go" and not target.startswith("."):
        return None
    if imported.get("rust_mod"):
        folder = path.parent if path.name in {"lib.rs", "main.rs", "mod.rs"} else path.with_suffix("")
        stem = (folder / target).as_posix()
        variants = [stem + ".rs", stem + "/mod.rs"]
    else:
        stem = posixpath.normpath((path.parent / target).as_posix())
        if stem == ".." or stem.startswith("../") or stem.startswith("/"):
            return None
        variants = [stem]
        if language in {"javascript", "typescript"}:
            variants += [stem + suffix for suffix in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".mts", ".cjs", ".cts")]
            variants += [stem + "/index" + suffix for suffix in (".js", ".jsx", ".ts", ".tsx")]
        elif language in {"ruby", "crystal"}:
            variants += [stem + ".rb", stem + ".cr"]
    candidates = [files[variant] for variant in set(variants) if variant in files]
    return candidates[0] if len(candidates) == 1 else None


def resolve_polyglot(parsed_files: list[dict]) -> list[dict]:
    files = {file["path"]: file for file in parsed_files}
    edges = []
    for file in parsed_files:
        symbols = {symbol["id"]: symbol for symbol in file["symbols"]}
        visible = defaultdict(list)
        imports_by_name = defaultdict(list)
        scopes = file.get("scopes", {})
        for symbol in file["symbols"]:
            if symbol["parent_id"]:
                visible[(symbol["parent_id"], symbol["name"])].append(symbol)
                edges.append(dict(source=symbol["parent_id"], target=symbol["id"], kind="contains",
                                  confidence="heuristic", evidence=symbol["signature"], path=file["path"],
                                  line=symbol["start_line"]))
        for imported in file["imports"]:
            imported.pop("target", None)
            imported["resolved"] = False
            target_file = _module_target(file, imported, files)
            if target_file:
                target = f"{target_file['path']}::module"
                imported.update(target=target, resolved=True)
                edges.append(dict(source=imported["source"], target=target, kind="imports",
                                  confidence="heuristic", evidence=imported["evidence"], path=file["path"],
                                  line=imported["line"]))
            for alias, name in imported.get("names", {}).items():
                candidates = [] if not target_file else [s for s in target_file["symbols"]
                              if s["parent_id"] == f"{target_file['path']}::module" and
                              ((name == "default" and s.get("default_export")) or
                               (name == s["name"] and s.get("exported")))]
                # Include unresolved imports as blocking bindings; another local
                # symbol with the same name must not silently win.
                imports_by_name[alias].append(candidates[0] if len(candidates) == 1 else None)
            if imported.get("alias"):
                imports_by_name[imported["alias"]].append(None)
        for reference in file["references"]:
            reference.pop("target", None)
            reference.pop("confidence", None)
            reference["resolved"] = False
            name, scope, target = reference["name"], reference["scope_id"], None
            if re.fullmatch(IDENT, name) and not file.get("dynamic_scope"):
                while scope:
                    if name in scopes.get(scope, {}).get("blocked", []):
                        break
                    candidates = visible.get((scope, name), [])
                    if scope == f"{file['path']}::module":
                        candidates = candidates + imports_by_name.get(name, [])
                    if candidates:
                        if len(candidates) == 1 and candidates[0] and candidates[0]["kind"] == "function":
                            target = candidates[0]["id"]
                        break
                    scope = symbols.get(scope, {}).get("parent_id")
            if target:
                reference.update(target=target, resolved=True, confidence="heuristic")
                reference.pop("reason", None)
                edges.append(dict(source=reference["source"], target=target, kind="calls", confidence="heuristic",
                                  evidence=reference["evidence"], path=file["path"], line=reference["line"]))
            else:
                reference["reason"] = "receiver, dynamic, external, shadowed, ambiguous or unsupported lexical binding"
    unique = {(e["source"], e["target"], e["kind"], e["path"], e["line"]): e for e in edges}
    return sorted(unique.values(), key=lambda e: (e["path"], e["line"], e["kind"], e["source"], e["target"]))
