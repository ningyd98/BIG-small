"""Paired development-only bootstrap corner study with sealed sources, frames and fresh episodes."""

import argparse
import base64
import io
import os
import sqlite3
import sys
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scripts.graduation import dynamic_vision as rt
from scripts.graduation import dynamic_vision_score as vs
from scripts.graduation import proposal_closed_loop as base
from scripts.graduation import proposal_scoring as scoring
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write
from scripts.graduation.perception_pixels import biased_observation

from cloud_edge_robot_arm.research.native_archived_tracker import _ArchivedTargetTracker
from cloud_edge_robot_arm.research.native_collection_grounding import (
    BootstrapCornerPolicy,
    collection_bootstrap_evidence,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation

ARMS = ("EXACT_DEFAULT", "EXPLICIT_SUBPIX")
GFILE = "src/cloud_edge_robot_arm/research/native_collection_grounding.py"
STUDY = "proposal-dev-bootstrap-corners-20261124"
POSES = ((0.437, 0.012, 0.035, 0.06), (0.463, -0.012, 0.035, -0.06), (0.451, 0.021, 0.035, 0.14))


def positions():
    cases = []
    for i, (x, y, z, yaw) in enumerate(POSES):
        group = f"b{i + 1:02d}"
        for arm in ARMS if i % 2 == 0 else ARMS[::-1]:
            cases.append(
                dict(
                    id=f"{group}-{arm.lower()}",
                    group=group,
                    arm=arm,
                    view="nominal",
                    seed=24112601 + i,
                    reset_fixture_center_m=[x, y, z],
                    yaw_rad=yaw,
                )
            )
    return cases


def source_snapshot(out, previous, plan):
    catalog = rt.inventory()
    old_source = previous / "r593-v4-source-inventory.json"
    old = pinned(
        old_source,
        plan["input_sha256"][
            next(k for k in plan["input_sha256"] if k.endswith("/r593-v4-source-inventory.json"))
        ],
    )
    if catalog.keys() != old.keys() or {k for k in old if old[k] != catalog[k]} != {GFILE}:
        raise ValueError("candidate catalog differs outside the registered product change")
    old_release = read(previous / "allocation.public.json")
    archive = rt.bind_catalog(out, catalog, old_release["geometry"]["nominal"]["asset_path"])
    scripts = {
        **old_release["source_sha256"],
        "scripts/graduation/proposal_scoring.py": None,
        "scripts/graduation/proposal_bootstrap_policy.py": None,
        "tests/test_proposal_bootstrap_corner_policy.py": None,
    }
    allowed_updates = {
        GFILE,
        "scripts/graduation/guarded_clock.py",
        "scripts/graduation/dynamic_vision.py",
    }
    for path, old_sha in scripts.items():
        current = sha(ROOT / path)
        if old_sha and path not in allowed_updates and current != old_sha:
            raise ValueError("unregistered source change: " + path)
        scripts[path] = current
    return dict(
        catalog=archive,
        catalog_sha256=rt.digest(catalog),
        worker_source_generation=rt.product_digest(catalog),
        source_sha256=scripts,
        old_product_sha256=old[GFILE],
        candidate_product_sha256=catalog[GFILE],
        previous_generation=rt.product_digest(old),
    )


def actual_import_paths():
    modules = {}
    for name, mod in list(sys.modules.items()):
        if (
            name.startswith(("cloud_edge_robot_arm.", "scripts.graduation.", "scripts.phase7."))
            or name == "__main__"
        ):
            filename = getattr(mod, "__file__", None)
            if filename is None:
                continue
            path = Path(filename).resolve()
            if not path.is_relative_to(ROOT):
                raise ValueError("foreign project module: " + str(path))
            modules[name] = str(path)
    return modules


def check_live(out, reg, *, imports=True):
    catalog = rt.inventory()
    if catalog != pinned(
        out / reg["catalog"]["private_filename"], reg["catalog"]["archived_json_sha256"]
    ):
        raise ValueError("candidate catalog changed")
    for k, h in reg["source_sha256"].items():
        if sha(ROOT / k) != h:
            raise ValueError("candidate glue differs: " + k)
    if imports:
        actual_import_paths()
    return catalog


def register(oldroot, plan_path, plan_sha, previous, out):
    if os.environ.get("MUJOCO_GL") != "egl":
        raise ValueError("EGL required")
    plan = pinned(plan_path, plan_sha)
    if sha(plan_path.with_suffix(".md")) != plan["plan_md_sha256"]:
        raise ValueError("plan markdown mismatch")
    for k, h in plan["input_sha256"].items():
        if sha(oldroot / k) != h:
            raise ValueError("original plan input changed: " + k)
    old_alloc = read(previous / "allocation.public.json")
    if sha(previous / "allocation.public.json") != next(
        h
        for k, h in plan["input_sha256"].items()
        if k.endswith("qualification-20261124/allocation.public.json")
    ):
        raise ValueError("wrong old allocation")
    if old_alloc["online_selected_view"] != "nominal":
        raise ValueError("original reference camera mismatch")
    if out.exists():
        raise ValueError("source/placement allocation already issued")
    out.mkdir()
    sources = source_snapshot(out, previous, plan)
    frames = []
    for row in old_alloc["cases"]:
        folder = previous / row["id"] / "instance"
        seal_path = folder / "acquisition-seal.json"
        seal = read(seal_path)
        index = pinned(folder / "pixel-index.json", seal["index_sha256"])
        run = pinned(folder / "run.json", seal["run_sha256"])
        key = next(r for r in index["frames"] if r["label"] == "bootstrap")
        stage = next(r for r in run["frame_roles"] if r["label"] == "bootstrap")
        src = folder / key["file"]
        if (
            key["physics_step"] != 120
            or stage["frame_id"] != key["frame_id"]
            or stage["checksum_sha256"] != key["checksum_sha256"]
            or sha(src) != key["file_sha256"]
            or not any(
                (oldroot / k).resolve() == src.resolve() and h == key["file_sha256"]
                for k, h in plan["input_sha256"].items()
            )
        ):
            raise ValueError("incorrect original bootstrap frame or role")
        frames.append(
            {
                **key,
                "case": row["id"],
                "episode": index["episode"],
                "checked_at": stage["checked_at"],
                "file": str(src),
                "truth_file": str(folder / "offline-truth.json"),
                "truth_sha256": seal["truth_sha256"],
            }
        )
    template = previous / old_alloc["cases"][0]["allocation_file"]
    write(
        out / "registration.json",
        {
            **sources,
            "actual_import_files": actual_import_paths(),
            "scope": "DEVELOPMENT_COMPONENT_ONLY",
            "baseline": plan["baseline"],
            "plan_sha256": plan_sha,
            "template": str(template),
            "template_sha256": sha(template),
            "frames": frames,
            "negative_derivation_case": "g03-nominal",
            "cases": positions(),
            "issued_at": datetime.now(UTC).isoformat(),
        },
    )
    return sha(out / "registration.json")


def options(arm, catalog, geometry):
    if arm not in ARMS:
        raise ValueError("unknown bootstrap arm")
    return (
        {}
        if arm == ARMS[0]
        else dict(
            corner_policy=BootstrapCornerPolicy.for_development(catalog, geometry),
            source_hashes=catalog,
        )
    )


def fixed_gate(frame, at, arm, catalog, geometry):
    traces = []
    try:
        evidence = collection_bootstrap_evidence(
            frame, geometry, corner_trace=traces.append, **options(arm, catalog, geometry)
        )
        tracker = _ArchivedTargetTracker(frame, evidence, evaluated_at=at)
        if tracker.initial is None or tracker.destination is None:
            raise ValueError("bootstrap color geometry unavailable")
        xy = evidence["original_pixel_target"]
        result = dict(
            allowed=True,
            reason=None,
            tcp=evidence["resolved_top_grasp_tcp"],
            target_pixel=xy,
            destination_pixel=evidence["original_pixel_destination"],
            center=evidence["estimated_object_center"],
            target_depth_m=frame.depth_values()[xy[1] * frame.width + xy[0]],
        )
    except ValueError as err:
        result = dict(allowed=False, reason=str(err))
    return dict(
        frame_id=frame.frame_id,
        frame_sha256=frame.checksum_sha256,
        at=at.isoformat(),
        arm=arm,
        trace=traces,
        **result,
    )


def build_controls(frame, xy):
    rgb = np.full((frame.height, frame.width, 3), 255, dtype=np.uint8)
    marker = cv2.aruco.generateImageMarker(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), 8, 60
    )
    rgb[80:140, 100:160] = marker[:, :, None]
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="PNG")
    data = frame.model_dump()

    def derived(tag, **fields):
        return RGBDObservation.model_validate(
            {
                **data,
                **fields,
                "frame_id": "derived-" + tag + "-" + frame.checksum_sha256[:16],
                "checksum_sha256": "",
                "observation_id": "",
            }
        )

    depth = (
        np.frombuffer(base64.b64decode(frame.depth_float32_base64), dtype="<f4")
        .copy()
        .reshape(frame.height, frame.width)
    )
    x, y = xy
    depth[y - 3 : y + 4, x - 3 : x + 4] = 0
    return {
        "wrong_id_8": derived("id8", rgb_png_base64=base64.b64encode(buf.getvalue()).decode()),
        "missing_all_depth": biased_observation(frame, None),
        "invalid_target_depth": derived(
            "targetdepth",
            depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
            valid_mask_base64=None,
        ),
    }


