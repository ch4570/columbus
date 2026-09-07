# Direct-caller skill workflow correction

The quality-passing caller pilot used broad source reads before four graph commands and increased input tokens 287.81%. The skill now distinguishes a known-name lookup from a caller relationship task. It recommends incoming calls first, copying the complete ID including its kind suffix, grouping by source ID, and reading returned call-site ranges. Transitive impact and direct nested-function ownership are distinguished. Focused import/coverage checks remain required; graph absence is not proof of no caller.

The concrete command verified against the frozen caller corpus was:

```sh
columbus neighbors 'skills/columbus/scripts/columbus/index.py::compact:function' --repo /path/to/frozen/repository --snapshot --direction in --hops 1 --kinds calls --limit 50 --format text
```

Its [text output](neighbors.txt) contains all **23 reviewed call sites from 7 callers**, exactly matching the independent corpus, and occupies **6,563 bytes**. It retains `semantic_complete=false`, unresolved/diagnostic counts and `truncated=false`. This response size is not an end-to-end or actual-model token measurement.

Skill validation passes. Fresh managed installation verified all **43 files** byte-for-byte and all entrypoint reference links. The skill grew from 2,966 to 3,546 bytes to give the targeted workflow; [verification hashes](verification.json) identify what was tested. No parser or resolver behavior changed.

A newly predeclared model comparison is still required to determine whether the agent follows this guidance early enough and reduces actual tokens. The previous unfavorable results remain retained. General graph precision, candidate Java grammar default distribution and repeated-session efficiency remain goal gates.
