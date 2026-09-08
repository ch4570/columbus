# Searchable literal assignment evidence

The repeated force_bytes observations misread VSI_DELETE_BUFFER_ON_READ without retrieving its False definition. The existing graph had no node for that assignment, so archive-search could not find it. The Python parser now emits search-only assignment nodes for module-scope uppercase Name targets with a direct AST Constant value whose unparsed representation is at most 256 characters. Assign and AnnAssign with values are supported; computed expressions, longer literals and assignments inside functions/classes are excluded. Negative numbers represented by UnaryOp are outside this first direct-Constant scope. This is explicitly bounded syntax coverage, not general value analysis.

The node retains path, source lines, module, name, assignment signature and containment. It does not modify the existing local assignment binding. Literal values therefore do not become callable symbols or resolved value-import targets. Reassignments have separate ordinal IDs and preserve search ambiguity. Assignments under module-level conditional/loop statements remain source occurrences, not claims that a branch ran or a value is immutable/current. The assignment kind distinguishes these from callable declarations.

Parser tests cover repeated declarations, annotated literals, computed aliases, class/function exclusions, missing values, long literals and invalid calls through direct imports/module attributes. Both gzip and XZ tests search the qualified literal name, confirm no call edge to the value, and retain ambiguity after reassignment. Ordinary and candidate engine suites each pass 244 tests; root tests pass 53.

The full same-source Django comparison uses 5466 files from the isolated cache-reuse corpus. It compares the restored saved baseline index with a fresh current index. Every source hash matches. After removing only new assignment symbols, all parsed facts equal the baseline, including scopes, imports and references. No previous edge is removed; additions are exclusively contains edges to the new assignments. Existing FTS documents are identical, though generic searches may now include additional assignment hits. This is not a claim that every bounded search ranking is unchanged.

| Stored data | Before | After |
| --- | ---: | ---: |
| Declaration nodes | 46631 | 47810 |
| SQLite bytes | 153391104 | 154386432 |
| XZ graph bytes | 8592976 | 8630760 |

There are 1179 added assignment nodes. The observed SQLite footprint is 995328 bytes larger (about 0.65%); the baseline has an edit/restore history whereas the after index is fresh, so physical size is not an isolated per-node allocation estimate. Both archives use the same current exporter; XZ grows 37784 bytes (about 0.44%). No latency or memory benchmark ran.

The fully qualified saved-graph search for django.contrib.gis.gdal.raster.const.VSI_DELETE_BUFFER_ON_READ previously returned no items and now returns one assignment at the source definition with signature VSI_DELETE_BUFFER_ON_READ = False. Results retain the source hash and syntax evidence. An agent must still inspect contradictory or multiple assignments and does not get runtime evaluation. No model experiment has shown that this availability fixes the prior answer errors or reduces tokens. Completed observation inputs are unchanged.

Fresh wheel and ZIP distribution verification passed; see distribution.txt. Remote platform CI is pending for the implementation revision.
