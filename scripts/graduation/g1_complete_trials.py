"""Prospective development allocation for native closed-loop RGB-D pick and place."""

import argparse
import re
import runpy
from datetime import UTC, datetime
from pathlib import Path

from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

ROUNDS = Path("artifacts/research/process/20261004-ced-development/astra-rounds")
ROUND = ROUNDS / "round-g1-complete-cv-repair-20261125"
PLAN_SHA = "4f84f847bc86f68d474d4f81feb0083f6f9e2e9ee93d49e4d5c5509600cc824b"
OLD = Path("experiments/results/g1-visibility-pose-repair-20261124")
PRIVATE = Path("experiments/results/g1-complete-cv-repair-20261125")
PARENT = "5c09e38b82e09a8c52de407bee97775aca8b8a48b4d14a3bfc387ffd626fa212"
PREVIOUS = ROUNDS / "round-g1-cv-grasp-validation-20261125"
TEMPLATE = OLD / "batches/train-radial30-contact-d02-02/d02/allocation.json"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def write_once(path, record):
    if path.exists():
        require(read(path) == record, f"existing registration differs at {path}")
    else:
        write(path, record)


def select_slots(registration, label):
    if label == "evaluation":
        scope = "independent_development"
    else:
        require(re.fullmatch(r"train-[a-z0-9-]+", label), "unregistered development batch")
        scope = "training"
    rows = [row for row in registration["slots"] if row["scope"] == scope]
    require(len(rows) == len({r["id"] for r in rows}) == 2, "two unique ordered slots required")
    return rows


def register(repo):
    from scripts.graduation.g1_visibility_selection import history_documents

    plan = pinned(repo / ROUND / "plan.json", PLAN_SHA)
    for path, expected in plan["input_sha256"].items():
        require(sha(repo / path) == expected, f"changed Astra input {path}")
    require(sha(repo / ROUND / "plan.md") == plan["plan_md_sha256"], "changed plan text")
    rows = plan["registration"]["slots"]
    historical = sorted((repo / OLD / "batches").glob("train-*/d*/allocation.json"))
    ensure_new = runpy.run_path(str(repo / PREVIOUS / "prospective.py"))["ensure_new_placements"]
    prior = read(repo / PREVIOUS / "prospective-registration.public.json")
    ensure_new(rows, [*history_documents(), prior["slots"], *(read(p)["case"] for p in historical)])
    registration = dict(
        schema="g1.development.native-complete-registration.v1",
        **plan["registration"],
        acceptance=plan["acceptance"],
        plan_sha256=PLAN_SHA,
        baseline=plan["baseline_commit"],
        parent_generation=PARENT,
        historical_training=len(historical),
        previous_prospective_sha256=sha(repo / PREVIOUS / "prospective-registration.public.json"),
        sealed_old_blind_slots=(
            "unopened; separately named and seeded; no cross-blind collision service"
        ),
        hardware_actions=0,
        formal_claims=0,
    )
    private = repo / PRIVATE
    private.mkdir(parents=True, exist_ok=True)
    write_once(private / "registration.json", registration)
    write_once(repo / ROUND / "development-registration.public.json", registration)
    return sha(private / "registration.json")


def training_gate(records, generation, calibration):
    from scripts.graduation.g1_visibility_trials import training_success

    require(len(records) == 2, "both registered training slots need independent scores")
    require(len({item.get("id") for item in records}) == 2, "duplicate training slot")
    for item in records:
        result = item.get("result", {})
        physical = result.get("independent_physical_outcome", {})
        require(
            item.get("runtime_build_sha256") == generation
            and item.get("calibration_sha256") == calibration
            and re.fullmatch("[a-f0-9]{64}", item.get("receipt_sha256") or "")
            and result.get("evidence_status") == "SCORED"
            and physical.get("safety_violation") is False
            and result.get("hand_contacts", {}).get("board_or_support_hand_or_finger_steps") == []
            and item.get("qualified")
            is (training_success(result) and item.get("complete_feedback_ok") is True),
            "training evidence is incomplete, inconsistent or has an unresolved safety event",
        )
    require(
        any(item["qualified"] for item in records),
        "no complete independently qualified training case",
    )


def read_sealed_score(path, expected=None):
    score = pinned(path, expected) if expected else read(path)
    case_dir = path.parent
    reads = score["independent_reads"]
    require(
        score["id"] == case_dir.name
        and score["receipt_sha256"] == sha(case_dir / "instance" / "receipt.json")
        and score["attempt_sha256"] == sha(case_dir / "attempt.json")
        and score["allocation_sha256"] == sha(case_dir / "allocation.json")
        and score["batch_sha256"] == sha(case_dir.parent / "allocation.json")
        and len(reads) == 2
        and reads[0]["area"] != reads[1]["area"]
        and reads[0]["pid"] != reads[1]["pid"]
        and reads[0]["result_sha256"] == reads[1]["result_sha256"]
        and all(
            (case_dir / r["area"]).resolve().is_relative_to(case_dir.resolve())
            and sha(case_dir / r["area"] / "result.json") == r["result_sha256"]
            and sha(case_dir / r["area"] / "process.json") == r["process_sha256"]
            for r in reads
        ),
        "independent result does not match its original acquisition or cold read",
    )
    require(
        read(case_dir / reads[0]["area"] / "result.json")
        == {k: v for k, v in score.items() if k != "independent_reads"},
        "published score differs from both native cold reads",
    )
    return score


