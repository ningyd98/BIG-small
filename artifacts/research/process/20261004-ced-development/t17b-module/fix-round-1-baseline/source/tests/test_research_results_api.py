"""研究结果仅只读完整冻结来源，软件判定不赋予实际成功。"""

import importlib
import json
import shutil
from dataclasses import asdict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def api():
    return importlib.import_module("cloud_edge_robot_arm.cloud.api.research_results")


@pytest.fixture(scope="module")
def prepared_sources(tmp_path_factory):
    api()  # Missing production boundary is the first RED, not fabricated data.
    from cloud_edge_robot_arm.datasets.rgbd.models import canonical_json, content_digest
    from cloud_edge_robot_arm.research.acceptance import analyze_research_runs
    from cloud_edge_robot_arm.research.assignments import build_assignments
    from cloud_edge_robot_arm.research.protocol import FrozenProtocol, ProtocolSpec
    from cloud_edge_robot_arm.research.runner import run_assignment
    from tests.test_research_assignments import scene_pool

    root = tmp_path_factory.mktemp("research-results")
    pool = scene_pool.__wrapped__()
    methods = ("JOINT", "B0", "B1", "B2", "NO_UNCERTAINTY", "NO_TIME_VALIDITY", "NO_LOCAL_REPAIR")
    spec = ProtocolSpec(
        selected_n=600,
        tcap_s=120,
        pool_hashes={"formal": content_digest(pool)},
        model_snapshot_hash="a" * 64,
        method_hashes={key: content_digest(key) for key in methods},
        initial_protocol_hash="b" * 64,
        opportunity_hash="c" * 64,
        recovery_fault_manifest_hash="d" * 64,
    )
    frozen = FrozenProtocol(
        spec=spec,
        stage="FINAL",
        content_hash=content_digest({"spec": spec.model_dump(mode="json"), "stage": "FINAL"}),
    )
    runs, protocol = root / "run-1/runs", root / "run-1/protocol"
    runs.mkdir(parents=True)
    protocol.mkdir()
    (protocol / "protocol.json").write_text(frozen.model_dump_json())
    assignments = build_assignments(frozen, methods, scene_pool=pool)
    manifest = {
        "schema_version": "ced.assignments.v1",
        "protocol_hash": frozen.content_hash,
        "assignments": [asdict(row) for row in assignments],
    }
    manifest["content_hash"] = content_digest(manifest)
    (runs / "assignments.json").write_text(canonical_json(manifest))
    (runs / "pools.json").write_text(canonical_json({"formal": pool}))
    (runs / "records.jsonl").write_text(
        "\n".join(
            canonical_json(run_assignment(row, frozen).to_payload(protocol=frozen))
            for row in assignments
        )
        + "\n"
    )
    analyze_research_runs(runs, protocol, root / "run-1/analysis", software_only=True)
    return root, frozen.content_hash


def browser(monkeypatch, root: Path):
    from cloud_edge_robot_arm.cloud.api.app import create_app
    from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
    from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline

    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "LOCAL_ONLY")
    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))
    app.state.research_artifact_root = root
    app.state.research_runs_registry = {
        "run-1": api().ResearchRunRegistration(
            runs_path="run-1/runs", protocol_path="run-1/protocol", analysis_path="run-1/analysis"
        )
    }
    return TestClient(app)


def test_results_keep_blocked_denominator_and_protocol_hash(prepared_sources, monkeypatch):
    root, protocol_hash = prepared_sources
    response = browser(monkeypatch, root).get("/api/v1/research/runs/run-1/evidence")
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["protocol_hash"] == protocol_hash
    assert value["assigned_denominator"] == 4200
    assert value["paired_group_denominator"] == 600
    assert value["terminal_status_counts"] == {"BLOCKED": 4200}
    assert {row["assigned_denominator"] for row in value["methods"]} == {600}
    assert value["formal_accepted"] is False and value["physical_success"] == 0
    assert value["actual_research_status"] == "NOT_RUN"
    assert value["scope"] == "SOFTWARE_ONLY"
    assert all(goal["actual_status"] == "NOT_RUN" for goal in value["goals"])


