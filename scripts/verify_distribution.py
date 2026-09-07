#!/usr/bin/env python3
"""Exercise a built wheel in a clean venv, including installed skill resources."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import venv
import zipfile


class VerificationError(RuntimeError):
    pass


def verify_archive(artifact: Path, target: Path) -> Path:
    with zipfile.ZipFile(artifact) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise VerificationError("Archive has duplicate members")
        prefixes = set()
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or len(path.parts) < 2:
                raise VerificationError(f"Unsafe archive path: {name}")
            prefixes.add(path.parts[0])
        if len(prefixes) != 1:
            raise VerificationError("Archive must have one top-level directory")
        prefix = prefixes.pop() + "/"
        manifest_name = prefix + "BUNDLE-MANIFEST.json"
        inventory = json.loads(archive.read(manifest_name))
        actual = {name[len(prefix):] for name in names if name != manifest_name}
        if actual != set(inventory["files"]):
            raise VerificationError("Archive inventory does not cover exactly its contents")
        for name, digest in inventory["files"].items():
            if hashlib.sha256(archive.read(prefix + name)).hexdigest() != digest:
                raise VerificationError(f"Archive checksum mismatch: {name}")
        archive.extractall(target)
        return target / prefix


def verify(wheel: Path, *, wheelhouse: Path | None = None, offline: bool = False,
           bundle: Path | None = None) -> dict:
    environment = dict(os.environ)
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        environment.pop(name, None)
    environment["PYTHONNOUSERSITE"] = "1"
    with tempfile.TemporaryDirectory(prefix="repoatlas distribution ") as temporary:
        root = Path(temporary).resolve()
        unrelated = root / "unrelated working directory"
        unrelated.mkdir()

        def run(command: list[str], expected: int = 0) -> str:
            result = subprocess.run(list(map(str, command)), cwd=unrelated, env=environment,
                                    capture_output=True, text=True, encoding="utf-8")
            if result.returncode != expected:
                raise VerificationError(f"Command failed ({result.returncode}, expected {expected}): {command}\n{result.stdout}\n{result.stderr}")
            return result.stdout

        runtime = root / "fresh environment with spaces"
        # Match `python -m venv`: relocatable POSIX Python distributions need
        # their executable symlinked so the interpreter can find its libraries.
        venv.EnvBuilder(with_pip=True, symlinks=os.name != "nt").create(runtime)
        binary = runtime / ("Scripts" if os.name == "nt" else "bin")
        python = binary / ("python.exe" if os.name == "nt" else "python")
        cli = binary / ("repoatlas.exe" if os.name == "nt" else "repoatlas")
        installation = [python, "-I", "-m", "pip", "--disable-pip-version-check", "install", "--no-input"]
        if offline:
            installation.append("--no-index")
        if wheelhouse:
            installation.extend(["--find-links", wheelhouse])
        run([*installation, wheel])
        if "repoatlas explore" not in run([cli]):
            raise VerificationError("Installed CLI did not show its getting-started guide")
        run([cli, "doctor"])
        version = run([python, "-I", "-c", "import importlib.metadata as m; print(m.version('repoatlas'))"]).strip()
        repo = root / "target repository with spaces"
        repo.mkdir()
        (repo / "payments.py").write_text("def settle_payment(amount):\n    return amount * 2\n", encoding="utf-8")
        fixtures = {
            "pricing.ts": "export function calculateTotal(price: number) { return price; }\n",
            "checkout.ts": "import { calculateTotal } from './pricing';\nexport function checkout() { return calculateTotal(3); }\n",
            "worker.go": "package worker\nfunc ProcessJob() int { return 1 }\n",
            "worker.rs": "fn validate_job() -> bool { true }\n",
            "Gateway.java": "class Gateway { int authorize() { return 1; } }\n",
            "Orders.kt": "class Orders { fun submitOrder(): Int = 1 }\n",
            "workflow.custom": "routine reserve_inventory\n",
            "ARCHITECTURE.unfamiliar": "The unusual_fallback_anchor documents the queue boundary.\n",
            ".repoatlas.json": json.dumps({"extensions": {".custom": "workflow"}, "declarations": {"workflow": ["routine"]}}),
        }
        for name, source in fixtures.items():
            (repo / name).write_text(source, encoding="utf-8")
        run([cli, "--repo", repo, "sync"])
        result = run([cli, "search", "settle_payment", "--repo", repo])
        if "settle_payment" not in result:
            raise VerificationError("Installed global CLI did not index the Python fixture")
        for name in ("calculateTotal", "ProcessJob", "validate_job", "authorize", "submitOrder", "reserve_inventory", "unusual_fallback_anchor"):
            if not json.loads(run([cli, "--repo", repo, "search", name]))["hits"]:
                raise VerificationError(f"Installed language/fallback search failed: {name}")
        packet_text = run([cli, "--repo", repo, "context", "calculateTotal", "--budget-tokens", "700"])
        packet = json.loads(packet_text)
        if not packet["items"] or len(packet_text.encode("utf-8")) > 2100 or packet["estimated_tokens"] > 700:
            raise VerificationError("Installed context violated its payload budget")
        outline = json.loads(run([cli, "--repo", repo, "map", "--budget-tokens", "2000"]))
        if outline["coverage"]["files"] != 9:
            raise VerificationError("Installed map did not cover the polyglot fixture")
        text_map = run([cli, "--repo", repo, "map", "--format", "text", "--budget-tokens", "700"])
        if "UNTRUSTED" not in text_map or len(text_map.encode("utf-8")) > 2100:
            raise VerificationError("Installed text map lost its evidence boundary or output budget")
        receipt, telemetry = root / "receipt.json", root / "queries.jsonl"
        delivered = []
        for _ in range(3):
            output = run([cli, "--repo", repo, "context", "settle_payment", "--path", "payments.py",
                          "--format", "text", "--budget-tokens", "700",
                          "--receipt", receipt, "--telemetry", telemetry])
            if len(output.encode("utf-8")) > 2100:
                raise VerificationError("Installed receipt context violated its output budget")
            row = json.loads(telemetry.read_text(encoding="utf-8").splitlines()[-1])
            if row["output_bytes"] != len(output.encode("utf-8")):
                raise VerificationError("Installed telemetry differs from actual output bytes")
            delivered.append(row["source_bytes"])
        if delivered[0] == 0 or delivered[-1] != 0:
            raise VerificationError("Installed receipt did not deliver then exhaust a small source file")
        totals = json.loads(run([cli, "telemetry", telemetry, "--format", "json"]))
        if totals["queries"] != 3 or totals["source_bytes"] != sum(delivered):
            raise VerificationError("Installed telemetry summary lost query measurements")
        for _ in range(3):
            output = run([cli, "explore", "settle_payment", "--repo", repo,
                          "--path", "payments.py", "--session", "first-task"])
            if "UNTRUSTED" not in output or len(output.encode("utf-8")) > 6000:
                raise VerificationError("Installed explore exceeded its default text budget")
        session = json.loads(run([cli, "stats", "first-task", "--repo", repo, "--format", "json"]))
        if session["queries"] != 3 or session["source_bytes"] == 0:
            raise VerificationError("Installed named session failed to collect source observations")
        for format in ("html", "graphml", "mermaid", "json"):
            run([cli, "--repo", repo, "graph", "--format", format, "--level", "file", "--output", root / ("graph." + format)])
        warm = json.loads(run([cli, "--repo", repo, "sync"]))
        if warm["refresh"]["parsed_files"] or warm["refresh"]["hashed_files"]:
            raise VerificationError("Unchanged installed index was reparsed or rehashed")
        planned = json.loads(run([cli, "--repo", repo, "init", "--plan"]))
        if (repo / ".agents").exists():
            raise VerificationError("init --plan changed the repository")
        run([cli, "--repo", repo, "init"])
        destination = repo / ".agents/skills/repoatlas-jvm"
        lock = json.loads((destination / ".bundle-lock.json").read_text(encoding="utf-8"))
        for name, digest in lock["files"].items():
            if hashlib.sha256((destination / name).read_bytes()).hexdigest() != digest:
                raise VerificationError(f"Installed skill checksum mismatch: {name}")
        repeated = json.loads(run([cli, "--repo", repo, "init"]))
        if repeated.get("status") != "noop":
            raise VerificationError(f"Repeated skill install must be noop: {repeated}")
        run([python, "-E", "-s", destination / "scripts/atlas.py", "--repo", repo, "search", "settle_payment"])
        skill = destination / "SKILL.md"
        local = skill.read_bytes() + b"\nLocal team instructions.\n"
        skill.write_bytes(local)
        run([cli, "--repo", repo, "init"], expected=2)
        if skill.read_bytes() != local:
            raise VerificationError("Reinstall overwrote local skill edits")
        # Reinstall the wheel itself while keeping its dependencies and verify
        # that the global entry point and package resources remain usable.
        run([*installation, "--force-reinstall", "--no-deps", wheel])
        run([cli, "--repo", repo, "status"])
        standalone = Path(__file__).resolve().parents[1] / "get-repoatlas.py"
        release_checksums = root / "release-checksums.txt"
        release_checksums.write_text(hashlib.sha256(wheel.read_bytes()).hexdigest() + "  " + wheel.name + "\n", encoding="ascii")
        global_bin = root / "global commands"
        release_install = [python, standalone, "--version", version,
                           "--prefix", root / "managed release environments", "--bin-dir", global_bin,
                           "--wheel", wheel, "--checksum-file", release_checksums]
        if offline:
            release_install.append("--offline")
        if wheelhouse:
            release_install.extend(["--wheelhouse", wheelhouse])
        run(release_install)
        run(release_install)
        global_cli = global_bin / ("repoatlas.cmd" if os.name == "nt" else "repoatlas")
        if run([global_cli, "--version"]).strip() != version:
            raise VerificationError("Standalone release installer did not activate the requested version")
        run([global_cli, "explore", "settle_payment", "--repo", repo])
        archive_files = None
        if bundle:
            extracted = verify_archive(bundle, root / "extracted bundle")
            archive_files = len(json.loads((extracted / "BUNDLE-MANIFEST.json").read_text(encoding="utf-8"))["files"])
            bootstrap_repo = root / "portable bootstrap target"
            bootstrap_repo.mkdir()
            (bootstrap_repo / "Orders.kt").write_text(fixtures["Orders.kt"], encoding="utf-8")
            (bootstrap_repo / "payments.py").write_text("def settle_payment(): return 1\n", encoding="utf-8")
            run([python, extracted / "install.py", "--repo", bootstrap_repo, "--plan"])
            command = [python, extracted / "install.py", "--repo", bootstrap_repo]
            if offline:
                command.append("--offline")
            if wheelhouse:
                command.extend(["--wheelhouse", wheelhouse])
            run(command)
            run(command)
            run([python, extracted / "run.py", "--repo", bootstrap_repo, "doctor"])
            if not json.loads(run([python, extracted / "run.py", "--repo", bootstrap_repo, "search", "submitOrder"]))["hits"]:
                raise VerificationError("ZIP bootstrap did not create its initial JVM index")
            extracted.rename(root / "relocated archive source")
            local_python = bootstrap_repo / ".repoatlas/runtime" / binary.name / python.name
            local_atlas = bootstrap_repo / ".agents/skills/repoatlas-jvm/scripts/atlas.py"
            run([local_python, "-E", "-s", local_atlas, "doctor"])
        return {"status": "passed", "version": version, "wheel": str(wheel),
                "clean_venv": True, "unrelated_cwd": True, "paths_with_spaces": True,
                "global_search": True, "skill_reinstall": repeated["status"],
                "polyglot_and_fallback": True, "budgeted_context": True, "graph_formats": 4,
                "text_budget": True, "receipt_continuation": True, "telemetry_bytes_verified": True,
                "named_sessions": True, "no_argument_guide": True, "standalone_release_install": True,
                "local_edits_preserved": True, "managed_files": len(lock["files"]),
                "archive_files": archive_files, "plan_status": planned.get("status")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)
    if args.offline and args.wheelhouse is None:
        parser.error("--offline requires --wheelhouse")
    try:
        result = verify(args.wheel.resolve(strict=True),
                        bundle=args.bundle.resolve(strict=True) if args.bundle else None,
                        wheelhouse=args.wheelhouse.resolve(strict=True) if args.wheelhouse else None,
                        offline=args.offline)
    except (OSError, ValueError, KeyError, VerificationError, subprocess.CalledProcessError) as error:
        print(f"Distribution verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
