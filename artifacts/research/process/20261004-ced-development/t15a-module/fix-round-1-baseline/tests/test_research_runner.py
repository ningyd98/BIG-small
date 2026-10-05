"""研究运行器保留全分母；显式软件适配不能伪装物理任务。"""

from dataclasses import replace
from importlib import import_module, util

import pytest

from cloud_edge_robot_arm.research.cost_ledger import CostSnapshot
from cloud_edge_robot_arm.research.models import EvidenceKind, RunProvenance
from cloud_edge_robot_arm.vision.evaluation import VisualEpisodeOutcome
from tests.test_research_assignments import api as assignment_api
from tests.test_research_assignments import frozen
from tests.test_research_assignments import scene_pool as _scene_pool

scene_pool = _scene_pool


def api():
    name = "cloud_edge_robot_arm.research.runner"
    assert util.find_spec(name) is not None, "missing production research runner"
    return import_module(name)


def assignment(pool):
    return assignment_api().build_assignments(frozen(pool), ("JOINT",), scene_pool=pool)[0]


def outcome(success=False, reason="BLOCKED", elapsed=1.0):
    return VisualEpisodeOutcome(
        success,
        "SUCCESS" if success else "FAILED",
        False,
        None if success else reason,
        0.05 if success else 0,
        0,
        0,
        elapsed,
        physical_success=success,
        online_reported_complete=success,
    )


def record(row, status="BLOCKED", success=False, elapsed=1.0):
    module = assignment_api()
    provenance = RunProvenance(
        run_id=row.assignment_id,
        source_tree_hash="a" * 64,
        scene_group_id=row.group_id,
        split_role="formal",
        physics_steps=0,
        evidence_kind=EvidenceKind.MOCK,
        blocked_reason=None if success else status,
    )
    return module.EpisodeRecord(
        row,
        outcome(success, status, elapsed),
        provenance,
        CostSnapshot(),
        120.0 if not success else elapsed,
        None,
        (),
        (),
        (),
        {},
        run_status=status,
    )


@pytest.mark.parametrize("terminal", ["BLOCKED", "TIMEOUT", "STOP", "FALLBACK", "FAILED"])
def test_blocked_timeout_stop_keep_assigned_denominator(scene_pool, terminal):
    row = assignment(scene_pool)

    class SoftwareAdapter:
        evidence_kind = EvidenceKind.MOCK

        def run(self, assignment, protocol):
            return record(assignment, terminal, elapsed=0.01)

    result = api().run_assignment(row, frozen(scene_pool), software_adapter=SoftwareAdapter())
    assert result.assignment == row
    assert result.duration_penalized_s == 120.0
    assert not result.outcome.success
    assert result.provenance.evidence_kind == EvidenceKind.MOCK


def test_formal_runner_requires_final_protocol_hash(scene_pool):
    row = assignment(scene_pool)
    module = api()
    initial = module.run_assignment(row, frozen(scene_pool, stage="INITIAL"))
    assert initial.run_status == "BLOCKED"
    assert "FINAL" in initial.provenance.blocked_reason
    forged = frozen(scene_pool).model_copy(update={"content_hash": "f" * 64})
    result = module.run_assignment(row, forged)
    assert result.run_status == "BLOCKED"
    assert "hash" in result.provenance.blocked_reason


def test_valid_metadata_without_actual_adapter_is_blocked(scene_pool):
    result = api().run_assignment(assignment(scene_pool), frozen(scene_pool))
    assert result.run_status == "BLOCKED"
    assert result.outcome.executed_actions == 0
    assert result.costs.model_requests == 0
    assert not result.outcome.success
    assert result.provenance.physics_steps == 0
    assert "runtime" in result.provenance.blocked_reason


def test_software_adapter_cannot_promote_mock_success(scene_pool):
    row = assignment(scene_pool)

    class SoftwareAdapter:
        evidence_kind = EvidenceKind.MOCK

        def run(self, assignment, protocol):
            return record(assignment, "COMPLETED", success=True, elapsed=0.1)

    result = api().run_assignment(row, frozen(scene_pool), software_adapter=SoftwareAdapter())
    assert result.provenance.evidence_kind == EvidenceKind.MOCK
    assert result.source_verified is False
    assert result.accepted_task_success is False