def issue(repo, generation, label, calibration_path, calibration, training_label=None):
    from scripts.graduation import dynamic_vision as native
    from scripts.graduation import g1_dual_asset as asset
    from scripts.graduation.g1_formal_trials import identities

    from cloud_edge_robot_arm.research.native_calibration_collection import digest as product_digest

    private = repo / PRIVATE
    lock = pinned(ROOT / "runtime-build.json", generation)
    require(ROOT == private / "builds" / generation / "runtime-source", "wrong isolated runtime")
    registration = pinned(
        private / "registration.json", sha(repo / ROUND / "development-registration.public.json")
    )
    require(registration["plan_sha256"] == lock["plan_sha256"] == PLAN_SHA, "plan binding differs")
    calibration_path = calibration_path.resolve()
    pinned(calibration_path / "manifest.json", calibration)
    rows = select_slots(registration, label)
    directory = private / "batches" / label
    training_scores = {}
    if label == "evaluation":
        require(
            isinstance(training_label, str) and training_label.startswith("train-"),
            "missing training batch",
        )
        matched = select_slots(registration, training_label)
        sources = [
            private / "batches" / training_label / r["id"] / "independent-score.json"
            for r in matched
        ]
        training_gate([read_sealed_score(p) for p in sources], generation, calibration)
        training_scores = {p.relative_to(private).as_posix(): sha(p) for p in sources}
    directory.mkdir(parents=True, exist_ok=False)
    prior = read(repo / TEMPLATE)
    geometry = asset.geometry_descriptor()
    paths = set(prior["sources_sha256"]) | set(
        geometry["development_dual"]["development_sources_sha256"]
    )
    paths.update(name for name in lock["runtime_files_sha256"] if name.startswith("scripts/"))
    paths.add(asset.ASSET_PATH)
    full = {name: lock["runtime_files_sha256"][name] for name in sorted(paths)}
    require(all(sha(ROOT / name) == h for name, h in full.items()), "runtime inventory drift")
    inventory = directory / "source-inventory.json"
    write(inventory, full)
    catalog = dict(
        private_filename=inventory.name,
        archived_json_sha256=sha(inventory),
        product_compact_sorted_utf8_sha256=product_digest(full),
        count=len(full),
    )
    release = registration["batch"] + "-" + label
    scope = "evaluation" if label == "evaluation" else "training"
    cases = []
    common = dict(
        plan_sha256=PLAN_SHA,
        runtime_build_sha256=generation,
        calibration_sha256=calibration,
        calibration_directory=str(calibration_path),
        scope=scope,
        catalog=catalog,
    )
    for slot, placement in enumerate(rows, 1):
        row = {k: v for k, v in placement.items() if k != "scope"}
        visual = release + "/" + row["id"]
        row.update(
            group=row["id"],
            slot=slot,
            visual_id=visual,
            arm="dual",
            view="nominal",
            **identities(visual),
            family=asset.FAMILY,
            asset_path=asset.ASSET_PATH,
            asset_sha256=asset.ASSET_SHA,
            physical_object_mass_kg=asset.BODY_MASS_KG,
        )
        case = dict(prior["case"], **row)
        case.update(
            visual_seed=row["seed"],
            release=release,
            private_output=row["id"] + "/instance",
            claim_scope=scope,
            attempts=1,
        )
        allocation = dict(prior)
        allocation.update(
            **common,
            schema="g1.development.native-complete-case.v1",
            baseline=registration["baseline"],
            case=case,
            geometry=geometry,
            sources_sha256=full,
            asset_sha256=asset.ASSET_SHA,
            component_catalog_sha256=native.digest(full),
            method_template_sha256=sha(repo / TEMPLATE),
        )
        casefile = directory / row["id"] / "allocation.json"
        casefile.parent.mkdir()
        write(casefile, allocation)
        cases.append(
            dict(
                row,
                allocation_file=casefile.relative_to(directory).as_posix(),
                allocation_sha256=sha(casefile),
            )
        )
    batch = dict(
        **common,
        schema="g1.development.native-complete-batch.v1",
        label=label,
        release=release,
        cases=cases,
        attempts_per_slot=1,
        hardware_actions=0,
        formal_claims=0,
        registration_sha256=sha(private / "registration.json"),
        training_scores_sha256=training_scores,
        scorer_files_sha256=lock["scorer_files_sha256"],
        issued_at=datetime.now(UTC).isoformat(),
    )
    write(directory / "allocation.json", batch)
    return sha(directory / "allocation.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["register", "issue"])
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--generation")
    parser.add_argument("--label")
    parser.add_argument("--calibration-directory", type=Path)
    parser.add_argument("--calibration-sha")
    parser.add_argument("--training-label")
    args = parser.parse_args()
    if args.mode == "register":
        print(register(args.repo.resolve()))
    else:
        print(
            issue(
                args.repo.resolve(),
                args.generation,
                args.label,
                args.calibration_directory,
                args.calibration_sha,
                args.training_label,
            )
        )


if __name__ == "__main__":
    main()
