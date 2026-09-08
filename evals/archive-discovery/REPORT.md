# Held-out archive discovery reproduction

This model-free check compares a complete declaration search followed by an exact-ID source batch against one `archive-source --overloads` query. It retrieves all frozen declaration bodies and checks exact IDs, ranges, file hashes and physical source lines. No model tokens or answer quality are measured, and the failed multilingual model cohort is unchanged.

Each case indexes one complete, unmodified upstream source file downloaded with its Apache 2.0 license. This tests a discovery mechanism on new source, not exploration across a complete repository. The baseline uses an explicit limit of 50 so all overloads fit in one search; it is not forced through one search per signature. Both workflows use the current runtime and compact renderer; baseline labels only the two-step graph workflow. Ordinary rg/model exploration and the previous package are outside this measurement.

| Case / format | Declarations / lines | Commands before → after | Command bytes before → after | Response bytes before → after |
| --- | ---: | ---: | ---: | ---: |
| gson-from-json / text | 11 / 97 | 2 → 1 | 1605 → 262 | 13857 → 8122 |
| gson-from-json / json | 11 / 97 | 2 → 1 | 1605 → 262 | 15764 → 10111 |
| okhttp-request-body / text | 4 / 59 | 2 → 1 | 976 → 269 | 7110 → 4162 |
| okhttp-request-body / json | 4 / 59 | 2 → 1 | 976 → 269 | 7559 → 4693 |

Command bytes are UTF-8 bytes of `shlex.join()` for the actual subprocess arguments, including the recorded interpreter/runtime paths and excluding the terminating newline. Response bytes are actual stdout plus stderr. Source indexing, validation/control queries and downloads are setup costs excluded equally from the two scripted workflows. Every command receipt retains exit status and stdout/stderr hashes in [results.json](results.json). These figures are not model input/output tokens, dollar costs, latency measurements or evidence that agents choose this workflow.

## Frozen upstream inputs

- gson-from-json: [b3f4ca20087f9066de4c340522ff84e0558e1ad1](https://github.com/google/gson/commit/b3f4ca20087f9066de4c340522ff84e0558e1ad1); [source](https://raw.githubusercontent.com/google/gson/b3f4ca20087f9066de4c340522ff84e0558e1ad1/gson/src/main/java/com/google/gson/Gson.java) SHA-256 `1a33f3eb5ddc01f0a33bbe2b43dc26f8474fc8d5b80876ad9a2f33056224fc94`; [license](https://raw.githubusercontent.com/google/gson/b3f4ca20087f9066de4c340522ff84e0558e1ad1/LICENSE).
- okhttp-request-body: [d4e7006216ddf06ffe628d1320b62ac01843b63d](https://github.com/square/okhttp/commit/d4e7006216ddf06ffe628d1320b62ac01843b63d); [source](https://raw.githubusercontent.com/square/okhttp/d4e7006216ddf06ffe628d1320b62ac01843b63d/okhttp/src/commonJvmAndroid/kotlin/okhttp3/RequestBody.kt) SHA-256 `1f998aafeaf38c3cbc922e9a3726b3f61c41b88e4e3989307ef7315427055e1a`; [license](https://raw.githubusercontent.com/square/okhttp/d4e7006216ddf06ffe628d1320b62ac01843b63d/LICENSE.txt).

[pins.json](pins.json) freezes exact declaration signatures and physical ranges, including annotations. Full source and licenses are fetched verbatim into temporary directories and verified against their pinned hashes on each run. No upstream source fixtures are committed.

## Controls

- gson-from-json / unflagged_ambiguity: PASS.
- gson-from-json / exact_id_stays_single: PASS.
- gson-from-json / grouped_pagination: PASS.
- okhttp-request-body / unflagged_ambiguity: PASS.
- okhttp-request-body / exact_id_stays_single: PASS.
- okhttp-request-body / grouped_pagination: PASS.
- okhttp-request-body / different_receivers_rejected: PASS.
- okhttp-request-body / receiver_exact_ids_readable: PASS.

Ambiguous queries without the flag must fail. Exact IDs with the flag must stay singular. Bounded pages must reconstruct every selected physical line once. OkHttp's four different `toRequestBody` receivers must be rejected as a group and remain individually readable by exact ID. An expected rejection is a passing negative control, not a silently discarded failure.

Overall: **PASS**. Unexpected failures: 0.

## Reproduction

Run from the repository root with the pinned parser dependencies installed:

```sh
recheck_dir="$(mktemp -d /tmp/columbus-archive-discovery.XXXXXX)"
.venv/bin/python evals/archive-discovery/verify.py --output "$recheck_dir"
```

Network access is needed only for the four immutable source/license URLs. The script writes its temporary fixtures and the explicitly selected report directory, never runs models, and records runtime/input hashes plus parser versions. Runtime edits during a run fail the check; a different runtime requires a fresh report rather than rewriting prior results.
