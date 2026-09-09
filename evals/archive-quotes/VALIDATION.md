# Development validation, not a token acceptance result

Base: development merge `9c0d3c3a54022237d32b9790ba4c1e0b2a758124`. Work was isolated from the immutable actual-model evaluation head `58f2a683496d9f0dd06351eb2efd3f6c27d97915`. No historical source, prompts, criteria, graders, results or input hashes were edited.

Local Python 3.12.14 checks passed:

- 317 engine tests, including 23 new exact-quote tests.
- 81 root/bootstrap/distribution/gate tests.
- 29 observation-harness and three continuous-session tests, with no model calls.
- 21/21 fixed multilingual release contracts; this is not whole-language semantic accuracy.
- Dependency consistency, Python compilation, diff whitespace and Skill Creator's skill validator.
- Clean installed wheel and relocated ZIP workflows, including exact multi-range quotes, the CLI-only `./` spelling, whole-file hashes, invalid-range/pretty/stale failures and no consumer index creation.
- Independent full-source Requests capture and no-write minimal-fixture replay. The same 13 physical source rows survive all three efficient comparison paths. See README.md for the distinct metadata and byte counts.

Independent review found and corrected option-like filenames, unescaped source-error controls, an explicit empty telemetry argument, and corrupt gzip DEFLATE exceptions. The regression suite covers each; malformed archives are rejected before source reads, and failures never emit a partial quote batch. Code and tests use the existing decoded physical-line convention, including Unicode separators, CRLF, JVM bare CR, Python encoding cookies, empty files and genuine blank lines.

The final runtime wheel SHA-256 is `c112e38af64745f85aa1765fee636b06575c5191013d9c544d192989152f728e`. The locally tested source ZIP SHA-256 is `4e53f537a88355db32e256b2a05c5747e6c29dddd59fdf4277d9978c29b4b81f`; it was built before final evaluation attachments/test additions, while containing the final runtime and installed-quote checks. Final-head CI rebuilds the complete committed package. These are unpublished local artifacts, not a release.

The prior development merge's twelve post-merge platform jobs also passed: PR run `34253440877` and push run `34253436318`. This does not alter its actual-token result: the latest six-pair cohort still accepts 0/6, with aggregate input/output increases. This feature has no actual-model savings or improved-answer-quality claim. Main/release PR #12 remains open and gated.

Skill Creator guidance kept the new skill route optional and conditional on a needed source read. It does not require an extra verification command or recommend rereading unchanged source already in context.
