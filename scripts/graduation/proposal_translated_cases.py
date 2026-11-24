"""Run the preregistered translated-camera held-out pairs after both qualification gates."""

from __future__ import annotations

import argparse
import math
import os
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from scripts.graduation import dynamic_vision as runtime
from scripts.graduation import dynamic_vision_score, guarded_clock, proposal_scoring
from scripts.graduation.perception_io import ROOT, check_sources, pinned, read, sha, write
from scripts.graduation.proposal_closed_loop import readback_reset
from scripts.graduation.proposal_translated import POSITION, check_view, slots

from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

RELEASE = "proposal-development-translated-20261124"
SOURCES = (
    "scripts/graduation/proposal_translated.py",
    "scripts/graduation/proposal_translated_cases.py",
    "scripts/graduation/proposal_closed_loop.py",
    "scripts/graduation/proposal_scoring.py",
    "scripts/graduation/dynamic_physics.py",
    "scripts/graduation/dynamic_vision_score.py",
    "scripts/graduation/guarded_clock_score.py",
    "tests/test_graduation_proposal_translated.py",
)


def issue(raw, qualified, qsha, b_manifest, bsha, prior_raw, public):
    interval_plan_path = (
        qualified.parent.parent / "round-proposal-paired-small-sample-20261124" / "plan.json"
    )
    interval_sha = "81627e0c00b5996dd16c441330dcd833d39c05b5f7b7bfe8ea38cb1cb4258654"
    interval_plan = pinned(interval_plan_path, interval_sha)
    if sha(interval_plan_path.with_suffix(".md")) != interval_plan["plan_md_sha256"]:
        raise ValueError("changed interval plan")
    check_sources({"sources_sha256": interval_plan["input_sha256"]})
    decision = pinned(qualified, qsha)
    if (
        decision["eligible"] is not True
        or decision["failure_reasons"]
        or decision["selected_view"] != "translated"
        or not all(v["real_zero_step_tracker"] for v in decision["views"].values())
    ):
        raise ValueError("both translated-camera qualifications are required")
    qa = pinned(raw / "qualification-allocation.json", decision["allocation_sha256"])
    if (
        qa["slots"] != slots()
        or sha(raw / "decision-seal.json") != decision["decision_seal_sha256"]
    ):
        raise ValueError("qualification and issue slots or pixel seal differ")
    old = pinned(b_manifest, bsha)
    if sha(prior_raw / "allocation.public.json") != bsha or old["selected_view"] != "nominal":
        raise ValueError("wrong baseline guarded allocation")
    old_case = old["cases"][0]
    template = pinned(prior_raw / old_case["allocation_file"], old_case["allocation_sha256"])
    if template["asset_sha256"] != qa["asset_sha256"] or template["baseline"] != qa["baseline"]:
        raise ValueError("source template or asset mismatch")
    if any(
        row["reset_fixture_center_m"]
        in [previous["reset_fixture_center_m"] for previous in old["cases"]]
        for row in slots()
    ):
        raise ValueError("translated and previous held-out placements overlap")
    check_sources({"sources_sha256": qa["sources_sha256"]})
    source_hashes = {**template["sources_sha256"], **{f: sha(ROOT / f) for f in SOURCES}}
    check_sources({"sources_sha256": source_hashes})
    catalog = runtime.inventory()
    if (
        os.environ.get("MUJOCO_GL") != "egl"
        or runtime.digest(catalog) != template["component_catalog_sha256"]
    ):
        raise ValueError("EGL or frozen product catalog mismatch")
    if shutil.disk_usage(raw).free < len(slots()) * 2**31:
        raise ValueError("insufficient headroom for paired evidence")
    dest = raw / "episodes"
    dest.mkdir()
    archive = runtime.bind_catalog(dest, catalog, qa["geometry"]["asset_path"])
    if (
        archive["product_compact_sorted_utf8_sha256"]
        != template["catalog"]["product_compact_sorted_utf8_sha256"]
    ):
        raise ValueError("frozen product inventory mismatch")
    geometries = {
        v: check_view(v, decision["views"][v]["camera"], qa["geometry"]) for v in POSITION
    }
    cases = []
    issued = datetime.now(UTC).isoformat()
    for row in slots():
        directory = dest / row["id"]
        directory.mkdir()
        case = {
            **template["case"],
            **row,
            "visual_seed": row["seed"],
            "visual_id": RELEASE + "/" + row["id"],
            "release": RELEASE,
            "private_output": row["id"] + "/instance",
        }
        a = {
            **template,
            "schema": "proposal.translated.case.v1",
            "case": case,
            "issued_at": issued,
            "geometry": geometries[row["view"]],
            "sources_sha256": source_hashes,
            "catalog": archive,
            "template_sha256": old_case["allocation_sha256"],
            "plan_sha256": qa["plan_sha256"],
            "plan_md_sha256": qa["plan_md_sha256"],
            "interval_plan_sha256": interval_sha,
            "selection_sha256": qsha,
        }
        path = directory / "allocation.json"
        write(path, a)
        cases.append(
            {
                **row,
                "allocation_file": str(path.relative_to(dest)),
                "allocation_sha256": sha(path),
                "camera_configuration_sha256": runtime.digest(a["geometry"]["camera"]),
            }
        )
    manifest = {
        "schema": "proposal.translated.paired-allocation.v1",
        "issued_at": issued,
        "release": RELEASE,
        "baseline": qa["baseline"],
        "previous_guarded_batch_sha256": bsha,
        "plan_sha256": qa["plan_sha256"],
        "interval_plan_sha256": interval_sha,
        "preflight_sha256": decision["allocation_sha256"],
        "selection_sha256": qsha,
        "geometry": geometries,
        "sources_sha256": source_hashes,
        "catalog": archive,
        "no_retries": True,
        "cases": cases,
        "model_calls": 0,
        "formal_claims": 0,
        "hardware_actions": 0,
    }
    write(dest / "allocation.json", manifest)
    write(public, manifest)


