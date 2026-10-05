"""SOFTWARE_ONLY prefix control effects, with real SQLite worker lease bookkeeping."""

import json
from dataclasses import replace
from importlib import import_module

import pytest

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import BackendOperationBoundary
from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
from tests.test_native_clock_publication_v2 import activate, application
from tests.test_native_reset_capture_v2 import reset_events
from tests.test_raw_episode_v3 import state
from tests.test_visual_raw_recorder_v3 import software_backend, software_sensor_camera


def publication():
    return import_module("cloud_edge_robot_arm.research.native_clock_publication_v2")


def test_registered_prefix_branch_precedes_planner_factory(tmp_path, monkeypatch):
    app = application(tmp_path)
    job, _, start = activate(app)
    called = []

    def no_planner():
        pytest.fail("planner constructed before native source-only prefix")

    app.worker.planner_factory = no_planner

    def coordinator(application, worker, current, *, start_monotonic):
        called.append((application, worker, current.job_id, start_monotonic))
        return (
            {"evaluation_scope": "NATIVE_RESET_PREFIX_EXCLUDED", "prefix_complete": False},
            [],
            [],
        )

    monkeypatch.setattr(
        publication(), "run_native_reset_clock_prefix_v2", coordinator, raising=False
    )
    result, events, metrics = app.worker._run_visual_closed_loop(job, None, start_monotonic=start)
    assert called == [(app, app.worker, job.job_id, start)]
    assert result["evaluation_scope"] == "NATIVE_RESET_PREFIX_EXCLUDED"
    assert events == metrics == []


def software_components(monkeypatch, app, *, reset_failure=False, settle_failure=False):
    module = publication()
    backend = software_backend()
    # Test effects replace initialization/reset/step; none call native MuJoCo routines.
    calls = []
    backend.initialize = lambda config: (
        calls.append(("initialize", config.model_dump(mode="json"))),
        setattr(backend, "_config", config),
    )

    def reset(scenario):
        calls.append(("RESET", scenario.seed))
        backend._scenario = scenario
        rec = backend._operation_observer.__self__
        if reset_failure:
            rec._on_boundary(
                BackendOperationBoundary(
                    1, "RESET", "BEGIN", None, 0, 0.0, {"requested": {}}, None, None, None
                )
            )
            rec._on_boundary(
                BackendOperationBoundary(
                    1,
                    "RESET",
                    "END",
                    None,
                    0,
                    0.0,
                    {},
                    None,
                    "RuntimeError",
                    "SOFTWARE_ONLY reset failed",
                )
            )
            raise RuntimeError("SOFTWARE_ONLY reset failed")
        reset_events(rec, backend)
        software_sensor_camera(backend)
        # A CPU fake render feeds real CAPTURE dispatch; this is cached, not explicit capture.
        backend.capture_sensor_frame_with_instances()

    def settle(*, steps):
        calls.append(("SETTLE", steps))
        rec = backend._operation_observer.__self__
        for n in range(1, steps + 1):
            if settle_failure and n == 11:
                raise RuntimeError("SOFTWARE_ONLY settling stopped10")
            for kind, op, result in (
                ("CONTROL", n * 2 + 1, {"control_state": {"physics_step": n}}),
                (
                    "PHYSICS",
                    n * 2 + 2,
                    {"physics_state": {**state(n), "episode_id": "software-new"}},
                ),
            ):
                rec._on_boundary(
                    BackendOperationBoundary(
                        op,
                        kind,
                        "BEGIN",
                        "software-new",
                        n - 1,
                        (n - 1) / 240,
                        {},
                        None,
                        None,
                        None,
                    )
                )
                rec._on_boundary(
                    BackendOperationBoundary(
                        op,
                        kind,
                        "END",
                        "software-new",
                        n if kind == "PHYSICS" else n - 1,
                        n / 240,
                        {},
                        result,
                        None,
                        None,
                    )
                )
            backend._total_physics_steps = n

    backend.reset = reset
    backend.step = settle
    backend.shutdown = lambda: calls.append(("shutdown",))
    monkeypatch.setattr(module, "_new_prefix_backend_v2", lambda: backend, raising=False)

    def unavailable(**kwargs):
        calls.append(("exchange", kwargs["exchange_id"]))
        module._live(app).attempts.append(
            {
                "exchange_id": kwargs["exchange_id"],
                "status": "UNAVAILABLE",
                "original": None,
                "error": "SOFTWARE_ONLY no external UTC",
            }
        )
        return None

    monkeypatch.setattr(app.clock_source, "exchange", unavailable)
    return calls, backend