def test_export_retains_same_protocol_denominators_and_software_scope(
    prepared_sources, monkeypatch
):
    root, _ = prepared_sources
    client = browser(monkeypatch, root)
    detail = client.get("/api/v1/research/runs/run-1/evidence").json()
    exported = client.get("/api/v1/research/runs/run-1/export")
    assert exported.status_code == 200 and exported.json() == detail
    assert "attachment" in exported.headers["content-disposition"]


@pytest.mark.parametrize("target", ["other", "..%2F..%2Fsecret", "a%3Btouch-secret"])
def test_result_ids_cannot_select_paths_or_other_runs(prepared_sources, monkeypatch, target):
    root, _ = prepared_sources
    assert (
        browser(monkeypatch, root).get(f"/api/v1/research/runs/{target}/evidence").status_code
        == 404
    )


def test_read_only_view_has_no_run_creation_and_requires_existing_auth(
    prepared_sources, monkeypatch
):
    root, _ = prepared_sources
    client = browser(monkeypatch, root)
    assert client.post("/api/v1/research/runs", json={"shell": "touch sentinel"}).status_code == 405
    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "TOKEN")
    assert client.get("/api/v1/research/runs").status_code == 401


@pytest.mark.parametrize("tamper", ["denominator", "source", "goals", "symlink"])
def test_results_reject_changed_summary_or_source(prepared_sources, monkeypatch, tmp_path, tamper):
    original, _ = prepared_sources
    root = tmp_path / "artifacts"
    shutil.copytree(original, root)
    analysis = root / "run-1/analysis"
    if tamper == "denominator":
        path = analysis / "metrics.json"
        value = json.loads(path.read_text())
        value["assignment_denominator"] = 1
        path.write_text(json.dumps(value))
    elif tamper == "source":
        (root / "run-1/runs/records.jsonl").write_text("{}\n")
    elif tamper == "goals":
        path = analysis / "goal_verdicts.json"
        value = json.loads(path.read_text())
        value[0]["status"] = "PASS"
        path.write_text(json.dumps(value))
    else:
        path = analysis / "metrics.json"
        outside = tmp_path / "outside.json"
        path.rename(outside)
        path.symlink_to(outside)
    assert browser(monkeypatch, root).get("/api/v1/research/runs/run-1/evidence").status_code == 409


def test_missing_registered_outputs_are_explicit_not_run(monkeypatch, tmp_path):
    client = browser(monkeypatch, tmp_path)
    response = client.get("/api/v1/research/runs/run-1/evidence")
    assert response.status_code == 200
    value = response.json()
    assert value["status"] == value["actual_research_status"] == "NOT_RUN"
    assert value["assigned_denominator"] is None
    assert value["source_missing"]
    assert value["timeline"]["candidate_count"] is None
    assert value["timeline"]["accepted_count"] is None
    assert value["timeline"]["started_count"] is None


def test_query_shell_and_path_are_not_an_input_surface(prepared_sources, monkeypatch):
    root, _ = prepared_sources
    response = browser(monkeypatch, root).get(
        "/api/v1/research/runs/run-1/evidence?path=/etc/passwd&shell=touch"
    )
    assert response.status_code == 422


@pytest.mark.parametrize("artifact", ["report.json", "metrics.json", "goal_verdicts.json"])
def test_malformed_result_shapes_fail_closed(prepared_sources, monkeypatch, tmp_path, artifact):
    original, _ = prepared_sources
    root = tmp_path / "artifacts"
    shutil.copytree(original, root)
    (root / "run-1/analysis" / artifact).write_text("null\n")
    response = browser(monkeypatch, root).get("/api/v1/research/runs/run-1/evidence")
    assert response.status_code == 409