def check_master(raw, path, digest):
    b = pinned(path, digest)
    if sha(raw / "episodes/allocation.json") != digest or b["release"] != RELEASE:
        raise ValueError("foreign public manifest or evidence root")
    if len(b["cases"]) != 8 or any(
        any(r.get(k) != v for k, v in s.items())
        or r["allocation_file"] != s["id"] + "/allocation.json"
        for r, s in zip(b["cases"], slots(), strict=True)
    ):
        raise ValueError("incomplete or altered paired allocation")
    check_sources(b)
    return b


class TranslatedBackend(MuJoCoPhysicsBackend):
    """Retain the actual reset boundary, then only translate the world-mounted camera."""

    def __init__(self, directory, view):
        super().__init__()
        self.directory = directory
        self.view = view

    def reset(self, scenario):
        boundaries = []

        def record(event):
            if event.kind == "RESET":
                boundaries.append(runtime.plain(event))

        with self.observe_operation_boundaries(record):
            super().reset(scenario)
        write(self.directory / "reset-observed.json", boundaries)
        if self.view == "translated":
            self.set_camera_position(POSITION[self.view])
        write(self.directory / "camera-setup.json", self.command_records)


class TranslatedEpisode(guarded_clock.GuardedClockEpisode):
    def __init__(self, directory, a, h, catalog):
        super().__init__(directory, a, h, catalog)
        self.backend = TranslatedBackend(directory, a["case"]["view"])
        self.robot = runtime.MuJoCoSkillRobot(self.backend)
        self.executor = guarded_clock.RecordedExecutor(
            self, runtime.SkillExecutor(robot=self.robot, registry=runtime.SkillRegistry.default())
        )


