"""Actual public reader and registry ingest a source-bound, one-step software graph."""

import os
import shutil
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from cloud_edge_robot_arm.research.native_calibration_collection import (
    CONFIG,
    ROOT,
    canonical,
    detached,
    digest,
    load_json,
    prepare_native_calibration,
    read_protocol,
    save_exclusive,
)
from cloud_edge_robot_arm.research.native_collection_application import _collection_guard, _Live
from cloud_edge_robot_arm.research.native_collection_grounding import build_collection_contract
from cloud_edge_robot_arm.research.native_full_horizon_originals import (
    _Audit,
    _restore_frame,
    read_native_full_horizon_group,
    reconstruct_native_full_horizon_registry,
)
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.worker_owner import WorkerLeaseObservation
from tests.native_collection_source_graph import (
    install_original_shape_camera,
    install_software_reset_engine,
    reseal_software_inventory,
    write_software_json,
)
from tests.test_native_collection_authority import source_recorder
from tests.test_visual_raw_recorder_v3 import recorder_fixture

GUARD_REASON = "operations:ValueError:source guard failed or did not close"


@pytest.fixture(scope="module")
def bound_guard_graph(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, str]:
    """Bind a synthetic owner/lease and original to real recorder operations; no claim or MuJoCo."""
    base = tmp_path_factory.mktemp("guard-readback")
    root, protocol = base / "group", base / "registration"
    prepare_native_calibration(ROOT / CONFIG, output=protocol)
    registration = read_protocol(protocol)
    assignment = registration["assignments"][0]
    root.mkdir()
    _, backend, capture, executor, raw_id, old_plan = recorder_fixture(root)
    sources = SimpleNamespace(source_root=ROOT, source_hashes=registration["source_hashes"])
    recorder, backend, capture, owner, _ = source_recorder(
        root, software_fixture=(sources, backend, capture, executor, raw_id, old_plan)
    )
    geometry = registration["geometry"]
    backend._config = backend._config.model_copy(
        update={"model_path": str(ROOT / geometry["asset_path"])}
    )
    backend._episode_id = None
    install_original_shape_camera(backend, geometry)
    install_software_reset_engine(backend)
    start = datetime.now(UTC)
    lease = WorkerLeaseObservation(
        "software-job",
        "software-run",
        "software-worker",
        "software-lease",
        1,
        start,
        start,
        start + timedelta(minutes=30),
        "a" * 64,
        "b" * 64,
        "c" * 64,
    )
    token = owner.begin_event("SOFTWARE_ONLY")
    owner.mark_event(token)
    origin = detached(owner.end_event(token))
    budget = 1800 * 10**9
    deadline = dict(origin=origin, budget_ns=budget, deadline_ns=origin["lower_ns"] + budget)
    startup = dict(
        assignment=assignment,
        protocol_sha256=digest(registration),
        origin=origin,
        deadline=deadline,
    )
    save_exclusive(root / "startup.json", startup)
    checks = []
    live = _Live(
        repository=None,
        worker=None,
        output=root,
        protocol_path=protocol,
        protocol_json=canonical(registration),
        assignment_id=assignment["assignment_id"],
        pid=os.getpid(),
        thread=threading.get_ident(),
        recorder=recorder,
        backend=backend,
    )

    def guard(checkpoint: Any) -> None:
        checks.append(
            dict(
                checkpoint=detached(checkpoint),
                step=backend.total_physics_steps,
                current=detached(owner.read_current(after=token)),
                lease_id=lease.lease_id,
            )
        )

    try:
        with capture, recorder:
            backend.reset(
                PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=assignment["seed"])
            )
            recorder.require_clean_reset()
            meta = load_json(recorder.directory / next(iter(recorder.frame_sources.values())))
            obs = RGBDObservation.model_validate(
                _restore_frame(recorder.directory, meta)["observation_payload"]
            )
            plan = build_collection_contract(
                assignment=assignment,
                geometry=geometry,
                observation=obs,
                source_hashes=registration["source_hashes"],
                current_owner=dict(
                    issued_at=start,
                    deadline_at=start + timedelta(minutes=30),
                    task_id=lease.job_id,
                    plan_id="software-plan",
                    lease=lease,
                    role_sha256=digest(registration["role"]),
                ),
            )
            # The fixed owner stands in for SQLite, while source binding and all reader stages run.
            source = {
                **startup,
                "original": plan,
                "assignment_id": assignment["assignment_id"],
                "assignment_basis": {"registered_assignment": assignment},
                "attempt_basis": {"fixture": "SOFTWARE_ONLY", "lease_id": lease.lease_id},
                "source_generation": registration["source_generation"],
                "source": {"lease": lease.to_payload()},
                "asset_sha256": registration["settings"]["marked_asset_sha256"],
                "control_source": "PIXELS_PROPRIO_REGISTERED_CONSTANTS",
                "truth": "OFFLINE_LABELS_ONLY",
            }
            recorder.bind_collection_source(SimpleNamespace(recorder_source=lambda _: source))
            with _collection_guard(live, guard, 1024):
                with backend.capture_each_physics_step(max_captures=1), recorder.purpose("SETTLE"):
                    backend.step(1)
            recorder._write_original("active-checks.json", checks)
            recorder.freeze()
    finally:
        owner.close()
    return protocol, root, assignment["assignment_id"]


