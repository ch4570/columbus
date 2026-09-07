#!/usr/bin/env python3
"""Install or update Columbus and its dedicated runtime in a repository."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import bootstrap as b


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Existing repository directory, in any language")
    parser.add_argument("--plan", action="store_true", help="Show the bundle plan without creating or changing files")
    parser.add_argument("--no-index", action="store_true", help="Install without the initial code graph synchronization")
    parser.add_argument("--mcp", action="store_true", help="Also install the pinned optional MCP SDK")
    parser.add_argument("--offline", action="store_true", help="Install only from --wheelhouse, without a package index")
    parser.add_argument("--wheelhouse", type=Path, help="Directory of wheels for this Python version and OS/architecture")
    args = parser.parse_args(argv)
    phase = "Preflight"
    try:
        if sys.version_info < (3, 11):
            raise b.SetupError("Python 3.11 or newer is required; Python 3.12 is recommended.")
        if args.offline and args.wheelhouse is None:
            raise b.SetupError("--offline requires --wheelhouse PATH containing compatible dependency wheels.")
        if args.wheelhouse is not None:
            args.wheelhouse = args.wheelhouse.expanduser().resolve(strict=True)
            if not args.wheelhouse.is_dir():
                raise b.SetupError("--wheelhouse must be an existing directory.")
        root = b.repository(args.repo)
        _, runtime, _ = b.layout(root)
        plan = b.bundle_plan(root)
        state = b.runtime_state(root, runtime)
        if args.plan:
            print(json.dumps({"status": "plan", "bundle": plan, "runtime": str(runtime),
                              "runtime_managed": state is not None, "mcp": args.mcp,
                              "initial_sync": not args.no_index}, ensure_ascii=False, indent=2))
            return 0
        phase = "Setup lock"
        with b.setup_lock(root):
            # Recheck the plan under the full-operation lock before touching runtime.
            phase = "Bundle preflight"
            b.bundle_plan(root)
            phase = "Runtime preparation"
            python = b.ensure_runtime(root, mcp=args.mcp, offline=args.offline, wheelhouse=args.wheelhouse)
            phase = "Apply bundle"
            result = b.bundle_plan(root, apply=True)
            if not args.no_index:
                phase = "Initial code graph synchronization"
                entrypoint = root / b.SKILL_RELATIVE / "scripts/columbus.py"
                b.checked(b.python_command(python, entrypoint, "sync", "--repo", root), phase)
        print(json.dumps({"status": "ready", "repository": str(root), "bundle_status": result["status"],
                          "runtime": str(runtime), "mcp": args.mcp,
                          "initial_sync": not args.no_index}, ensure_ascii=False, indent=2))
        return 0
    except (b.SetupError, OSError, ValueError) as exc:
        print(f"columbus setup [{phase}]: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