def test_real_poll_lease_attempt_prefix_120_settle_cached_capture_no_planner(tmp_path, monkeypatch):
    app = application(tmp_path)
    calls, _ = software_components(monkeypatch, app)
    app.worker.planner_factory = lambda: pytest.fail("model/planner construction forbidden")
    receipt = app.execute_once()
    assert receipt["prefix_complete"] is True
    assert receipt["cached_capture_allocations"] == 1
    assert receipt["explicit_acquisitions"] == receipt["allocated_actions"] == 0
    assert receipt["current_time_utc"] == receipt["native_utc"] == "UNAVAILABLE"
    assert receipt["consumer_feasibility"] == "UNAVAILABLE"
    assert receipt["historical_width_ns"] is None
    expected = SimulatorConfig(render_rgb=True, render_depth=True, seed=0).model_dump(mode="json")
    assert calls[0] == ("initialize", expected)
    assert ("SETTLE", 120) in calls and calls[-1] == ("shutdown",)
    job = app.repository.list_jobs()[0]
    assert job.status == RuntimeJobStatus.SUCCEEDED
    assert len(app.repository.list_attempts(job.run_id)) == 1
    assert (app.output / "prefix-originals/frames/acquisition-1/rgb.png").is_file()
    with pytest.raises(RuntimeError):
        app.execute_once()


@pytest.mark.parametrize("failure", ["reset", "settle"])
def test_failed_real_worker_prefix_keeps_all_originals_and_marks_failed(
    tmp_path, monkeypatch, failure
):
    app = application(tmp_path)
    software_components(
        monkeypatch, app, reset_failure=failure == "reset", settle_failure=failure == "settle"
    )
    receipt = app.execute_once()
    assert receipt["prefix_complete"] is False
    job = app.repository.list_jobs()[0]
    assert job.status == RuntimeJobStatus.FAILED
    assert (app.output / "prefix-originals/prefix-failures.json").is_file()
    physics = json.loads((app.output / "prefix-originals/unbound-physics.json").read_text())
    assert len(physics) == (10 if failure == "settle" else 0)


def test_two_exchange_coordinator_freezes_every_pair_before_b(tmp_path, monkeypatch):
    app = application(tmp_path)
    calls, backend = software_components(monkeypatch, app)
    seen = []

    def exchange(**kwargs):
        rec = backend._operation_observer.__self__
        seen.append((kwargs["exchange_id"], rec._frozen_prefix is not None))
        publication()._live(app).attempts.append(
            {"exchange_id": kwargs["exchange_id"], "status": "SOFTWARE_ONLY", "original": None}
        )
        if kwargs["exchange_id"] == "A":
            return replace(
                import_module(
                    "cloud_edge_robot_arm.research.native_clock_source_v2"
                ).ClockExchangeOriginalV2.from_payload(
                    json.loads(
                        (
                            app.clock_source.verifier.source_root
                            / "tools/research/native-clock-v2/testdata/software-only-exchange.json"
                        ).read_text()
                    )["causal_exchanges"]["A"]
                ),
                clock_domain_id=rec._clock_domain_id,
            )
        assert kwargs["commitment"] == import_module(
            "cloud_edge_robot_arm.research.native_clock_source_v2"
        ).slab_commitment(
            tuple(
                import_module(
                    "cloud_edge_robot_arm.research.native_clock_source_v2"
                ).ClockTupleV2.from_payload(p)
                for p in rec._frozen_prefix.to_payload()["clock_pairs"]
            ),
            acquisition_sha256=rec._frozen_prefix.digest(),
        )
        return None

    monkeypatch.setattr(app.clock_source, "exchange", exchange)
    receipt = app.execute_once()
    assert seen == [("A", False), ("B", True)]
    assert receipt["current_time_utc"] == "UNAVAILABLE"
    assert (
        len(json.loads((app.output / "prefix-originals/exchange-attempts.json").read_text())) == 2
    )