def fixed(out, registration_sha):
    reg = pinned(out / "registration.json", registration_sha)
    catalog = check_live(out, reg)
    geo = pinned(Path(reg["template"]), reg["template_sha256"])["geometry"]
    rows = []
    controls = []
    for src in reg["frames"]:
        f = RGBDObservation.model_validate(pinned(Path(src["file"]), src["file_sha256"]))
        if f.episode_id != src["episode"] or f.checksum_sha256 != src["checksum_sha256"]:
            raise ValueError("registration source frame changed")
        at = datetime.fromisoformat(src["checked_at"])
        decisions = [fixed_gate(f, at, a, catalog, geo) for a in ARMS]
        rows.append(dict(case=src["case"], decisions=decisions))
        if src["case"] == reg["negative_derivation_case"]:
            for name, derived in build_controls(f, decisions[0]["target_pixel"]).items():
                write(out / (name + "-derived.json"), derived.model_dump(mode="json"))
                for arm in ARMS:
                    res = fixed_gate(derived, at, arm, catalog, geo)
                    if res["allowed"] or (
                        name == "wrong_id_8" and 8 not in res["trace"][0]["marker_ids"]
                    ):
                        raise ValueError("negative control failed: " + name)
                    controls.append(dict(case=name, result=res, source_checksum=f.checksum_sha256))
            base_policy = BootstrapCornerPolicy.for_development(catalog, geo)
            for name, policy, source in (
                ("foreign_source", base_policy, {**catalog, GFILE: "0" * 64}),
                ("foreign_policy", replace(base_policy, mode="OTHER"), catalog),
            ):
                try:
                    collection_bootstrap_evidence(
                        f, geo, corner_policy=policy, source_hashes=source
                    )
                except ValueError as exc:
                    controls.append(dict(case=name, refusal=str(exc)))
                else:
                    raise ValueError("invalid binding admitted")
            try:
                RGBDObservation.model_validate({**f.model_dump(), "checksum_sha256": "f" * 64})
            except ValueError:
                controls.append(
                    dict(
                        case="foreign_frame_hash", refusal="paired observation checksum validation"
                    )
                )
            else:
                raise ValueError("corrupt observation admitted")
    write(
        out / "fixed-pixel-decisions.json",
        dict(registration_sha256=registration_sha, rows=rows, negative_controls=controls),
    )
    sealed = sha(out / "fixed-pixel-decisions.json")
    physical = []
    for src, row in zip(reg["frames"], rows, strict=True):
        states = pinned(Path(src["truth_file"]), src["truth_sha256"])
        s = states["samples"][120]
        if states["episode"] != src["episode"] or s["physics_step"] != 120:
            raise ValueError("foreign fixed-frame truth")
        errs = {}
        for dec in row["decisions"]:
            if not dec["allowed"]:
                errs[dec["arm"]] = None
                continue
            center = [dec["center"][k] for k in "xyz"]
            errs[dec["arm"]] = 1000 * float(
                np.linalg.norm(np.subtract(center, s["object_geom_position_m"]))
            )
        physical.append(dict(case=src["case"], bootstrap_center_error_mm=errs))
    write(
        out / "fixed-scored.json",
        dict(
            registration_sha256=registration_sha,
            pixel_decisions_sha256=sealed,
            rows=rows,
            negative_controls=controls,
            physical_read_after_pixel_seal=physical,
        ),
    )
    return sha(out / "fixed-scored.json")


