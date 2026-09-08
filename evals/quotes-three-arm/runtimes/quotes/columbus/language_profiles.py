"""Dependency-free language detection; unrecognized text remains navigable."""
from __future__ import annotations

from pathlib import Path
import re
import shlex

EXTENSIONS = {
    "python": "py pyi pyw", "java": "java", "kotlin": "kt kts",
    "javascript": "js jsx mjs cjs", "typescript": "ts tsx mts cts",
    "go": "go", "rust": "rs", "c": "c h", "cpp": "cc cpp cxx c++ hpp hxx hh ipp",
    "csharp": "cs csx", "ruby": "rb rake gemspec", "php": "php phtml php3 php4 php5",
    "swift": "swift", "dart": "dart", "scala": "scala sc", "groovy": "groovy gvy",
    "shell": "sh bash zsh fish ksh", "powershell": "ps1 psm1 psd1",
    "lua": "lua", "r": "r rmd", "julia": "jl", "elixir": "ex exs",
    "erlang": "erl hrl", "haskell": "hs lhs", "ocaml": "ml mli",
    "fsharp": "fs fsi fsx", "clojure": "clj cljs cljc edn", "lisp": "lisp lsp cl el scm ss rkt",
    "perl": "pl pm t", "raku": "raku rakumod", "zig": "zig", "nim": "nim nims",
    "crystal": "cr", "d": "d di", "fortran": "f f90 f95 f03 f08 for f77",
    "cobol": "cob cbl cpy", "pascal": "pas pp", "ada": "ada adb ads",
    "objective-c": "m mm", "solidity": "sol", "v": "v vv", "odin": "odin",
    "assembly": "s asm", "verilog": "sv svh vh", "vhdl": "vhd vhdl",
    "vue": "vue", "svelte": "svelte", "html": "html htm", "css": "css scss sass less",
    "sql": "sql", "graphql": "graphql gql", "protobuf": "proto", "terraform": "tf tfvars hcl",
    "json": "json jsonc json5", "yaml": "yaml yml", "toml": "toml",
    "xml": "xml xsd xsl xslt csproj fsproj vbproj props targets resx",
    "markdown": "md mdx markdown rst adoc", "text": "txt text csv tsv ini cfg conf properties",
    "cmake": "cmake", "make": "mk mak", "dockerfile": "dockerfile", "nix": "nix",
    "batch": "bat cmd", "visual-basic": "vb vbs", "apex": "cls trigger",
}
EXTENSION_LANGUAGES = {"." + ext: language for language, extensions in EXTENSIONS.items()
                       for ext in extensions.split()}
NAME_LANGUAGES = {
    "Dockerfile": "dockerfile", "Containerfile": "dockerfile", "Makefile": "make",
    "GNUmakefile": "make", "CMakeLists.txt": "cmake", "Jenkinsfile": "groovy",
    "Gemfile": "ruby", "Rakefile": "ruby", "Vagrantfile": "ruby", "Brewfile": "ruby",
    "Justfile": "make", "justfile": "make", "BUILD": "python", "BUILD.bazel": "python",
    "WORKSPACE": "python", "WORKSPACE.bazel": "python", "go.mod": "go-module",
    "go.sum": "go-module", ".bashrc": "shell", ".zshrc": "shell", ".profile": "shell",
}
SHEBANG_LANGUAGES = {
    "python": "python", "python3": "python", "python2": "python",
    "node": "javascript", "nodejs": "javascript", "deno": "typescript", "bun": "javascript",
    "ruby": "ruby", "perl": "perl", "raku": "raku", "php": "php", "lua": "lua",
    "bash": "shell", "sh": "shell", "zsh": "shell", "fish": "shell", "ksh": "shell",
    "pwsh": "powershell", "Rscript": "r", "julia": "julia", "elixir": "elixir",
    "escript": "erlang", "runghc": "haskell", "swift": "swift",
}
HEURISTIC_LANGUAGES = {
    "javascript", "typescript", "go", "rust", "c", "cpp", "csharp", "ruby", "php",
    "swift", "dart", "scala", "groovy", "shell", "powershell", "lua", "r", "julia",
    "elixir", "erlang", "haskell", "ocaml", "fsharp", "clojure", "lisp", "perl",
    "zig", "nim", "crystal", "d", "fortran", "cobol", "pascal", "ada", "solidity",
    "v", "odin", "sql", "graphql", "protobuf", "terraform", "nix", "apex",
}


def language_for(path: str, source: str | None = None, config: dict | None = None) -> str:
    """Explicit extension mappings win; unknown UTF-8 content uses a text module."""
    name, suffix = Path(path).name, Path(path).suffix
    overrides = (config or {}).get("extensions", {})
    if suffix.lower() in overrides:
        return overrides[suffix.lower()]
    if name in NAME_LANGUAGES:
        return NAME_LANGUAGES[name]
    if suffix == ".C":
        return "cpp"
    if suffix.lower() in EXTENSION_LANGUAGES:
        return EXTENSION_LANGUAGES[suffix.lower()]
    if source and source.startswith("#!"):
        try:
            command = shlex.split(source.splitlines()[0][2:])
        except ValueError:
            command = []
        if command:
            executable = Path(command[0]).name
            if executable == "env":
                # env -S and ordinary env arguments; skip flags and assignments.
                executable = next((Path(part).name for part in command[1:]
                                   if not part.startswith("-") and "=" not in part), "")
            if re.fullmatch(r"python[23](?:\.\d+)?", executable):
                return "python"
            if executable in SHEBANG_LANGUAGES:
                return SHEBANG_LANGUAGES[executable]
    return "text"


def fidelity_for(language: str, config: dict | None = None) -> str:
    if language in {"python", "java", "kotlin"}:
        return "ast"
    if language in HEURISTIC_LANGUAGES or (config or {}).get("declarations", {}).get(language):
        return "heuristic"
    return "text"
