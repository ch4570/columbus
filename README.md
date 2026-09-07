![RepoAtlas — a compact repository map connecting only the code needed for a task](docs/assets/repoatlas-hero.png)

# RepoAtlas

[English](README.md) · [한국어](README.ko.md) · [Download v0.5.0](https://github.com/ch4570/repo-graph/releases/tag/v0.5.0)

[![Tests](https://github.com/ch4570/repo-graph/actions/workflows/distribution.yml/badge.svg)](https://github.com/ch4570/repo-graph/actions/workflows/distribution.yml)

**Find the code. Carry less context.**

RepoAtlas builds a local graph of your repository so a coding agent can move from a small map to relevant symbols and verified source. Find an entry point, follow a dependency, and retrieve only the code the task needs.

**Local indexing · 66 language detection profiles · 4 graph formats · CLI + optional MCP · MIT**

No LLM or API key is needed to index a repository. RepoAtlas does not build or execute the project. Language detection is broader than semantic analysis: Python, Java, and Kotlin use ASTs; 43 profiles use declaration heuristics; other UTF-8 text stays searchable as files. [Coverage and limits](docs/languages.md).

[Quick start](#quick-start) · [Agent workflow](#give-an-agent-a-smaller-working-set) · [Graphs](#make-the-graph-you-need) · [Measurements](#measure-the-work-not-just-the-payload) · [Docs](#documentation)

## Quick start

**Private preview.** Repository access is required. Use an authenticated GitHub CLI to download the wheel, or download it from the [release page](https://github.com/ch4570/repo-graph/releases/tag/v0.5.0). Install it, then run RepoAtlas inside your project. **Python 3.11+** is required; the target project can use any language.

```sh
gh release download v0.5.0 --repo ch4570/repo-graph --pattern 'repoatlas-0.5.0-py3-none-any.whl'
uv tool install ./repoatlas-0.5.0-py3-none-any.whl
repoatlas explore
repoatlas explore checkout
```

`explore` gives you a small map; `explore checkout` returns relevant source in readable text, capped at 2,000 estimated tokens. Replace `checkout` with a name in your code. Both synchronize the local index automatically. Add `--repo /path/to/project` to run from elsewhere. Running `repoatlas` alone shows a short guide.

**Use pipx instead:** replace `uv tool install` with `pipx install` in the install command. Neither method requires cloning RepoAtlas or installing its dependencies into your project. If the executable is not on PATH, follow the installer's PATH hint (`uv tool update-shell` for uv).

<details>
<summary>Only have Python? Download the standalone installer.</summary>

Download `get-repoatlas.py`, the wheel, and `SHA256SUMS.txt` from the authenticated [release page](https://github.com/ch4570/repo-graph/releases/tag/v0.5.0), then run:

```sh
python3 get-repoatlas.py --wheel ./repoatlas-0.5.0-py3-none-any.whl --checksum-file ./SHA256SUMS.txt
```

On Windows, replace `python3` with `py -3`. It verifies the release wheel's checksum, creates a dedicated user environment, and prints the command location and any PATH step. It preserves unrelated installations and shell configuration. Initial installation needs internet access; [offline and advanced installation](INSTALL.md) are also supported.

</details>

Already have a source checkout? `uv tool install .` works too. Browse the [release assets](https://github.com/ch4570/repo-graph/releases/tag/v0.5.0) for wheels, a portable ZIP, and checksums. The release wheel is the published distribution; these instructions do not assume a PyPI package.

## Start with the question

| Your task | Command |
| --- | --- |
| Understand an unfamiliar repository | `repoatlas explore` |
| Locate a feature or exact symbol ID | `repoatlas search checkout --format text --limit 5` |
| Read declarations before opening source | `repoatlas context checkout --mode signatures --format text` |
| Fetch a bounded amount of current code | `repoatlas explore checkout` |
| Follow callers, imports, or inheritance | `repoatlas neighbors EXACT_SYMBOL_ID --kinds calls imports inherits --format text` |
| Inspect incoming calls and inheritance | `repoatlas impact EXACT_SYMBOL_ID --format text` |
| Share a dependency graph | `repoatlas graph --level file --format mermaid --output dependencies.mmd` |

Run these in the target repository, or add `--repo /absolute/path/to/project`. Use IDs returned by `search`, not a guessed ID. `impact` is a bounded graph traversal, not a proof of every runtime effect.

## Give an agent a smaller working set

**Start with the smallest useful read.** For a known name or file, use a short search or read the relevant source range directly. Use a small map only when the structure is unclear, and inspect declarations or relationships as needed. Stop retrieving once the evidence answers the question. JSON remains the default for automation; `--format text` makes query results compact and readable in an agent transcript.

```sh
repoatlas init
repoatlas explore checkout --session checkout
repoatlas explore calculateTotal --session checkout
repoatlas stats checkout
```

`init` installs the agent skill in the current repository. A named session chooses its receipt and telemetry files for you under `.repoatlas/sessions/checkout/`. Later snippet queries omit source ranges already delivered in that session and continue unread portions. `stats` shows query count, output size, and source bytes. Use a new session name for a new task or an agent that has not received the previous output; a receipt does not restore lost model context. Sessions require a source query, not a map or declaration-only query.

Session logging is local and opt-in. Telemetry records metadata, not source bodies or queries. Add `.repoatlas/` to your project's ignore rules. Advanced `context --receipt PATH --telemetry PATH` commands remain available.

An agent prompt after installation:

```text
Read .agents/skills/repoatlas-jvm/SKILL.md. For a known name or file,
use a short search or read the relevant source range directly. Use a map
capped at 2,000 estimated tokens only when the structure is unclear.
Inspect declarations and relationships as needed; stop retrieving when
the evidence is sufficient. Reuse one receipt for this task's snippet
queries and log retrieval metadata locally. Verify source before editing,
then run the relevant tests and synchronize the index.
```

The skill path `repoatlas-jvm` and cache filename `jvm-v2.sqlite` remain for installation compatibility; they do not restrict the indexed languages. See [agent usage, receipts, and MCP](docs/agents.md).

## Make the graph you need

| Format | Use it for |
| --- | --- |
| JSON | Structured graph data for scripts and tools |
| Mermaid | Editable diagrams in documentation |
| GraphML | Importing into external graph tools |
| HTML | Exploring a self-contained graph offline |

```sh
repoatlas graph --repo /absolute/path/to/project --format html --output graph.html
repoatlas graph --repo /absolute/path/to/project --format mermaid --level file \
  --kinds imports calls --output dependencies.mmd
repoatlas graph --repo /absolute/path/to/project --format graphml \
  --language typescript --path 'src/*' --output frontend.graphml
```

Filter by language, path, relationship, direction, and a focus symbol. Graphs expose confidence and truncation; unknown languages still produce file nodes. Existing output files are preserved. [Graph options and examples](docs/usage.md#export-a-graph).

## Measure the work, not just the payload

**Smaller responses are measurable. Lower model usage still depends on the task and the agent's choices.** These are the actual observations, including the regressions.

### CLI delivery: what got smaller

Measured on the included polyglot example with the 0.4.0 engine, without a model call:

| Comparison | Before | After | Observed change |
| --- | ---: | ---: | ---: |
| Same 28 map items: JSON → text | 6,639 bytes | 3,535 bytes | **46.8% smaller output** |
| Three identical context calls: no receipt → receipt | 9,633 bytes | 4,483 bytes | **53.5% smaller total output** |
| Source delivered across receipt calls 1 → 2 → 3 | 1,429 bytes | 188 → 0 bytes | Unread ranges first, then no repeated source |

Text preserves the selected map IDs and navigation evidence, not every JSON metadata field. Receipt continuation can return new ranges that a repeated ordinary query would miss. An exhausted receipt still returns status metadata. [Exact records and fixture hashes](evals/exploration/results/2026-09-07/delivery.json).

### Actual Codex exploration: what happened to tokens

Three fixed code-location questions on the same real source snapshot; ordinary `rg`/bounded reads versus those tools plus RepoAtlas. Each condition ran once with Codex CLI 0.153.4, requested model `gpt-5.6-sol`, effort `xhigh`, and the same installed skill catalog. RepoAtlas received a prebuilt index; its 1.105-second construction was measured separately. Arrows mean **ordinary → RepoAtlas**.

| Question | Citation check | Cumulative input tokens | Input change | Commands | Command output bytes |
| --- | --- | ---: | ---: | ---: | ---: |
| Graph export protection | Pass → Pass | 79,358 → 106,334 | **+34.0%** | 4 → 7 | 49,750 → 66,502 |
| Configuration invalidation | Fail → Pass | 157,482 → 138,864 | −11.8% | 10 → 8 | 81,885 → 43,542 |
| Managed installation conflicts | Fail → Pass | 70,775 → 88,411 | **+24.9%** | 4 → 3 | 23,514 → 11,993 |

The two baseline citation failures used ellipses instead of contiguous source quotations; this is not proof that the agent misunderstood the mechanisms. Those pairs are excluded from equal-quality savings claims. **The one pair passing both citation checks used 34.0% more input. General model-token savings were not established.** In the installation case, command output fell by 49.0% while input increased, showing why response size alone is insufficient.

Actual usage comes from the runtime, not the byte estimate. Cached input is already part of input; do not add it again. Startup instructions, tool exchanges, repeated context, reasoning and cache behavior affect the total. No billing savings or broad accuracy improvement is claimed. This small read-only pilot does not establish results for large repositories or implementation tasks. All six trials and the entire excluded initial empty-index cohort are preserved. [Prompts, answers, usage and grading](evals/exploration/results/2026-09-07/controlled.json).

### Apply the findings

Use direct search/read for a known location, a small map for unfamiliar structure, and graph queries only when relationships matter. Avoid repeated long natural-language searches. Keep one receipt per task and stop when the evidence is sufficient. These lessons shaped the easier `explore` and session workflow; **the 0.5.0 workflow has functional tests, not a new model-token A/B claim**.

To reproduce the model-free delivery check from a checkout:

```sh
python scripts/observe_delivery.py
```

[Full methodology](docs/token-efficiency.md) · [Agent experiment harness](evals/exploration/README.md) · [Validation evidence](VALIDATION.md)

## How it works

Discovery enumerates eligible files and detects languages. AST and heuristic analyzers emit source-backed facts into a local SQLite graph with full-text search. Retrieval selects a bounded set of declarations or verified source spans; exporters and MCP reuse that index.

The index and optional receipt/telemetry files stay local. Source presented to an agent is still untrusted repository content. [Architecture and data boundaries](docs/architecture.md).

## Documentation

| Guide | Contents |
| --- | --- |
| [Install](INSTALL.md) | Wheel, ZIP, offline install, updates, and troubleshooting |
| [CLI usage](docs/usage.md) · [한국어 사용법](docs/usage.ko.md) | Queries, filters, output formats, budgets, and freshness |
| [Agent integration](docs/agents.md) | Skill setup, progressive retrieval, receipts, telemetry, and MCP |
| [Language coverage](docs/languages.md) | AST / heuristic / text contracts and custom language rules |
| [Architecture](docs/architecture.md) | Source map, index lifecycle, and local data |
| [Token observations](docs/token-efficiency.md) | Reproducible measurements and interpretation |
| [Contributing](CONTRIBUTING.md) | Development, test commands, and change expectations |
| [Changelog](CHANGELOG.md) | Source and bundle changes |

Questions and bugs: [support guide](SUPPORT.md). Security concerns: [security policy](SECURITY.md). Code and documentation are under the [MIT license](LICENSE).