def freeze(out, registration_sha, fixed_sha):
    reg = pinned(out / "registration.json", registration_sha)
    catalog = check_live(out, reg)
    gates = pinned(out / "fixed-scored.json", fixed_sha)
    if (
        gates["registration_sha256"] != registration_sha
        or gates["pixel_decisions_sha256"] != sha(out / "fixed-pixel-decisions.json")
        or len(gates["negative_controls"]) != 9
    ):
        raise ValueError("fixed readback/negative controls incomplete")
    template = pinned(Path(reg["template"]), reg["template_sha256"])
    rows = []
    for row in reg["cases"]:
        folder = out / row["id"]
        folder.mkdir()
        binding = {
            **asdict(BootstrapCornerPolicy.for_development(catalog, template["geometry"])),
            "mode": row["arm"],
        }
        case = {
            **template["case"],
            **row,
            "release": STUDY,
            "visual_id": STUDY + "/" + row["id"],
            "visual_seed": row["seed"],
            "private_output": row["id"] + "/instance",
        }
        alloc = {
            k: template[k]
            for k in (
                "geometry",
                "asset_sha256",
                "capture_grid",
                "selected_entry",
                "r1_allocation_sha256",
                "software_receipt_sha256",
            )
        }
        intent = {**template["intent_descriptor"], "bootstrap_policy_binding": binding}
        alloc.update(
            schema="proposal.bootstrap.case.v1",
            baseline=reg["baseline"],
            case=case,
            sources_sha256=reg["source_sha256"],
            intent_descriptor=intent,
            bootstrap_policy_binding=binding,
            component_catalog_sha256=reg["catalog_sha256"],
            worker_source_generation=reg["worker_source_generation"],
            fixed_sha256=fixed_sha,
            registration_sha256=registration_sha,
            catalog=reg["catalog"],
        )
        path = folder / "allocation.json"
        write(path, alloc)
        rows.append(
            {
                **row,
                "allocation_sha256": sha(path),
                "allocation_file": str(path.relative_to(out)),
                "bootstrap_policy_binding": binding,
            }
        )
    write(
        out / "allocation.json",
        dict(
            schema="proposal.bootstrap.heldout.v1",
            registration_sha256=registration_sha,
            fixed_sha256=fixed_sha,
            issued_at=datetime.now(UTC).isoformat(),
            cases=rows,
            source_generation=reg["worker_source_generation"],
            previous_generation=reg["previous_generation"],
            source_sha256=reg["source_sha256"],
            actual_import_files=reg["actual_import_files"],
            scope="DEVELOPMENT_COMPONENT_ONLY",
            native_claims=0,
            model_calls=0,
            hardware_actions=0,
        ),
    )
    return sha(out / "allocation.json")


