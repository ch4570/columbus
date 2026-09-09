# Install Columbus

[Overview](README.md) · [한국어 소개](README.ko.md) · [CLI usage](docs/usage.md)

**Columbus 1.1.0 is an unreleased candidate.** Its mandatory [actual-token gate failed](evals/multilang-token-batch/ANALYSIS.md), so no 1.1.0 release assets are published. Use [checkout or local-wheel installation](#from-a-checkout-or-local-wheel) to inspect the candidate, or consult [published releases](https://github.com/ch4570/columbus/releases). The version-pinned release-download examples below are reserved for publication; no PyPI package with the same name is assumed.

Install a CLI once for use across repositories, or install a ZIP bundle with a dedicated runtime in one project. Neither approach requires the target project to use Python.

## Requirements

| Requirement | Why |
| --- | --- |
| Python 3.11 or newer | Runs the CLI, parsers, and installer |
| SQLite with FTS5 | Stores the graph and full-text search index |
| Compatible wheels for pinned dependencies | Provides the Java/Kotlin Tree-sitter parsers |
| Git, when available | Enumerates tracked and untracked files with Git ignore rules |

`columbus doctor` checks Python, FTS5, and the pinned parser dependencies. Without Git, discovery uses the filesystem. Native platform checks actually executed are recorded in [VALIDATION.md](VALIDATION.md); a CI matrix is not a claim that every platform has passed.

The wheel contains the Python package and installable skill. The ZIP contains source, the installer, documentation, and examples. **Neither includes Python or a platform-independent set of dependency wheels.** Initial dependency installation needs a package index unless you prepare an offline wheelhouse.

The ordinary v1.1.0 artifacts use upstream `tree-sitter-java==0.23.5`. The separately tested `0.23.5+columbus.1` annotation-parser candidate is experimental and is not bundled or selected by this release's default installation. Candidate CI results do not describe the ordinary artifact's annotation coverage.

## Install the CLI

### Recommended: one command with uv or pipx

After 1.1.0 is published, install the pinned GitHub release with whichever tool you already use:

```sh
uv tool install https://github.com/ch4570/columbus/releases/download/v1.1.0/columbus-1.1.0-py3-none-any.whl
```

```sh
pipx install https://github.com/ch4570/columbus/releases/download/v1.1.0/columbus-1.1.0-py3-none-any.whl
```

Then open your project and run `columbus explore`, or pass `--repo /absolute/path/to/project`. Use `columbus doctor` to check the installation. If the command is not on PATH, use `uv tool update-shell` or `pipx ensurepath`, then open a new terminal.

### Python only: download and run the release installer

If you have Python 3.11+ but do not use uv or pipx, download [get-columbus.py from release v1.1.0](https://github.com/ch4570/columbus/releases/download/v1.1.0/get-columbus.py), review it, and run it. On macOS/Linux, these two commands download a local file and execute it:

```sh
curl -fL https://github.com/ch4570/columbus/releases/download/v1.1.0/get-columbus.py -o get-columbus.py
python3 get-columbus.py
```

On Windows, use PowerShell:

```powershell
Invoke-WebRequest https://github.com/ch4570/columbus/releases/download/v1.1.0/get-columbus.py -OutFile get-columbus.py
py -3 get-columbus.py
```

The installer downloads the pinned release wheel and `SHA256SUMS.txt`, checks the wheel's exact SHA256 entry, creates a dedicated environment, checks the installed version, and runs `doctor`. It publishes the command only after those checks pass. Dependency installation uses compatible binary wheels from the package index; the installer itself uses only Python's standard library. On distributions that package `venv` separately, install the Python venv package first.

| Platform | Environments | Command directory |
| --- | --- | --- |
| macOS/Linux | `~/.local/share/columbus/versions/VERSION/` | `~/.local/bin/` |
| Windows | `%LOCALAPPDATA%\Columbus\versions\VERSION\` | `%LOCALAPPDATA%\Columbus\bin\` |

Use `--prefix PATH --bin-dir PATH` to choose both locations. Paths may contain spaces; quote them in your shell. The script prints the absolute command path and an exact command to add its directory to PATH for the current shell session. It does not edit shell profiles, system Python, or your project. Existing commands and directories must belong to this installer before it can reuse them. Choose another location if it reports a conflict. Installation paths that contain a symlink or junction are refused; use their real directory paths.

Run the same command again to verify an existing healthy installation without reinstalling packages. If dependency installation was interrupted, fix the reported problem and rerun the same command: the installer checks the owned environment before resuming. To update later, use `python3 get-columbus.py --version X.Y.Z` with the desired published release. Every version has a fixed environment path, and the previous command remains active until the new version is healthy. Older environments are retained. Existing locally edited project skills remain subject to the separate `columbus init` conflict check.

For a completely offline installation, copy the release wheel, `SHA256SUMS.txt`, installer, and a compatible dependency wheelhouse to the destination. Then run:

```sh
python3 get-columbus.py --offline \
  --wheel /absolute/path/to/columbus-1.1.0-py3-none-any.whl \
  --checksum-file /absolute/path/to/SHA256SUMS.txt \
  --wheelhouse /absolute/path/to/wheels
```

Local wheels also require the matching checksum file. See [Offline installation](#offline-installation) for wheelhouse preparation. The standalone installer installs the core CLI; use the dedicated environment's Python with the wheel's `[mcp]` extra if you also need MCP.

### From a checkout or local wheel

From this checkout:

```sh
pipx install .
# Alternative:
uv tool install .
```

From a reviewed wheel copied to your machine:

```sh
pipx install /absolute/path/to/columbus-1.1.0-py3-none-any.whl
# Alternative:
uv tool install /absolute/path/to/columbus-1.1.0-py3-none-any.whl
```

After installation, use an existing project directory:

```sh
columbus doctor
columbus map --repo /absolute/path/to/project --format text --budget-tokens 2000
```

The package name and executable are both `columbus`. This guide does not assume a public PyPI release. To create the wheel from source:

```sh
python3 -m pip wheel --no-deps --wheel-dir dist .
```

### Use a virtual environment directly

If you only have pip, use a dedicated environment. On macOS/Linux:

```sh
python3 -m venv /absolute/path/to/columbus-env
/absolute/path/to/columbus-env/bin/python -m pip install /absolute/path/to/columbus-1.1.0-py3-none-any.whl
/absolute/path/to/columbus-env/bin/columbus doctor
```

On Windows, use PowerShell and the `Scripts` directory:

```powershell
py -3 -m venv C:\tools\columbus-env
C:\tools\columbus-env\Scripts\python.exe -m pip install C:\downloads\columbus-1.1.0-py3-none-any.whl
C:\tools\columbus-env\Scripts\columbus.exe map --repo C:\projects\example --format text
```

Quote paths that contain spaces. You may also run `python -m columbus` with the environment's Python.

## Install the agent skill

The CLI works without installing a skill. To add the bundled workflow to a project:

```sh
columbus init --repo /absolute/path/to/project --plan
columbus init --repo /absolute/path/to/project
```

The default destination is `.agents/skills/columbus/`. For a Claude Code project path:

```sh
columbus init --repo /absolute/path/to/project --skills-dir .claude/skills
```

`--plan` inspects the installation without writing files. The installer preserves locally edited managed files and reports a conflict. It does not edit your agent instructions, hooks, or Git configuration. Point your agent at the installed `SKILL.md`; discovery and invocation conventions depend on the host runtime. [Agent integration](docs/agents.md).

## Install a project-local ZIP bundle

Build the ZIP from a source checkout, or use a previously built archive:

```sh
python3 scripts/build_bundle.py
```

Extract `dist/columbus-1.1.0.zip`, open its extracted directory, and run:

```sh
python3 install.py --repo /absolute/path/to/project
python3 run.py --repo /absolute/path/to/project map --format text --budget-tokens 2000
```

The installer creates `.columbus/runtime/`, installs the skill, and performs the first index synchronization. Use `--no-index` to defer that synchronization, or `--plan` to inspect changes. The installation remains usable after moving the original extracted bundle.

Run the installed skill directly on macOS/Linux:

```sh
/absolute/path/to/project/.columbus/runtime/bin/python -E -s \
  /absolute/path/to/project/.agents/skills/columbus/scripts/columbus.py \
  map --repo /absolute/path/to/project --format text
```

On Windows, the runtime interpreter is `.columbus/runtime/Scripts/python.exe`. Do not copy an existing virtual environment between operating systems; create the runtime on the destination machine.

## Offline installation

Prepare dependency wheels on a connected machine with the **same OS, CPU architecture, and Python version** as the destination. From a checkout or extracted ZIP:

```sh
python3 -m pip download --only-binary=:all: --dest /absolute/path/to/wheels \
  -r skills/columbus/scripts/requirements.txt
```

Copy the wheelhouse and Columbus artifact to the offline machine. For a project-local ZIP installation:

```sh
python3 install.py --repo /absolute/path/to/project --offline --wheelhouse /absolute/path/to/wheels
```

For a dedicated environment with pip:

```sh
python -m pip install --no-index --find-links /absolute/path/to/wheels \
  /absolute/path/to/columbus-1.1.0-py3-none-any.whl
```

For MCP, also download `skills/columbus/scripts/requirements-mcp.txt`; add `--mcp` to the ZIP installer or install the wheel's `[mcp]` extra. Keep the requirements files with the wheelhouse so dependency pins remain reviewable.

## Enable MCP

Install the optional dependency in the same environment that runs `columbus serve`:

```sh
python -m pip install '/absolute/path/to/columbus-1.1.0-py3-none-any.whl[mcp]'
columbus sync --repo /absolute/path/to/project
columbus serve --repo /absolute/path/to/project
```

With pipx, use `pipx install '/absolute/path/to/columbus-1.1.0-py3-none-any.whl[mcp]'` when installing. For ZIP installation, pass `--mcp`. The server uses stdio and a saved index; it does not synchronize on each request. See [client configuration and tools](docs/agents.md#mcp).

## Updates and local files

Reinstall the new wheel with your chosen tool, then run `columbus init --repo PATH` to update the installed skill. Examples for an existing installation:

```sh
pipx install --force /absolute/path/to/columbus-1.1.0-py3-none-any.whl
# Or, for a uv installation:
uv tool install --force /absolute/path/to/columbus-1.1.0-py3-none-any.whl
```

For a ZIP installation, run the new bundle's `install.py` against the same project. Review reported conflicts rather than deleting locally edited skill files. A runtime ownership marker prevents adoption of an unrelated environment. If dependency installation fails, fix the reported issue and rerun; an interrupted package install may have partially changed the environment.

The default graph cache is `.columbus/index-v1.sqlite`. Add `.columbus/` to the target project's ignore rules. The directory may also contain a dedicated runtime, receipts, and telemetry, so deleting it removes more than the graph. Columbus 1.0 uses new installation and cache paths. See the migration instructions below if you used the RepoAtlas preview.

Columbus 1.1 reads schema 2/3 caches and upgrades them transactionally to compressed schema 4 on synchronization. Older engines reject schema 4; use a separate `--db` path when comparing or returning to an older engine. Migration does not automatically shrink existing SQLite files. Portable gzip/XZ graphs are separate artifacts and can be stored outside `.columbus/`. [Versioned graph workflow](docs/portable-graph-workflow.md).

## Troubleshooting

| Symptom | Check and next step |
| --- | --- |
| `columbus` is not found | Check the pipx/uv binary directory is on PATH, or use the environment's absolute executable path. |
| `doctor` reports a missing dependency | Install the matching wheel or requirements in the interpreter running the CLI. |
| `doctor` reports `fts5: false` | Use a Python distribution whose SQLite build includes FTS5, then recreate the dedicated environment. |
| Installation reports a managed-file conflict | Compare the local file with the new bundle; preserve your changes before retrying. |
| Installation is locked | Check for a live installer. Only after it has stopped, remove an empty stale `.columbus/.bootstrap-lock` directory. |
| MCP reports an unavailable or stale index | Run CLI `sync` for the same repository and DB; MCP uses snapshots. |
| Offline pip cannot find a distribution | Confirm the wheelhouse contains every pinned dependency for the destination platform and Python version. |

For a reproducible report, include `doctor`, the exact command, relevant diagnostics, and a small synthetic fixture. [Support](SUPPORT.md).

## Releases that require authentication

If this repository or a private fork requires GitHub sign-in, direct asset URLs cannot be downloaded anonymously. Sign in to the release page and download the wheel; then run `uv tool install ./columbus-1.1.0-py3-none-any.whl` or `pipx install ./columbus-1.1.0-py3-none-any.whl`.

With the GitHub CLI already authenticated, download the installer inputs together:

```sh
gh release download v1.1.0 --repo ch4570/columbus \
  --pattern 'columbus-1.1.0-py3-none-any.whl' --pattern SHA256SUMS.txt --pattern get-columbus.py
python3 get-columbus.py --wheel ./columbus-1.1.0-py3-none-any.whl --checksum-file ./SHA256SUMS.txt
```

Use `py -3` instead of `python3` on Windows. No GitHub token is stored by the installer. Dependencies still come from the public package index unless you also provide `--offline --wheelhouse PATH`.

## Moving from the RepoAtlas preview

Columbus 1.0 is a new package and command. Install it using the pinned release URL above, then run `columbus init` and `columbus explore` inside your project. The new skill is `.agents/skills/columbus/` and the new index is `.columbus/index-v1.sqlite`.

If you customized `.repoatlas.json` or `.repoatlasignore`, copy their settings to `.columbus.json` or `.columbusignore`. The configuration syntax is unchanged. Add `.columbus/` to your ignore rules. Old `.repoatlas/` caches, receipt files, and `.agents/skills/repoatlas-jvm/` installations are left intact; use a new Columbus session and rebuild the index. Do not reuse preview receipts as evidence of source delivered in a new task.

Update agent instructions and MCP commands to use `columbus`. After checking the new installation, remove the old tool through the package manager that installed it, if desired. Columbus does not uninstall it or move user-owned files automatically. Historical benchmark records keep the RepoAtlas name because that is the engine they measured.
