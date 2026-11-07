"""Historical real pixels and original clocks; SOFTWARE_ONLY, no physical execution."""

import copy
import hashlib
from datetime import datetime, timedelta, timezone
from importlib import import_module, util

import pytest

from cloud_edge_robot_arm.research import native_collection_grounding as grounding
from cloud_edge_robot_arm.research.native_calibration_collection import (
    canonical,
    detached,
    load_json,
)
from cloud_edge_robot_arm.research.native_full_horizon_originals import _Audit
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker
from tests.test_native_collection_grounding import _registration_case


def _case(monkeypatch, tmp_path):
    c = _registration_case(monkeypatch, tmp_path)
    c.app._handoff_registered_capture(c.live, c.b, c.lease, c.protocol, consume_capture=c.consume)
    return c


def _archive_type():
    return import_module(
        "cloud_edge_robot_arm.research.native_archived_tracker"
    )._ArchivedTargetTracker


def _hashes(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def _software_app(c, monkeypatch, tmp_path):
    from tests.test_native_collection_authority import application

    app = application(tmp_path)
    live = c.app._REGISTRY[app]
    for name in ("original", "tracker", "grounding_evidence", "recorder", "robot"):
        setattr(live, name, getattr(c.live, name))
    # Only source-clock integration is exercised; no worker lease or motion is issued.
    monkeypatch.setattr(
        c.app.NativeCollectionApplication, "_consume_capture", lambda self: c.consume()
    )
    return app, live


def test_archived_pixels_replay_at_original_time_without_live_clock_override(monkeypatch, tmp_path):
    assert isinstance(getattr(OpenCVTargetTracker, "last_binding_evaluated_at", None), property), (
        "R449 actual tracker evaluation UTC property missing"
    )
    c = _case(monkeypatch, tmp_path)
    c.clock[0] += timedelta(milliseconds=10)
    c.app._collect_grounded_step(c.live, 0, c.e, c.protocol, consume_capture=c.consume)
    recorded = load_json(c.root / "grounding/step-1.json")
    hashes = _hashes(c.root)
    original_when = c.live.tracker.last_binding_evaluated_at
    with pytest.raises(AttributeError):
        c.live.tracker.last_binding_evaluated_at = original_when
    c.clock[0] += timedelta(days=3)
    with pytest.raises(ValueError, match="capture_time_not_fresh"):
        grounding.bootstrap_collection_tracker(c.e, c.protocol["geometry"])
    stale = c.live.tracker.facts(c.e, c.state)
    assert all(
        v["value"] is None and "capture_time_not_fresh" in v["reasons"] for v in stale.values()
    )
    audit = c.audit()
    archive, evidence = audit.registration_bootstraps()
    when = audit.tracker_clock(
        recorded["tracker_clock"], c.e, purpose="GROUNDING", index=0, step_id="step-1"
    )
    assert when == original_when
    assert canonical(archive.facts_at(c.e, c.state, evaluated_at=when)) == canonical(
        recorded["online"]["visual_facts"]
    )
    assert evidence["depth_error_bound_m"] is None
    assert recorded["online"]["visual_facts"]["object_stable"]["value"] is None
    assert _hashes(c.root) == hashes


def test_original_expired_and_invalid_clock_records_fail_closed(monkeypatch, tmp_path):
    assert callable(getattr(_Audit, "tracker_clock", None)), (
        "R449 original tracker clock validation missing"
    )
    c = _case(monkeypatch, tmp_path / "originals")
    original = load_json(c.root / "tracker-clock/dispatch.json")
    assert c.audit().tracker_clock(original, c.e, purpose="BOOTSTRAP_E") == c.clock[0]

    def change(path, value):
        def mutate(row):
            target = row
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value

        return mutate

    changes = [
        change(("purpose",), "BOOTSTRAP_B"),
        change(("source_generation",), "f" * 64),
        change(("observation_id",), c.b.observation_id),
        change(("checksum_sha256",), c.b.checksum_sha256),
        change(("index",), 0),
        change(("evaluated_at",), c.clock[0].replace(tzinfo=None).isoformat()),
        change(("evaluated_at",), c.clock[0].astimezone(timezone(timedelta(hours=1))).isoformat()),
        change(("started_at",), (c.clock[0] + timedelta(seconds=1)).isoformat()),
        change(("acquisition", "acquisition_id"), "B"),
        change(("consumption_before", "step"), 121),
        change(("consumption_before", "acquisition_id"), "B"),
        change(("consumption_before", "live_owner", "lease", "lease_id"), "foreign"),
        change(("consumption_before", "live_owner", "lease", "job_id"), "foreign"),
        change(("consumption_before", "live_owner", "original_deadline_ns"), 10**12 + 1),
        change(("consumption_before", "consumed", "domain"), {"scope": "foreign"}),
        change(("consumption_before", "consumed", "upper_ns"), 5 * 10**9 + 1000),
        change(("consumption_after", "consumed", "lower_ns"), 0),
        change(("consumption_before", "capture", "lower_ns"), 199),
        change(("consumption_before", "live_owner", "lease", "expires_at"), c.clock[0].isoformat()),
        change(
            ("consumption_after", "live_owner", "lease", "observed_at"), c.e.captured_at.isoformat()
        ),
        lambda row: row.pop("evaluated_at"),
        lambda row: row.pop("consumption_after"),
    ]
    for expired in (
        c.e.captured_at + timedelta(seconds=5.000001),
        c.e.captured_at - timedelta(seconds=0.050001),
    ):
        changes.append(
            lambda row, expired=expired: row.update(
                started_at=expired.isoformat(),
                evaluated_at=expired.isoformat(),
                finished_at=expired.isoformat(),
            )
        )
    for mutate in changes:
        row = copy.deepcopy(original)
        mutate(row)
        audit = c.audit()
        read = audit.read
        # Keep source joins internally consistent to test the invalid boundary itself.
        audit.read = lambda name, row=row, read=read: (
            [row.get("consumption_before"), row.get("consumption_after")]
            if name == "capture-consumptions.json"
            else read(name)
        )
        with pytest.raises((ValueError, KeyError, TypeError)):
            audit.tracker_clock(row, c.e, purpose="BOOTSTRAP_E")
    archive = _archive_type()(c.e, c.live.grounding_evidence, evaluated_at=c.clock[0])
    for expired in (
        c.e.captured_at + timedelta(seconds=5.000001),
        c.e.captured_at - timedelta(seconds=0.050001),
    ):
        facts = archive.facts_at(c.e, c.state, evaluated_at=expired)
        assert facts["target_visible"]["value"] is None
        assert "capture_time_not_fresh" in facts["target_visible"]["reasons"]
    tampered = _case(monkeypatch, tmp_path / "tampered-bytes")
    path = tampered.root / "E.json"
    before = path.read_bytes()
    path.write_bytes(before + b" ")
    row = load_json(tampered.root / "tracker-clock/dispatch.json")
    with pytest.raises(ValueError, match="reference changed"):
        tampered.audit().tracker_clock(row, tampered.e, purpose="BOOTSTRAP_E")


def test_archive_tracker_cannot_enter_live_collection(monkeypatch, tmp_path):
    assert util.find_spec("cloud_edge_robot_arm.research.native_archived_tracker") is not None, (
        "R449 private archived tracker module missing"
    )
    c = _case(monkeypatch, tmp_path / "pixels")
    archive = _archive_type()(c.e, c.live.grounding_evidence, evaluated_at=c.clock[0])
    other = _archive_type()(c.e, c.live.grounding_evidence, evaluated_at=c.clock[0])
    with pytest.raises(ValueError, match="single-use"):
        archive.facts(c.e, c.state)
    bound = archive._binding_reason_at

    def rejected(*args):
        raise RuntimeError("SOFTWARE_ONLY interrupted computation")

    monkeypatch.setattr(archive, "_binding_reason_at", rejected)
    with pytest.raises(RuntimeError, match="interrupted"):
        archive.facts_at(c.e, c.state, evaluated_at=c.clock[0])
    assert archive._original_time is None
    assert other.facts_at(c.e, c.state, evaluated_at=c.clock[0])["target_visible"]["value"] is True
    monkeypatch.setattr(archive, "_binding_reason_at", bound)
    with pytest.raises(ValueError, match="single-use"):
        archive.facts(c.e, c.state)
    with pytest.raises(ValueError, match="aware UTC"):
        archive.facts_at(c.e, c.state, evaluated_at=c.clock[0].replace(tzinfo=None))
    app, live = _software_app(c, monkeypatch, tmp_path / "factory")
    live.tracker = archive
    with pytest.raises(RuntimeError, match="exact original pixel tracker"):
        app._evaluate_collection_admission(
            phase="PRE",
            step=c.original.contract.steps[0],
            conditions=(),
            observation=c.e,
            shield=None,
        )
    assert live.session is None and not c.live.recorder.decisions
    now = c.clock[0]
    c.clock[0] += timedelta(days=2)
    with pytest.raises(ValueError, match="capture_time_not_fresh"):
        OpenCVTargetTracker(c.e, c.live.grounding_evidence)
    assert archive.facts_at(c.e, c.state, evaluated_at=now)["target_visible"]["value"] is True


def test_bootstrap_grounding_and_admission_replay_consumes_exact_clock_sources(
    monkeypatch, tmp_path
):
    assert callable(getattr(grounding, "collection_bootstrap_evidence", None)), (
        "R449 pure pixel bootstrap evidence seam missing"
    )
    from cloud_edge_robot_arm.contracts import ExecutionCheckpoint, TaskStep
    from cloud_edge_robot_arm.edge.evidence.conditions import (
        OnlineEvidenceSnapshot,
        evaluate_conditions,
    )
    from cloud_edge_robot_arm.edge.safety.models import SafetyContext
    from cloud_edge_robot_arm.research.raw_episode_v3 import _owner_decode
    from cloud_edge_robot_arm.vision.execution import research_safety_shield
    from cloud_edge_robot_arm.vision.owner_registration import (
        DeterministicGroundingPolicy,
        StepGroundingBinding,
        bind_step_grounding,
    )
    from cloud_edge_robot_arm.vision.worker_owner import grounded_worker_effect_conditions

    c = _case(monkeypatch, tmp_path / "pixels")
    app, live = _software_app(c, monkeypatch, tmp_path / "factory")
    shield = research_safety_shield(1800)
    recorder = c.live.recorder
    recorder.record_shield_config(shield)
    for index in range(8):
        c.clock[0] += timedelta(milliseconds=10)
        contract, step, binding, _, _ = c.app._collect_grounded_step(
            c.live, index, c.e, c.protocol, consume_capture=c.consume
        )
        live.next_index = index
        for phase in ["PRE", "POST", "TERMINAL"] if index == 7 else ["PRE", "POST"]:
            c.clock[0] += timedelta(milliseconds=10)
            if phase != "TERMINAL":
                context = shield.context_builder.build(
                    contract=contract,
                    step=step,
                    robot_state=c.state,
                    scene_version=contract.scene_version,
                    resolved_parameters=step.parameters,
                    scene_updated_at=c.e.captured_at,
                    telemetry_timestamp=c.clock[0],
                    wall_clock_now=c.clock[0],
                    monotonic_now=0.0,
                    step_started_at_mono=0.0,
                    task_started_at_mono=0.0,
                )
                result, sources = recorder.check_shield(shield, context, index=index, phase=phase)
            else:
                sources = dict(sources, reused_from="POST")
            conditions = (
                c.original.requirements[step.step_id].preconditions
                if phase == "PRE"
                else grounded_worker_effect_conditions(c.original, binding)
            )
            before = len(recorder.decisions)
            try:
                app._evaluate_collection_admission(
                    phase=phase,
                    step=step,
                    conditions=conditions,
                    observation=c.e,
                    shield=result,
                    binding=binding,
                    shield_source=sources,
                )
            except RuntimeError as error:
                # Static pixels cannot prove physical completion. Preserve each actual STOP.
                assert str(error).startswith("collection admission stopped:")
            assert len(recorder.decisions) == before + 1
    assert len(recorder.decisions) == 17 and live.session is None
    recorder._write_original("decisions.software-only.json", recorder.decisions)
    hashes = _hashes(c.root)
    c.clock[0] += timedelta(days=4)
    audit = c.audit()
    tracker, evidence = audit.registration_bootstraps()
    decisions = load_json(c.root / "decisions.software-only.json")
    assert any(v["status"] == "UNKNOWN" for row in decisions for v in row["inputs"]["verdicts"])
    for index in range(8):
        record = audit.reference(recorder.grounding_sources[index])
        when = audit.tracker_clock(
            record["tracker_clock"],
            c.e,
            purpose="GROUNDING",
            index=index,
            step_id=f"step-{index + 1}",
        )
        facts = tracker.facts_at(c.e, c.state, evaluated_at=when)
        assert canonical(facts) == canonical(record["online"]["visual_facts"])
        checkpoint = ExecutionCheckpoint.model_validate(record["checkpoint"])
        online = OnlineEvidenceSnapshot(c.e, c.state, facts, 1, 1, checkpoint.checkpoint_hash)
        binding = _owner_decode(StepGroundingBinding, record["binding"])
        inputs = grounding.collection_grounding_inputs(
            c.e,
            c.state,
            c.protocol["geometry"],
            tracker=tracker,
            evidence=evidence,
            source_hashes=c.original.source_hashes,
        )
        replay = bind_step_grounding(
            c.original,
            original_step_id=record["step_id"],
            grounded_step=TaskStep.model_validate(record["grounded_step"]),
            online=online,
            source_checkpoint=checkpoint,
            current_identity=c.original.identity,
            owner_revision=index + 1,
            state_generation=index + 1,
            grounding_inputs=inputs,
            grounding_policy=DeterministicGroundingPolicy(**record["policy"]),
            now=datetime.fromisoformat(record["binding_now"]),
        )
        assert replay.digest() == binding.digest()
        for row in decisions[2 * index : 2 * index + (3 if index == 7 else 2)]:
            item = row["inputs"]
            when = audit.tracker_clock(
                item["tracker_clock"],
                c.e,
                purpose="ADMISSION_" + item["phase"],
                index=index,
                step_id=f"step-{index + 1}",
            )
            facts = tracker.facts_at(c.e, c.state, evaluated_at=when)
            assert canonical(facts) == canonical(item["facts"])
            conditions = (
                c.original.requirements[f"step-{index + 1}"].preconditions
                if item["phase"] == "PRE"
                else grounded_worker_effect_conditions(c.original, binding)
            )
            verdicts = evaluate_conditions(
                conditions,
                OnlineEvidenceSnapshot(c.e, c.state, facts, 1, 1, c.original.digest()),
                now=datetime.fromisoformat(item["evaluation_at"]),
            )
            assert detached(verdicts) == item["verdicts"]
            source = audit.reference(item["shield_source"]["input"])
            output = audit.reference(item["shield_source"]["result"])
            shield_result = getattr(shield, source["method"])(
                SafetyContext.model_validate(source["context"])
            )
            assert detached(shield_result) == output["result"] == item["shield"]
            assert facts["object_stable"]["value"] is None
    assert len(audit.tracker_clock_keys) == 27
    assert _hashes(c.root) == hashes
    for name in ("tracker-clock/bootstrap.json", "tracker-clock/dispatch.json"):
        broken = c.audit()
        read = broken.reference
        broken.reference = lambda ref, name=name, read=read: (
            {} if ref["path"] == name else read(ref)
        )
        with pytest.raises(KeyError):
            broken.registration_bootstraps()
    for item in (
        load_json(c.root / "grounding/step-1.json")["tracker_clock"],
        decisions[0]["inputs"]["tracker_clock"],
    ):
        broken = copy.deepcopy(item)
        broken.pop("evaluated_at")
        with pytest.raises(KeyError):
            c.audit().tracker_clock(broken, c.e, purpose=item["purpose"], index=0, step_id="step-1")
