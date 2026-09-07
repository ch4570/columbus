# Support

For installation questions, start with [INSTALL.md](INSTALL.md#troubleshooting). For unexpected graph or retrieval results, check [language coverage](docs/languages.md), [CLI usage](docs/usage.md), and [validation limits](VALIDATION.md).

## Report a reproducible problem

Open a repository issue and include:

- The exact command, RepoAtlas version, OS, Python version, and installation method.
- The relevant `repoatlas doctor` output and index diagnostics.
- Expected and observed behavior, including output format and budgets.
- A small synthetic fixture or a public source path and revision that reproduces it.

For a wrong relationship, include symbol IDs, source locations, `fidelity`, and `confidence`. For a token-efficiency concern, include both the task outcome and the measurement definition; a byte estimate and model billing are different measurements.

Review attachments before sharing. Source indexes can contain repository text. Use the [security policy](SECURITY.md) for vulnerabilities or sensitive details.

## Request a feature

Describe the repository task you want to complete, the current obstacle, the smallest useful outcome, and how success could be verified. A concrete language fixture or agent exploration trace is more actionable than a request for “full support.”

This repository does not publish a support SLA. Contributions and reproducible reports are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).
