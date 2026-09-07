# Contributing to Columbus

Keep changes source-backed, bounded, and reproducible. A useful contribution improves what an agent can find, the amount of context it needs, or the reliability of installation and retrieval.

## Set up a development environment

From the repository root on macOS/Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[mcp]'
.venv/bin/columbus doctor
```

The MCP extra enables the stdio integration tests. On Windows, use `.venv\Scripts\python.exe` and `.venv\Scripts\columbus.exe`. The runtime source lives under `skills/columbus/scripts/columbus/`.

## Verify a change

Run the root installation/distribution suite from the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Run the engine suite from its own directory:

```sh
cd skills/columbus/scripts
../../../.venv/bin/python -m unittest discover -s tests -v
```

Then return to the repository root for compilation and dependency checks:

```sh
.venv/bin/python -m compileall -q bootstrap.py install.py get-columbus.py run.py scripts skills/columbus/scripts evals/exploration
.venv/bin/python -m pip check
```

The repository currently uses standard-library tests and compilation checks; it does not have a separately configured lint or static type checker. Do not report an unconfigured check as passing. Add focused regression coverage for behavior changes and run the relevant existing suite. For documentation-only changes, verify links, commands, and claim accuracy.

## Check the distribution

From the repository root:

```sh
.venv/bin/python -m pip wheel --no-deps --wheel-dir dist .
.venv/bin/python scripts/build_bundle.py
.venv/bin/python scripts/release_assets.py
.venv/bin/python scripts/verify_distribution.py \
  --wheel dist/columbus-1.0.0-py3-none-any.whl \
  --bundle dist/columbus-1.0.0.zip
```

The distribution verifier creates isolated environments and may download dependencies. The ZIP inventory is checksummed and reproducible for the same input. Keep package and skill bundle versions aligned. New shipped assets must be included in the distribution inventory rather than only existing in the checkout.

A `vX.Y.Z` tag triggers the [release workflow](.github/workflows/release.yml). It requires the platform matrix, checks that the tag matches the package version, and publishes one set of wheel/ZIP/installer assets with checksums. Write `docs/releases/X.Y.Z.md` and update the standalone installer default before tagging.

The [distribution workflow](.github/workflows/distribution.yml) defines the platform matrix. Record actual execution evidence in [VALIDATION.md](VALIDATION.md); configured jobs are not completed jobs.

## Keep the contract honest

- Distinguish detected language, extraction fidelity, and relationship confidence. Add negative cases for declarations hidden in comments or strings.
- Preserve budgets on serialized responses, including metadata. Test Unicode, truncation, and stale source where the behavior changes.
- Keep receipts task-scoped and source-aware. A partially delivered snippet must not be recorded as a fully read symbol.
- Keep local telemetry free of raw source and raw queries. Separate payload estimates from model usage.
- Preserve managed-file conflict checks and existing installation ownership. Do not add runtime dependencies without explicit agreement.
- Use the existing engine and patterns before introducing a second implementation or abstraction.

For efficiency changes, compare the same task and fixture, retain raw measurements, and assess answer quality alongside bytes and tokens. See [token observations](docs/token-efficiency.md).

## Submit a change

Explain the concrete problem, resulting behavior, relevant validation, and known gaps. Update both overview languages when their user-facing claims change. Keep detailed contracts in the linked guides.

Commit messages in this workspace use the Lore protocol: start with why the change was made, add useful context, and include applicable native Git trailers such as `Tested:`, `Not-tested:`, `Confidence:`, and `Scope-risk:`. Example:

```text
Prevent repeated parent and child snippets from inflating agent context

Record only source ranges actually delivered so a later query can retrieve
an unread remainder without resending the surrounding declaration.

Confidence: high
Scope-risk: narrow
Tested: Overlapping spans, partial output, and changed-source regression cases
Not-tested: Long-running agent conversations across model compaction
```

Questions belong in a repository issue with a reproducible example. For sensitive reports, follow [SECURITY.md](SECURITY.md).
