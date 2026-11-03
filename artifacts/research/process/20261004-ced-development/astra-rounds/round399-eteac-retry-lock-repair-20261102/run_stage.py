"""执行 R399 已批准阶段，保留真实退出和原始证据；不自动重试。"""
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = Path.cwd()
PLAN = json.loads((HERE / "plan.json").read_text())
ALLOWED = {row["path"] for row in PLAN["changes"]}
AUDIT = json.loads((HERE / "input-audit.json").read_text())
INPUTS = AUDIT["source_pins"] + AUDIT["evidence_pins"]
OVERLAY_PATH = HERE.parent / "round401-operational-fence-timeout-localization-20261102/plan.json"
assert hashlib.sha256(OVERLAY_PATH.read_bytes()).hexdigest() == "dc75c1ca4b57a419093c4be06d848223991be46fff1d40cf45600547ce617d94"
OVERLAY = json.loads(OVERLAY_PATH.read_text())
EXTRA_IDS = {row["id"] for row in OVERLAY["successor_stages"]}
NATIVE_OVERLAY_PATH = HERE.parent / "round402-native-result-identity-join-20261102/plan.json"
assert hashlib.sha256(NATIVE_OVERLAY_PATH.read_bytes()).hexdigest() == "a941e071f9e41fffc6eb340d31b6361e2a13be00ba74aec8bb729874e79098af"
NATIVE_OVERLAY = json.loads(NATIVE_OVERLAY_PATH.read_text())
NATIVE_SUCCESSOR = "native_queue_identity_successor"
STAGES = PLAN["commands"] + OVERLAY["successor_stages"] + NATIVE_OVERLAY["successor_stages"]
OBS_PATH = HERE.parent / "round403-foreign-owner-target-precondition-20261102/plan.json"
assert hashlib.sha256(OBS_PATH.read_bytes()).hexdigest() == "d8dd39c8b8608ff2f576b9f4523772fee5d37fd164fc1cfd61e5bd43e9eba559"
OBS = json.loads(OBS_PATH.read_text())
OBS_ID = "foreign_owner_observed"
STAGES += [{"id": OBS_ID, "argv": OBS["execution"]["command"], "child_timeout_s": 60,
            "stage_dir": OBS["execution"]["env"]["R373_STAGE_DIR"]}]
ADMIN_ALLOWED = {str(Path(__file__).resolve().relative_to(ROOT))}


def frozen_fence_precondition():
    overlay_audit = json.loads((OVERLAY_PATH.parent / "input-audit.json").read_text())
    for row in overlay_audit["pins"]:
        if row["path"] not in ADMIN_ALLOWED:
            assert pin(ROOT / row["path"]) == row, row["path"]
    original = json.loads((HERE / "implementation/operational_fences_green/result.json").read_text())
    assert original["state"] == "TIMEOUT" and original["reaped"] and not original["errors"]
    assert not original["remaining_live"] and not original["source_drift_during_stage"]
    assert original["prerequisite_accepted"] and not original["expected_accepted"]
    for name in ("lock_contract_red", "lock_contract_green", "repository_semantics_green", "visual_repository_green"):
        result = json.loads((HERE / "implementation" / name / "result.json").read_text())
        assert result["expected_accepted"] and result["reaped"] and not result["source_drift_during_stage"]
    events = [json.loads(line) for line in (HERE / "implementation/operational_fences_green/pytest-events.jsonl").read_text().splitlines()]
    memory = [row for row in events if row.get("nodeid", "").endswith("[memory]") and row.get("event") == "report"]
    assert any(row["when"] == "call" and row["outcome"] == "passed" for row in memory)
    assert any(row["when"] == "teardown" and row["outcome"] == "passed" for row in memory)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def pin(path):
    raw = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


def sources():
    original = json.loads((HERE / "preflight/source-before.json").read_text())
    paths = {r["path"] for r in original["files"]} | ALLOWED
    return [pin(ROOT / name) for name in sorted(paths) if (ROOT / name).is_file()]


def members(pgid):
    found = []
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            raw = (path / "stat").read_text()
            fields = raw[raw.rfind(")") + 2:].split()
            if int(fields[2]) == pgid and fields[0] != "Z":
                found.append({"pid": int(path.name), "pgid": pgid,
                              "starttime_ticks": fields[19], "state": fields[0]})
        except (FileNotFoundError, ProcessLookupError):
            pass
    return found


