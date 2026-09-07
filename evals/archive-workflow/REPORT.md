# Versioned graph relocation workflow

The CLI probe creates a temporary Git project, indexes two Python functions, publishes codegraph/demo-v1.jsonl.gz, and commits source plus graph locally. Git tracks the graph while excluding .columbus. An unchanged sync confirms the generated gzip is not indexed as source.

The graph is copied to an empty consumer directory and the entire producer (including SQLite) is deleted. archive-search locates target; archive-neighbors returns exactly entry → target with next_offset=null and semantic_complete=false. The consumer still contains only the graph and its hash is unchanged. Both parser environments pass; artifact sizes are 837 and 839 bytes respectively. This is a deliberately small workflow fixture, not a real-repository size claim. Runtime fingerprints/snapshot metadata can produce different archive bytes between environments.

[Core pinned environment](pinned.json), [candidate environment](candidate.json). Reproduce using `PYTHONPATH=skills/columbus/scripts .venv/bin/python evals/archive-workflow/verify.py`. The public guide links an immutable source revision that contains archive pagination and explicitly excludes old release assets. This does not claim a new release was published or that actual model-token savings are proven.

The ordinary distribution workflow now runs this CLI relocation probe on its supported OS/Python matrix; hosted results for the added gate are pending.
