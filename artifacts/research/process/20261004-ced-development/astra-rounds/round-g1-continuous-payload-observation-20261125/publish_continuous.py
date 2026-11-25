"""Bind the frozen print-observer experiment to raw receipts and independent labels."""

from collections import Counter
from pathlib import Path

from scripts.graduation.g1_complete_trials import write_once
from scripts.graduation.perception_io import ROOT, pinned, read, sha

HERE = Path(__file__).resolve().parent
RAW = ROOT / "experiments/results/g1-continuous-payload-observation-20261125"
OLD = ROOT / "experiments/results/g1-complete-cv-repair-20261125"
RUN = "3f6e2706bfa488c9ca57e156385e70892adab9a44729f78fc34e58361b88d0da"


def verify_one(id_, freeze, catalog):
    source = RAW / "physical-03" / id_
    prediction = RAW / (id_ + "-prediction-02.json")
    score = RAW / (id_ + "-score-02.json")
    observed = read(prediction)
    result = read(score)
    assert observed["id"] == result["id"] == id_ and observed["print_runtime_sha256"] == RUN
    frozen = freeze["sources_sha256"]
    assert (
        observed["observer_sha256"]
        == frozen["scripts/graduation/g1_complete_cv_payload_observation.py"]
    )
    assert (
        observed["current_profile_sha256"]
        == frozen["scripts/graduation/g1_complete_cv_relation_profile.json"]
    )
    assert (
        observed["physics_labels_read"] is False
        and sha(prediction) == result["source_prediction_sha256"]
    )
    for name, token in observed["source_sha256"].items():
        path = source / name
        assert sha(path) == token
    receipt_path = source / "sensor-receipt.json"
    receipt = pinned(receipt_path, observed["source_sha256"][receipt_path.name])
    physical = source / "offline-physics.json"
    assert sha(physical) == result["raw_physics_sha256"]
    for entry in (prediction, score, physical, receipt_path, source / "rgbd-index.json"):
        catalog[entry.relative_to(ROOT).as_posix()] = sha(entry)
    draft = result["exposure_answers"]
    pose = Counter(z["measured_pose"] for z in draft)
    states = result["stage_by_stage"]
    lift = states.get("LIFT", {})
    motion = states.get("MOVE_TO_REGION", {})
    return dict(
        id=id_,
        prospective_role=receipt["role"],
        rgbd=len(draft),
        poses=dict(pose),
        native_successful_returns=result["original_controller_posts"],
        stop=receipt["actions"][-1]["error"],
        total_physics=receipt["actions"][-1]["return_step"],
        bench_capture_and_ik_ms_max=result["max_capture_and_native_ik_ms"],
        observer_only_ms_max=max((z["rgbd_ms"] for z in draft), default=None),
        load_lift_frames=lift.get("receipts", 0),
        lift_held=lift.get("observed", {}).get("held", 0),
        move_frames=motion.get("receipts", 0),
        move_held=motion.get("observed", {}).get("held", 0),
        separated_supported=sum(
            v["observed"].get("supported_and_separated", 0) for v in states.values()
        ),
        missed_pose=[
            dict(
                step=z["step"],
                phase=z["phase"],
                skill=z["skill"],
                method=z["method"],
                frame_id=z["frame_id"],
                relation=z["relation"],
            )
            for z in draft
            if z["measured_pose"] == "outside"
        ],
        false_relation=result["anomalies"],
        forbidden_physical_steps=result["forbidden_steps"],
    )


def preflights(catalog):
    raw = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds"
    summary = raw / "round-g1-complete-cv-repair-20261125/train-preflight-05.public.json"
    pre = read(summary)
    assert pre["runtime_build_sha256"] == RUN
    assert len(pre["cases"]) == 2
    out = []
    for row in pre["cases"]:
        slot = OLD / "batches/train-preflight-05" / row["id"] / "independent-score.json"
        score = read(slot)
        assert row["stop"]["reason"] == "DEVELOPMENT_PREFLIGHT_PASSED_BEFORE_FIRST_DISPATCH"
        assert score["result"]["dispatched"] == 0 and not score["qualified"]
        a, b = score["independent_reads"]
        assert a["pid"] != b["pid"] and a["result_sha256"] == b["result_sha256"]
        out.append(
            dict(
                id=row["id"],
                stopped_before_dispatch=True,
                receipt_sha256=row["receipt_sha256"],
                independent_score_sha256=sha(slot),
            )
        )
    catalog[summary.relative_to(ROOT).as_posix()] = sha(summary)
    return out


def main():
    freeze_path = HERE / "observer-freeze.public.json"
    freeze = read(freeze_path)
    assert freeze["runtime"] == RUN and freeze["no_integrated_dispatch_authorization"] is True
    catalog = {freeze_path.relative_to(ROOT).as_posix(): sha(freeze_path)}
    fit = [verify_one(f"dense-fit-0{i}", freeze, catalog) for i in range(1, 4)]
    holdout = [verify_one(f"dense-check-0{i}", freeze, catalog) for i in range(1, 5)]
    negatives = [verify_one(f"dense-negative-0{i}", freeze, catalog) for i in (1, 2, 4)]
    result = dict(
        scope="original-controller development bench and shadow observer, no action authorization",
        runtime=RUN,
        qualification=False,
        preflight=preflights(catalog),
        open_pose_bound_failures=sum(len(r["missed_pose"]) for r in holdout),
        blocked_runtime_feature="single_id8_red_print",
        heldout_lift_frames=sum(r["load_lift_frames"] for r in holdout),
        heldout_lift_held=sum(r["lift_held"] for r in holdout),
        fit=fit,
        holdout=holdout,
        negative_companions=negatives,
        sources_sha256=catalog,
        formal=0,
        hardware=0,
        heldout_integrated_slots=0,
    )
    output = HERE / "continuous-observation.public.json"
    write_once(output, result)
    print(
        result["heldout_lift_held"],
        result["heldout_lift_frames"],
        result["open_pose_bound_failures"],
        sha(output),
    )


if __name__ == "__main__":
    main()
