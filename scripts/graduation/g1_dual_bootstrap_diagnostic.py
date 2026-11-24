"""Read second-generation failures and replay paired stationary support-visibility interventions."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from scripts.graduation import g1_dual_asset as asset
from scripts.graduation import g1_dual_observer as observer
from scripts.graduation import g1_dual_probe as probe
from scripts.graduation import g1_dual_trials as trials
from scripts.graduation import proposal_camera as camera
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

from cloud_edge_robot_arm.research.native_collection_grounding import collection_bootstrap_evidence
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker

PLAN = "0813917c9745b46b960c16e006741298a78c7dd4e83e9c9aa2ba9df0f720725e"
SUPPORTS = ("g1_dual_id7_support", "g1_dual_id8_support")
REASON = "target_outer_boundary_depth_unresolved"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def ring_summary(ring, depth, valid, top, bound):
    ok = (valid > 0) & np.isfinite(depth) & (depth - bound > top + bound)
    return dict(
        ring_pixels=int(ring.sum()),
        positive=int(((depth > 0) & ring).sum()),
        invalid=int((ring & (valid == 0)).sum()),
        threshold_top_max_m=float(top),
        bound_m=float(bound),
        failures=[
            dict(
                rc=[int(y), int(x)],
                depth_m=float(depth[y, x]),
                valid=bool(valid[y, x]),
                margin_m=float((depth[y, x] - bound) - (top + bound)),
            )
            for y, x in zip(*np.where(ring & ~ok), strict=True)
        ],
    )


def assess(matched, rejected, restored, hits):
    if not (matched and rejected and restored and hits):
        return "unresolved"
    if all(x == "direct" for x in hits):
        return "direct_support_instances_and_hidden_recovery"
    if all(x in ("direct", "mixed_boundary") for x in hits):
        return "support_boundary_and_hidden_recovery"
    return "unresolved"


def mask_sha(a):
    return hashlib.sha256(np.ascontiguousarray(a, dtype="u1").tobytes()).hexdigest()


def pixel_geometry(f, g, folder):
    evidence = collection_bootstrap_evidence(f, g)
    source_geometry = OpenCVTargetTracker._geometry.__code__
    observed = {}

    def trace(frame, event, arg):
        if (
            event == "return"
            and frame.f_code is source_geometry
            and frame.f_locals.get("target")
            and "ring" in frame.f_locals
        ):
            loc = frame.f_locals
            for name in (
                "selected",
                "mask",
                "color",
                "ring",
                "shaded_edge",
                "top_selector",
                "ys",
                "xs",
                "bound",
                "top_depth_min",
                "top_depth_max",
            ):
                observed[name] = loc[name]
        return trace

    details = {}
    error = None
    prior = sys.gettrace()
    sys.settrace(trace)
    try:
        OpenCVTargetTracker._inspect_frozen_geometry(f, evidence, details)
    except ValueError as exc:
        error = str(exc)
    finally:
        sys.settrace(prior)
    require(bool(observed), "original target did not reach optical outer-ring test")
    rgb = camera.rgb(f).astype(float)
    dep = camera.depth(f).astype(float)
    valid = np.frombuffer(f.valid_mask_bytes(), np.uint8).reshape(dep.shape)
    color = observed["color"]
    selected = observed["selected"]
    kernel = np.ones((3, 3), np.uint8)
    chroma = rgb / np.maximum(rgb.sum(axis=2, keepdims=True), 1.0)
    mask = (np.linalg.norm(chroma - color, axis=2) < 0.14) & (np.ptp(rgb, axis=2) > 30)
    pure = rgb - rgb.min(axis=2, keepdims=True)
    pure /= np.maximum(pure.sum(axis=2, keepdims=True), 1.0)
    col = color - color.min()
    col = col / max(float(col.sum()), 1e-6)
    shell = (cv2.dilate(selected.astype(np.uint8), kernel) > 0) & ~selected
    shaded = (
        shell
        & (
            (np.linalg.norm(chroma - color, axis=2) < 0.24)
            | (np.linalg.norm(pure - col, axis=2) < 0.20)
        )
        & (np.ptp(rgb, axis=2) >= 14)
        & (valid > 0)
        & np.isfinite(dep)
        & (dep >= observed["top_depth_min"])
    )
    footprint = selected | shaded
    ring = (cv2.dilate(footprint.astype(np.uint8), kernel) > 0) & ~footprint
    require(
        np.array_equal(mask, observed["mask"])
        and np.array_equal(shaded, observed["shaded_edge"])
        and np.array_equal(ring, observed["ring"]),
        "recomputed native color, shade or ring differs",
    )
    top = np.zeros_like(ring)
    keep = observed["top_selector"]
    top[observed["ys"][keep], observed["xs"][keep]] = True
    rings = ring_summary(ring, dep, valid, observed["top_depth_max"], observed["bound"])
    require(
        bool(rings["failures"]) == (details["target"]["reason"] == REASON),
        "strict depth predicate and recorded target disagree",
    )
    masks_file = folder / (f.frame_id + "-masks.npz")
    with masks_file.open("xb") as stream:
        np.savez_compressed(stream, red=mask, selected=selected, shaded=shaded, top=top, ring=ring)
    return dict(
        frame_id=f.frame_id,
        checksum=f.checksum_sha256,
        target_uv=list(evidence["original_pixel_target"]),
        destination_uv=list(evidence["original_pixel_destination"]),
        target_color_chromaticity=color.tolist(),
        destination_color_chromaticity=OpenCVTargetTracker._color(
            rgb, tuple(evidence["original_pixel_destination"])
        ).tolist(),
        target=details["target"],
        destination=details["destination"],
        frozen_bootstrap_reason=error,
        raw_red_pixels=int(mask.sum()),
        selected_red_pixels=int(selected.sum()),
        allowed_shaded_pixels=int(shaded.sum()),
        top_pixels=int(top.sum()),
        top_depth_quantiles_m=dict(
            zip(
                ("min", "p05", "median", "p95", "max"),
                np.quantile(dep[top], [0, 0.05, 0.5, 0.95, 1]).tolist(),
                strict=True,
            )
        ),
        red_sha256=mask_sha(mask),
        allowed_shaded_sha256=mask_sha(shaded),
        top_mask_sha256=mask_sha(top),
        ring_mask_sha256=mask_sha(ring),
        mask_bundle_sha256=sha(masks_file),
        **rings,
    )


def source_files(workspace, d, archive, plan):
    inventory = {}
    for key, h in plan["input_sha256"].items():
        old = (workspace / key).resolve()
        if old.is_relative_to(d / "probes") or old.is_relative_to(d / "runtime-source"):
            path = archive / old.relative_to(d)
        elif old.name in (
            "runtime-build.public.json",
            "zero-step-probes.public.json",
            "compiled-geometry.public.json",
        ):
            path = archive / old.name
        elif key.startswith(("scripts/", "src/")):
            path = archive / "runtime-source" / key
        else:
            path = old
        require(sha(path) == h, "changed planned input: " + key)
        inventory[key] = h
    build = read(archive / "runtime-source/runtime-build.json")
    for rel, h in build["runtime_files_sha256"].items():
        require(sha(ROOT / rel) == h, "changed archived runtime file: " + rel)
    return inventory, build


def fresh(geometry, config, kind, hide, folder):
    backend = probe.runtime.MuJoCoPhysicsBackend()
    backend.initialize(probe.config({"geometry": geometry}, config.seed))
    model = backend._model
    try:
        compiled = trials.mass_properties(model)
        backend.reset(config)
        restored = trials.mass_properties(model)
        require(
            all(np.allclose(compiled[k], restored[k], rtol=0, atol=1e-12) for k in compiled),
            "changed rigid-body physical parameters",
        )
        probe.runtime.MuJoCoSkillRobot(backend).get_state()
        before = model.geom_rgba.copy()
        ids = [model.geom(name).id for name in SUPPORTS]
        if hide:
            model.geom_rgba[ids, 3] = 0
        try:
            f, labels, instances, state_hash = probe.capture(backend, kind, segmented=True)
            # Freshness is checked here by the native bootstrap before further offline work.
            try:
                probe.runtime.bootstrap_collection_tracker(f, geometry)
                live_reason = None
            except ValueError as exc:
                live_reason = str(exc)
        finally:
            model.geom_rgba[:] = before
        require(
            backend.total_physics_steps == 0
            and not backend.command_records
            and np.array_equal(model.geom_rgba, before)
            and (not hide or set(SUPPORTS).isdisjoint(labels.values())),
            "unexpected intervention, motion or time",
        )
        packet = folder / ("hidden.json" if hide else "normal.json")
        write(packet, f.model_dump(mode="json"))
        mask = packet.with_suffix(".npy")
        with mask.open("xb") as stream:
            np.save(stream, instances, allow_pickle=False)
        lab = packet.with_suffix(".labels.json")
        write(lab, labels)
        return (
            f,
            instances,
            labels,
            dict(
                packet_sha256=sha(packet),
                instance_sha256=sha(mask),
                labels_sha256=sha(lab),
                physics_state_sha256=state_hash,
                compiled=compiled,
                reset=restored,
                live_bootstrap_reason=live_reason,
                genuine_bootstrap_pass=live_reason is None,
                physics_steps=backend.total_physics_steps,
                command_count=len(backend.command_records),
            ),
        )
    finally:
        backend.shutdown()


def case_data(spec, archive, out, g):
    ident = spec["pose"] + "-" + spec["kind"]
    folder = out / ident
    folder.mkdir()
    anchor = archive / "probes" / ident
    seal = pinned(anchor / "seal.json", spec["seal_sha256"])
    require(seal["bootstrap.json"] == spec["packet_sha256"], "foreign source packet")
    f0 = RGBDObservation.model_validate(pinned(anchor / "bootstrap.json", seal["bootstrap.json"]))
    result = pinned(anchor / "result.json", seal["result.json"])
    tr = pinned(anchor / "probe-trace.json", seal["probe-trace.json"])
    require(
        (f0.frame_id, f0.checksum_sha256) == (spec["frame_id"], spec["checksum"])
        and result["stopped_stage"] == "pixel_bootstrap"
        and REASON in result["reason"],
        "foreign source or different refusal",
    )
    requested = tr["registered_reset"]["requested"]
    config = probe.runtime.PhysicalScenarioConfig(
        **{
            **requested,
            "object_pose": probe.runtime.Pose(**requested["object_pose"]),
            "target_region_pose": probe.runtime.Pose(**requested["target_region_pose"]),
        }
    )
    require(probe.runtime.plain(config) == requested, "archived physical reset differs")
    all_frames = []
    for hide in (False, True):
        all_frames.append(fresh(g, config, spec["kind"], hide, folder))
    return folder, f0, result, all_frames


def classify(f0, raw, result, frames, g):
    (fn, ins, names, normal), (fh, hin, hnames, hidden) = frames
    require(
        normal["physics_state_sha256"] == hidden["physics_state_sha256"]
        and normal["reset"] == hidden["reset"],
        "foreign static posture",
    )
    rgb0, rgbn, rgbh = (camera.rgb(f) for f in (f0, fn, fh))
    d0, dn, dh = (camera.depth(f) for f in (f0, fn, fh))
    equal = dict(
        rgb_equal=np.array_equal(rgb0, rgbn),
        depth_equal=np.array_equal(d0, dn),
        valid_mask_equal=f0.valid_mask_bytes() == fn.valid_mask_bytes(),
        camera_equal=camera.camera_meta(f0) == camera.camera_meta(fn) == camera.camera_meta(fh),
        rgb_changed_pixels=int((rgb0 != rgbn).any(axis=2).sum()),
        depth_changed_pixels=int((d0 != dn).sum()),
        common_depth_max_abs_m=float(np.abs(d0 - dn).max()),
    )
    native, nr, hr = (pixel_geometry(f, g, raw) for f in (f0, fn, fh))
    native_decoded = observer.measure_frame(f0, g)
    bad = []
    hits = []
    for failure in native["failures"]:
        y, x = failure["rc"]
        name = names.get(int(ins[y, x]), "background")
        after = hnames.get(int(hin[y, x]), "background")
        neighborhood = Counter(
            names.get(int(v), "background") for v in ins[y - 1 : y + 2, x - 1 : x + 2].ravel()
        )
        changed = bool(np.any(rgbn[y, x] != rgbh[y, x]) or dn[y, x] != dh[y, x])
        mode = (
            "direct"
            if name in SUPPORTS
            else (
                "mixed_boundary"
                if changed and any(k in SUPPORTS for k in neighborhood)
                else "other"
            )
        )
        bad.append(
            dict(
                **failure,
                normal_instance=name,
                hidden_instance=after,
                normal_rgb=rgbn[y, x].tolist(),
                hidden_rgb=rgbh[y, x].tolist(),
                hidden_depth_m=float(dh[y, x]),
                nearby_normal_instances=dict(neighborhood),
                classification=mode,
            )
        )
        hits.append(mode)
    same = (
        all(equal[k] for k in ("rgb_equal", "depth_equal", "valid_mask_equal", "camera_equal"))
        and native["failures"] == nr["failures"]
    )
    verdict = assess(
        same,
        normal["live_bootstrap_reason"] == result["reason"] and nr["target"]["reason"] == REASON,
        hr["frozen_bootstrap_reason"] is None and hidden["genuine_bootstrap_pass"],
        hits,
    )
    return dict(
        native_packet_status="original_has_no_instance_pass",
        pose=result["pose"],
        pose_xyzyaw=result["pose_xyzyaw"],
        kind=result["kind"],
        seed=result["seed"],
        source_archive_sha256=sha(
            raw.parents[1] / "bootstrap-second-generation/probes" / raw.name / "bootstrap.json"
        ),
        original=native,
        original_decoder={
            k: native_decoded[k] for k in ("observed_ids", "usable_ids", "selected_id", "reason")
        },
        normal_segmented={**normal, **nr},
        connector_hidden_segmented={**hidden, **hr},
        original_to_normal_raster=equal,
        failed_pixel_instances=bad,
        attribution=verdict,
    )


def run(planfile, archive, out, report):
    workspace = Path(__file__).resolve().parents[2]
    raw = archive.parent
    require(
        ROOT == archive / "runtime-source"
        and Path(probe.__file__).resolve().is_relative_to(ROOT)
        and os.environ.get("MUJOCO_GL") == "egl",
        "must execute archived runtime with EGL",
    )
    plan = pinned(planfile, PLAN)
    require(sha(planfile.with_suffix(".md")) == plan["plan_md_sha256"], "plan differs")
    inventory, build = source_files(workspace, raw, archive, plan)
    out.mkdir()
    g = asset.geometry_descriptor()
    asset.validate_asset(ROOT)
    cases = []
    with (raw / "egl.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for spec in plan["source_positive_frames"]:
            cases.append(case_data(spec, archive, out, g))
    rows = [classify(f, folder, result, frames, g) for folder, f, result, frames in cases]
    failures = Counter(v["classification"] for r in rows for v in r["failed_pixel_instances"])
    verified = sum(r["attribution"] != "unresolved" for r in rows)
    for r in rows:
        frozen = plan["frozen_frame_ring"]["invalid_poses"][int(r["pose"].split("-")[-1])]
        require(
            r["original"]["ring_pixels"] == frozen["ring_pixels"]
            and [b["rc"] for b in r["original"]["failures"]] == frozen["fail_rc"]
            and r["original"]["threshold_top_max_m"] == frozen["top_depth_max_m"],
            "original mask or ring no longer reproduces",
        )
    results = dict(
        schema="g1.dual-marker.second-generation-connector-intervention.v1",
        plan_sha256=PLAN,
        archive_tree_sha256=sha(ROOT / "runtime-build.json"),
        archived_runtime_files_rehashed=len(build["runtime_files_sha256"]),
        planned_inputs_rehashed=len(inventory),
        diagnostic_producer_sha256=sha(Path(__file__)),
        source_asset_sha256=asset.ASSET_SHA,
        source_packets=len(rows),
        new_stationary_segmented_renders=2 * len(rows),
        new_motion_dispatches=0,
        new_physics_steps=0,
        original_raster_exact_matches=sum(
            r["original_to_normal_raster"]["rgb_equal"]
            and r["original_to_normal_raster"]["depth_equal"]
            and r["original_to_normal_raster"]["valid_mask_equal"]
            for r in rows
        ),
        bad_pixel_observations=sum(failures.values()),
        bad_pixel_classification=dict(failures),
        actual_unchanged_bootstrap_with_support_hidden=sum(
            r["connector_hidden_segmented"]["genuine_bootstrap_pass"] for r in rows
        ),
        supported_source_cases=verified,
        connector_effect_supported=verified == 6,
        diagnostic_counts_in_motion_qualification=0,
        rows=rows,
    )
    write(out / "diagnostic.json", results)
    write(report, results)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("plan", "archive", "out", "report"):
        p.add_argument(arg, type=Path)
    a = p.parse_args()
    run(a.plan.resolve(), a.archive.resolve(), a.out.resolve(), a.report.resolve())


if __name__ == "__main__":
    main()
