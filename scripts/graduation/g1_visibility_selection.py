"""Commit a placement sampler, then open it after independent training qualification."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import random
import secrets
from pathlib import Path

from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig

FORMAL = Path(
    "artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-formal-paired-20261124"
)
HISTORY = FORMAL / "placement-overlap.public.json"
ALLOCATION = FORMAL / "trial-allocation.public.json"
HISTORY_SHA = "f4b63cc8c7946a0adfd007370f1d946cf878c075a33d11d8f452122025b147ea"
ALLOCATION_SHA = "5888fad03b9e2572d58dce0c60ae07ef17783276fa9148c221231003ea1aa7b4"
SCORE_SCHEMA = "g1.visibility.development-score.v1"
QUADRANTS = ((-1, -1), (-1, 1), (1, -1), (1, 1))


def rule(secret):
    return {
        "schema": "g1.visibility.sampling-rule.v1",
        "scope": "DEVELOPMENT",
        "seed_commitment_sha256": hashlib.sha256(secret).hexdigest(),
        "sampler_sha256": sha(Path(__file__)),
        "placement_history_sha256": {str(HISTORY): HISTORY_SHA, str(ALLOCATION): ALLOCATION_SHA},
        "domain_source": "scripts/graduation/proposal_closed_loop.py",
        "domain_source_sha256": sha(ROOT / "scripts/graduation/proposal_closed_loop.py"),
        "nominal_center_m": [0.45, 0.0, 0.035],
        "signs_xy_in_slot_order": [list(pair) for pair in QUADRANTS],
        "integer_micrometre_offsets": {"abs_x": [1, 15000], "abs_y": [1, 20000]},
        "integer_microradian_yaw": [-120000, 120000],
        "seed_range_inclusive": [1, 2147483647],
        "draw": "Per slot ASCII ID and collision counter separated by slash, HMAC-SHA256, "
        "Python Random(bytes) draws x, y, yaw, scene seed in order. Retry only exact "
        "XYZ/seed overlap with a historical placement or an earlier allocated slot.",
        "trials_per_slot": 1,
    }


def register_rule(secret_file, output):
    if output.exists():
        raise FileExistsError(output)
    secret = secrets.token_bytes(32)
    with os.fdopen(
        os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
    ) as stream:
        stream.write(secret)
    write(output, rule(secret))


def history_documents():
    history = pinned(ROOT / HISTORY, HISTORY_SHA)
    for path, record in sorted(history["sources"].items()):
        source = pinned(ROOT / path, record["sha256"])
        yield source
        if path.endswith("/round-v10-phase5-20261122/registration/protocol.json"):
            for row in source["assignments"]:
                sample = PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=row["seed"])
                pose = sample.object_pose
                yield [pose.x, pose.y, pose.z]
    yield pinned(ROOT / ALLOCATION, ALLOCATION_SHA)


def draw(secret, documents, additional_seeds):
    centers, seeds = set(), set(additional_seeds)

    def index(value):
        if isinstance(value, dict):
            for child in value.values():
                index(child)
        elif isinstance(value, list):
            if len(value) in (3, 4) and all(type(x) in (int, float) for x in value):
                centers.add(tuple(value[:3]))
            for child in value:
                index(child)
        elif type(value) is int:
            seeds.add(value)

    for document in documents:
        index(document)
    slots = []
    for number, (xsign, ysign) in enumerate(QUADRANTS, 1):
        slot = f"e{number:02d}"
        collision = 0
        while True:
            stream = hmac.digest(secret, f"{slot}/{collision}".encode("ascii"), "sha256")
            rng = random.Random(stream)
            center = (
                (450000 + xsign * rng.randint(1, 15000)) / 1000000,
                ysign * rng.randint(1, 20000) / 1000000,
                0.035,
            )
            yaw = rng.randint(-120000, 120000) / 1000000
            seed = rng.randint(1, 2147483647)
            if center not in centers and seed not in seeds:
                break
            collision += 1
        centers.add(center)
        seeds.add(seed)
        slots.append(dict(id=slot, seed=seed, reset_fixture_center_m=list(center), yaw_rad=yaw))
    return slots


def qualified(case):
    if case.get("evidence_status") != "SCORED":
        return False
    outcome = case["independent_physical_outcome"]
    windows = case["registered_windows"]
    return (
        case["dispatched"] == case["verified_posts"] == 8
        and all(
            case[key] is True
            for key in (
                "online_success",
                "physical_success",
                "joint_success",
                "both_windows_qualified",
            )
        )
        and all(
            windows[name]["qualified"] is True and windows[name]["actual_samples"] == n
            for name, n in (("lift", 121), ("release", 241))
        )
        and outcome["success"] is True
        and outcome["safety_assessment"] == "SCOPED_NO_VIOLATION"
        and outcome["measured_lift_m"] >= 0.05
        and outcome["hold_s"] >= 0.5
        and outcome["placed_stable_s"] >= 1.0
        and case["contacts"]["bilateral_cube_steps"] > 0
        and case["hand_contacts"]["board_or_support_hand_or_finger_steps"] == []
    )


def select(secret_file, rule_file, build, training_score, output):
    if output.exists():
        raise FileExistsError(output)
    secret = secret_file.read_bytes()
    if len(secret) != 32 or read(rule_file) != rule(secret):
        raise ValueError("selection seed, historical pins or sampler differ from registration")
    score = read(training_score)
    if (
        score["schema"] != SCORE_SCHEMA
        or score["scope"] != "training"
        or score["runtime_build_sha256"] != sha(build)
        or not any(qualified(c) for c in score["cases"])
    ):
        raise ValueError("training success with this frozen runtime is required")
    for key in ("blind_seals_sha256", "score_passes_sha256"):
        passes = score[key]
        if len(passes) != 2 or passes[0] != passes[1] or len(bytes.fromhex(passes[0])) != 32:
            raise ValueError("training verification passes disagree")
    write(
        output,
        {
            "schema": "g1.visibility.evaluation-selection.v1",
            "runtime_build_sha256": sha(build),
            "training_score_sha256": sha(training_score),
            "sampling_rule_sha256": sha(rule_file),
            "seed_opening_hex": secret.hex(),
            "placements": draw(secret, history_documents(), set()),
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="phase", required=True)
    for name, params in (
        ("commit", ["secret", "rule"]),
        ("select", ["secret", "rule", "build", "training_score", "output"]),
    ):
        command = commands.add_parser(name)
        for param in params:
            command.add_argument(param, type=Path)
    args = parser.parse_args()
    if args.phase == "commit":
        register_rule(args.secret, args.rule)
    else:
        select(args.secret, args.rule, args.build, args.training_score, args.output)