def capture(out, allocation_sha, case):
    a = pinned(out / "allocation.json", allocation_sha)
    reg = pinned(out / "registration.json", a["registration_sha256"])
    catalog = check_live(out, reg)
    if [{k: r[k] for k in positions()[0]} for r in a["cases"]] != positions():
        raise ValueError("case denominator changed")
    row = next(r for r in a["cases"] if r["id"] == case)
    alloc = pinned(out / row["allocation_file"], row["allocation_sha256"])
    if (
        alloc["case"]["arm"] != row["arm"]
        or alloc["intent_descriptor"]["bootstrap_policy_binding"] != row["bootstrap_policy_binding"]
        or alloc["worker_source_generation"] != rt.product_digest(catalog)
    ):
        raise ValueError("allocation policy/source mismatch")
    dest = out / case / "instance"
    dest.mkdir()
    write(
        dest / "started.json",
        dict(
            case=case,
            allocation_sha256=row["allocation_sha256"],
            master_sha256=allocation_sha,
            started=datetime.now(UTC).isoformat(),
            argv=sys.argv,
            actual_import_paths=actual_import_paths(),
        ),
    )
    ep = base.HeldoutEpisode(dest, alloc, row["allocation_sha256"], catalog)
    clock = time.monotonic()
    try:
        ep.run()
    finally:
        ep.backend.shutdown()
    seal = read(dest / "acquisition-seal.json")
    reset = base.readback_reset(row, read(dest / "reset-observed.json"))
    run = pinned(dest / "run.json", seal["run_sha256"])
    index = pinned(dest / "pixel-index.json", seal["index_sha256"])
    if reset["episode_id"] != index["episode"] or run["lease_summary"]["attempt"] != 1:
        raise ValueError("foreign reset/job")
    write(
        dest / "capture-summary.json",
        dict(
            wall_s=time.monotonic() - clock,
            actual_import_files=actual_import_paths(),
            reset=reset,
            source_seal_sha256=sha(dest / "acquisition-seal.json"),
            stop=run.get("stop"),
            stages=run["actions"],
        ),
    )


