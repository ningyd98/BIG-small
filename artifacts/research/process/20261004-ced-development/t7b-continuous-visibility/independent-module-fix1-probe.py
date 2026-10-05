"""Replay the retained original software counterexample fixtures after the fix."""

import ast
import hashlib
import json
import sys
import tempfile
from pathlib import Path


original = Path(__file__).with_name("independent-module-probe.py")
tree = ast.parse(original.read_text(), filename=str(original))
definitions = [node for node in tree.body if isinstance(
    node, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.FunctionDef))]
namespace = {}
exec(compile(ast.Module(body=definitions, type_ignores=[]), str(original), "exec"), namespace)


def rejection(operation):
    try:
        operation()
    except Exception as error:
        return {"type": type(error).__name__, "reason": str(error)}
    return None


source = Path("src/cloud_edge_robot_arm/research/step_rgbd.py")
tests = Path("tests/test_step_rgbd.py")
results = {
    "scope": "SOFTWARE_ONLY",
    "rendering_or_physics": False,
    "original_probe_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "tests_sha256": hashlib.sha256(tests.read_bytes()).hexdigest(),
}
fixture, record = namespace["fixture"], namespace["record"]
with tempfile.TemporaryDirectory(prefix="step-rgbd-independent-fix1-") as temporary:
    root = Path(temporary)
    recorder, state = fixture(root / "begin-failure")
    recorder._index = namespace["FailFirstWrite"](recorder._index)
    first = rejection(lambda: record(recorder, state, 0))
    second = rejection(lambda: record(recorder, state, 0))
    summary = recorder.finish(final_step=0, final_sim_time_s=0)
    results["begin_failure"] = {
        "first_error": first,
        "retry_error": second,
        "camera_calls": state["calls"],
        "journal_events": [json.loads(line)["event"] for line in
                           (root / "begin-failure/index.jsonl").read_text().splitlines()],
        "summary": summary,
    }
    assert first["type"] == "OSError" and second["type"] == "RuntimeError"
    assert state["calls"] == summary["capture_calls_started"] == 0
    assert summary["status"] == "INCOMPLETE" and summary["failed_captures"] == 1
    assert "qualified BEGIN journal failure" in summary["reason"]

    recorder, state = fixture(root / "mutable-gap")
    record(recorder, state, 0)
    assignment = rejection(lambda: setattr(recorder, "max_sample_gap_s", 0.1))
    state["time"] = 0.1
    gap_error = rejection(lambda: record(recorder, state, 1))
    summary = recorder.finish(final_step=1, final_sim_time_s=0.1)
    results["mutable_gap"] = {
        "assignment_error": assignment, "gap_error": gap_error,
        "camera_calls": state["calls"], "summary": summary,
    }
    assert assignment["type"] == "AttributeError" and gap_error["type"] == "ValueError"
    assert state["calls"] == 1 and summary["status"] == "INCOMPLETE"
    assert summary["original_max_sample_gap_s"] == 0.005

    recorder, state = fixture(root / "mutable-episode")
    record(recorder, state, 0)
    assignment = rejection(lambda: setattr(recorder, "episode_id", "other"))
    state.update(episode="other", time=1 / 240)
    episode_error = rejection(lambda: record(recorder, state, 1))
    summary = recorder.finish(final_step=1, final_sim_time_s=1 / 240)
    events = [json.loads(line) for line in
              (root / "mutable-episode/index.jsonl").read_text().splitlines()]
    results["mutable_episode"] = {
        "assignment_error": assignment, "episode_error": episode_error,
        "camera_calls": state["calls"],
        "begin_episode_ids": [event["episode_id"] for event in events if event["event"] == "BEGIN"],
        "summary": summary,
    }
    assert assignment["type"] == "AttributeError" and episode_error["type"] == "ValueError"
    assert results["mutable_episode"]["begin_episode_ids"] == ["episode"]
    assert state["calls"] == 1 and summary["status"] == "INCOMPLETE"
    assert summary["episode_id"] == "episode"

for value in (results["begin_failure"], results["mutable_gap"], results["mutable_episode"]):
    assert value["summary"]["continuous_motion"] == "NOT_CERTIFIED"
    assert value["summary"]["external_utc_uncertainty"] == "UNAVAILABLE"
    assert value["summary"]["formal_accepted"] is False
assert results["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
Path(sys.argv[1]).write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps({"closed": ["begin_failure", "mutable_gap", "mutable_episode"],
                  "source_sha256": results["source_sha256"]}))