def capture(raw, path, h, id_):
    if os.environ.get("MUJOCO_GL") != "egl":
        raise ValueError("registered EGL backend required")
    b = check_master(raw, path, h)
    selected = [r for r in b["cases"] if r["id"] == id_]
    if len(selected) != 1:
        raise ValueError("case is not in translated assignment")
    row = selected[0]
    dest = raw / "episodes"
    a = pinned(dest / row["allocation_file"], row["allocation_sha256"])
    case = a["case"]
    if (
        any(case[k] != row[k] for k in slots()[0])
        or case["visual_seed"] != row["seed"]
        or case["visual_id"] != RELEASE + "/" + id_
        or a["geometry"] != b["geometry"][row["view"]]
        or runtime.digest(a["geometry"]["camera"]) != row["camera_configuration_sha256"]
        or a["selection_sha256"] != b["selection_sha256"]
    ):
        raise ValueError("identity or measured camera differs from allocated pair")
    catalog = runtime.inventory()
    if catalog != pinned(
        dest / b["catalog"]["private_filename"], b["catalog"]["archived_json_sha256"]
    ):
        raise ValueError("changed frozen inventory")
    d = dest / id_ / "instance"
    d.mkdir()
    start = time.monotonic()
    write(
        d / "started.json",
        {
            "case": id_,
            "argv": sys.argv,
            "issued_sha256": h,
            "case_sha256": row["allocation_sha256"],
            "start_utc": datetime.now(UTC).isoformat(),
            "attempt": 1,
        },
    )
    episode = TranslatedEpisode(d, a, row["allocation_sha256"], catalog)
    try:
        episode.run()
    except BaseException as e:
        write(
            d / "interrupted.json",
            {"type": type(e).__name__, "error": str(e), "wall_s": time.monotonic() - start},
        )
        raise
    finally:
        episode.backend.shutdown()
    reset = readback_reset(row, read(d / "reset-observed.json"))
    seal = read(d / "acquisition-seal.json")
    index = pinned(d / "pixel-index.json", seal["index_sha256"])
    if (
        index["episode"] != reset["episode_id"]
        or index["allocation_sha256"] != row["allocation_sha256"]
    ):
        raise ValueError("foreign acquisition or reset")
    write(
        d / "receipt.json",
        {
            "case": id_,
            "allocation_sha256": row["allocation_sha256"],
            "batch_sha256": h,
            "physical_reset": reset,
            "reset_sha256": sha(d / "reset-observed.json"),
            "camera_setup_sha256": sha(d / "camera-setup.json"),
            "started_sha256": sha(d / "started.json"),
            "capture_sha256": sha(d / "acquisition-seal.json"),
            "wall_s": time.monotonic() - start,
        },
    )


def exact_discordance_interval(count, n):
    """Two-sided 97.5% Clopper–Pearson, for one of the two discordance probabilities."""
    if type(n) is not int or type(count) is not int or not 0 <= count <= n or n < 1:
        raise ValueError("invalid binomial count")

    def lower(k):
        if not k:
            return 0.0
        lo, hi = 0.0, 1.0
        for _ in range(70):
            mid = (lo + hi) / 2
            tail = sum(math.comb(n, x) * mid**x * (1.0 - mid) ** (n - x) for x in range(k, n + 1))
            if tail < 0.0125:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    return lower(count), 1.0 - lower(n - count)


