# Suppress candidates contradicted by known class writes

A runtime-traced counterexample showed that `C.helper = replacement` still produced a lexical `C.helper` retrieval candidate at commit `e1f1d09`, although `C().run()` invoked the replacement. The reference was unresolved in both versions and never became a stored call edge. Merely labelling the candidate uncertain did not make that known contradiction useful for navigation.

The parser now records dotted member writes in lexical scope facts. During relinking, the resolver maps their receivers to known classes through existing lexical/import resolution. Writes to the selected member, unknown member names, `__bases__`, `__getattr__`, or `__getattribute__` suppress receiver candidates for that class. This includes assignments, deletion, direct `setattr`/`delattr`, and imported/module-qualified class names. Writes to unrelated members preserve the candidate. Removing the mutation restores the candidate on relink.

`verify-class-mutation.py` executes only its literal generated fixture and compares the old parser against the current one. `class-mutation.json` records the runtime replacement, old misleading candidate, and corrected absence. Tests also cover cross-module mutations and relinking in both directions. The initial implementation probe exposed a missing `kind` input to the internal reference resolver; it was fixed before tests passed.

Both pinned and candidate Java parser environments passed 202 engine tests. The frozen source path remains navigable with its uncertain first hop (`class-mutation-path.json`); the original observation is preserved separately. No model token trial was run.

This does not resolve arbitrary value aliases or reflective mutation. It also does not upgrade any Python call edge to a runtime guarantee. The overall correctness and token-saving goals remain open.

The correction was pushed as `2ffb051e306662fd3e177510880dea6da1275006`. Its [ordinary distribution](https://github.com/ch4570/columbus/actions/runs/34151020873) and [candidate/aggregate distribution](https://github.com/ch4570/columbus/actions/runs/34151039384) jobs were both confirmed in progress. Their eventual outcomes must be checked before claiming cross-platform verification of this correction.

The correction's ordinary distribution run `34151020873` completed successfully in all six environments; `platform/class-mutation-production.json` retains exact-commit job/step results. Its candidate/aggregate run remained active at the subsequent check.

Candidate/aggregate run `34151039384` also completed successfully at the correction commit: six candidate builds, one shared aggregate, and six consumers. `platform/class-mutation-candidate.json` records the completed jobs and verification steps. Both distribution routes now have successful hosted evidence for the correction.

Downloaded all six aggregate-consumer verification receipts and checked their source revision and artifact hashes. Each verified the same ZIP (`096439026ae0b47d4e3e7e0fb91d0f9312e1ded5b08708ccb846252052881941`) and wheel (`a4da719e3062fb4999e02a3a5f4a7eed4149c1ee71aca9c6d52127d05584028a`), with unchanged bytes after verification. See `platform/class-mutation-shared-artifacts.json`.