def test_declared_physics_metadata_cannot_accept_success_without_raw_validator(
    scene_pool, tmp_path
):
    import hashlib

    from cloud_edge_robot_arm.research.models import StageEvidence, StageStatus

    row = assignment(scene_pool)
    trace = tmp_path / "declared.json"
    trace.write_text('{"declared":"physical success"}')
    ref = assignment_api().ArtifactReference(
        "trace.v1", hashlib.sha256(trace.read_bytes()).hexdigest(), str(trace)
    )
    declared = RunProvenance(
        run_id=row.assignment_id,
        source_tree_hash="a" * 64,
        scene_group_id=row.group_id,
        split_role="formal",
        model_snapshot_hash="b" * 64,
        observation_hashes=["c" * 64],
        physics_steps=100,
        evidence_kind=EvidenceKind.PHYSICS,
        task_success=True,
        stages=[
            StageEvidence(stage=key, status=StageStatus.REAL, source_hashes=["d" * 64])
            for key in ("PERCEPTION", "INFERENCE", "ACTION")
        ],
    )
    from dataclasses import asdict

    from cloud_edge_robot_arm.datasets.rgbd.models import content_digest

    verification = {
        "schema_version": "ced.verification-record.v1",
        "record": {"status": "PASS"},
        "source_refs": [asdict(ref)],
    }
    verification["content_hash"] = content_digest(verification)
    result = assignment_api().EpisodeRecord(
        row,
        outcome(True),
        declared,
        CostSnapshot(),
        1.0,
        None,
        (ref,),
        (verification,),
        (),
        {"cloud": "v1"},
        source_verified=True,
    )
    assert result.accepted_task_success is False
    assert result.structurally_complete_success is True


def test_attested_verification_requires_source_bound_envelope(scene_pool):
    original = record(assignment(scene_pool), "STOP")
    with pytest.raises(ValueError, match="verification"):
        replace(original, verification_records=({"status": "PASS"},), source_verified=True)


def test_verification_content_hash_rejects_changed_verdict(scene_pool, tmp_path):
    import hashlib
    from dataclasses import asdict

    from cloud_edge_robot_arm.datasets.rgbd.models import content_digest

    original = record(assignment(scene_pool), "STOP")
    raw = tmp_path / "verdict.json"
    raw.write_text('{"status":"PASS"}')
    ref = assignment_api().ArtifactReference(
        "online-verdict.v1", hashlib.sha256(raw.read_bytes()).hexdigest(), str(raw)
    )
    envelope = {
        "schema_version": "ced.verification-record.v1",
        "record": {"status": "PASS"},
        "source_refs": [asdict(ref)],
    }
    envelope["content_hash"] = content_digest(envelope)
    bound = replace(original, verification_records=(envelope,), source_verified=True)
    assert bound.verification_records[0]["record"] == {"status": "PASS"}
    envelope["record"] = {"status": "FAIL"}
    with pytest.raises(ValueError, match="verification.*hash"):
        replace(original, verification_records=(envelope,))


def test_recovery_failure_penalty_is_fixed_sixty_seconds(scene_pool):
    row = assignment(scene_pool)
    value = record(row, "FAILED")
    assert api().penalized_recovery_duration(value, elapsed_s=0.1) == 60.0
    with pytest.raises(ValueError, match="finite"):
        api().penalized_recovery_duration(value, elapsed_s=float("nan"))


