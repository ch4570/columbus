"""Language dispatch and the parser/configuration versions defining a snapshot."""
from __future__ import annotations

from importlib import metadata
from pathlib import Path
import json
import platform

from .discovery import decode_python, digest
from .language_profiles import language_for, fidelity_for
from . import parser
from . import __version__

ANALYZER_VERSION = f"columbus-{__version__}"
JVM_DEPENDENCIES = {"tree-sitter": "0.26.0", "tree-sitter-java": "0.23.5",
                    "tree-sitter-kotlin": "1.1.0"}


def decode_source(path: str, data: bytes, *, config: dict | None = None,
                  language: str | None = None) -> str:
    if b"\0" in data:
        raise ValueError(f"Binary source is excluded: {path}")
    language = language or language_for(path, data[:8192].decode("utf-8-sig", errors="replace"), config)
    return decode_python(data) if language == "python" else data.decode("utf-8-sig")


def code_lines(source: str, language: str | None = None) -> list[str]:
    """Source coordinates use physical newlines, not Unicode text separators."""
    source = source.replace('\r\n', '\n')
    if language not in {'java', 'kotlin'}:
        source = source.replace('\r', '\n')
    lines = source.split('\n')
    return lines[:-1] if lines[-1] == '' else lines


def analyzer_fingerprint(paths: list[str], config: dict | None = None,
                         detected_languages: dict[str, str] | None = None) -> dict:
    """Missing JVM dependencies fail sync before any graph mutation."""
    from . import discovery, language_profiles, polyglot
    detected_languages = detected_languages or {}
    languages = sorted({detected_languages.get(path) or language_for(path, config=config) for path in paths})
    versions = {"engine": ANALYZER_VERSION, "python_ast": platform.python_version()}
    analyzer_files = [Path(module.__file__) for module in (parser, discovery, language_profiles, polyglot)]
    analyzer_files.extend([Path(__file__), Path(__file__).with_name("index.py"),
                           Path(__file__).with_name("parse_cache.py")])
    if any(language in {"kotlin", "java"} for language in languages):
        for package, expected in JVM_DEPENDENCIES.items():
            try:
                versions[package] = metadata.version(package)
            except metadata.PackageNotFoundError as exc:
                raise RuntimeError(f"JVM analyzer dependency missing: {package}. "
                                   f"Install the bundled parser requirements ({package}=={expected}) and retry sync.") from exc
        from . import jvm
        analyzer_files.append(Path(jvm.__file__))
    versions["analyzer_code"] = digest(b"\n".join(path.read_bytes() for path in analyzer_files))[:20]
    versions["language_config"] = digest(json.dumps(config or {}, sort_keys=True, separators=(",", ":")).encode())[:20]
    return {"languages": languages, "versions": versions,
            "fidelity": {language: fidelity_for(language, config) for language in languages}}


def parse_source(path: str, source: str, module: str = "", *, config: dict | None = None,
                 language: str | None = None) -> dict:
    language = language or language_for(path, source, config)
    if language == "python":
        result = parser.parse_source(path, source, module)
    elif language in {"java", "kotlin"}:
        from .jvm import parse_jvm
        result = parse_jvm(path, source, module)
    else:
        from .polyglot import parse_polyglot
        return parse_polyglot(path, source, module, language, config)
    result["language"] = language
    result["fidelity"] = "ast"
    # Python resets failed parses to a file node; that node is still an
    # incomplete AST view, just like a JVM recovery node.
    result["partial"] = bool(result.get("partial") or result.get("diagnostics"))
    for symbol in result["symbols"]:
        symbol["language"] = language
        symbol["fidelity"] = "ast"
        symbol["partial"] = result["partial"]
    return result


def resolve_files(parsed_files: list[dict]) -> list[dict]:
    python_files = [file for file in parsed_files if file.get("language", "python") == "python"]
    jvm_files = [file for file in parsed_files if file.get("language") in {"kotlin", "java"}]
    polyglot_files = [file for file in parsed_files if file.get("language", "python") not in {"python", "java", "kotlin"}]
    edges = parser.resolve_files(python_files) if python_files else []
    if jvm_files:
        from .jvm import resolve_jvm
        edges.extend(resolve_jvm(jvm_files))
    if polyglot_files:
        from .polyglot import resolve_polyglot
        edges.extend(resolve_polyglot(polyglot_files))
    return sorted(edges, key=lambda edge: (edge["source"], edge["target"], edge["kind"], edge.get("line", 0)))
