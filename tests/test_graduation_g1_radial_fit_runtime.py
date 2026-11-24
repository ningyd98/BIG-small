"""Versioned semantic and timing qualifications on the same physical radial parent."""

from pathlib import Path

import pytest
from scripts.graduation import g1_visibility_runtime as build
from scripts.graduation.perception_io import read


@pytest.fixture
def local_fit_inputs():
    parent = Path(build.PRIVATE) / "builds" / build.TIMING_PARENT
    if not (parent / "preflight.json").is_file():
        pytest.skip("private frozen native sources and calibration packets unavailable")


def test_failed_previous_candidate_and_unregistered_digests_remain_distinct():
    assert build.registered_timing_round(build.TIMING_RELEASE_SHA).directory == build.TIMING_ROUND
    with pytest.raises(ValueError, match="window budget"):
        build.timing_qualification(Path.cwd(), build.TIMING_RELEASE_SHA)
    for digest in ("f" * 64, None, build.TIMING_BUDGET_SHA, build.TIMING_PARENT):
        with pytest.raises(ValueError, match="unreleased"):
            build.registered_timing_round(digest)


def test_fit_source_verifies_original_and_supplementary_versions_without_changing_worktree(
    local_fit_inputs,
):
    plan = read(build.FIT_DIRECTORY / "plan.json")
    build.check_timing_plan(Path.cwd(), build.FIT_ROUND, plan)
    bad_plan = {**plan, "inputs_sha256": dict(plan["inputs_sha256"])}
    bad_plan["inputs_sha256"][build.GRID] = "c" * 64
    with pytest.raises(ValueError, match="changed timing plan input"):
        build.check_timing_plan(Path.cwd(), build.FIT_ROUND, bad_plan)


def test_live_and_allocation_routes_must_use_the_registered_round(monkeypatch):
    fit = build.FIT_ROUND._replace(
        release_sha256="1" * 64, budget_sha256="2" * 64, grid_sha256="3" * 64
    )
    monkeypatch.setattr(build, "FIT_ROUND", fit)
    expected = {
        "timing_plan_sha256": fit.plan_sha256,
        "replay_release_sha256": fit.release_sha256,
        "paired_budget_sha256": fit.budget_sha256,
    }
    assert build.issued_timing_round({"radial_timing": expected}) == fit
    for key, value in (
        ("timing_plan_sha256", build.TIMING_PLAN_SHA),
        ("paired_budget_sha256", build.TIMING_BUDGET_SHA),
        ("replay_release_sha256", build.TIMING_RELEASE_SHA),
    ):
        with pytest.raises(ValueError, match="timing round"):
            build.issued_timing_round({"radial_timing": {**expected, key: value}})
    with pytest.raises(ValueError, match="unreleased"):
        build.issued_timing_round({})


def test_legacy_preflight_routing_keeps_existing_native_parent_and_eligibility_rules():
    from scripts.graduation import g1_visibility_trials as trials

    assert trials.parser().parse_args(["prepare", "--radial-mm", "15"]).radial_timing is None
    assert trials.parser().parse_args(["prepare", "--radial-timing", "a" * 64]).radial_mm == 0
    assert not trials.training_success({})
    assert trials.timing_assignment("train-radial15-timing-01", ["d02"])
    assert trials.timing_assignment("train-radial15-contact-01", ["d01"])


def test_fit_gate_checks_the_new_round_and_rejects_changed_underlying_measurements(
    tmp_path, monkeypatch
):
    from scripts.graduation.perception_io import sha, write

    # The native acquisition/score bytes and algorithm have separate coverage. Exercise
    # the normal gate here using a small signed pair in an isolated software fixture.
    folder = Path("staged-fit")
    root = tmp_path / folder
    root.mkdir()
    write(root / "plan.json", {"fixture": "offline gate"})
    plan_sha = sha(root / "plan.json")
    monkeypatch.setattr(build, "FIT_DIRECTORY", folder)
    monkeypatch.setattr(build, "check_timing_plan", lambda *args: None)
    raw = root / "pixel-timing-samples.public.json.gz"
    raw.write_bytes(b"sealed fixture timing measurements")
    sources = {(folder / raw.name).as_posix(): sha(raw)}
    detectors = {**build.TIMING_DETECTOR_FILES, build.GRID: "c" * 64}
    semantic = {
        **read(build.TIMING_RELEASE),
        "timing_plan_sha256": plan_sha,
        "fit_reuse_plan_sha256": plan_sha,
        "previous_timing_plan_sha256": build.TIMING_PLAN_SHA,
        "previous_software_release_sha256": build.TIMING_RELEASE_SHA,
        "source_switch_control_passed": True,
        "detector_files_sha256": detectors,
        "input_artifacts_sha256": sources,
    }
    budget = {
        **read(build.TIMING_BUDGET),
        "eligible": True,
        "detector_files_sha256": detectors,
        "estimated_p95_ms": 79.9,
        "samples_sha256": sha(raw),
        "input_artifacts_sha256": sources,
        "fit_reuse_plan_sha256": plan_sha,
        "prior_failed_budget_sha256": build.TIMING_BUDGET_SHA,
        "sample_group_counts": {"cycle": 615, "neighbors": 60, "cold": 5},
    }
    release_file = root / "replay-release.public.json"
    budget_file = root / "paired-budget.public.json"
    write(release_file, semantic)
    write(budget_file, budget)
    fit = build.TimingRound(
        folder, plan_sha, sha(release_file), sha(budget_file), detectors[build.GRID]
    )
    monkeypatch.setattr(build, "FIT_ROUND", fit)
    qualified = build.timing_qualification(tmp_path, fit.release_sha256)
    assert build.issued_timing_round({"radial_timing": qualified}) == fit
    assert qualified["detector_files_sha256"] == detectors
    raw.write_bytes(b"changed fixture timing measurements")
    with pytest.raises(ValueError, match="changed or foreign timing evidence"):
        build.timing_qualification(tmp_path, fit.release_sha256)