def paired_summary(rows):
    if len(rows) != 8 or len({(r["group"], r["view"]) for r in rows}) != 8:
        raise ValueError("translated analysis requires the eight assigned slots")
    outcomes = {}
    for group in sorted({r["group"] for r in rows}):
        pair = {r["view"]: r for r in rows if r["group"] == group}
        if set(pair) != set(POSITION):
            raise ValueError("paired group requires both cameras")
        if all(v["acquired"] for v in pair.values()):
            outcomes[group] = [int(pair[v]["joint_success"]) for v in POSITION]
        else:
            outcomes[group] = None
    complete = [r for r in outcomes.values() if r is not None]
    stat = {
        "order": ["nominal", "translated"],
        "outcomes": outcomes,
        "fully_acquired_groups": len(complete),
        "paired_success_difference": None,
        "conservative_difference_ci95": None,
    }
    if len(complete) == 4:
        gains = sum(r == [0, 1] for r in complete)
        losses = sum(r == [1, 0] for r in complete)
        # Simultaneous exact binomial bounds for the two discordance probabilities.
        plus_low, plus_high = exact_discordance_interval(gains, 4)
        minus_low, minus_high = exact_discordance_interval(losses, 4)
        stat.update(
            gains=gains,
            losses=losses,
            paired_success_difference=(gains - losses) / 4,
            conservative_difference_ci95=[
                max(-1.0, plus_low - minus_high),
                min(1.0, plus_high - minus_low),
            ],
            interval_method="Bonferroni two-sided exact binomial intervals for each discordance",
        )
    return stat


def analyze(mode, raw, path, h, output=None):
    b = check_master(raw, path, h)
    dest = raw / "episodes"
    scored, errors = [], {v: [] for v in POSITION}
    for r in b["cases"]:
        ap = dest / r["allocation_file"]
        d = ap.parent / "instance"
        if not (d / "acquisition-seal.json").exists():
            scored.append({**r, "acquired": False})
            continue
        if mode == "pixels":
            dynamic_vision_score.pixels(d, ap, r["allocation_sha256"])
            continue
        rec = read(d / "receipt.json")
        if (
            rec["capture_sha256"] != sha(d / "acquisition-seal.json")
            or rec["reset_sha256"] != sha(d / "reset-observed.json")
            or rec["camera_setup_sha256"] != sha(d / "camera-setup.json")
            or rec["physical_reset"] != readback_reset(r, read(d / "reset-observed.json"))
        ):
            raise ValueError("reset or capture differs from original receipt")
        result, values = proposal_scoring.read_case(r, ap, d)
        if result["episode"] != rec["physical_reset"]["episode_id"]:
            raise ValueError("reset and offline episode differ")
        scored.append(
            {**r, **result, "wall_s": rec["wall_s"], "receipt_sha256": sha(d / "receipt.json")}
        )
        errors[r["view"]].extend(values)
    if mode == "pixels":
        return
    episodes = [r["episode"] for r in scored if r["acquired"]]
    if len(set(episodes)) != len(episodes):
        raise ValueError("duplicate experimental episode")
    by_view = {
        v: proposal_scoring.summarize_view([r for r in scored if r["view"] == v], errors[v])
        for v in POSITION
    }
    write(
        output,
        {
            "schema": "proposal.translated.heldout-results.v1",
            "scope": "PAIRED_DEVELOPMENT_EVIDENCE",
            "allocation_sha256": h,
            "views": by_view,
            "paired": paired_summary(scored),
            "instances": scored,
            "placement_unit": "four independent static placements, both cameras at each placement",
            "formal_claims": 0,
            "model_calls": 0,
            "hardware_actions": 0,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="cmd", required=True)
    p = commands.add_parser("issue")
    for n in ("raw", "qualification", "q_sha", "b_manifest", "b_sha", "b_raw", "output"):
        p.add_argument(n, type=str if n.endswith("sha") else Path)
    for name in ("capture", "pixels", "score"):
        p = commands.add_parser(name)
        p.add_argument("raw", type=Path)
        p.add_argument("manifest", type=Path)
        p.add_argument("digest")
        if name == "capture":
            p.add_argument("case")
        if name == "score":
            p.add_argument("output", type=Path)
    a = parser.parse_args()
    if a.cmd == "issue":
        issue(a.raw, a.qualification, a.q_sha, a.b_manifest, a.b_sha, a.b_raw, a.output)
    elif a.cmd == "capture":
        capture(a.raw, a.manifest, a.digest, a.case)
    else:
        analyze(a.cmd, a.raw, a.manifest, a.digest, getattr(a, "output", None))


if __name__ == "__main__":
    main()