def run(stage_id):
    stage = next(row for row in STAGES if row["id"] == stage_id)
    drift = []
    for row in INPUTS:
        if row["path"] not in ALLOWED and pin(ROOT / row["path"]) != row:
            drift.append(row["path"])
    before = sources()
    frozen = json.loads((HERE / "preflight/source-before.json").read_text())["files"]
    frozen_test = next(row for row in frozen if row["path"] == "tests/test_eteac_retry_lock_regression.py")
    if stage_id in {NATIVE_SUCCESSOR, OBS_ID}:
        native_audit = json.loads((NATIVE_OVERLAY_PATH.parent / "input-audit.json").read_text())
        assert pin(ROOT / frozen_test["path"]) == native_audit["expected_test_after"]
        old_test = NATIVE_OVERLAY_PATH.parent / "inputs/test.before.py"
        assert hashlib.sha256(old_test.read_bytes()).hexdigest() == frozen_test["sha256"]
        for row in native_audit["pins"]:
            if row["path"] not in ADMIN_ALLOWED | {frozen_test["path"]}:
                assert pin(ROOT / row["path"]) == row, row["path"]
        failure = json.loads((HERE / "implementation/native_queue_green/result.json").read_text())
        assert failure["state"] == "FINISHED" and failure["returncode"] == 1 and failure["reaped"]
        assert not failure["errors"] and not failure["remaining_live"] and not failure["source_drift_during_stage"]
        worker_result = json.loads((HERE / "implementation/worker_short_green/result.json").read_text())
        assert worker_result["expected_accepted"] and worker_result["reaped"]
    else:
        assert pin(ROOT / frozen_test["path"]) == frozen_test, "New regression source must remain frozen"
    initial = json.loads((HERE / "preflight/source-before.json").read_text())
    before_map = {r["path"]: r for r in before}
    drift.extend(r["path"] for r in initial["files"]
                 if r["path"] not in ALLOWED | ADMIN_ALLOWED and before_map.get(r["path"]) != r)
    if drift:
        raise RuntimeError({"unplanned_input_drift": sorted(set(drift))})
    directory = Path(stage["stage_dir"]) if stage_id in EXTRA_IDS or stage_id in {NATIVE_SUCCESSOR, OBS_ID} else HERE / "implementation" / stage_id
    directory.mkdir(parents=True, exist_ok=False)
    start = json.loads((HERE / "round-start.json").read_text())
    remaining = start["started_epoch_s"] + start["max_wall_s"] - time.time()
    if remaining < stage["child_timeout_s"] + 15:
        save(directory / "result.json", {"stage_id": stage_id, "state": "NOT_RUN_BUDGET",
                                        "remaining_s": remaining})
        return
    order = [row["id"] for row in PLAN["commands"]]
    position = order.index(stage_id) if stage_id in order else -1
    if stage_id in {NATIVE_SUCCESSOR, OBS_ID}:
        pass  # Exact native-failure, worker and successor source gates already checked above.
    elif stage_id in EXTRA_IDS or stage_id == "worker_short_green":
        frozen_fence_precondition()
    elif position:
        previous = json.loads((HERE / "implementation" / order[position - 1] / "result.json").read_text())
        assert previous["expected_accepted"] and previous["reaped"], "Previous stage must be accepted"
    for name in ["resources", "resources-a", "r223/resources", "r223/cases", "runtime/artifacts", "tmp"]:
        (directory / name).mkdir(parents=True)
    env_template = OBS["execution"]["env"] if stage_id == OBS_ID else PLAN["environment_template"]
    env = {key: value.replace("{STAGE_DIR}", str(directory)) for key, value in env_template.items()}
    if stage_id == OBS_ID:
        observe_audit = json.loads((OBS_PATH.parent / "input-audit.json").read_text())
        for row in observe_audit["pins"]:
            if row["path"] not in ADMIN_ALLOWED:
                assert pin(ROOT / row["path"]) == row, row["path"]
    assert all(key not in env for key in PLAN["environment_absent"])
    argv = [arg.replace("{STAGE_DIR}", str(directory)) for arg in stage["argv"]]
    save(directory / "source-before.json", before)
    invocation = {"stage_id": stage_id, "argv": argv, "env": env, "cwd": str(ROOT),
                  "started_utc": datetime.now(UTC).isoformat(),
                  "child_timeout_s": stage["child_timeout_s"], "cleanup_reserve_s": 15,
                  "launcher": pin(Path(__file__)), "plan": pin(HERE / "plan.json"), "overlay": pin(OVERLAY_PATH), "native_overlay": pin(NATIVE_OVERLAY_PATH), "observer_overlay": pin(OBS_PATH),
                  "permission_profile": "workspace-write/network restricted (calling executor)",
                  "retry": False}
    save(directory / "invocation.json", invocation)
    process = None
    identity = None
    errors = []
    signals = []
    state = "FINISHED"
    began = time.monotonic()
    previous_handlers = {}

    def interrupted(signum, frame):
        raise InterruptedError(signal.Signals(signum).name)

    def owned_signal(sig):
        current = members(identity["pgid"])
        leader = next((row for row in current if row["pid"] == process.pid), None)
        if leader and leader["starttime_ticks"] != identity["starttime_ticks"]:
            errors.append({"identity_changed": current})
            return
        if current:
            try:
                os.killpg(identity["pgid"], sig)
                signals.append(signal.Signals(sig).name)
            except ProcessLookupError:
                pass

    with (directory / "stdout.log").open("xb") as stdout, (directory / "stderr.log").open("xb") as stderr:
        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                previous_handlers[sig] = signal.signal(sig, interrupted)
            process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                                       stdin=subprocess.DEVNULL, start_new_session=True)
            try:
                initial_members = members(process.pid)
                leader = next(row for row in initial_members if row["pid"] == process.pid)
                identity = {**leader, "members_at_launch": initial_members}
                save(directory / "process-identity.json", identity)
                process.wait(timeout=max(0.01, stage["child_timeout_s"] - (time.monotonic() - began)))
            except subprocess.TimeoutExpired:
                state = "TIMEOUT"
            finally:
                if identity is None:
                    current = members(process.pid)
                    leader = next((row for row in current if row["pid"] == process.pid), None)
                    if leader:
                        identity = {**leader, "members_at_launch": current}
        except BaseException as error:
            state = "INFRASTRUCTURE_ERROR" if process is None else "INTERRUPTED"
            errors.append({"type": type(error).__name__, "message": str(error)})
        finally:
            cleanup_started = time.monotonic()
            if process is not None:
                if identity is not None:
                    owned_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if identity is not None:
                        owned_signal(signal.SIGKILL)
                    else:
                        process.kill()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        errors.append({"reason": "child_not_reaped"})
                if identity is not None:
                    remaining_live = members(identity["pgid"])
                    if remaining_live:
                        owned_signal(signal.SIGKILL)
                        until = cleanup_started + 15
                        while members(identity["pgid"]) and time.monotonic() < until:
                            time.sleep(0.05)
            for sig, handler in previous_handlers.items():
                signal.signal(sig, handler)
    cleanup = {"signals": signals, "errors": errors,
               "remaining_live": members(identity["pgid"]) if identity else [],
               "reaped": bool(process and process.returncode is not None)}
    save(directory / "cleanup.json", cleanup)
    after = sources()
    save(directory / "source-after.json", after)
    precondition_path = directory / "prerequisite.json"
    prerequisite = json.loads(precondition_path.read_text()) if precondition_path.exists() else {}
    expected_accepted = bool(process and process.returncode == 0 and state == "FINISHED")
    if stage_id == "lock_contract_red":
        child = json.loads((directory / "child-retry-sqlite.json").read_text()) if (directory / "child-retry-sqlite.json").exists() else {}
        child_out = (directory / "child-retry-sqlite.stdout").read_text() if (directory / "child-retry-sqlite.stdout").exists() else ""
        child_err = (directory / "child-retry-sqlite.stderr").read_text() if (directory / "child-retry-sqlite.stderr").exists() else ""
        expected_accepted = bool(process and process.returncode == 1 and state == "FINISHED"
            and child.get("timed_out") and child.get("reaped")
            and "READY; ENTER initialize_retry_budget_if_absent" in child_out
            and "initialize_retry_budget_if_absent" in child_err and "protocol.py" in child_err)
    prerequisite_ok = (prerequisite.get("accepted_prerequisite", False)
                       if stage_id == "operational_fences_green" or stage_id in EXTRA_IDS or stage_id == OBS_ID else True)
    result = {"stage_id": stage_id, "state": state,
              "returncode": process.returncode if process else None,
              "elapsed_s": time.monotonic() - began, "ended_utc": datetime.now(UTC).isoformat(),
              "prerequisite_accepted": prerequisite_ok, "expected_accepted": expected_accepted and prerequisite_ok,
              "source_drift_during_stage": [] if before == after else ["SOURCE_SNAPSHOT_CHANGED"],
              **cleanup}
    save(directory / "result.json", result)
    with (HERE / "step-report.md").open("a") as ledger:
        ledger.write(f"\n- {stage_id}: {state}, exit={result['returncode']}, {result['elapsed_s']:.3f}s; reaped={result['reaped']}.\n")
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if errors or cleanup["remaining_live"] or not cleanup["reaped"] or before != after or not result["expected_accepted"]:
        raise RuntimeError("Stage infrastructure/cleanup/source check failed; no next launch")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {item["id"] for item in STAGES}:
        raise SystemExit("Use one approved R399 stage_id")
    run(sys.argv[1])
