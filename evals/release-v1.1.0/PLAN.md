# v1.1.0 release acceptance preparation

The user requested multilingual evaluation followed by merge and release only after the acceptance threshold is met. Whether measured actual-model token savings are mandatory for this release is awaiting user clarification. No merge or tag is authorized by these proposed functional checks alone until that condition is resolved.

Functional release requirements:

- Existing engine, root, observation-harness and distribution checks all pass at the release candidate; no known failing regression is waived.
- The fixed multilingual evaluator passes all 21 cases (13 programming languages and text fallback): expected simple calls and explicit JSX literal negatives, honest AST/heuristic/text fidelity, lossless gzip/XZ node/edge parity, saved lookup/source access, and incremental/fresh graph parity. This is a contract gate, not population precision or complete semantics for each language.
- The newly exposed JSX/TSX false text calls/declarations are rejected while supported embedded expression calls survive. Ordinary TypeScript generic/comparison syntax remains available.
- Existing JVM compiler gates and this-argument positives/negative continue passing; unsupported external/generic/anonymous paths remain disclosed.
- All six hosted OS/Python ordinary-distribution jobs pass on the final PR head; release publication runs the same matrix on the final tag.
- Package, bundle, installer and tag versions agree on 1.1.0. Wheel, ZIP and installer checksums and clean installation/relocation tests pass.
- Experimental Java grammar stays a separate tested candidate; the ordinary release uses upstream 0.23.5. Release notes disclose the difference and no actual-token savings claim.

If actual-model savings are also required, the existing unchanged gate remains: both baseline and Columbus answers pass all quality criteria and Columbus reduces both total input and output. All eleven recent pairs fail that gate; cached input and response-byte reductions do not substitute. No new model trial or relaxed scoring is implied by this release plan.

Merge must target the verified final PR SHA. Tag only the resulting verified merge commit. GitHub Release assets must be produced by the successful tag workflow, and published version/checksums must then be checked. No PyPI publication is configured.
