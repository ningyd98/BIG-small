"""Finite local Git census under R229; no product imports or Git mutations."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
ROUND = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round229-p6-t2-git-delivery-census-20261015"
OUT = ROUND / "implementation"
PLAN_SHA = "a0b0e2aea04a34e9dc3233bad59604121c4938b9d80c99cdb5b48f97afb4d966"
RUNS = []
CHECKS = []


def require(name, condition):
    CHECKS.append({"name": name, "passed": bool(condition)})
    if not condition:
        raise ValueError(name)


def pin(path):
    path = Path(path)
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
            size += len(block)
    return {"path": str(path), "bytes": size, "sha256": h.hexdigest()}


def verify(record):
    require("pin:" + record["path"], pin(record["path"]) == {k: record[k] for k in ("path", "bytes", "sha256")})


def read_json(path):
    return json.loads(Path(path).read_bytes())


def write_json(path, data):
    path = Path(path)
    with path.open("xb") as stream:
        stream.write((json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return pin(path)


def bytes_value(value):
    return {"base64": base64.b64encode(value).decode("ascii"), "display": value.decode("utf-8", "backslashreplace")}


def snapshot():
    gitdir = ROOT / ".git"
    require("main_gitdir", gitdir.is_dir())
    head = (gitdir / "HEAD").read_bytes()
    reference = None
    if head.startswith(b"ref: "):
        name = head[5:].strip().decode("ascii")
        require("safe_symbolic_ref", name.startswith("refs/") and ".." not in name.split("/"))
        reference = gitdir / name
    records = [pin(gitdir / "HEAD"), pin(gitdir / "index")]
    if reference is not None:
        records.append(pin(reference) if reference.is_file() else {"path": str(reference), "exists": False})
    return {"gitdir": str(gitdir), "records": records, "head_text": bytes_value(head), "symbolic_ref": None if reference is None else str(reference.relative_to(gitdir))}


def reserve(spec):
    target = ROUND / "command-ledger.json"
    old = target.read_bytes()
    data = json.loads(old)
    entry = data["commands"][spec["id"]]
    require(spec["id"] + ".held", entry["used"] == 0 and entry["remaining"] == 1 and entry["state"] == "HELD")
    archive = OUT / ("ledger-before-" + spec["id"] + ".json")
    with archive.open("xb") as stream:
        stream.write(old)
    entry.update({"used": 1, "remaining": 0, "state": "RESERVED", "before": pin(archive)})
    require(spec["id"] + ".ledger_cas", target.read_bytes() == old)
    target.write_bytes((json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def settle(spec, result_pin):
    target = ROUND / "command-ledger.json"
    old = target.read_bytes()
    data = json.loads(old)
    entry = data["commands"][spec["id"]]
    require(spec["id"] + ".reserved", entry["used"] == 1 and entry["remaining"] == 0 and entry["state"] == "RESERVED")
    with (OUT / ("ledger-reserved-" + spec["id"] + ".json")).open("xb") as stream:
        stream.write(old)
    entry.update({"state": "SPENT", "actual_result": result_pin})
    require(spec["id"] + ".settlement_cas", target.read_bytes() == old)
    target.write_bytes((json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def group_exists(pid):
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False


def execute(spec):
    reserve(spec)
    started = time.monotonic()
    process = None
    timed_out = False
    capped = False
    notes = []
    creation_error = None
    caps = {"stdout": 32 * 1024 * 1024, "stderr": 2 * 1024 * 1024}
    paths = {name: Path(spec[name + "_path"]) for name in caps}
    with paths["stdout"].open("xb") as out, paths["stderr"].open("xb") as err:
        streams = {"stdout": out, "stderr": err}
        try:
            process = subprocess.Popen(spec["argv"], cwd=spec["cwd"], env=spec["env"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, start_new_session=True)
        except OSError as error:
            creation_error = {"type": type(error).__name__, "message": str(error)}
        if process is not None:
            selector = selectors.DefaultSelector()
            for name, pipe in (("stdout", process.stdout), ("stderr", process.stderr)):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, name)
            stop_at = started + spec["timeout_seconds"]
            cleanup_at = None
            killed_at = None
            while selector.get_map() or process.poll() is None:
                now = time.monotonic()
                if cleanup_at is None and (now >= stop_at or capped):
                    timed_out = now >= stop_at
                    cleanup_at = now
                    notes.append("TERM process group: timeout" if timed_out else "TERM process group: output cap")
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                if cleanup_at is not None and now - cleanup_at >= 5 and killed_at is None:
                    killed_at = now
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                        notes.append("KILL process group")
                    except ProcessLookupError:
                        pass
                if cleanup_at is not None and now - cleanup_at >= 10:
                    notes.append("cleanup deadline reached; remaining pipes closed")
                    break
                for key, _ in selector.select(0.1):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    name = key.data
                    room = caps[name] - streams[name].tell()
                    streams[name].write(data[:max(room, 0)])
                    if len(data) > room:
                        capped = True
            for key in list(selector.get_map().values()):
                selector.unregister(key.fileobj)
                key.fileobj.close()
            selector.close()
            try:
                process.wait(timeout=max(0, 10 - (time.monotonic() - cleanup_at)) if cleanup_at is not None else 0)
            except subprocess.TimeoutExpired:
                notes.append("leader not reaped within cleanup bound")
    reaped = process is not None and process.returncode is not None
    result = {
        "id": spec["id"], "argv": spec["argv"], "cwd": spec["cwd"], "env": spec["env"],
        "numeric_exit": None if process is None else process.returncode,
        "elapsed_seconds": time.monotonic() - started, "timed_out": timed_out, "truncated": capped,
        "creation_error": creation_error, "stdout": pin(paths["stdout"]), "stderr": pin(paths["stderr"]),
        "cleanup": {"leader_reaped": reaped, "group_remaining": None if process is None else group_exists(process.pid), "notes": notes},
        "attempt": 1, "retry": 0,
    }
    result_pin = write_json(spec["result_path"], result)
    RUNS.append({**result, "result_pin": result_pin})
    settle(spec, result_pin)
    require(spec["id"] + ".success", result["numeric_exit"] == 0 and not timed_out and not capped and reaped and result["cleanup"]["group_remaining"] is False)
    return paths["stdout"].read_bytes()


def parse_status(raw):
    tokens = raw.split(b"\0")
    require("status_terminated", not tokens[-1])
    headers = {}
    tracked = []
    untracked = []
    index = 0
    while index < len(tokens) - 1:
        row = tokens[index]
        index += 1
        if row.startswith(b"# "):
            key, separator, value = row[2:].partition(b" ")
            require("branch_header", bool(key) and bool(separator) and key.decode("ascii") not in headers)
            headers[key.decode("ascii")] = value.decode("utf-8", "backslashreplace")
        elif row.startswith(b"1 ") or row.startswith(b"2 ") or row.startswith(b"u "):
            kind = row[:1]
            count = {b"1": 8, b"2": 9, b"u": 10}[kind]
            fields = row.split(b" ", count)
            require("status_fields", len(fields) == count + 1 and len(fields[1]) == 2 and bool(fields[-1]))
            item = {"type": kind.decode("ascii"), "index_status": chr(fields[1][0]), "worktree_status": chr(fields[1][1]), "metadata": [x.decode("ascii") for x in fields[2:-1]], "path": bytes_value(fields[-1]), "attribution": "UNATTRIBUTED"}
            if kind == b"2":
                require("rename_original_present", index < len(tokens) - 1 and bool(tokens[index]))
                item["original_path"] = bytes_value(tokens[index])
                index += 1
            tracked.append(item)
        elif row.startswith(b"? "):
            require("untracked_path", len(row) > 2)
            untracked.append({"path": bytes_value(row[2:]), "recursive_complete": False, "attribution": "UNATTRIBUTED"})
        else:
            raise ValueError("Unknown porcelain-v2 record shape")
        require("status_record_cap", len(tracked) + len(untracked) + len(headers) <= 100000)
    return {"headers": headers, "tracked_changes": tracked, "untracked": untracked}


def parse_refs(raw):
    records = []
    for row in raw.splitlines():
        fields = row.split(b"\0")
        require("ref_fields", len(fields) == 5 and fields[-1] == b"")
        records.append({"refname": fields[0].decode("utf-8", "backslashreplace"), "objectname": fields[1].decode("ascii"), "upstream": fields[2].decode("utf-8", "backslashreplace"), "upstream_track": fields[3].decode("ascii"), "refname_bytes": bytes_value(fields[0]), "upstream_bytes": bytes_value(fields[2])})
        require("ref_record_cap", len(records) <= 100000)
    require("unique_refs", len({x["refname"] for x in records}) == len(records))
    return records


def parse_worktrees(raw):
    require("worktree_terminated", raw.endswith(b"\0\0"))
    records = []
    current = {}
    for field in raw.split(b"\0")[:-1]:
        if not field:
            require("worktree_has_path", "worktree" in current)
            records.append(current)
            current = {}
            require("worktree_record_cap", len(records) <= 100000)
            continue
        key, separator, value = field.partition(b" ")
        key = key.decode("ascii")
        require("worktree_known_field", key in ("worktree", "HEAD", "branch", "bare", "detached", "locked", "prunable") and key not in current)
        current[key] = bytes_value(value) if key in ("worktree", "locked", "prunable") else value.decode("utf-8", "backslashreplace") if separator else True
    require("worktree_no_partial_record", not current)
    return records


def main():
    require("cwd", Path.cwd() == ROOT)
    require("plan_sha", pin(ROUND / "plan.json")["sha256"] == PLAN_SHA)
    plan = read_json(ROUND / "plan.json")
    gate = read_json(ROUND / "script-gate.json")
    ledger = read_json(ROUND / "command-ledger.json")
    require("full_source_review", gate["full_source_reviewed"] is True)
    verify(gate["source"])
    require("own_source", gate["source"]["path"] == str(Path(__file__).absolute()))
    require("exact_budget", gate["git_calls"] == plan["budget"]["git_calls"] and gate["orchestration"] == plan["budget"]["orchestration"])
    require("root_orchestration_reserved", ledger["orchestration"]["used"] == 1 and ledger["orchestration"]["remaining"] == 0 and ledger["orchestration"]["state"] == "RESERVED")
    for record in gate["input_records"]:
        verify(record)
    for spec in plan["budget"]["git_calls"]:
        for key in ("stdout_path", "stderr_path", "result_path"):
            require("exclusive_output:" + spec[key], not Path(spec[key]).exists())
            Path(spec[key]).parent.mkdir(parents=True, exist_ok=True)
    before = snapshot()
    invocation = write_json(OUT / "invocation.json", {"argv": plan["budget"]["orchestration"]["argv"], "cwd": str(ROOT), "env": plan["budget"]["orchestration"]["env"], "source": pin(__file__), "gate": pin(ROUND / "script-gate.json"), "activation": pin(ROUND / "root-activation.json"), "before": before, "observed_at_unix": time.time()})
    status = parse_status(execute(plan["budget"]["git_calls"][0]))
    refs = parse_refs(execute(plan["budget"]["git_calls"][1]))
    worktrees = parse_worktrees(execute(plan["budget"]["git_calls"][2]))
    after = snapshot()
    require("metadata_unchanged", before == after)
    headers = status["headers"]
    oid = headers.get("branch.oid")
    branch = headers.get("branch.head")
    require("branch_headers_present", oid is not None and branch is not None)
    main_trees = [row for row in worktrees if base64.b64decode(row["worktree"]["base64"]) == os.fsencode(ROOT)]
    require("main_worktree_exactly_one", len(main_trees) == 1)
    if oid != "(initial)":
        require("head_matches_main_worktree", main_trees[0].get("HEAD") == oid)
    if branch != "(detached)":
        matching = [row for row in refs if row["refname"] == "refs/heads/" + branch]
        require("branch_ref_identity", (not matching and oid == "(initial)") or (len(matching) == 1 and matching[0]["objectname"] == oid))
        require("main_worktree_branch", main_trees[0].get("branch") == "refs/heads/" + branch)
        if matching:
            upstream = matching[0]["upstream"]
            short_upstream = upstream.removeprefix("refs/remotes/").removeprefix("refs/heads/")
            require("cached_upstream_relation", short_upstream == headers.get("branch.upstream", ""))
    else:
        require("main_worktree_detached", main_trees[0].get("detached") is True)
    report = {
        "schema_version": "r229-local-git-census.v1", "complete": True, "observed_at_unix": time.time(),
        "invocation": invocation, "git_runs": RUNS, "checks": CHECKS,
        "repository": {"root": str(ROOT), "before": before, "after": after, **headers},
        "refs": refs, "worktrees": worktrees, "tracked_changes": status["tracked_changes"], "untracked": status["untracked"],
        "attribution": "UNATTRIBUTED unless independently joined to accepted provenance; no such join is performed here.",
        "boundaries": {"T2_validated": False, "delivery_authorized": False, "live_remote_verified": False, "full_remote_reproduction": False}, "findings": [],
    }
    target = write_json(OUT / "census.json", report)
    summary = json.dumps({"status": "COMPLETE_LOCAL_READ_ONLY_CENSUS", "report": target, "git_calls": len(RUNS), "tracked_changes": len(status["tracked_changes"]), "untracked_summaries": len(status["untracked"]), "refs": len(refs), "worktrees": len(worktrees), "T2_validated": False, "delivery_authorized": False}, ensure_ascii=False)
    require("stdout_cap", len(summary.encode("utf-8")) <= 6000)
    print(summary)


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        target = OUT / "failure.json"
        if not target.exists():
            write_json(target, {"status": "FAILED_NO_RETRY", "error_type": type(error).__name__, "error": str(error), "git_runs": RUNS, "checks": CHECKS, "T2_validated": False})
        raise
