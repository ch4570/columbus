# Install RepoAtlas

[Overview](README.md) · [한국어 소개](README.ko.md) · [CLI usage](docs/usage.md)

**Current access:** this repository is a private preview. Start with the [authenticated release download](#releases-that-require-authentication), then install the downloaded wheel. Anonymous GitHub asset URLs are available only after publication.

Install a CLI once for use across repositories, or install a ZIP bundle with a dedicated runtime in one project. Neither approach requires the target project to use Python.

## Requirements

| Requirement | Why |
| --- | --- |
| Python 3.11 or newer | Runs the CLI, parsers, and installer |
| SQLite with FTS5 | Stores the graph and full-text search index |
| Compatible wheels for pinned dependencies | Provides the Java/Kotlin Tree-sitter parsers |
| Git, when available | Enumerates tracked and untracked files with Git ignore rules |

`repoatlas doctor` checks Python, FTS5, and the pinned parser dependencies. Without Git, discovery uses the filesystem. Native platform checks actually executed are recorded in [VALIDATION.md](VALIDATION.md); a CI matrix is not a claim that every platform has passed.

The wheel contains the Python package and installable skill. The ZIP contains source, the installer, documentation, and examples. **Neither includes Python or a platform-independent set of dependency wheels.** Initial dependency installation needs a package index unless you prepare an offline wheelhouse.

## Install the CLI

### Recommended: one command with uv or pipx

Install the pinned GitHub release with whichever tool you already use:

```sh
uv tool install https://github.com/ch4570/repo-graph/releases/download/v0.5.0/repoatlas-0.5.0-py3-none-any.whl
```

```sh
pipx install https://github.com/ch4570/repo-graph/releases/download/v0.5.0/repoatlas-0.5.0-py3-none-any.whl
```

Then open your project and run `repoatlas explore`, or pass `--repo /absolute/path/to/project`. Use `repoatlas doctor` to check the installation. If the command is not on PATH, use `uv tool update-shell` or `pipx ensurepath`, then open a new terminal.

### Python only: download and run the release installer

If you have Python 3.11+ but do not use uv or pipx, download [get-repoatlas.py from release v0.5.0](https://github.com/ch4570/repo-graph/releases/download/v0.5.0/get-repoatlas.py), review it, and run it. On macOS/Linux, these two commands download a local file and execute it:

```sh
curl -fL https://github.com/ch4570/repo-graph/releases/download/v0.5.0/get-repoatlas.py -o get-repoatlas.py
python3 get-repoatlas.py
```

On Windows, use PowerShell:

```powershell
Invoke-WebRequest https://github.com/ch4570/repo-graph/releases/download/v0.5.0/get-repoatlas.py -OutFile get-repoatlas.py
py -3 get-repoatlas.py
```

The installer downloads the pinned release wheel and `SHA256SUMS.txt`, checks the wheel's exact SHA256 entry, creates a dedicated environment, checks the installed version, and runs `doctor`. It publishes the command only after those checks pass. Dependency installation uses compatible binary wheels from the package index; the installer itself uses only Python's standard library. On distributions that package `venv` separately, install the Python venv package first.

| Platform | Environments | Command directory |
| --- | --- | --- |
| macOS/Linux | `~/.local/share/repoatlas/versions/VERSION/` | `~/.local/bin/` |
| Windows | `%LOCALAPPDATA%\RepoAtlas\versions\VERSION\` | `%LOCALAPPDATA%\RepoAtlas\bin\` |

Use `--prefix PATH --bin-dir PATH` to choose both locations. Paths may contain spaces; quote them in your shell. The script prints the absolute command path and an exact command to add its directory to PATH for the current shell session. It does not edit shell profiles, system Python, or your project. Existing commands and directories must belong to this installer before it can reuse them. Choose another location if it reports a conflict. Installation paths that contain a symlink or junction are refused; use their real directory paths.

Run the same command again to verify an existing healthy installation without reinstalling packages. If dependency installation was interrupted, fix the reported problem and rerun the same command: the installer checks the owned environment before resuming. To update later, use `python3 get-repoatlas.py --version X.Y.Z` with the desired published release. Every version has a fixed environment path, and the previous command remains active until the new version is healthy. Older environments are retained. Existing locally edited project skills remain subject to the separate `repoatlas init` conflict check.

For a completely offline installation, copy the release wheel, `SHA256SUMS.txt`, installer, and a compatible dependency wheelhouse to the destination. Then run:

```sh
python3 get-repoatlas.py --offline \
  --wheel /absolute/path/to/repoatlas-0.5.0-py3-none-any.whl \
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
pipx install /absolute/path/to/repoatlas-0.5.0-py3-none-any.whl
# Alternative:
uv tool install /absolute/path/to/repoatlas-0.5.0-py3-none-any.whl
```

After installation, use an existing project directory:

```sh
repoatlas doctor
repoatlas map --repo /absolute/path/to/project --format text --budget-tokens 2000
```

The package name and executable are both `repoatlas`. This guide does not assume a public PyPI release. To create the wheel from source:

```sh
python3 -m pip wheel --no-deps --wheel-dir dist .
```

### Use a virtual environment directly

If you only have pip, use a dedicated environment. On macOS/Linux:

```sh
python3 -m venv /absolute/path/to/atlas-env
/absolute/path/to/atlas-env/bin/python -m pip install /absolute/path/to/repoatlas-0.5.0-py3-none-any.whl
/absolute/path/to/atlas-env/bin/repoatlas doctor
```

On Windows, use PowerShell and the `Scripts` directory:

```powershell
py -3 -m venv C:\tools\atlas-env
C:\tools\atlas-env\Scripts\python.exe -m pip install C:\downloads\repoatlas-0.5.0-py3-none-any.whl
C:\tools\atlas-env\Scripts\repoatlas.exe map --repo C:\projects\example --format text
```

Quote paths that contain spaces. You may also run `python -m repoatlas` with the environment's Python.

## Install the agent skill

The CLI works without installing a skill. To add the bundled workflow to a project:

```sh
repoatlas init --repo /absolute/path/to/project --plan
repoatlas init --repo /absolute/path/to/project
```

The default destination is `.agents/skills/repoatlas-jvm/`. For a Claude Code project path:

```sh
repoatlas init --repo /absolute/path/to/project --skills-dir .claude/skills
```

`--plan` inspects the installation without writing files. The installer preserves locally edited managed files and reports a conflict. It does not edit your agent instructions, hooks, or Git configuration. Point your agent at the installed `SKILL.md`; discovery and invocation conventions depend on the host runtime. [Agent integration](docs/agents.md).

## Install a project-local ZIP bundle

Build the ZIP from a source checkout, or use a previously built archive:

```sh
python3 scripts/build_bundle.py
```

Extract `dist/repoatlas-0.5.0.zip`, open its extracted directory, and run:

```sh
python3 install.py --repo /absolute/path/to/project
python3 run.py --repo /absolute/path/to/project map --format text --budget-tokens 2000
```

The installer creates `.repoatlas/runtime/`, installs the skill, and performs the first index synchronization. Use `--no-index` to defer that synchronization, or `--plan` to inspect changes. The installation remains usable after moving the original extracted bundle.

Run the installed skill directly on macOS/Linux:

```sh
/absolute/path/to/project/.repoatlas/runtime/bin/python -E -s \
  /absolute/path/to/project/.agents/skills/repoatlas-jvm/scripts/atlas.py \
  map --repo /absolute/path/to/project --format text
```

On Windows, the runtime interpreter is `.repoatlas/runtime/Scripts/python.exe`. Do not copy an existing virtual environment between operating systems; create the runtime on the destination machine.

## Offline installation

Prepare dependency wheels on a connected machine with the **same OS, CPU architecture, and Python version** as the destination. From a checkout or extracted ZIP:

```sh
python3 -m pip download --only-binary=:all: --dest /absolute/path/to/wheels \
  -r skills/repoatlas-jvm/scripts/requirements.txt
```

Copy the wheelhouse and RepoAtlas artifact to the offline machine. For a project-local ZIP installation:

```sh
python3 install.py --repo /absolute/path/to/project --offline --wheelhouse /absolute/path/to/wheels
```

For a dedicated environment with pip:

```sh
python -m pip install --no-index --find-links /absolute/path/to/wheels \
  /absolute/path/to/repoatlas-0.5.0-py3-none-any.whl
```

For MCP, also download `skills/repoatlas-jvm/scripts/requirements-mcp.txt`; add `--mcp` to the ZIP installer or install the wheel's `[mcp]` extra. Keep the requirements files with the wheelhouse so dependency pins remain reviewable.

## Enable MCP

Install the optional dependency in the same environment that runs `repoatlas serve`:

```sh
python -m pip install '/absolute/path/to/repoatlas-0.5.0-py3-none-any.whl[mcp]'
repoatlas sync --repo /absolute/path/to/project
repoatlas serve --repo /absolute/path/to/project
```

With pipx, use `pipx install '/absolute/path/to/repoatlas-0.5.0-py3-none-any.whl[mcp]'` when installing. For ZIP installation, pass `--mcp`. The server uses stdio and a saved index; it does not synchronize on each request. See [client configuration and tools](docs/agents.md#mcp).

## Updates and local files

Reinstall the new wheel with your chosen tool, then run `repoatlas init --repo PATH` to update the installed skill. Examples for an existing installation:

```sh
pipx install --force /absolute/path/to/repoatlas-0.5.0-py3-none-any.whl
# Or, for a uv installation:
uv tool install --force /absolute/path/to/repoatlas-0.5.0-py3-none-any.whl
```

For a ZIP installation, run the new bundle's `install.py` against the same project. Review reported conflicts rather than deleting locally edited skill files. A runtime ownership marker prevents adoption of an unrelated environment. If dependency installation fails, fix the reported issue and rerun; an interrupted package install may have partially changed the environment.

The default graph cache is `.repoatlas/jvm-v2.sqlite`. Add `.repoatlas/` to the target project's ignore rules. The directory may also contain a dedicated runtime, receipts, and telemetry, so deleting it removes more than the graph. The `repoatlas-jvm` skill ID and `jvm-v2.sqlite` filename remain for compatibility with earlier installations.

## Troubleshooting

| Symptom | Check and next step |
| --- | --- |
| `repoatlas` is not found | Check the pipx/uv binary directory is on PATH, or use the environment's absolute executable path. |
| `doctor` reports a missing dependency | Install the matching wheel or requirements in the interpreter running the CLI. |
| `doctor` reports `fts5: false` | Use a Python distribution whose SQLite build includes FTS5, then recreate the dedicated environment. |
| Installation reports a managed-file conflict | Compare the local file with the new bundle; preserve your changes before retrying. |
| Installation is locked | Check for a live installer. Only after it has stopped, remove an empty stale `.repoatlas/.bootstrap-lock` directory. |
| MCP reports an unavailable or stale index | Run CLI `sync` for the same repository and DB; MCP uses snapshots. |
| Offline pip cannot find a distribution | Confirm the wheelhouse contains every pinned dependency for the destination platform and Python version. |

For a reproducible report, include `doctor`, the exact command, relevant diagnostics, and a small synthetic fixture. [Support](SUPPORT.md).

## Releases that require authentication

If this repository or a private fork requires GitHub sign-in, direct asset URLs cannot be downloaded anonymously. Sign in to the release page and download the wheel; then run `uv tool install ./repoatlas-0.5.0-py3-none-any.whl` or `pipx install ./repoatlas-0.5.0-py3-none-any.whl`.

With the GitHub CLI already authenticated, download the installer inputs together:

```sh
gh release download v0.5.0 --repo ch4570/repo-graph \
  --pattern 'repoatlas-0.5.0-py3-none-any.whl' --pattern SHA256SUMS.txt --pattern get-repoatlas.py
python3 get-repoatlas.py --wheel ./repoatlas-0.5.0-py3-none-any.whl --checksum-file ./SHA256SUMS.txt
```

Use `py -3` instead of `python3` on Windows. No GitHub token is stored by the installer. Dependencies still come from the public package index unless you also provide `--offline --wheelhouse PATH`.