@pytest.mark.parametrize(
    "case",
    [
        "healthy",
        "explicit-failure",
        "termination_entry_error",
        "termination_exit_error",
        "stop_error",
        "prior-failure-then-closed",
        "prior-closed-then-failure",
        "nested-error",
        "nested-error-then-closed",
        "bounded-checkpoint-nested-failure",
        "snapshot-error-type-in-allowed-checkpoint",
        "prior-full-failure-then-closed",
    ],
)
def test_public_group_and_registry_check_guard_closure(
    bound_guard_graph: tuple[Path, Path, str],
    tmp_path: Path,
    case: str,
) -> None:
    protocol, healthy, assigned = bound_guard_graph
    target = tmp_path / "group"
    shutil.copytree(healthy, target)
    directory = target / "originals"
    path = directory / "partial-originals.json"
    raw = load_json(path)
    events = raw["guard_events"]
    closed = events[-1]
    assert closed == {"kind": "CLOSED", "physics_step": 1}
    failure = {**closed, "kind": "FAILURE", "error_type": "OSError", "error": "fixture brake"}
    if case == "explicit-failure":
        events[-1] = failure
    elif case in {"termination_entry_error", "termination_exit_error", "stop_error"}:
        closed.update({case: "fixture source failure", case + "_type": "OSError"})
    elif case == "prior-failure-then-closed":
        events.insert(-1, {"kind": "FAILURE", "physics_step": 1})
    elif case == "prior-full-failure-then-closed":
        events.insert(-1, failure)
    elif case == "prior-closed-then-failure":
        events.append(failure)
    elif case == "nested-error":
        events[-1] = {**closed, "closure": failure}
    elif case == "nested-error-then-closed":
        events[-2]["closure"] = {**closed, "termination_exit_error": "fixture ledger"}
    elif case == "bounded-checkpoint-nested-failure":
        # The actual bounded writer nests its terminal on the last retained event.
        events.pop()
        events[-1]["closure"] = failure
    elif case == "snapshot-error-type-in-allowed-checkpoint":
        events[-2]["snapshot_error_type"] = "OSError"
    if case != "healthy":
        write_software_json(path, raw)
        reseal_software_inventory(directory)

    groups: list[dict[str, Any]] = []
    joint = reconstruct_native_full_horizon_registry(
        protocol, roots={assigned: target}, group_sink=groups.append
    )
    group = read_native_full_horizon_group(protocol, assignment_id=assigned, root=target)
    [via_registry] = [g for g in groups if g["assignment_id"] == assigned]
    assert tuple(via_registry["reasons"]) == group.reasons
    assert not any(
        reason.startswith(("source:", "inventory:", "physics:")) for reason in group.reasons
    ), group.reasons
    operations = [reason for reason in group.reasons if reason.startswith("operations:")]
    assert operations == ([] if case == "healthy" else [GUARD_REASON])
    assert sum(g.get("state") == "NOT_RUN" for g in groups) == 8
    assert joint.joint_bound_m is None and group.native_qualification == "UNKNOWN"

    registration = read_protocol(protocol)
    audit = _Audit(registration, registration["assignments"][0], target)
    audit.inventory()
    audit.source()
    audit.physics()
    assert audit.source_ok and set(audit.states) == {0, 1}
    if case == "healthy":
        audit.operations()
    else:
        with pytest.raises(ValueError, match="^source guard failed or did not close$"):
            audit.operations()
