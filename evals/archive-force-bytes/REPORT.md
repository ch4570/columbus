# Completed force_bytes comparison

No accepted token savings: both answers find all 37 lexical owners and pass the citation gate, but both fail semantic review and graph exploration consumes more actual tokens. The shortened skill did not eliminate repeated searching or source reading in this task.

| Measurement | Baseline | Graph |
| --- | ---: | ---: |
| Elapsed seconds | 605.409 | 820.475 |
| Total input tokens | 253,653 | 692,264 |
| Cached input tokens, subset | 181,120 | 599,424 |
| Uncached input tokens | 72,533 | 92,840 |
| Output tokens | 18,081 | 23,907 |
| Reasoning output tokens, subset | 7,014 | 12,180 |
| Commands | 34 | 70 |
| Command output bytes | 139,993 | 247,167 |
| Exact caller/citation gate | pass | pass |
| Manual semantic review | fail | fail |

Graph input increased 172.92%, uncached input 28.00%, and output 32.22%. Both runs completed normally within the predeclared 1,200-second limit. Baseline ran first, graph second, once each, requested gpt-5.6-sol/xhigh; backend identity is not independently attested. The task was selected before inspecting its inventory and inputs/criteria were committed at 9d5213c before either model. Its larger scope motivated the longer limit before execution; comparison to prior 600-second tasks is not controlled. No retry, timeout extension, prompt tuning or task narrowing occurred.

Both answers assert that GDALRaster.vsi_buffer asks GDAL to delete the buffer on read, although the passed VSI_DELETE_BUFFER_ON_READ constant is False. The frozen review explicitly required checking rather than inferring this value. The graph answer also says non-string Feature.index inputs would be stringified, overlooking force_bytes's existing-bytes and memoryview paths. Per-owner judgments and exact source/hash evidence are in baseline-semantic-review.json and graph-semantic-review.json. Automated identification and bounded quotations do not prove explanation correctness.

The graph agent read the shortened 3,706-byte skill and additionally listed runtime files, then read the 7,117-byte archive reference. It made four archive searches: a full Python module-qualified name, a module path, the bare name and a shorter qualified name. The qualified forms yielded no declaration matches. It then queried scoped callers with radius 3 and again with radius 0, rather than the skill's behavior example radius 20, and performed substantial ordinary source/prototype reading. Repeated searches and context retrieval are observations, not proof that every additional source check was unnecessary. The qualified-name mismatch is a concrete interface gap for future work; this completed pair must not be replayed after a fix.

The independent AST/import oracle covers all 883 Python files under django/ and 46 scoped direct call sites, including nested owners and same-line multiplicity. The saved graph has 51 incoming calls before excluding top-level tests. Frozen context verification reproduces all 46 sites and exact source excerpts in six 12,000-byte pages (66,257 bytes total); the model chose different query options, so that preflight size is not its observed consumption.

Source/runtime manifests, harness/schema/case/review hashes and archive pre/postflight checks pass. The artifact remains 61a036d5a9eac24e9788531d8b803a2664d312383372500a58c1f8d042a12aa7, with no consumer SQLite. It contains 5,465 indexed files, 46,630 nodes and 86,828 edges in 8,592,880 bytes. Producer indexing took 17.172 seconds and export 7.526 seconds, separate from model usage. results.json retains answers, usage, commands and event hashes; raw traces remain under .omx/observations/archive-force-bytes and the original trial directory.

The objective remains incomplete. Functional graph storage, retrieval and smaller instruction files are not a substitute for correct answers with lower actual usage. This broader task is still on the same Django repository and provides no population-wide conclusion.
