# Multi-hop navigation: correct answers, higher token usage

The predeclared paired run passed both automatic source/set checks and manual shortest-path review. Columbus did not reduce token usage. The candidate path was actually used, so this is evidence about a working optional traversal rather than a run that never reached the feature.

| Measurement | Baseline | Columbus | Change |
| --- | ---: | ---: | ---: |
| Input tokens | 66,318 | 104,367 | +57.37% |
| Cached input tokens (subset) | 43,264 | 63,104 | — |
| Uncached input tokens | 23,054 | 41,263 | +78.98% |
| Output tokens | 3,059 | 4,539 | +48.38% |
| Command count | 3 | 10 | — |
| Command output bytes | 47,575 | 55,952 | — |
| Elapsed seconds | 106.456 | 160.976 | — |

The task and oracle were committed as `d85796e` before either trial. Both sessions requested gpt-5.6-sol/xhigh, used the same immutable c67b20a source, and had a 600-second timeout. Baseline ran first. No retries or prompt changes occurred. The skill includes optional receiver candidates and was frozen with the engine before either trial. Harness tests passed 17 and the skill validator passed before running. This is a single pair on a familiar small repository, not a held-out repository benchmark or a causal model of the overhead.

The independent standard-library AST oracle found `_source`, `refresh`, and `status` at two calls and `symbol` at three under the explicitly stated lexical rules. Automatic grading requires exactly those methods and grounded first-handoff citations without exposing their names/count to the prompt. Manual review checked each ordered path, hop count, import handoff and runtime uncertainty in both answers. All eight finding reviews passed. This does not demonstrate general runtime completeness.

Columbus first read the skill, ran a broad source search, then queried `callers safe_source`. It read substantial index.py ranges before querying `callers read_stable` and finally `impact read_stable --hops 2 --include-candidates` as command six. It then ran two more searches and two source-read commands, including a final numbered reread. The three graph responses totalled 7,254 bytes; the skill was 4,032 bytes. These traces show graph retrieval supplementing source exploration and repeated evidence reads. They do not isolate one feature as the cause of the token increase.

`preflight.json` and `postflight.json` are identical: source manifests, frozen runtime manifest, index revision, database byte hash, the four methods and all shortest handoffs match. `results.json` retains measured counters, both complete answers, command hashes, event hashes and manual semantic reviews. `manifest.json` and `engine.json` retain frozen inputs. Full raw events and outputs are preserved locally at `.omx/observations/multihop` and the original `/tmp/columbus-multihop-ready` directory.

The result contradicts a savings claim for this task. Do not tune and rerun the same pair until it passes. Exact enumeration requires extra completeness checking that the uncertain graph cannot discharge. Future work must distinguish useful source-navigation tasks from completeness claims, use a genuinely different larger repository/task after an independent oracle is ready, and continue resolving the outstanding JVM precision/storage acceptance requirements. The full goal remains open.