def test_only_documented_infrastructure_damage_allows_paired_rerun(scene_pool, tmp_path):
    module = api()
    rows = assignment_api().build_assignments(
        frozen(scene_pool), ("JOINT", "B0"), scene_pool=scene_pool
    )
    group = rows[0].group_id
    originals = [record(row, "FAILED") for row in rows if row.group_id == group]
    with pytest.raises(ValueError, match="incident"):
        module.authorize_paired_rerun(originals, None)
    import json

    note = tmp_path / "incident.json"
    note.write_text(
        json.dumps(
            {
                "incident_id": "infra-1",
                "category": "RENDERER_CRASH",
                "group_id": group,
                "original_record_hashes": [r.content_hash for r in originals],
                "affected_methods": [r.assignment.method_id for r in originals],
                "diagnostic": "renderer process exited before valid capture",
                "source_hashes": ["a" * 64],
            }
        )
    )
    import hashlib

    ref = assignment_api().ArtifactReference(
        "incident.v1", hashlib.sha256(note.read_bytes()).hexdigest(), str(note)
    )
    authorized = module.authorize_paired_rerun(originals, ref, expected_method_ids=("JOINT", "B0"))
    assert set(authorized.original_record_hashes) == {r.content_hash for r in originals}
    assert set(authorized.method_ids) == {"JOINT", "B0"}
    assert all(r.run_status == "FAILED" for r in originals)
    note.write_text(note.read_text().replace("RENDERER_CRASH", "TASK_FAILED"))
    with pytest.raises(ValueError, match="hash"):
        module.authorize_paired_rerun(originals, ref)
    ref = replace(ref, content_hash=hashlib.sha256(note.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match="infrastructure"):
        module.authorize_paired_rerun(originals, ref)


def test_infrastructure_rerun_cannot_omit_part_of_frozen_method_pair(scene_pool, tmp_path):
    import hashlib
    import json

    module = api()
    rows = assignment_api().build_assignments(
        frozen(scene_pool), ("JOINT", "B0", "B1"), scene_pool=scene_pool
    )
    group = rows[0].group_id
    originals = [record(row, "FAILED") for row in rows if row.group_id == group][:2]
    note = tmp_path / "partial-incident.json"
    note.write_text(
        json.dumps(
            {
                "incident_id": "infra-partial",
                "category": "RENDERER_CRASH",
                "group_id": group,
                "original_record_hashes": [r.content_hash for r in originals],
                "affected_methods": [r.assignment.method_id for r in originals],
                "diagnostic": "crash",
                "source_hashes": ["a" * 64],
            }
        )
    )
    ref = assignment_api().ArtifactReference(
        "incident.v1", hashlib.sha256(note.read_bytes()).hexdigest(), str(note)
    )
    with pytest.raises(ValueError, match="complete"):
        module.authorize_paired_rerun(originals, ref, expected_method_ids=("JOINT", "B0", "B1"))


def test_trace_reference_verifies_hash_and_missing_content(tmp_path):
    module = assignment_api()
    with pytest.raises(ValueError, match="hash"):
        module.ArtifactReference("trace.v1", "not-sha", "trace.json")
    ref = module.ArtifactReference("trace.v1", "a" * 64, str(tmp_path / "missing.json"))
    with pytest.raises(ValueError, match="missing"):
        ref.verify()


def test_gate_replay_preserves_identical_candidate_snapshot():
    from tests.test_fixed_opportunity_replay import opportunities

    values = opportunities()
    records = api().run_gate_replay(values, "JOINT")
    assert [r.opportunity_id for r in records] == ["opp-safe", "opp-unsafe", "opp-unknown"]
    assert [r.verdict.status for r in records] == ["VALID", "INVALID", "UNKNOWN"]
    b3 = api().run_gate_replay(values, "B3")
    assert [r.opportunity_hash for r in records] == [r.opportunity_hash for r in b3]
    changed_labels = [replace(v, oracle_label="INVALID") for v in values]
    assert [r.verdict for r in api().run_gate_replay(changed_labels, "JOINT")] == [
        r.verdict for r in records
    ]


def test_gate_replay_keeps_per_opportunity_frozen_clock():
    from datetime import timedelta

    from tests.test_fixed_opportunity_replay import opportunities

    values = opportunities()
    values[1] = replace(values[1], replay_at=values[1].replay_at + timedelta(seconds=10))
    records = api().run_gate_replay(values, "B3")
    assert len(records) == 3
    assert records[1].verdict.status == "INVALID"


def test_cli_missing_final_writes_not_run_without_model_or_physics(tmp_path):
    import json
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_rgbd_research.py",
            "--protocol",
            str(tmp_path / "absent"),
            "--output",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 3
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "NOT_RUN"
    assert report["executed_assignments"] == report["physical_success"] == 0


def test_record_roundtrip_detects_content_tampering(scene_pool):
    module = assignment_api()
    original = record(assignment(scene_pool), "STOP")
    payload = original.to_payload()
    restored = module.episode_record_from_payload(payload)
    assert restored.content_hash == original.content_hash
    payload["duration_penalized_s"] = 0.01
    with pytest.raises(ValueError, match="hash"):
        module.episode_record_from_payload(payload)


def test_gate_cli_requires_explicit_software_fixture_without_accepted_final(tmp_path):
    import json
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_rgbd_gate_replay.py",
            "--protocol",
            str(tmp_path / "absent"),
            "--opportunities",
            str(tmp_path / "absent.json"),
            "--method",
            "JOINT",
            "--output",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 3
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "NOT_RUN"
    assert report["replayed_opportunities"] == 0


def test_gate_cli_software_fixture_replays_all_with_explicit_mock_label(tmp_path):
    import json
    import subprocess
    import sys

    from cloud_edge_robot_arm.datasets.rgbd.models import content_digest
    from cloud_edge_robot_arm.research.assignments import _json
    from tests.test_fixed_opportunity_replay import opportunities

    rows = [_json(value) for value in opportunities()]
    path = tmp_path / "opportunities.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "ced.opportunity-set.v1",
                "opportunities": rows,
                "content_hash": content_digest(rows),
            }
        )
    )
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_rgbd_gate_replay.py",
            "--opportunities",
            str(path),
            "--method",
            "JOINT",
            "--output",
            str(tmp_path / "out"),
            "--software-fixture",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "SOFTWARE_ONLY"
    assert report["evidence_kind"] == "MOCK"
    assert report["replayed_opportunities"] == 3
    assert report["formal_source_accepted"] is False