def test_four_placement_issue_uses_both_blind_scores_from_the_qualified_generation(tmp_path):
    from scripts.graduation import g1_visibility_trials as trials
    from scripts.graduation.perception_io import sha, write

    case = dict(
        evidence_status="SCORED",
        verified_posts=8,
        dispatched=8,
        online_success=True,
        physical_success=True,
        joint_success=True,
        both_windows_qualified=True,
        registered_windows={k: {"qualified": True} for k in ("lift", "release")},
        independent_physical_outcome=dict(
            success=True,
            safety_assessment="SCOPED_NO_VIOLATION",
            measured_lift_m=0.05,
            hold_s=0.5,
            placed_stable_s=1.0,
        ),
        contacts={"bilateral_cube_steps": 1},
        hand_contacts={"board_or_support_hand_or_finger_steps": []},
    )
    directory = trials.batch_path(tmp_path, "train-radial15-timing-01")
    files = {
        "allocation.json": {},
        "acquisition.json": {},
        "scoring/pixels/index.json": {},
        "scoring/blind-one/seal.json": {"input": "fixture"},
        "scoring/blind-two/seal.json": {"input": "fixture"},
        "scoring/score-one.json": {"cases": [case]},
        "scoring/score-two.json": {"cases": [case]},
    }
    for name, payload in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        write(path, payload)
    generation = "9" * 64
    score = dict(
        schema="g1.visibility.development-score.v1",
        scope="training",
        runtime_build_sha256=generation,
        plan_sha256=build.PLAN_SHA,
        cases=[case],
        allocation_sha256=sha(directory / "allocation.json"),
        acquisition_sha256=sha(directory / "acquisition.json"),
        pixel_index_sha256=sha(directory / "scoring/pixels/index.json"),
        blind_seals_sha256=[
            sha(directory / f"scoring/blind-{n}/seal.json") for n in ("one", "two")
        ],
        score_passes_sha256=[sha(directory / f"scoring/score-{n}.json") for n in ("one", "two")],
    )
    report = directory / "score.json"
    write(report, score)
    assert trials.check_training_score(tmp_path, generation, report, sha(report)) == score
    placements = [
        dict(id=f"e{n:02}", seed=n, reset_fixture_center_m=[0.45 + 0.0001 * n, 0, 0.035], yaw_rad=0)
        for n in range(1, 5)
    ]
    assert trials.checked_placements(placements, "evaluation") == placements
    with pytest.raises(ValueError, match="independently successful"):
        trials.check_training_score(tmp_path, "8" * 64, report, sha(report))
    with pytest.raises(ValueError, match="four prospectively ordered"):
        trials.checked_placements(placements[:3], "evaluation")
    (directory / "scoring/score-two.json").write_text("{}")
    with pytest.raises(ValueError, match="two matching independent reads"):
        trials.check_training_score(tmp_path, generation, report, sha(report))


def test_published_final_release_opens_only_its_frozen_overlay(local_fit_inputs):
    from scripts.graduation.perception_io import sha

    gate = build.FIT_ROUND.release_sha256
    evidence = build.timing_qualification(Path.cwd(), gate)
    assert build.issued_timing_round({"radial_timing": evidence}) == build.FIT_ROUND
    assert evidence["detector_files_sha256"][build.GRID] == sha(Path(build.GRID))
    assert evidence["baseline_preflight_sha256"] == build.TIMING_PARENT_PREFLIGHT
    assert evidence["paired_budget_sha256"] != build.TIMING_BUDGET_SHA
    with pytest.raises(ValueError, match="unreleased"):
        build.timing_qualification(Path.cwd(), build.FIT_ROUND.budget_sha256)
