---
title: Language detection and graph fidelity
source: ../scripts/repoatlas/language_profiles.py
last_fetched: 2026-09-07
skills: [repoatlas-jvm]
---

# Language coverage

RepoAtlas detects language from suffixes, conventional filenames, shebangs, and explicit extension mappings. A repository may contain any mixture. Language detection is separate from semantic fidelity:

- `ast`: Python's built-in AST; Java/Kotlin Tree-sitter grammars. Name resolution is still conservative, especially dynamic dispatch and JVM overloads.
- `heuristic`: lexical declaration patterns for common languages, including JavaScript/TypeScript, Go, Rust, C/C++, C#, Ruby, PHP, Swift, Dart and additional profiles. Comments/strings are masked for declaration extraction. Imports and uniquely resolvable local calls are candidates. Type checking, generated bindings, macro expansion, DI, and arbitrary runtime dispatch are not implemented.
- `text`: one file/module node and full-file lexical search for other UTF-8 text. No invented function/call graph. This keeps unknown languages navigable and exportable.

Inspect each symbol's `fidelity`, each edge's `confidence`, and `status` diagnostics. The complete detected-language registry is in `language_profiles.py`; recognized extensions do not imply equal parser accuracy.

## Custom languages

Add a repository-owned `.repoatlas.json`:

```json
{
  "include": ["src/*", "lib/*"],
  "exclude": ["**/generated/*"],
  "extensions": {".acme": "acme"},
  "declarations": {"acme": ["procedure", "routine"]}
}
```

Keywords are literal declaration prefixes followed by an identifier. They are not regexes or executable plugins. Custom extraction is heuristic. Configuration is size/shape validated, included in the analyzer fingerprint, and changing it invalidates the index. `.repoatlasignore` remains supported.

Git discovery respects untracked ignores, and excludes symlinks, known secret files, binary suffixes, dependency/build directories and files above 1 MB. Unknown suffixes are probed for UTF-8 text; `inventory.probe_files/probe_bytes` expose this work. Known languages avoid discovery body probes. Ignored control files are still tracked as index configuration. Binary or invalid encoded known source causes sync to fail rather than returning an apparently fresh graph.

## 리뷰 훅

- Is detected language distinguished from AST/heuristic/text fidelity?
- Is custom configuration declarative, bounded, and fingerprinted?
- Are unknown text, binary exclusions, and unresolved relationships visible?
