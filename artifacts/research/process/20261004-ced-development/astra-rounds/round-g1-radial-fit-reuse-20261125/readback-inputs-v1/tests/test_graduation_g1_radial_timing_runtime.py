"""The timed radial overlay may use only a released detector on the qualified 115-mm fixture."""

import copy
import shutil
from pathlib import Path

import pytest
from scripts.graduation import g1_visibility_runtime as build
from scripts.graduation import g1_visibility_trials as trials
from scripts.graduation.perception_io import read

PARENT = "36f9658b9e7ef0d94db0a87876f4224e30d357d59f6dcc18dc65768dbb1e23bf"


def test_timing_prepare_is_explicit_and_exclusive_of_a_different_fixture():
    parser = trials.parser()
    assert parser.parse_args(["prepare"]).radial_mm == 0
    assert parser.parse_args(["prepare", "--radial-mm", "30"]).radial_timing is None
    args = parser.parse_args(["prepare", "--radial-timing", "a" * 64])
    assert args.radial_timing == "a" * 64 and args.radial_mm == 0
    with pytest.raises(SystemExit):
        parser.parse_args(["prepare", "--radial-timing", "a" * 64, "--radial-mm", "30"])


@pytest.fixture
def qualifying_budget():
    detector = {build.GRID: "1" * 64, build.DETECTOR: "2" * 64}
    return detector, dict(
        schema="g1.visibility.radial-paired-window-budget.v1",
        eligible=True,
        baseline_generation=PARENT,
        original_native_windows=123,
        detector_files_sha256=detector,
        estimated_p95_ms=80.0,
        estimated_max_ms=90.0,
        pixel_p95_ms=35.0,
        pixel_max_ms=45.0,
        limits_ms=dict(estimated_p95=80, estimated_max=90, pixel_p95=35, pixel_max=45),
        samples_sha256="f" * 64,
    )


def test_budget_checks_all_four_boundaries_and_the_exact_candidate(qualifying_budget):
    detector, record = qualifying_budget
    assert build.qualified_timing_budget(record, detector)
    for field, value in (
        ("eligible", False),
        ("baseline_generation", "x"),
        ("original_native_windows", 122),
        ("estimated_p95_ms", 80.00001),
        ("estimated_max_ms", 90.00001),
        ("pixel_p95_ms", 35.00001),
        ("pixel_max_ms", 45.00001),
        ("pixel_p95_ms", float("nan")),
        ("pixel_max_ms", True),
        ("estimated_p95_ms", -1),
        ("limits_ms", dict(estimated_p95=80, estimated_max=100, pixel_p95=35, pixel_max=45)),
        ("detector_files_sha256", {**detector, build.GRID: "0" * 64}),
    ):
        assert not build.qualified_timing_budget({**record, field: value}, detector), field


def test_candidate_inventory_rejects_a_changed_camera_controller_scorer_or_mount():
    parent_file = Path(build.PRIVATE) / "builds" / PARENT / "runtime-source/runtime-build.json"
    if not parent_file.exists():
        pytest.skip("sealed private baseline absent")
    prior = read(parent_file)
    measured = {
        build.GRID: "1" * 64,
        build.DETECTOR: prior["detector_files_sha256"][build.DETECTOR],
    }
    release = dict(detector_files_sha256=measured)
    effective = {**prior["runtime_files_sha256"], **measured}
    assert build.timing_files_ok(prior, effective, release)
    for name in (
        prior["radial_assembly"]["asset_path"],
        "src/cloud_edge_robot_arm/simulation/mujoco/visual_servo.py",
        "scripts/graduation/g1_dual_pixel_readback.py",
        "scripts/graduation/g1_dual_asset.py",
        "scripts/graduation/dynamic_vision.py",
        "unregistered_file.py",
        build.GRID,
    ):
        assert not build.timing_files_ok(prior, {**effective, name: "f" * 64}, release), name
    missing = copy.copy(effective)
    del missing["scripts/graduation/g1_dual_asset.py"]
    assert not build.timing_files_ok(prior, missing, release)