def test_resume_preserves_all_original_blocked_records_and_detects_drift(scene_pool, tmp_path):
    import json
    import subprocess
    import sys

    protocol_dir = tmp_path / "protocol"
    protocol_dir.mkdir()
    (protocol_dir / "protocol.json").write_text(frozen(scene_pool).model_dump_json())
    pools_path = tmp_path / "pools.json"
    pools_path.write_text(json.dumps({"formal": scene_pool}))
    config = tmp_path / "formal.yaml"
    config.write_text("schema_version: ced.formal.v1\nmethods: [JOINT]\n")
    command = [
        sys.executable,
        "scripts/run_rgbd_research.py",
        "--config",
        str(config),
        "--protocol",
        str(protocol_dir),
        "--pools",
        str(pools_path),
        "--output",
        str(tmp_path / "out"),
    ]
    first = subprocess.run(command, capture_output=True, text=True, check=False)
    assert first.returncode == 3, first.stdout + first.stderr
    records_path = tmp_path / "out" / "records.jsonl"
    original = records_path.read_bytes()
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["assigned_denominator"] == report["blocked_assignments"] == 600
    assert report["executed_assignments"] == report["physical_success"] == 0
    second = subprocess.run(command + ["--resume"], capture_output=True, text=True, check=False)
    assert second.returncode == 3
    assert records_path.read_bytes() == original
    payload = json.loads(records_path.read_text().splitlines()[0])
    payload["duration_penalized_s"] = 0.001
    records_path.write_text(
        json.dumps(payload) + "\n" + "\n".join(records_path.read_text().splitlines()[1:]) + "\n"
    )
    corrupt = records_path.read_bytes()
    third = subprocess.run(command + ["--resume"], capture_output=True, text=True, check=False)
    assert third.returncode == 3
    assert records_path.read_bytes() == corrupt
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "NOT_RUN"
    assert "hash" in report["reasons"][0]
