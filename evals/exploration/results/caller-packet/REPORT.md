# Batched packet pilot: evidence returned, but reread

Both predeclared answers passed exact caller-set, contiguous-citation and source-based semantic review. Source and settings matched. Columbus successfully ran search and callers as commands 2 and 3, then reread seven source ranges and performed import/name checks. The supplied hash-verified excerpts did not replace those extra interactions.

| Measure | Baseline | Columbus |
| --- | ---: | ---: |
| Input tokens | 61,134 | 110,537 |
| Cached input subset | 37,120 | 89,984 |
| Uncached input | 24,014 | 20,553 |
| Output tokens | 3,301 | 3,926 |
| Command output bytes | 55,305 | 29,537 |
| Commands | 11 | 15 |
| Elapsed seconds | 115.354 | 144.173 |

Total input increased **80.81%**, output **18.93%**, and time **24.98%**. Uncached input decreased **14.41%** and command output **46.59%**. These mixed results do not satisfy the overall token-reduction goal and do not establish billing savings. No favorable-only reruns were performed.

[Controlled evidence](controlled.json) preserves answers, usage, commands, prompt/invocation settings, hashes and grades. Raw events and frozen engine/source remain at `.omx/observations/caller-packet/`. The model used the frozen c407d6b engine; subsequent Windows test-encoding changes did not alter that runtime.

The packet is correct for the reviewed corpus but insufficient by itself to prevent redundant source inspection. Next work should distinguish the need to check graph coverage/import binding from rereading already hash-verified citations, and evaluate repeated-context reuse rather than extrapolating from this single small task. Keep all prior regressions visible; no general or quality-preserving total-token reduction has been proven.