def test_performance_issuance_consumes_only_preregistered_development_labels():
    assert trials.timing_assignment("train-radial15-timing-01", ["d02"])
    assert trials.timing_assignment("train-radial15-contact-01", ["d01"])
    for label, names in (
        ("train-radial15-timing-01", ["d01"]),
        ("train-radial15-contact-01", ["d02"]),
        ("train-radial15-timing-01", ["d02", "d01"]),
        ("train-radial15-timing-02", ["d02"]),
        ("train-feedback-deadline-01", ["d02"]),
        ("evaluation", ["d02"]),
    ):
        assert not trials.timing_assignment(label, names)


def test_prior_offline_gate_cannot_claim_the_new_timing_release():
    old_release = "b71309ac61e4ce6fb35864f942d42d7ddeda6ab7ec47760655c1409044767624"
    with pytest.raises(ValueError, match="unreleased"):
        build.timing_qualification(Path.cwd(), old_release)


def test_released_semantics_cannot_override_a_failed_recorded_window_budget():
    from scripts.graduation.perception_io import pinned

    budget = pinned(build.TIMING_BUDGET, build.TIMING_BUDGET_SHA)
    semantics = pinned(build.TIMING_RELEASE, build.TIMING_RELEASE_SHA)
    assert (
        semantics["eligible"] and semantics["detector_files_sha256"] == build.TIMING_DETECTOR_FILES
    )
    assert (
        not budget["eligible"] and budget["estimated_p95_ms"] > budget["limits_ms"]["estimated_p95"]
    )
    assert not build.qualified_timing_budget(budget, semantics["detector_files_sha256"])
    with pytest.raises(ValueError, match="same-frame window budget has not qualified"):
        build.timing_qualification(Path.cwd(), build.TIMING_RELEASE_SHA)


def test_issuance_rechecks_live_qualification_and_original_source_bindings(tmp_path, monkeypatch):
    from scripts.graduation.perception_io import write

    parent = (Path(build.PRIVATE) / "builds" / PARENT).resolve()
    if not (parent / "preflight.json").is_file():
        pytest.skip("four frozen diagnostic controls unavailable")
    original = read(parent / "preflight.json")
    prior = read(parent / "runtime-source/runtime-build.json")
    generation = "9" * 64
    gate = dict(replay_release_sha256="8" * 64, paired_budget_sha256="7" * 64)
    lock = {**prior, "radial_timing": gate}
    live = {
        **original,
        "runtime_build_sha256": generation,
        "parent_runtime_build_sha256": PARENT,
        "parent_preflight_sha256": build.TIMING_PARENT_PREFLIGHT,
        "radial_timing": gate,
    }
    root = tmp_path / "builds" / generation
    raw = root / live["full_occlusion_directory"]
    shutil.copytree(parent / raw.name, raw)
    file = root / "preflight.json"
    monkeypatch.setattr(
        build, "verify_timing_build", lambda repo, private, lock: (parent, original)
    )
    write(file, live)
    trials.timing_preflight(Path.cwd(), tmp_path, generation, lock, file, original["registration"])
    for key, bad in (
        ("runtime_build_sha256", PARENT),
        ("parent_preflight_sha256", "f" * 64),
        ("calibration", dict(calibration_version="other")),
        ("radial_assembly", {"offset_mm": 30}),
        ("imported_project_files", {}),
        ("motion_commands", 1),
        ("diagnostic_resets", 3),
        ("radial_timing", {**gate, "paired_budget_sha256": "1" * 64}),
    ):
        file.unlink()
        write(file, {**live, key: bad})
        with pytest.raises(ValueError, match="radial timing qualification"):
            trials.timing_preflight(
                Path.cwd(), tmp_path, generation, lock, file, original["registration"]
            )
    file.unlink()
    write(file, live)
    (raw / "only-8/tested.rgbd.json").write_text("{}")
    with pytest.raises(ValueError, match="changed radial diagnostic packet"):
        trials.timing_preflight(
            Path.cwd(), tmp_path, generation, lock, file, original["registration"]
        )
