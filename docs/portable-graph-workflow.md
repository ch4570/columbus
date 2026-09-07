# Keep a graph in Git and explore it without SQLite

This workflow requires development revision `c27137e11c61b5d18c4698ece6c6eca0d1281654` or newer. The published v1.0.0 assets do not include these archive commands. Install the pinned source into an isolated environment using Python 3.11+:

```sh
python -m venv .venv
# Activate the environment, then:
python -m pip install "git+https://github.com/ch4570/columbus@c27137e11c61b5d18c4698ece6c6eca0d1281654"
```

Run the following inside the project being indexed. Add `.columbus/` to its `.gitignore`; SQLite is a local cache. Keep the compressed archive at a versioned path outside that ignored directory:

```sh
columbus archive --repo . --output codegraph/graph-v1.jsonl.gz
git add codegraph/graph-v1.jsonl.gz
```

The archive command synchronizes first and publishes a complete file. Existing destinations are never overwritten. After source changes, generate a new name such as graph-v2.jsonl.gz and review the Git change. The gzip file is excluded from source indexing, so storing it inside the repository does not recursively index the graph. Source code is not executed during indexing.

Only the graph file is required on a consuming machine with this Columbus version installed. It can be copied to another directory or obtained with the repository. From that directory:

```sh
columbus archive-search Class.method --input graph-v1.jsonl.gz --budget-bytes 2048
```

Replace Class.method with a declaration in the indexed project. Copy the desired exact `id` from the response, then query incoming stored calls:

```sh
columbus archive-neighbors 'EXACT_ID_FROM_SEARCH' --input graph-v1.jsonl.gz --direction in --kinds calls --budget-bytes 6000
```

Use `out` for outgoing edges or `both` for either direction. Omit `--kinds` to include all stored relationship kinds. If `next_offset` is a number, repeat with `--offset NUMBER`, keeping the same archive, ID, direction and kinds. Stop when next_offset is null. A changed revision requires restarting the sequence. Repeated pages scan the artifact again and repeat some metadata; use the response size suitable for the task rather than assuming smaller pages reduce total cost.

These commands do not create SQLite or read project source. They return source locations/hashes, declarations and saved edges. `semantic_complete=false` and unresolved counts remain visible. An absent saved edge does not prove there is no dependency, and archive freshness does not verify a receiving checkout. For changes to code, use the matching source checkout and normal `explore`/`symbol` queries to verify current bytes. Do not load the full decompressed JSONL into model context.

The agent skill includes this route in its archive reference. Install the managed skill with `columbus init --repo /path/to/project`; tell the agent where the versioned graph is located. This does not automatically force graph use or establish model-token savings.

The [executable workflow probe](../evals/archive-workflow/verify.py) creates a small Git repository, tracks the archive but excludes SQLite, deletes the producer, and verifies incoming calls using only the moved graph. [Receipts and limits](../evals/archive-workflow/REPORT.md).
