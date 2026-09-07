# Graphify comparison and reliability findings

This investigation compares Columbus `9a4108d` with Graphify-Labs/graphify `c9f99018774e2e0380e9f65b3959944559a0d5f6` (0.9.55). It supports the subsequent AST workflow work; it is not a claim that Graphify is a correctness oracle or that either tool provides compiler-equivalent call graphs.

The reproducible [probe](probe.py) runs nine source-based Java cases. [Columbus results](results/columbus.json) and [Graphify results](results/graphify.json) preserve emitted targets, source fixtures, confidence labels and diagnostics. Oracles follow Java scope/shadowing and overload rules ([JLS 6.4.1](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.4.1), [JLS 15.12.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.2)). A JDK was not installed on the observation host: these were not compiler-backed measurements.

| Case | Columbus | Graphify |
| --- | --- | --- |
| `this.hit()` | Missing | Expected declaration |
| Explicit `Box<String>` receiver | Missing | Expected declaration |
| Enhanced-for receiver | Missing | Missing |
| Explicit parameter receiver | Expected declaration | Expected declaration |
| External imported type vs unrelated same-name local type | Correctly abstains | **Wrong package target** |
| Type parameter T shadows concrete class T | **Wrong concrete T target** | Abstains |
| Inherited `hit(int)` vs subclass `hit(String)` | **Wrong subclass target** | **Wrong subclass target** |
| Parameter shadows field | Expected interface declaration | Expected interface declaration |
| Good method in file with annotated-varargs recovery | Whole-file suppression | Expected call, no failed-source diagnostic |

Both engines fail the `--require-safe` gate (exit 1) because each emits two forbidden targets in this deliberately adversarial fixture set. This small set is not a representative precision/recall estimate. Ordinary probe mode records findings without asserting product safety. Graphify's wrong-package edge is `INFERRED` with hard-coded score 0.8; its inherited-overload edge is `EXTRACTED`. Columbus labels its wrong edges `heuristic`. Labels do not repair an incorrect target.

## Why Columbus misses Graphify-like structure

1. Columbus's JVM resolver explicitly declines this/super, generic receivers and opaque loop/lambda/catch scopes. Its type lookup does not implement a Java type namespace or inherited overload applicability. Graphify has a separate method receiver table, generic-base extraction and additional language passes: see pinned [engine.py](https://github.com/Graphify-Labs/graphify/blob/c9f99018774e2e0380e9f65b3959944559a0d5f6/graphify/extractors/engine.py) and [extract.py](https://github.com/Graphify-Labs/graphify/blob/c9f99018774e2e0380e9f65b3959944559a0d5f6/graphify/extract.py). These add useful coverage but are still syntactic approximations.
2. Columbus drops resolution for entire partial files. Both installations used Java grammar 0.23.5, so a richer result does not establish better grammar correctness. Graphify's fixture extraction returned `failed_sources=[]` despite the recovery construct; absence of a failed-file result is not a parse-completeness proof.
3. The products expose different relations. Graphify's extraction also includes method ownership, references, implements and case_of; simply comparing total edges rewards different schemas. Its broader document/community/path workflows were inspected in source/docs but not benchmarked here. Its simplified [SCIP module](https://github.com/Graphify-Labs/graphify/blob/c9f99018774e2e0380e9f65b3959944559a0d5f6/graphify/scip_ingest.py) explicitly says it is not a full protobuf implementation and is not wired to the CLI; it must not be described as a compiler backend.
4. Columbus has snapshot/source-hash/budget guards, but its response evidence was incomplete. [Disclosure probe](results/diagnostic-disclosure.json) shows a partial search symbol losing `partial` in bounded context. Empty neighbors had `truncated=false` with no response-level semantic-completeness marker. The later portable AST change preserves partial metadata and adds semantic-completeness disclosure; it does not fix the false-target cases.

## Real spring-core census

Same Spring commit as [the earlier field evaluation](../spring-core/README.md). Graphify's code-only extractor ran against the same 1,091 Java and 34 Kotlin files, single process, no model calls. It produced 17,140 raw nodes and 60,445 raw edges, including 17,459 calls, in 19.15 seconds. There were 6,933 raw dangling endpoints. Calling its directed graph builder yielded 17,138 nodes and 50,778 edges; raw output and built graph are different stages. [Raw-stage census](results/graphify-corpus.json), [built-stage census](results/graphify-built.json), [environment pins](results/provenance.json).

Columbus's earlier 34,314 edges include 12,506 calls and a different declaration/containment schema. Its full index also includes non-code files, FTS, cached parse facts and transactional freshness metadata. The Graphify timing and 27.8 MB raw JSON are not comparable to Columbus's full SQLite lifecycle as speed or storage parity claims. Run [corpus.py](corpus.py) in the pinned Graphify environment to reproduce the extraction/build census; raw full-corpus output remains outside this repository to avoid duplicating Spring source.

The 199 MB Columbus SQLite breakdown is concrete: files table 95.2 MB, symbols 32.3 MB, FTS content 28.3 MB, edges 16.4 MB plus indexes. Cached parse JSON alone is 94.1 MB: references 51.4 MB, symbols 19.6 MB, scopes 17.8 MB and imports 4.9 MB. This is repeated verbose facts/IDs plus searchable content, not proof that SQLite itself is unsuitable. [Storage census](results/columbus-storage.json).

## Guardrails required before broader call resolution

- Keep type/value namespaces, packages, imports, type parameters, lexical scopes and overload signatures explicit in AST facts. Resolve only with the applicable evidence; preserve unresolved candidates and reasons.
- Treat AST containment, static declaration targets, possible runtime dispatch and retrieval-only suggestions as distinct relations. Source hashes prove freshness, not semantic validity. Confidence scores need calibration before being interpreted as probabilities.
- Preserve parse status and scope coverage in tree, context, neighbors and impact. Empty traversal does not establish that no caller exists. Display output truncation separately from parser and semantic incompleteness.
- Gate known wrong-target cases before optimizing recall. Keep positive tests alongside negatives so blanket abstention cannot masquerade as successful navigation. Add compiler-backed oracles for a larger corpus, changed/deleted dependencies, incremental/full parity and cache failure recovery.
- Keep source labels/comments untrusted, never execute repository code during indexing, preserve existing hooks, and distinguish framework-visible working-tree snapshots from Git staging contents.

The concrete false targets and required response guards are tracked in [issue #8](https://github.com/ch4570/columbus/issues/8). The new AST/pre-commit workflow makes declaration exploration portable; it does not close the call-resolution part of that issue.

## Reproduction

Use separate Python environments: Columbus uses tree-sitter 0.26.0 with byte-offset line handling; this Graphify revision constrains tree-sitter below 0.26 and installed 0.25.2. Full dependency and revision pins are in the provenance JSON.

```sh
.venv/bin/python evals/graphify-comparison/probe.py columbus --require-safe --output /tmp/columbus-probe.json
/path/to/graphify-env/bin/python evals/graphify-comparison/probe.py graphify --require-safe --output /tmp/graphify-probe.json
/path/to/graphify-env/bin/python evals/graphify-comparison/corpus.py --repo /path/to/spring-core --output /tmp/new-graphify-census
```

The two safety commands are expected to exit 1 on the recorded versions. The recorded source/JLS oracles and the broader corpus census serve different purposes; do not infer all-corpus correctness from these nine cases.
