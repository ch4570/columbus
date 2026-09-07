# Language coverage

[Overview](../README.md) · [CLI usage](usage.md) · [Analyzer contract](../skills/columbus/references/polyglot.md)

Columbus recognizes mixed-language repositories without requiring a build. Detection uses extensions, conventional filenames, shebangs, and explicit repository mappings. **Detection and semantic analysis are separate capabilities.**

## Capability matrix

| Level | Coverage | What the graph can represent |
| --- | --- | --- |
| `ast` | Python, Java, Kotlin | Parsed declarations and containment, conservative imports, inheritance, and calls |
| `heuristic` | 43 declared language profiles | Lexically detected declarations and relationships supported by local evidence |
| `text` | Remaining detected profiles and other eligible UTF-8 text | File/module nodes, full-text search, and located source excerpts |

There are 66 extension-based profiles in the [language registry](../skills/columbus/scripts/columbus/language_profiles.py). Conventional filenames and custom mappings can add language labels. That count is not 66 complete parsers. Inspect `fidelity` on symbols, `confidence` on relationships, and unresolved references and diagnostics in the index.

### AST analysis

Python uses the standard-library AST. Java and Kotlin use pinned Tree-sitter grammars. Parsed syntax does not resolve all runtime semantics: dynamic dispatch, overloads, reflection, dependency injection, and generated code can remain unresolved. An AST-backed graph is not a compiler's complete type or call graph.

### Heuristic analysis

The declared profiles are:

| Group | Profiles |
| --- | --- |
| Web and application | JavaScript, TypeScript, C#, Ruby, PHP, Swift, Dart, Scala, Groovy, Crystal, Apex |
| Systems | Go, Rust, C, C++, Zig, Nim, D, V, Odin, Ada, Pascal |
| Scripting and functional | Shell, PowerShell, Lua, R, Julia, Elixir, Erlang, Haskell, OCaml, F#, Clojure, Lisp, Perl |
| Domain languages | Fortran, COBOL, Solidity, SQL, GraphQL, Protocol Buffers, Terraform, Nix |

Comments and strings are masked before extracting declarations. Supported local imports and uniquely resolvable calls may become relationship candidates. Patterns differ by language; an import or call rule for one profile does not imply the same rule exists for every profile. Macros, arbitrary package resolution, generated bindings, and runtime receiver types are not resolved.

### Text coverage

Recognized document, configuration, markup, and other text profiles remain searchable even when no declaration parser is available. Eligible unknown extensions also receive a file node. For example, a custom workflow file can be searched and exported as a file graph without inventing function calls.

Some familiar source labels, including Vue, Svelte, Objective-C, and Visual Basic, currently use text-level fallback. Inspect the actual `fidelity` rather than assuming a declaration parser from the filename.

## Add a repository language rule

Create `.columbus.json` at the repository root:

```json
{
  "include": ["src/*", "lib/*"],
  "exclude": ["**/generated/*"],
  "extensions": {".acme": "acme"},
  "declarations": {"acme": ["procedure", "routine"]}
}
```

`include` is optional; omit it to scan all eligible paths. Extension mappings use dotted suffixes and lowercase language names. A declaration keyword is a literal prefix followed by an identifier. Custom extraction is heuristic. These settings are bounded declarative data, not executable plugins or arbitrary regexes.

Changing the configuration invalidates the analysis fingerprint and refreshes the index. `.columbusignore` remains supported for additional exclusion patterns. The included [polyglot example](../examples/polyglot-demo/README.md) demonstrates an extension mapping for a small workflow language.

## Discovery boundaries

Git discovery includes tracked and untracked files while respecting untracked ignore rules. If Git is unavailable, Columbus walks the filesystem. Both paths exclude dependency/build directories, symlinks, known secret filenames, binary suffixes, and files larger than 1,000,000 bytes.

There is one explicit-root exception: if the selected `--repo` directory is itself ignored by an enclosing Git repository and Git returns no files, Columbus walks that selected directory instead. This makes an intentionally selected copy under an ignored temporary directory discoverable. It does not unignore ordinary files when scanning their Git repository root. The fallback still applies Columbus's built-in exclusions, `.columbusignore`, and `.columbus.json` filters; its enumeration mode is reported in inventory metadata.

Unknown extensions may need content probes to identify UTF-8 text. This work is visible as `inventory.probe_files` and `inventory.probe_bytes`. Known extensions avoid discovery body probes. A warm metadata-based sync is therefore not a promise of zero filesystem reads for every repository.

The exclusion list is not a secret scanner. Sensitive content in an ordinary source filename may still be indexed; configure repository exclusions accordingly. Invalid or binary content in known source files can cause synchronization to fail rather than producing an apparently fresh index.

## Contribute a language improvement

Add a small fixture that demonstrates the useful declaration or relationship and a negative case that could be mistaken for code, such as a comment or string. Keep unresolved behavior explicit. See [contributing](../CONTRIBUTING.md) and the existing [polyglot tests](../skills/columbus/scripts/tests/test_polyglot.py).