def score(out, allocation_sha):
    a = pinned(out / "allocation.json", allocation_sha)
    check_live(out, pinned(out / "registration.json", a["registration_sha256"]))
    rows = []
    by_arm = {arm: [] for arm in ARMS}
    errs = {arm: [] for arm in ARMS}
    for row in a["cases"]:
        dest = out / row["id"] / "instance"
        p = out / row["allocation_file"]
        if not (dest / "decision-seal.json").exists():
            vs.pixels(dest, p, row["allocation_sha256"])
        summary, errors = scoring.read_case(row, p, dest)
        run = read(dest / "run.json")
        ledger = run["bootstrap_consumers"]
        index = read(dest / "pixel-index.json")
        frame_labels = {frame["label"]: frame["checksum_sha256"] for frame in index["frames"]}
        refs = dict(
            bootstrap="bootstrap",
            reset_readonly="reset",
            v2_region_reference="registration-handoff",
            guarded_handoff="registration-handoff",
        )
        binding = rt.digest(row["bootstrap_policy_binding"])
        needed = "NONE" if row["arm"] == ARMS[0] else "SUBPIX"
        for item in ledger:
            if (
                item["frame_sha256"] != frame_labels[refs[item["role"]]]
                or item["binding_sha256"] != binding
                or item["arm"] != row["arm"]
                or item["corner_refinement"] != needed
            ):
                raise ValueError("actual bootstrap consumer frame, source or mode changed")
        if "dispatch_reference" in run and [i["role"] for i in ledger] != list(refs):
            raise ValueError("guarded handoff lacks all four measured bootstrap consumers")
        with sqlite3.connect(
            (dest / "development-worker.db").resolve().as_uri() + "?mode=ro", uri=True
        ) as db:
            jobs = db.execute(
                "SELECT run_id,status,seed,attempt,max_attempts,reproducibility_hash "
                "FROM simulation_jobs"
            ).fetchall()
            leases = db.execute("SELECT released_at FROM simulation_job_leases").fetchall()
        if (
            jobs
            != [
                (
                    STUDY + ":" + row["id"],
                    run["lease_summary"]["final_job_status"],
                    row["seed"],
                    1,
                    1,
                    row["allocation_sha256"],
                )
            ]
            or len(leases) != 1
            or not leases[0][0]
        ):
            raise ValueError("SQLite did not confirm the sole run and closed lease")
        summary.update(
            case_id=row["id"],
            group=row["group"],
            arm=row["arm"],
            seed=row["seed"],
            bootstrap_complete="dispatch_reference" in run,
            bootstrap_consumers=ledger,
            db_sha256=sha(dest / "development-worker.db"),
            scenario_reset=read(dest / "capture-summary.json")["reset"],
            source_seal_sha256=sha(dest / "acquisition-seal.json"),
        )
        # PRE stores condition rows and a real Shield result, with dispatch checked independently.
        first_pre = run["actions"][0].get("pre")
        summary["passed_first_pre"] = bool(
            first_pre
            and first_pre["shield"]["allowed"]
            and all(c["status"] == "PASS" for c in first_pre["conditions"])
        )
        rows.append(summary)
        by_arm[row["arm"]].append(summary)
        errs[row["arm"]].extend(errors)
    if len(rows) != 6 or len({r["episode"] for r in rows}) != 6:
        raise ValueError("incomplete paired denominator")
    summaries = {}
    for arm in ARMS:
        armrows = by_arm[arm]
        summaries[arm] = {
            **scoring.summarize_view(armrows, errs[arm]),
            **{
                key: sum(r[key] for r in armrows)
                for key in (
                    "bootstrap_complete",
                    "passed_first_pre",
                    "dispatched_actions",
                    "verified_posts",
                )
            },
        }
    paired = []
    for i in range(3):
        pair = {r["arm"]: r for r in rows if r["group"] == f"b{i + 1:02d}"}
        paired.append(
            dict(
                group=pair[ARMS[0]]["group"],
                candidate_minus_default={
                    k: int(pair[ARMS[1]][k]) - int(pair[ARMS[0]][k])
                    for k in (
                        "bootstrap_complete",
                        "passed_first_pre",
                        "verified_posts",
                        "joint_success",
                    )
                },
            )
        )
    write(
        out / "scored.json",
        dict(
            schema="proposal.bootstrap.heldout.readback.v1",
            allocation_sha256=allocation_sha,
            cases=rows,
            arms=summaries,
            paired=paired,
            formal_claims=0,
            model_calls=0,
            hardware_actions=0,
        ),
    )
    return sha(out / "scored.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for func, fields in (
        (register, ["oldroot", "plan_path", "plan_sha", "previous", "out"]),
        (fixed, ["out", "registration_sha"]),
        (freeze, ["out", "registration_sha", "fixed_sha"]),
        (capture, ["out", "allocation_sha", "case"]),
        (score, ["out", "allocation_sha"]),
    ):
        cmd = sub.add_parser(func.__name__)
        cmd.set_defaults(function=func)
        for field in fields:
            cmd.add_argument(field, type=str if field.endswith("_sha") or field == "case" else Path)
    args = vars(parser.parse_args())
    args.pop("command")
    func = args.pop("function")
    result = func(**args)
    if result:
        print(result)
