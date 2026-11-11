"""封存多场景证据的历史时间回放；仅CPU，不加载模型或访问网络。"""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_molmo_multiscene import recorded_suite, saved_response


def api():
    return importlib.import_module("scripts.verify_molmo_multiscene_archive")


def inventory(root):
    return {
        str(p.relative_to(root)): (
            p.stat().st_size,
            p.stat().st_mtime_ns,
            hashlib.sha256(p.read_bytes()).hexdigest(),
        )
        for p in root.rglob("*")
        if p.is_file()
    }


@pytest.fixture(scope="module")
def archive(tmp_path_factory):
    from tests.test_molmo_current_execution import current_binding

    with pytest.MonkeyPatch.context() as patch:
        base = tmp_path_factory.mktemp("r569-archive")
        binding = current_binding(base, patch)

        def hook(module, state, root, registry):
            delegate = module.MolmoPointProvider.point

            def point(provider, observation, phrase):
                active = state.active
                try:
                    if active == "N02":
                        state.active = "CPU_POINT_N02"
                    return delegate(provider, observation, phrase)
                finally:
                    state.active = active

            patch.setattr(module.MolmoPointProvider, "point", point)

        data = recorded_suite(
            base, patch, groups=("G1", "G2", "G3"), damage="decoy", setup_hook=hook,
            execution_plan=binding[3],
        )
        module, cases, root, registry, state = data
        assert all(r["status"] == "COMPLETED" for r in state.reports)
        assert next(r for r in state.reports[0]["results"] if r["case_id"] == "N02")["passed"]
        from cloud_edge_robot_arm.vision import tracking

        class Later(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2090, 1, 1, tzinfo=UTC)

        with pytest.MonkeyPatch.context() as clock_patch:
            clock_patch.setattr(tracking, "datetime", Later)
            rows = [r for report in state.reports for r in report["results"]]
            original = module.summarize(registry, rows, root=root)
        assert not original["valid_suite"]
        module._write(root / "summary.local.json", original)
        yield SimpleNamespace(module=module, cases=cases, root=root, registry=registry, state=state)


def tracker_inputs(archive):
    h = archive.module
    case = next(c for c in archive.cases if c.case_id == "N02")
    events = h._read_events(archive.root, "N02")
    opened, ended = h._event_check(archive.root, archive.registry, "G1", case, events)
    end = next(e for e in ended.values() if e["kind"] == "stage" and e["stage"] == "tracker")
    start = opened[end["op_id"]]
    request = h.InitialPlanningRequest.model_validate(
        h._read(archive.root / "G1/N02/capture-01/request.json")
    )
    return request.observation, start, end


def test_delayed_archive_revalidates_without_changing_originals_or_online_clock(
    archive, monkeypatch
):
    from cloud_edge_robot_arm.vision import tracking

    module = api()
    original_class = tracking.OpenCVTargetTracker
    original_visual = archive.module._visual_source
    observation, _, end = tracker_inputs(archive)
    before = inventory(archive.root)
    results = []
    for year in (2090, 2095):

        class Later(datetime):
            @classmethod
            def now(cls, tz=None, _year=year):
                return datetime(_year, 1, 1, tzinfo=UTC)

        with monkeypatch.context() as patch:
            patch.setattr(tracking, "datetime", Later)

            def forbidden(*args, **kwargs):
                raise AssertionError("offline verifier invoked online work")

            for name in ("MolmoPointProvider", "MuJoCoCaptureSession", "run_group"):
                patch.setattr(archive.module, name, forbidden)
            result = module.verify_archive(archive.root)
            assert result["derived_summary"]["valid_suite"], result
            assert result["derived_summary"]["passed_cases"] == 7
            assert not result["historical_summary"]["valid_suite"]
            assert all(r["matches"] for r in result["case_comparisons"])
            assert tracking.OpenCVTargetTracker is original_class
            assert archive.module._visual_source is original_visual
            with pytest.raises(ValueError, match="capture_time_not_fresh"):
                original_class(observation, end["context"]["grounding"])
            results.append(result["derived_summary"])
    assert results[0] == results[1]
    assert inventory(archive.root) == before


@pytest.mark.parametrize(
    "first,last,accepted",
    [
        (-0.05, -0.05, True),
        (0.0, 5.0, True),
        (5.0, 5.0, True),
        (-0.050001, 0.0, False),
        (0.0, 5.000001, False),
    ],
)
def test_original_freshness_limits_apply_at_both_interval_ends(archive, first, last, accepted):
    from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker

    observation, _, end = tracker_inputs(archive)
    grounding = end["context"]["grounding"]
    start = observation.captured_at + timedelta(seconds=first)
    finish = observation.captured_at + timedelta(seconds=last)
    cls = api()._tracker_class_at_interval(
        OpenCVTargetTracker, observation, grounding, start, finish
    )
    reason = "color_identity_ambiguous" if accepted else "capture_time_not_fresh"
    with pytest.raises(ValueError, match=reason):
        cls(observation, grounding)


