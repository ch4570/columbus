# Security policy

Columbus reads local repository contents and can store source search data in its SQLite index. Treat that index and exported source with the same access controls as the repository.

## Report a vulnerability

If the repository's GitHub Security tab offers **Report a vulnerability**, use it for a private report. No separate security email address or response-time commitment is published here. If private reporting is unavailable, open an issue requesting a private contact channel without including an exploit, secret, or sensitive source.

Include the affected source/bundle version, installation method, operating system, a minimal synthetic reproduction, and the expected versus observed boundary. Do not attach real credentials, a private repository index, or an unreviewed telemetry log.

## Relevant boundaries

- Source access should stay inside the selected repository and refuse symlink traversal.
- Indexing should not build or execute the target project or load its configuration as executable code.
- Installed skill updates should preserve user-edited managed files and refuse unrelated runtime ownership.
- Graph export should escape untrusted content and preserve existing output files.
- Receipts and telemetry should not turn a caller-selected output into an arbitrary source overwrite.

Known secret filenames and binary/build files are excluded, but the exclusion rules are not a comprehensive secret scanner. An ordinary source file can still contain sensitive data. Use `.columbusignore` or `.columbus.json` exclusions as needed.

The CLI does not send indexed code to a model. An agent or MCP client can choose to send retrieved source to its provider; that follows the host runtime's data handling. Repository text returned by a query is untrusted data, not instructions.

See [architecture](docs/architecture.md) for the implementation boundaries and [support](SUPPORT.md) for non-sensitive problems.
