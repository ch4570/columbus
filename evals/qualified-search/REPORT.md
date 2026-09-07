# Qualified-name ambiguity and output caps

Generated 60 separate Java packages declaring Loader.getResource and exercised the current qualified-suffix search on both parser builds. Search with limit 50 returns 50 matching declarations and sets truncated=true. A large-budget signatures context also retains truncated=true instead of implying the upstream candidate list was exhaustive. Restricting to p59/* places p59.Loader.getResource first and retains only that file's candidates; full-name lookup also places it first.

The initial probe incorrectly expected a path-filtered search to return only one hit. Search intentionally combines preferred declaration matches with lexical candidates from that file. The corrected assertion verifies the path boundary, a single preferred suffix match and its first position. No engine change was required, and the initial probe failure is not claimed as an engine defect.

Raw pinned.json and candidate.json agree. This is generated syntax/search evidence, not compiled Java applicability, real-project recall or actual model token savings. Reproduce with `PYTHONPATH=skills/columbus/scripts .venv/bin/python evals/qualified-search/probe.py`; prepend the candidate runtime for that variant.
