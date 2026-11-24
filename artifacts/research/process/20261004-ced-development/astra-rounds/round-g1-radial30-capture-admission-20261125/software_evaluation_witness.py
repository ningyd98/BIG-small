"""Test d01 and evaluation admission with marked, ephemeral synthetic histories and placements."""

import contextlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts.graduation import g1_dual_trials as dual
from scripts.graduation import g1_visibility_radial_contact as contact
from scripts.graduation import g1_visibility_runtime as build
from scripts.graduation import g1_visibility_trials as trials
from scripts.graduation.perception_io import ROOT, sha, write
from software_capture_witness import Boundary, cli, replace


def simulated_score(folder, group, generation, *, reached=1500, success=True, safe=True):
    marker = {"fixture_only": True}
    row = dict(
        id=group,
        acquired=True,
        evidence_status="SCORED",
        physics_steps=reached,
        stop={"kind": "COMPONENT_SEQUENCE_RETURNED"},
        safe_stop_succeeded=None,
        phases={"APPROACH": {"status": "PASS" if success else "FAIL", "end_step": reached}},
        verified_posts=8 if success else 1,
        dispatched=8 if success else 2,
        online_success=success,
        physical_success=success,
        joint_success=success,
        both_windows_qualified=success,
        registered_windows={"lift": {"qualified": success}, "release": {"qualified": success}},
        independent_physical_outcome=dict(
            success=success,
            safety_assessment="SCOPED_NO_VIOLATION" if safe else "VIOLATION",
            safety_violation=not safe,
            measured_lift_m=0.051,
            hold_s=0.51,
            placed_stable_s=1.01,
        ),
        contacts={"bilateral_cube_steps": 30 if success else 0},
        hand_contacts={"board_or_support_hand_or_finger_steps": [] if safe else [1221]},
        **marker,
    )
    for name, obj in {
        "acquisition.json": marker,
        "scoring/pixels/index.json": marker,
        "scoring/blind-one/seal.json": marker,
        "scoring/blind-two/seal.json": marker,
        "scoring/score-one.json": {"cases": [row], **marker},
        "scoring/score-two.json": {"cases": [row], **marker},
    }.items():
        file = folder / name
        file.parent.mkdir(parents=True, exist_ok=True)
        replace(file, obj)
    score = dict(
        schema="g1.visibility.development-score.v1",
        scope="training",
        plan_sha256=build.PLAN_SHA,
        runtime_build_sha256=generation,
        cases=[row],
        allocation_sha256=sha(folder / "allocation.json"),
        acquisition_sha256=sha(folder / "acquisition.json"),
        pixel_index_sha256=sha(folder / "scoring/pixels/index.json"),
        blind_seals_sha256=[sha(folder / f"scoring/blind-{n}/seal.json") for n in ("one", "two")],
        score_passes_sha256=[sha(folder / f"scoring/score-{n}.json") for n in ("one", "two")],
        **marker,
    )
    path = folder / "score.json"
    replace(path, score)
    return path


def witness(repo, generation, scratch):
    assert (
        (repo / build.PRIVATE / "builds" / generation / "runtime-source").resolve()
        == ROOT
        == Path.cwd()
    )
    real_batch, real_device = trials.batch_path, trials.device
    options = ["--gate", str(repo / contact.SCREEN), "--gate-sha", contact.SCREEN_SHA]
    events, checks = [], {}

    @contextlib.contextmanager
    def device(_):
        with real_device(scratch):
            yield

    def stop_before_native(_plan, folder, digest, case_id, **kwargs):
        assert folder.is_relative_to(scratch) and callable(kwargs["before_start"])
        events.append(case_id)
        raise Boundary("synthetic admission reached native boundary")

    def refused(name, fn, expected):
        try:
            fn()
        except (ValueError, FileNotFoundError) as e:
            assert expected in str(e), (name, str(e))
            checks[name] = True
        else:
            raise AssertionError(name)

    with (
        patch.object(trials, "batch_path", lambda _, name: real_batch(scratch, name)),
        patch.object(trials, "device", device),
        patch.object(dual.g1_mount_trials, "capture", stop_before_native),
    ):
        label1 = "train-radial30-contact-d01-01"
        label2 = contact.REPLACEMENT
        h = cli(repo, "issue-training", generation, label2, "d02", *options)
        d02, d01 = real_batch(scratch, label2), real_batch(scratch, label1)
        assert sha(d02 / "allocation.json") == h

        def issue1():
            return cli(repo, "issue-training", generation, label1, "d01", *options)

        simulated_score(d02, "d02", contact.PARENT)
        refused("other_generation_d02_score", issue1, "prior d02")
        simulated_score(d02, "d02", generation, safe=False)
        refused("unsafe_d02_prevents_d01", issue1, "safety")
        score = simulated_score(d02, "d02", generation)
        h1 = issue1()
        try:
            cli(repo, "capture", generation, label1, h1, "d01")
        except Boundary:
            checks["d01_after_qualified_synthetic_d02"] = True
        else:
            raise AssertionError("d01 was not admitted to the test boundary")
        placements = [
            dict(
                id=f"e{n:02}",
                seed=180 + n,
                reset_fixture_center_m=[0.4 + n / 1000, 0.02, 0.035],
                yaw_rad=0.1 * n,
            )
            for n in range(1, 5)
        ]
        selection = scratch / "fixture-only-selection.json"

        def issue_eval():
            replace(
                selection,
                dict(
                    schema="g1.visibility.evaluation-selection.v1",
                    runtime_build_sha256=generation,
                    sampling_rule_sha256="b" * 64,
                    training_score_sha256=sha(score),
                    placements=placements,
                    fixture_only=True,
                ),
            )
            return cli(
                repo,
                "issue-evaluation",
                generation,
                str(selection),
                sha(selection),
                str(score),
                *options,
            )

        simulated_score(d01, "d01", generation, reached=1119, success=False)
        refused("d01_hazard_interval_unreached", issue_eval, "hazard intervals")
        simulated_score(d01, "d01", generation, reached=1120, success=False)
        simulated_score(d02, "d02", generation, reached=1220, success=False)
        refused("d02_hazard_interval_unreached", issue_eval, "hazard intervals")
        simulated_score(d02, "d02", generation, reached=1221, success=False)
        refused("no_complete_training_success", issue_eval, "independently successful")
        simulated_score(d02, "d02", generation)
        he = issue_eval()
        try:
            cli(repo, "capture", generation, "evaluation", he, "e01")
        except Boundary:
            checks["four_fixture_placements_admitted"] = True
        else:
            raise AssertionError("evaluation did not reach its software boundary")
        assert (
            events == ["d01", "e01"]
            and not list(scratch.rglob("attempt.json"))
            and not list(scratch.rglob("instance"))
        )
    return dict(
        schema="g1.visibility.radial30.synthetic-evaluation-boundary.v1",
        fixture_only=True,
        generation=generation,
        preflight_sha256=sha(ROOT.parent / "preflight.json"),
        checks=checks,
        synthetic_held_out_placements=4,
        synthetic_capture_boundary_calls=events,
        real_new_slots=0,
        real_history_issuance=0,
        physics_steps=0,
        worker_runs=0,
        attempts=0,
    )


if __name__ == "__main__":
    repo, generation, output = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    with tempfile.TemporaryDirectory(prefix="g1-synthetic-evaluation-") as tmp:
        result = witness(repo, generation, Path(tmp))
    assert not output.exists()
    write(output, result)
    print(len(result["checks"]), sha(output))
