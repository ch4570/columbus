"""Fetch pinned upstream slices and compare discovery workflows without a model.

Only this script's temporary fixtures/index/archive and explicit report directory
are written. Upstream source, copyright notices and Apache licenses are downloaded
verbatim; no project code, tests or builds from the upstream repositories run.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import re
import shlex
import subprocess
import sys
import tempfile
from urllib.request import urlopen


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPTS = ROOT / "skills/columbus/scripts"
CLI = SCRIPTS / "columbus.py"
COMMAND_LOG = []
sys.path.insert(0, str(SCRIPTS))

from columbus.archive import _validated_rows, archive
from columbus.index import RepositoryIndex


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inventory():
    paths = [HERE / "pins.json", Path(__file__)]
    paths += sorted(SCRIPTS.rglob("*.py"))
    return {path.relative_to(ROOT).as_posix(): sha(path.read_bytes()) for path in paths}


def download(case, path, expected_hash):
    url = f"https://raw.githubusercontent.com/{case['repository']}/{case['commit']}/{path}"
    with urlopen(url, timeout=30) as response:
        content = response.read()
    require(sha(content) == expected_hash, f"Upstream hash mismatch: {url}")
    return content, dict(url=url, sha256=expected_hash, bytes=len(content))


def command(repo, arguments):
    argv = [sys.executable, str(CLI), *arguments]
    result = subprocess.run(argv, cwd=repo, capture_output=True, timeout=120)
    display = shlex.join(argv)
    receipt = dict(command=display, command_bytes=len(display.encode("utf-8")),
                   exit_code=result.returncode, stdout_bytes=len(result.stdout),
                   stderr_bytes=len(result.stderr), stdout_sha256=sha(result.stdout),
                   stderr_sha256=sha(result.stderr))
    COMMAND_LOG.append(dict(case=repo.name, **receipt))
    return receipt, result.stdout.decode("utf-8"), result.stderr.decode("utf-8")


def search_packet(text, fmt):
    if fmt == "json":
        return json.loads(text)
    lines = text.splitlines()
    require(lines[1].startswith("metadata ") and lines[2] == "declarations",
            "Unexpected archive-search text framing")
    packet = json.loads(lines[1][9:])
    packet["items"] = [json.loads(line) for line in lines[3:]]
    return packet


def source_packet(text, fmt):
    if fmt == "json":
        return json.loads(text)
    lines = text.splitlines()
    require(lines[1].startswith("metadata "), "Unexpected archive-source framing")
    packet = json.loads(lines[1][9:])
    packet.update(targets=[], sources=[])
    files, section, current = {}, None, None
    for line in lines[2:]:
        if line.startswith("files ["):
            section = "files"
        elif line.startswith("targets ["):
            section = "targets"
        elif line.startswith("sources:"):
            section = "sources"
        elif section == "files":
            number, path, digest = json.loads(line)
            files[number] = (path, digest)
        elif section == "targets":
            number, target = json.loads(line)
            target.update(path=files[number][0], source_hash=files[number][1])
            packet["targets"].append(target)
        elif section == "sources" and line.startswith("source "):
            current = json.loads(line[7:])
            number = current.pop("file_number")
            current.update(path=files[number][0], source_hash=files[number][1], source="")
            current["_physical_rows"] = []
            packet["sources"].append(current)
        elif section == "sources":
            match = re.fullmatch(r"(\d+)\| (.*)", line)
            require(match is not None and current is not None, "Unexpected physical source row")
            current["_physical_rows"].append((int(match[1]), match[2]))
        else:
            raise ValueError("Unexpected source section")
    for block in packet["sources"]:
        physical = block.pop("_physical_rows")
        require([n for n, _ in physical] == list(range(block["start_line"], block["end_line"] + 1)),
                "Source line numbering is not contiguous")
        block["source"] = "\n".join(line for _, line in physical)
    return packet


def expected_targets(case, definition=None):
    definition = definition or case
    return {f"{case['path']}::{definition['query']}:{signature}": (start, end)
            for signature, start, end in definition["declarations"]}


def physical_lines(content):
    # Independently use physical LF coordinates, not parser/renderer helpers.
    lines = content.decode("utf-8").replace("\r\n", "\n").split("\n")
    return lines[:-1] if lines[-1] == "" else lines


def expected_rows(case, content, targets):
    lines = physical_lines(content)
    selected = sorted({number for start, end in targets.values() for number in range(start, end + 1)})
    return [(case["path"], number, lines[number - 1]) for number in selected]


def validate_source(packet, case, targets):
    require("targets" in packet, "Expected batch source response")
    returned = {target["id"]: (target["declaration_start_line"], target["declaration_end_line"])
                for target in packet["targets"]}
    require(len(packet["targets"]) == len(returned), "Duplicate returned target")
    require(returned == targets, "Returned declaration IDs/ranges differ from frozen source oracle")
    require(packet["semantic_complete"] is False, "Source retrieval claimed complete semantics")
    rows = []
    for target in packet["targets"]:
        require(target["path"] == case["path"] and target["source_hash"] == case["sha256"],
                "Target provenance mismatch")
        require(target["fidelity"] == "ast" and target["partial"] is False,
                "Expected complete AST declaration")
    for block in packet["sources"]:
        require(block["path"] == case["path"] and block["source_hash"] == case["sha256"],
                "Source block provenance mismatch")
        lines = block["source"].split("\n")
        require(len(lines) == block["end_line"] - block["start_line"] + 1,
                "Source extent does not match its physical line count")
        rows.extend((block["path"], number, line)
                    for number, line in enumerate(lines, block["start_line"]))
    return rows


def read_pages(repo, queries, fmt, overloads, case, targets, limit=400):
    rows, receipts, offset = [], [], 0
    while True:
        args = ["archive-source", *queries, "--input", "graph.jsonl.xz", "--repo", ".",
                "--format", fmt, "--limit", str(limit), "--budget-bytes", "32000"]
        if overloads:
            args.append("--overloads")
        if offset:
            args += ["--offset", str(offset)]
        receipt, stdout, stderr = command(repo, args)
        receipts.append(receipt)
        require(receipt["exit_code"] == 0 and not stderr, f"Source command failed: {stderr}")
        require(receipt["stdout_bytes"] <= 32000, "Source response exceeded byte budget")
        packet = source_packet(stdout, fmt)
        if overloads:
            require("same-owner JVM overload groups" in packet.get("selection", ""),
                    "Grouped source selection lacks provenance")
        require(packet["offset"] == offset, "Incorrect pagination offset")
        page_rows = validate_source(packet, case, targets)
        require(page_rows and len(page_rows) <= limit, "Empty or oversized source page")
        rows.extend(page_rows)
        require(packet["next_offset"] in (None, len(rows)), "Incorrect next source offset")
        offset = packet["next_offset"]
        if offset is None:
            require(packet["total_lines"] == len(rows), "Source pagination ended early")
            break
    return rows, receipts


def totals(receipts):
    return dict(command_count=len(receipts), command_bytes=sum(r["command_bytes"] for r in receipts),
                response_bytes=sum(r["stdout_bytes"] + r["stderr_bytes"] for r in receipts),
                failed_commands=sum(r["exit_code"] != 0 for r in receipts), commands=receipts)


def rejected(repo, args):
    receipt, stdout, stderr = command(repo, args)
    return dict(passed=receipt["exit_code"] != 0 and not stdout and "ambiguous or absent" in stderr,
                expected="nonzero ambiguous-or-absent failure with no source output",
                observed_error=stderr.strip(), receipt=receipt)


def run_case(case, parent):
    repo = parent / case["id"]
    repo.mkdir()
    content, source_receipt = download(case, case["path"], case["sha256"])
    require(len(content) == case["bytes"], "Frozen source byte length mismatch")
    source = repo / case["path"]
    source.parent.mkdir(parents=True)
    source.write_bytes(content)
    license_body, license_receipt = download(case, case["license_path"], case["license_sha256"])
    (repo / case["license_path"]).write_bytes(license_body)
    index = RepositoryIndex(parent / (case["id"] + ".sqlite"))
    index.refresh(repo)
    exported = archive(index, repo / "graph.jsonl.xz", "xz")
    expected = expected_targets(case)
    oracle = expected_rows(case, content, expected)
    with (repo / "graph.jsonl.xz").open("rb") as raw:
        nodes = [data for kind, data in _validated_rows(raw) if kind == "node"]
    actual = {n["id"]: (n["start_line"], n["end_line"])
              for n in nodes if n["qualname"] == case["query"]}
    require(actual == expected, "Indexed family differs from frozen declaration oracle")
    result = dict(id=case["id"], repository=case["repository"], commit=case["commit"],
                  source=source_receipt, license=license_receipt,
                  archive_sha256=exported["sha256"], indexed_files=exported["files"],
                  declarations=len(expected), physical_source_lines=len(oracle),
                  source_rows_sha256=sha(json.dumps(oracle, ensure_ascii=False).encode()),
                  workflows={}, controls={})
    for fmt in ("text", "json"):
        args = ["archive-search", case["query"], "--input", "graph.jsonl.xz", "--format", fmt,
                "--limit", "50", "--budget-bytes", "32000"]
        discovery, stdout, stderr = command(repo, args)
        require(discovery["exit_code"] == 0 and not stderr, f"Discovery failed: {stderr}")
        search = search_packet(stdout, fmt)
        ids = [item["id"] for item in search["items"]]
        require(not search["truncated"] and set(ids) == set(expected), "Incomplete old-workflow discovery")
        before_rows, before_commands = read_pages(repo, ids, fmt, False, case, expected)
        after_rows, after_commands = read_pages(repo, [case["query"]], fmt, True, case, expected)
        require(before_rows == after_rows == oracle, "Retrieved physical source differs from frozen source")
        before, after = totals([discovery, *before_commands]), totals(after_commands)
        result["workflows"][fmt] = dict(baseline=before, overloads=after,
                                             exact_target_parity=True, source_hash_parity=True,
                                             physical_source_parity=True,
                                             command_bytes_change=after["command_bytes"] - before["command_bytes"],
                                             response_bytes_change=after["response_bytes"] - before["response_bytes"])
    args = ["archive-source", case["query"], "--input", "graph.jsonl.xz", "--repo", "."]
    result["controls"]["unflagged_ambiguity"] = rejected(repo, args)
    exact = next(iter(expected))
    rows, receipts = read_pages(repo, [exact], "text", True, case, {exact: expected[exact]})
    result["controls"]["exact_id_stays_single"] = dict(
        passed=rows == expected_rows(case, content, {exact: expected[exact]}),
        declaration_id=exact, commands=receipts)
    rows, receipts = read_pages(repo, [case["query"]], "text", True, case, expected, limit=17)
    result["controls"]["grouped_pagination"] = dict(passed=rows == oracle,
                                                          pages=len(receipts), physical_source_lines=len(rows))
    if "receiver_control" in case:
        control = case["receiver_control"]
        receivers = sorted({node["receiver_type"] for node in nodes if node["qualname"] == control["query"]})
        require(receivers == control["receivers"], "Receiver negative control lacks expected distinct receivers")
        args = ["archive-source", control["query"], "--overloads", "--input", "graph.jsonl.xz", "--repo", "."]
        result["controls"]["different_receivers_rejected"] = dict(rejected(repo, args), receivers=receivers)
        for signature, start, end in control["declarations"]:
            exact = f"{case['path']}::{control['query']}:{signature}"
            rows, _ = read_pages(repo, [exact], "text", True, case, {exact: (start, end)})
            require(rows == expected_rows(case, content, {exact: (start, end)}),
                    "Receiver-specific exact ID did not retrieve its source")
        result["controls"]["receiver_exact_ids_readable"] = dict(passed=True, declarations=4)
    result["source_unchanged"] = sha(source.read_bytes()) == case["sha256"]
    result["archive_unchanged"] = sha((repo / "graph.jsonl.xz").read_bytes()) == exported["sha256"]
    result["license_unchanged"] = sha((repo / case["license_path"]).read_bytes()) == case["license_sha256"]
    require(result["source_unchanged"], "Upstream source was modified")
    require(result["archive_unchanged"] and result["license_unchanged"], "Archive or license was modified")
    result["passed"] = all(item["passed"] for item in result["controls"].values())
    return result


def report(result):
    lines = ["# Held-out archive discovery reproduction", "",
             "This model-free check compares a complete declaration search followed by an exact-ID source batch "
             "against one `archive-source --overloads` query. It retrieves all frozen declaration bodies and "
             "checks exact IDs, ranges, file hashes and physical source lines. No model tokens or answer quality "
             "are measured, and the failed multilingual model cohort is unchanged.", "",
             "Each case indexes one complete, unmodified upstream source file downloaded with its Apache 2.0 "
             "license. This tests a discovery mechanism on new source, not exploration across a complete repository. "
             "The baseline uses an explicit limit of 50 so all overloads fit in one search; it is not forced "
             "through one search per signature. Both workflows use the current runtime and compact renderer; "
             "baseline labels only the two-step graph workflow. Ordinary rg/model exploration and the "
             "previous package are outside this measurement.", "",
             "| Case / format | Declarations / lines | Commands before → after | Command bytes before → after | Response bytes before → after |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for case in result["cases"]:
        for fmt, workflow in case["workflows"].items():
            before, after = workflow["baseline"], workflow["overloads"]
            lines.append(f"| {case['id']} / {fmt} | {case['declarations']} / {case['physical_source_lines']} "
                         f"| {before['command_count']} → {after['command_count']} "
                         f"| {before['command_bytes']} → {after['command_bytes']} "
                         f"| {before['response_bytes']} → {after['response_bytes']} |")
    lines += ["", "Command bytes are UTF-8 bytes of `shlex.join()` for the actual subprocess arguments, "
              "including the recorded interpreter/runtime paths and excluding the terminating newline. "
              "Response bytes are actual stdout plus stderr. Source indexing, validation/control queries and "
              "downloads are setup costs excluded equally from the two scripted workflows. Every command receipt "
              "retains exit status and stdout/stderr hashes in [results.json](results.json). "
              "These figures are not model input/output tokens, dollar costs, latency measurements or evidence "
              "that agents choose this workflow.", "", "## Frozen upstream inputs", ""]
    for case in result["cases"]:
        url = f"https://github.com/{case['repository']}/commit/{case['commit']}"
        lines.append(f"- {case['id']}: [{case['commit']}]({url}); "
                     f"[source]({case['source']['url']}) SHA-256 `{case['source']['sha256']}`; "
                     f"[license]({case['license']['url']}).")
    lines += ["", "[pins.json](pins.json) freezes exact declaration signatures and physical ranges, "
              "including annotations. Full source and licenses are fetched verbatim into temporary directories "
              "and verified against their pinned hashes on each run. No upstream source fixtures are committed.",
              "", "## Controls", ""]
    for case in result["cases"]:
        for name, control in case["controls"].items():
            lines.append(f"- {case['id']} / {name}: {'PASS' if control['passed'] else 'FAIL'}.")
    lines += ["", "Ambiguous queries without the flag must fail. Exact IDs with the flag must stay singular. "
              "Bounded pages must reconstruct every selected physical line once. OkHttp's four different "
              "`toRequestBody` receivers must be rejected as a group and remain individually readable by exact ID. "
              "An expected rejection is a passing negative control, not a silently discarded failure.", "",
              f"Overall: **{'PASS' if result['passed'] else 'FAIL'}**. "
              f"Unexpected failures: {len(result['errors'])}.", "", "## Reproduction", "",
              "Run from the repository root with the pinned parser dependencies installed:", "", "```sh",
              'recheck_dir="$(mktemp -d /tmp/columbus-archive-discovery.XXXXXX)"',
              '.venv/bin/python evals/archive-discovery/verify.py --output "$recheck_dir"',
              "```", "", "Network access is needed only for the four immutable source/license URLs. "
              "The script writes its temporary fixtures and the explicitly selected report directory, never "
              "runs models, and records runtime/input hashes plus parser versions. Runtime edits during a run "
              "fail the check; a different runtime requires a fresh report rather than rewriting prior results."]
    for error in result["errors"]:
        lines += ["", f"Failure: `{error}`"]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pins = json.loads((HERE / "pins.json").read_text())
    before = inventory()
    result = dict(schema="columbus.archive-discovery/v1", model_trial=False,
                  model_usage=None, answer_semantics_measured=False, scope=pins["scope"],
                  acceptance="Exact source parity and required controls; no model-token acceptance claim",
                  comparison="Two scripted command sequences using the same current runtime",
                  python_version=platform.python_version(),
                  parser_versions={name: metadata.version(name) for name in
                                   ("tree-sitter", "tree-sitter-java", "tree-sitter-kotlin")},
                  input_hashes=before, command_log=COMMAND_LOG, cases=[], errors=[], passed=False)
    with tempfile.TemporaryDirectory(prefix="columbus-archive-discovery-") as directory:
        for case in pins["cases"]:
            try:
                result["cases"].append(run_case(case, Path(directory)))
            except Exception as exc:
                result["errors"].append(f"{case['id']}: {type(exc).__name__}: {exc}")
    result["inputs_unchanged"] = before == inventory()
    if not result["inputs_unchanged"]:
        result["errors"].append("Runtime or protocol inputs changed during verification")
    result["passed"] = (not result["errors"] and len(result["cases"]) == len(pins["cases"])
                        and all(case["passed"] for case in result["cases"]))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    (args.output / "REPORT.md").write_text(report(result))
    print(json.dumps({key: result[key] for key in ("passed", "model_trial", "errors")}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