@pytest.mark.parametrize(
    "mutation", ["timezone", "reverse_utc", "reverse_monotonic", "op", "parent", "case", "context"]
)
def test_stage_interval_rejects_invalid_or_unbound_boundaries(archive, mutation):
    _, start, end = tracker_inputs(archive)
    start, end = copy.deepcopy(start), copy.deepcopy(end)
    if mutation == "timezone":
        start["utc"] = datetime.fromisoformat(start["utc"]).replace(tzinfo=None).isoformat()
    elif mutation == "reverse_utc":
        start["utc"] = (datetime.fromisoformat(end["utc"]) + timedelta(seconds=1)).isoformat()
    elif mutation == "reverse_monotonic":
        start["monotonic_s"] = end["monotonic_s"] + 1
    elif mutation == "context":
        start["context"]["native_pixel"] = [-1, -1]
    else:
        start[{"op": "op_id", "parent": "parent_op_id", "case": "case_id"}[mutation]] = "wrong"
    with pytest.raises(ValueError):
        api()._stage_interval(start, end)


def test_historical_scope_restores_both_bindings_on_exception(archive):
    from cloud_edge_robot_arm.vision import tracking

    h = archive.module
    original, visual = tracking.OpenCVTargetTracker, h._visual_source
    with pytest.raises(RuntimeError, match="CPU caller failure"):
        with api()._historical_tracker_refusal_scope(h, archive.root, archive.registry):
            raise RuntimeError("CPU caller failure")
    assert tracking.OpenCVTargetTracker is original and h._visual_source is visual


def test_replay_constructor_requires_the_bound_grounding(archive):
    from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker

    observation, start, end = tracker_inputs(archive)
    grounding = end["context"]["grounding"]
    cls = api()._tracker_class_at_interval(
        OpenCVTargetTracker,
        observation,
        grounding,
        datetime.fromisoformat(start["utc"]),
        datetime.fromisoformat(end["utc"]),
    )
    altered = copy.deepcopy(grounding)
    altered["original_pixel_target"] = [0, 0]
    with pytest.raises(ValueError, match="grounding"):
        cls(observation, altered)


@pytest.mark.parametrize("damage", ["missing_raw", "changed_raw", "registry", "harness_source"])
def test_bad_original_evidence_never_passes(archive, monkeypatch, damage):
    module = api()
    if damage == "harness_source":
        original = archive.module._sha
        actual = Path(archive.module.__file__)
        monkeypatch.setattr(
            archive.module,
            "_sha",
            lambda path: "0" * 64 if Path(path) == actual else original(path),
        )
        assert not module.verify_archive(archive.root)["derived_summary"]["valid_suite"]
        return
    p = archive.root / ("registry.json" if damage == "registry" else "G1/N02/capture-01/depth.f32")
    data, stat = p.read_bytes(), p.stat()
    try:
        if damage == "missing_raw":
            p.unlink()
        else:
            p.write_bytes(data + b" ")
        result = module.verify_archive(archive.root)
        assert not result["derived_summary"]["valid_suite"]
    finally:
        import os

        p.write_bytes(data)
        os.utime(p, ns=(stat.st_atime_ns, stat.st_mtime_ns))


def test_non_whitelisted_error_does_not_get_tracker_replay(archive):
    h = archive.module
    observation, _, _ = tracker_inputs(archive)
    case = next(c for c in archive.cases if c.case_id == "N02")
    events = h._read_events(archive.root, "N02")
    opened, ended = h._event_check(archive.root, archive.registry, "G1", case, events)
    altered = copy.deepcopy(ended)
    for e in altered.values():
        if e["kind"] == "stage" and e["stage"] == "tracker":
            e["error_message"] = "unknown original failure"
    parsed = [SimpleNamespace(status="POINT", normalized_1000=(150, 410))] * 2
    response = saved_response(h, archive.root, case)
    with api()._historical_tracker_refusal_scope(h, archive.root, archive.registry):
        assert (
            h._visual_source(
                case, response, {observation.checksum_sha256: observation}, opened, altered, parsed
            )
            is None
        )


def test_cli_requires_new_external_output_and_returns_evidence_status(
    archive, tmp_path, monkeypatch
):
    module = api()
    output = tmp_path / "derived"
    monkeypatch.setattr(
        module,
        "verify_archive",
        lambda root: {
            "derived_summary": {"valid_suite": True, "all_cases_pass": False, "passed_cases": 0}
        },
    )
    assert module.main(["--raw-root", str(archive.root), "--output-new", str(output)]) == 0
    assert (
        json.loads((output / "report.local.json").read_bytes())["derived_summary"]["all_cases_pass"]
        is False
    )
    with pytest.raises((FileExistsError, ValueError)):
        module.main(["--raw-root", str(archive.root), "--output-new", str(output)])
    with pytest.raises(ValueError):
        module.main(["--raw-root", str(archive.root), "--output-new", str(archive.root / "new")])


def test_current_archive_reports_its_bound_execution_identity(archive):
    report = api().verify_archive(archive.root)
    assert report["derived_summary"]["valid_suite"], report
    execution = archive.module._execution_for_registry(archive.registry)
    assert report["original_source_commit"] == execution["source_commit"]
    assert report["derived_verifier"]["expected_harness_sha256"] == (
        archive.registry["source_hashes"]["scripts/probe_molmo_multiscene.py"]
    )


@pytest.mark.parametrize("schema", ["molmo.interface.r558.v2", "unknown"])
def test_legacy_and_unknown_identity_cannot_use_changed_harness(tmp_path, schema):
    root = tmp_path / "archive"
    root.mkdir()
    (root / "registry.json").write_text(json.dumps({"schema": schema}))
    result = api().verify_archive(root)
    assert not result["derived_summary"]["valid_suite"]
    error = " ".join(result["derived_summary"]["evidence_errors"])
    assert ("historical harness source drift" if schema.endswith("r558.v2")
            else "unknown registry") in error
