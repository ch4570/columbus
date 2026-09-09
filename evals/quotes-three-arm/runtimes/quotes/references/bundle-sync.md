# Repository bundle installation and updates

One skill contains the engine, installer, instructions, and pinned requirements. Avoid distributing several skills with independent engine copies that can drift.

## Apply to a local repository

Resolve `SKILL_DIR` from the selected skill and inspect the plan:

```bash
python3 "$SKILL_DIR/scripts/install.py" --repo "$REPO"
```

For an already-requested install/update with no conflicts, apply it:

```bash
python3 "$SKILL_DIR/scripts/install.py" --repo "$REPO" --apply
```

Default target: `REPO/.agents/skills/columbus`. A host using another directory can select `--skills-dir .claude/skills`. Do not duplicate copies unless requested. Creating a directory does not prove a particular host has loaded it.

To update from another reviewed local bundle, pass `--source /absolute/path/to/columbus`. The installer does not fetch moving branches or execute downloaded installers. Version plus managed-file hashes identifies the content even when a version string is reused.

## Managed files and conflicts

The installed `.bundle-lock.json` records version and file SHA-256 values. Planning compares new source, last-installed content, and current repository files.

| State | Action |
|---|---|
| Same source and installed content | No-op |
| Upstream changed, local equals previous content | Update managed file |
| Upstream removed unchanged managed file | Remove managed file |
| Locally edited or intentionally deleted managed file | Report conflict; preserve local work |
| Unrelated additional file | Preserve |
| Unmanaged destination or colliding new file | Report conflict |
| Symlink/path escape/malformed manifest | Refuse update |

There is no blanket force option. Resolve local customizations deliberately or keep them in a separate project reference; never silently delete them to make installation succeed.

The installer stages a candidate directory and uses locking, replacement, and rollback for ordinary failures. Multiple directory rename operations are not a fully crash-transactional installation. Inspect interrupted state rather than inferring success from a version alone.

The installer does not edit `AGENTS.md`, `.gitignore`, hooks, build files, or MCP host settings. Team use should version the installed skill and its manifest using the user's normal repository process. Generated `.columbus/` databases/virtual environments should stay untracked; adding ignore rules is a separate project edit when needed.

After upgrade, run `doctor` with the selected interpreter and update pinned dependencies. Subsequent index sync invalidates incompatible analyzer/configuration state. Old schema 1 DBs are not silently migrated/deleted; schema 2 and 3 snapshots are readable and atomically rebuilt into compressed schema 4 on the next sync. Older engines require their own DB path after this upgrade.
