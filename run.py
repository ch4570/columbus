#!/usr/bin/env python3
"""Run the installed Columbus using its repository-owned Python environment."""
from __future__ import annotations

import argparse
import sys

sys.dont_write_bytecode = True
import bootstrap as b


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print('Columbus repository runner\n\n'
              '  python3 run.py --repo /path/to/project explore\n'
              '  python3 run.py --repo /path/to/project explore checkout --session checkout-task\n'
              '  python3 run.py --repo /path/to/project stats checkout-task\n\n'
              'Set up the target first with: python3 install.py --repo /path/to/project')
        return 0
    parser = argparse.ArgumentParser(description=__doc__, epilog="Example: python3 run.py --repo /path/to/project search PaymentService")
    parser.add_argument("--repo", required=True)
    parser.add_argument("command", choices=["doctor", "tree", "hook-install", "hook-update", "sync", "status", "search", "symbol", "neighbors", "impact", "context", "map", "explore", "stats", "graph", "serve", "telemetry"])
    parser.add_argument("arguments", nargs=argparse.REMAINDER, help="Arguments passed to columbus.py (use COMMAND --help for details)")
    args = parser.parse_args(argv)
    try:
        root = b.repository(args.repo)
        _, runtime, skill = b.layout(root)
        lock = b.internal(root, ".columbus/.bootstrap-lock")
        if lock.exists():
            raise b.SetupError("Repository setup is in progress or its lock is stale. Finish installation before running code queries.")
        state = b.runtime_state(root, runtime)
        if not state or not state.get("requirements_sha256"):
            raise b.SetupError("Runtime setup is incomplete. Run install.py --repo PATH first.")
        python = b.interpreter(root, runtime)
        entrypoint = b.internal(root, b.SKILL_RELATIVE / "scripts/columbus.py")
        if not python.is_file() or not entrypoint.is_file():
            raise b.SetupError("Installed runtime or skill is missing. Rerun install.py --repo PATH.")
        if any(value == "--repo" or value.startswith("--repo=") for value in args.arguments):
            raise b.SetupError("Specify --repo only before the command.")
        command = b.python_command(python, entrypoint, args.command)
        if args.command != "doctor":
            command.extend(["--repo", str(root)])
        command.extend(args.arguments)
        return b.invoke(command).returncode
    except (b.SetupError, OSError, ValueError) as exc:
        print(f"columbus run: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
