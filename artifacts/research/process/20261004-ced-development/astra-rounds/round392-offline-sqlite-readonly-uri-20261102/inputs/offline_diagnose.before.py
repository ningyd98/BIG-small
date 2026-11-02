"""One bounded, stdlib-only analysis of closed evidence; never run product code."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import time
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import zipfile

ROUND = Path(__file__).resolve().parent.parent
ROOT = Path.cwd().resolve()
OUT = ROUND / "analysis"
PRIOR = ROUND.parent / "round377-browser-draft-input-contract-20261101"
DEADLINE = 0.0


def check_time():
    if time.monotonic() >= DEADLINE:
        raise TimeoutError("R390 internal120s analysis deadline")


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def pin(path):
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            check_time()
            digest.update(chunk)
            size += len(chunk)
    return {"path": str(path.relative_to(ROOT)), "bytes": size, "sha256": digest.hexdigest()}


def test_cases(path):
    return [{"name": c.attrib["name"], "classname": c.attrib.get("classname"),
             "state": next((k.upper() for k in ("failure", "error", "skipped")
                            if c.find(k) is not None), "PASS")}
            for c in ET.parse(path).getroot().findall(".//testcase")]


def body(archive, value):
    name = value.get("_sha1") if isinstance(value, dict) else None
    if not name:
        return None
    resource = "resources/" + name
    if resource not in archive.namelist() or archive.getinfo(resource).file_size > 25_000_000:
        return None
    try:
        return json.loads(archive.read(resource))
    except (ValueError, UnicodeError):
        return None


def trace_rows(path):
    rows, run_ids, job_ids = [], set(), set()
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.endswith(".network"):
                continue
            with archive.open(name) as stream:
                for line in stream:
                    check_time()
                    entry = json.loads(line)
                    snap = entry.get("snapshot", {})
                    request, response = snap.get("request", {}), snap.get("response", {})
                    route = urlsplit(request.get("url", "")).path
                    if not any(key in route for key in ("/simulation/", "/rgbd", "/datasets")):
                        continue
                    payload = body(archive, response.get("content", {}))
                    selected = {}
                    if isinstance(payload, dict):
                        for key in ("run_id", "job_id", "batch_id", "capture_id", "status", "attempt",
                                    "started_at", "completed_at", "queue_position", "progress", "published_groups"):
                            if key in payload:
                                selected[key] = payload[key]
                        run_ids.update(x for x in payload.get("run_ids", []) if isinstance(x, str))
                        if isinstance(payload.get("run_id"), str):
                            run_ids.add(payload["run_id"])
                        if isinstance(payload.get("job_id"), str):
                            job_ids.add(payload["job_id"])
                        config = payload.get("manifest", {}).get("normalized_config", {})
                        if config:
                            selected["config"] = {k: config.get(k) for k in ("backend", "input_mode")}
                    rows.append({"method": request.get("method"), "route": route,
                        "response_status": response.get("status"), "startedDateTime": snap.get("startedDateTime"),
                        "monotonicTime": snap.get("_monotonicTime"), "response": selected})
    # Keep first/last and actual state changes, without merging relative clocks across traces.
    compact, previous = [], {}
    for index, row in enumerate(rows):
        key = (row["method"], row["route"])
        signature = json.dumps(row["response"], sort_keys=True)
        if previous.get(key) != signature or index == len(rows) - 1:
            compact.append(row)
        previous[key] = signature
    return {"trace": pin(path), "request_count": len(rows), "transitions": compact}, run_ids, job_ids


def database_copy(run_ids, job_ids):
    invocation = json.loads((PRIOR / "implementation/browser_default_green_escalated/invocation.json").read_text())
    original = Path(invocation["env"]["R377_STAGE_DIR"]) / "runtime/simulation_runtime.db"
    if not original.is_file():
        return {"state": "NOT_AVAILABLE", "resolved_path": str(original)}
    paths = [Path(str(original) + suffix) for suffix in ("", "-wal", "-shm")]
    present = [p for p in paths if p.is_file()]
    assert all(not p.is_symlink() and p.resolve().is_relative_to(PRIOR.resolve()) for p in present)
    before = [pin(p) for p in present]
    destination = ROUND / "forensic-copy"
    destination.mkdir(exist_ok=False)
    for source in present:
        check_time()
        shutil.copyfile(source, destination / source.name)
        assert (destination / source.name).read_bytes() == source.read_bytes()
    after = [pin(p) for p in present]
    if before != after or [p for p in paths if p.is_file()] != present:
        return {"state": "STOP_ORIGINAL_TUPLE_CHANGED", "before": before, "after": after}
    copy_before = [pin(destination / p.name) for p in present]
    result = {"state": "COPIED_QUIESCENT_TUPLE", "original_before": before,
              "original_after": after, "copy_before_query": copy_before, "tables": {}}
    allowed_columns = {"job_id", "run_id", "batch_id", "backend", "scenario_id", "control_mode",
        "status", "attempt", "created_at", "queued_at", "started_at", "completed_at", "updated_at",
        "timeout_seconds", "error_code", "error_message", "lease_id", "lease_expires_at", "released_at",
        "event_type", "source", "sequence", "timestamp", "result", "ended_at"}
    connection = None
    try:
        connection = sqlite3.connect((destination / original.name).as_uri() + "?mode=ro", timeout=1)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.set_progress_handler(lambda: int(time.monotonic() >= DEADLINE), 1000)
        for table in ("simulation_jobs", "simulation_job_attempts", "simulation_job_events", "simulation_job_leases"):
            check_time()
            available = {r["name"] for r in connection.execute(f'PRAGMA table_info("{table}")')}
            columns = sorted(available & allowed_columns)
            clauses, parameters = [], []
            for column, values in (("run_id", run_ids), ("job_id", job_ids)):
                if column in available and values:
                    clauses.append(f'"{column}" IN ({",".join("?" for _ in values)})')
                    parameters.extend(sorted(values))
            if not clauses or not columns:
                result["tables"][table] = {"state": "NO_MATCHING_KNOWN_COLUMNS_OR_IDS"}
                continue
            sql = 'SELECT ' + ','.join('"' + c + '"' for c in columns)
            sql += f' FROM "{table}" WHERE ' + ' OR '.join(clauses) + ' LIMIT 10000'
            records = [dict(row) for row in connection.execute(sql, parameters)]
            result["tables"][table] = {"rows": records, "row_limit": 10000}
            if table == "simulation_jobs":
                job_ids.update(r["job_id"] for r in records if r.get("job_id"))
    except sqlite3.Error as error:
        result["copy_query_limitation"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        if connection is not None:
            connection.close()
    result["original_final"] = [pin(p) for p in present]
    assert result["original_final"] == before
    result["copy_after_query"] = [pin(p) for p in sorted(destination.iterdir()) if p.is_file()]
    return result


def main():
    global DEADLINE
    began = time.monotonic()
    DEADLINE = began + 120
    save(OUT / "execution-start.json", {"started_utc": datetime.now(UTC).isoformat(),
        "child_cap_s": 120, "wall_cap_s": 300, "attempt": 1, "product_tests": 0,
        "interpreter": "/usr/bin/python3 -I", "script_sha256": pin(Path(__file__))["sha256"]})
    plan = json.loads((ROUND / "plan.json").read_text())
    frozen = []
    for expected in plan["inputs"]:
        actual = pin(ROOT / expected["path"])
        assert actual == expected, {"input_drift": expected["path"]}
        frozen.append(actual)
    save(OUT / "input-freeze.json", frozen)
    default = test_cases(PRIOR / "implementation/browser_default_green_escalated/junit.xml")
    research = test_cases(PRIOR / "implementation/browser_research_green/junit.xml")
    old_plan = json.loads((PRIOR / "plan.json").read_text())
    mapping = [{"name": r["name"], "old_state": r["state"],
                "new_state": next(c["state"] for c in default if c["name"] == r["name"])}
               for r in old_plan["original_evidence"]["failed_cases"]]
    save(OUT / "case-target-map.json", {"default": default, "research": research, "old18": mapping})
    queue, capture, run_ids, job_ids = [], [], set(), set()
    for expected in plan["inputs"]:
        if not expected["path"].endswith(".zip"):
            continue
        path = ROOT / expected["path"]
        rows, runs, jobs = trace_rows(path)
        (capture if "rgbd-datasets" in str(path) else queue).append(rows)
        run_ids.update(runs)
        job_ids.update(jobs)
    save(OUT / "queue-chronology.json", {"traces": queue,
         "queue_position_semantics": "repository.queued_count(), not exact job rank"})
    save(OUT / "capture-chronology.json", {"traces": capture,
         "limits": "Three targets separate; no common root or rendering/visual-planning/cancel arrival inferred"})
    database = database_copy(run_ids, job_ids)
    save(OUT / "database-copy-observations.json", database)
    result = {"state": "BOUNDED_OFFLINE_DIAGNOSIS_COMPLETED", "elapsed_s": time.monotonic() - began,
        "closed_trace_count": len(queue) + len(capture), "run_ids": sorted(run_ids), "job_ids": sorted(job_ids),
        "database_state": database["state"],
        "original_db_unchanged": (database["original_before"] == database["original_final"]
                                  if "original_final" in database else None),
        "confirmed": "Downstream target noncompletion after valid LEGACY input; queue observations and exact capture stopping points retained",
        "internal_blocking_location": "UNKNOWN", "deadlock": "NOT_PROVEN", "performance_root_cause": "NOT_PROVEN",
        "next_action": "New actual Astra plan before any probe/source fix/timeout or concurrency policy change",
        "new_product_tests": 0, "research_acceptance": False, "source_modifications": 0}
    save(OUT / "diagnostic-result.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except TimeoutError as error:
        partial = {"state": "PARTIAL_INTERNAL_LIMIT", "reason": str(error),
                   "new_product_tests": 0, "source_modifications": 0,
                   "internal_blocking_location": "UNKNOWN"}
        if not (OUT / "diagnostic-result.json").exists():
            save(OUT / "diagnostic-result.json", partial)
        print(json.dumps(partial))
