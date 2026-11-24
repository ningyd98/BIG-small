"""Independently measure the two registered grasp points in frozen formal feedback frames."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import importlib.util
import io
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "experiments/results/g1-formal-paired-20261124"
ROUNDS = REPO / "artifacts/research/process/20261004-ced-development/astra-rounds"
ROUND = ROUNDS / "round-g1-formal-failure-observation-20261124"
FORMAL = ROUNDS / "round-g1-formal-paired-20261124"
PLAN_SHA = "31d5db8c1fea5aa9bdccdef8a2ccceac66dabaa5382ad5488ca2d6bc2d5f4767"
CASES = ("f01-dual", "f02-dual", "f03-dual", "f04-dual")
VARIANTS = ("observed", "true_depth", "true_corners", "both_true")


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_pinned(path, sha):
    data = path.read_bytes()
    require(digest(data) == sha, f"SHA-256 mismatch: {path}")
    return json.loads(data)


def json_bytes(value, *, indent=None):
    def native(x):
        if isinstance(x, (np.ndarray, np.generic)):
            return x.tolist()
        raise TypeError(type(x))

    return (
        json.dumps(
            value,
            default=native,
            indent=indent,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=None if indent else (",", ":"),
        )
        + "\n"
    ).encode()


def norm(x):
    return float(np.linalg.norm(x))


def rotation_deg(a, b):
    """Principal angle of the relative rotation, stable for nearly equal rotations."""
    d = a.T @ b
    skew = np.array([d[2, 1] - d[1, 2], d[0, 2] - d[2, 0], d[1, 0] - d[0, 1]])
    return float(np.degrees(np.arctan2(norm(skew), np.trace(d) - 1)))


def yaw_deg(r):
    return float(np.degrees(np.arctan2(r[1, 0], r[0, 0])))


def angle_delta_deg(a, b):
    return (a - b + 180.0) % 360.0 - 180.0


class Camera:
    def __init__(self, f):
        t = np.reshape(f["camera_to_world"], (4, 4))
        self.rot, self.origin = t[:3, :3], t[:3, 3]
        self.focal = np.array(f["intrinsics"][:2])
        self.principal = np.array(f["intrinsics"][2:])

    def rays(self, uv):
        xy = (uv - self.principal) / self.focal
        return np.column_stack((xy, np.ones(len(xy)))) @ self.rot.T

    def project(self, world):
        optical = (world - self.origin) @ self.rot
        require(np.all(optical[:, 2] > 0), "registration projects behind the camera")
        return self.principal + self.focal * optical[:, :2] / optical[:, 2, None]

    def plane_z(self, uv, center, normal):
        return ((center - self.origin) @ normal) / (self.rays(uv) @ normal)

    def world(self, uv, z):
        return self.origin + self.rays(uv) * z[:, None]


def frozen_pixel_decoder(plan):
    """Share only the registered image decoder. All metric estimation below is independent."""
    tree = RAW / "runtime-source"
    build_file = tree / "runtime-build.json"
    lock = read_pinned(build_file, plan["inputs_sha256"][str(build_file.relative_to(REPO))])
    names = (
        "scripts/graduation/g1_dual_observer.py",
        "src/cloud_edge_robot_arm/vision/pose_markers.py",
        "scripts/graduation/g1_dual_asset.py",
        "src/cloud_edge_robot_arm/vision/observations.py",
    )
    for name in names:
        require(digest((tree / name).read_bytes()) == lock["runtime_files_sha256"][name], name)
    sys.path[:0] = [str(tree), str(tree / "src")]
    spec = importlib.util.spec_from_file_location("frozen_conflict_decoder", tree / names[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for import_name, src in (
        ("cloud_edge_robot_arm.vision.pose_markers", names[1]),
        ("scripts.graduation.g1_dual_asset", names[2]),
        ("cloud_edge_robot_arm.vision.observations", names[3]),
    ):
        require(
            Path(sys.modules[import_name].__file__).resolve() == tree / src,
            f"unexpected decoder dependency: {import_name}",
        )
    return module._decode, {name: lock["runtime_files_sha256"][name] for name in names}


def depths_at(quad, raw_z, camera, true_center, true_rot, half):
    # The archived estimator locates the fifth sample at the arithmetic mean of the four pixels.
    uv = np.vstack((quad, quad.mean(axis=0)))
    pixel_plane = camera.plane_z(uv, true_center, true_rot[:, 2])
    medians, patches = [], []
    for k, (subpx, exact_z) in enumerate(zip(uv, pixel_plane, strict=True)):
        x, y = np.rint(subpx).astype(int)
        grid = np.array([[u, v] for v in range(y - 1, y + 2) for u in range(x - 1, x + 2)])
        z = raw_z[grid[:, 1], grid[:, 0]].astype(float)
        positive = np.isfinite(z) & (z > 0)
        expected = camera.plane_z(grid, true_center, true_rot[:, 2])
        residuals_mm = (z - expected) * 1000
        local = (camera.world(grid, expected) - true_center) @ true_rot
        inside = np.max(abs(local[:, :2]), axis=1) <= half
        measured = np.median(z) if positive.all() else np.nan
        # np.median on float32 for an odd nine-element patch returns the same observed sample.
        medians.append(measured)
        patches.append(
            dict(
                site=("corner_0", "corner_1", "corner_2", "corner_3", "center")[k],
                site_px=subpx,
                rounded_px=[x, y],
                valid_pixels=int(positive.sum()),
                pixel_centers_inside_registered_print=int(inside.sum()),
                median_optical_z_m=float(measured) if positive.all() else None,
                true_optical_z_at_site_m=exact_z,
                median_minus_true_at_site_mm=(measured - exact_z) * 1000
                if positive.all()
                else None,
                raw_minus_plane_mm_row_major=[
                    val if valid else None
                    for val, valid in zip(residuals_mm, positive, strict=True)
                ],
                nearer_than_plane_by_gt5mm=int((positive & (residuals_mm < -5)).sum()),
                nearer_than_plane_by_gt20mm=int((positive & (residuals_mm < -20)).sum()),
                farther_than_plane_by_gt5mm=int((positive & (residuals_mm > 5)).sum()),
                depth_range_mm=float(np.ptp(z[positive]) * 1000) if positive.any() else None,
                depth_mad_mm=float(np.median(abs(z[positive] - np.median(z[positive]))) * 1000)
                if positive.any()
                else None,
            )
        )
    return uv, np.asarray(medians), pixel_plane, patches


def fit_marker(camera, uv, z, lever):
    """Construct orthonormal ordered axes from 0->1 and 3->0 in the registered corner order."""
    world = camera.world(uv, z)
    corners = world[:4]
    rel = corners - corners.mean(axis=0)
    _, _, vh = np.linalg.svd(rel)
    x_axis = corners[1] - corners[0]
    x_axis /= norm(x_axis)
    normal = np.cross(x_axis, corners[0] - corners[3])
    require(norm(normal) > 1e-8, "degenerate ordered axes")
    normal /= norm(normal)
    rotation = np.column_stack((x_axis, np.cross(normal, x_axis), normal))
    center = world[4]
    return dict(
        center=center,
        rotation=rotation,
        target=center + rotation @ lever,
        edges_m=np.linalg.norm(np.roll(corners, -1, axis=0) - corners, axis=1),
        center_plane_residual_mm=float(abs((center - corners.mean(axis=0)) @ vh[-1]) * 1000),
        max_corner_plane_residual_mm=float(np.max(abs(rel @ vh[-1])) * 1000),
    )


def metric_checks(fit, marker_size, mount_rotation):
    """Report the archived metric tests even when a counterfactual is inadmissible."""
    upright = (fit["rotation"] @ mount_rotation.T)[2, 2]
    rejected = []
    if np.max(abs(fit["edges_m"] / marker_size - 1)) > 0.30:
        rejected.append("registered_marker_size_inconsistent")
    if max(fit["center_plane_residual_mm"], fit["max_corner_plane_residual_mm"]) > 2:
        rejected.append("marker_depth_not_planar")
    if upright < 0.98:
        rejected.append("registered_object_not_upright")
    return dict(
        gates_pass=not rejected,
        failed_tests_in_order=rejected,
        edge_lengths_mm=fit["edges_m"] * 1000,
        center_plane_residual_mm=fit["center_plane_residual_mm"],
        max_corner_plane_residual_mm=fit["max_corner_plane_residual_mm"],
        upright_zz=upright,
    )


def two_orders(targets):
    """Vector reductions from observed to exact substitutions, expressed in input units."""
    obs, dz, xy, both = (targets[k] for k in VARIANTS)
    depth_first = [obs - dz, dz - both]
    corners_first = [obs - xy, xy - both]
    interaction = obs - dz - xy + both
    residual = max(norm(sum(order) - (obs - both)) for order in (depth_first, corners_first))
    require(residual < 1e-8, "replacement vectors do not close")
    return dict(
        depth_first_reductions=depth_first,
        corners_first_reductions=corners_first,
        interaction=interaction,
        order_closure_error=residual,
    )


def side_row(candidate, reg, object_pose, object_tcp, camera, raw_z):
    mat = np.reshape(reg["object_T_marker"], (4, 4))
    marker = object_pose @ mat
    true_rot, true_center = marker[:3, :3], marker[:3, 3]
    lever = np.linalg.solve(mat, object_tcp)[:3, 3]
    true_target = (object_pose @ object_tcp)[:3, 3]
    require(norm(true_center + true_rot @ lever - true_target) < 1e-12, "registration mismatch")
    corners_world = np.asarray(reg["ordered_corners_marker_m"]) @ true_rot.T + true_center
    projected = camera.project(corners_world)
    side = dict(
        marker_id=reg["marker_id"],
        observed=candidate is not None,
        usable=False,
        reason="known_marker_not_observed",
        truth_center_world_m=true_center,
        truth_rotation_marker_to_world=true_rot,
        lever_marker_mm=1000 * lever,
        truth_target_world_m=true_target,
        truth_print_corners_px=projected,
    )
    if candidate is None:
        return side
    quad = np.asarray(candidate["corners"], dtype=float)
    delta = quad - projected
    lengths = np.linalg.norm(np.roll(quad, -1, axis=0) - quad, axis=1)
    side.update(
        origins=candidate["origins"],
        detected_corners_px=quad,
        sides_px=lengths,
        corner_error_xy_px=delta,
        corner_rms_px=float(np.sqrt((delta**2).sum(axis=1).mean())),
        corner_max_px=float(np.linalg.norm(delta, axis=1).max()),
    )
    height, width = raw_z.shape
    if np.any(quad < 1) or np.any(quad >= [width - 2, height - 2]):
        return {**side, "reason": "marker_boundary_clipped"}
    if min(lengths) < 8:
        return {**side, "reason": "marker_resolution_insufficient"}
    fits = {}
    for xy_tag, corners in (("detected", quad), ("projected", projected)):
        uv, measured, plane, patches = depths_at(
            corners, raw_z, camera, true_center, true_rot, reg["marker_size_m"] / 2
        )
        side[xy_tag + "_patches"] = patches
        if not np.isfinite(measured).all():
            return {**side, "reason": "marker_metric_depth_unavailable"}
        for name, z in zip(
            ("observed", "true_depth") if xy_tag == "detected" else ("true_corners", "both_true"),
            (measured, plane),
            strict=True,
        ):
            fits[name] = fit_marker(camera, uv, z, lever)
    m = fits["observed"]
    r = m["rotation"]
    checks = {
        name: metric_checks(fit, reg["marker_size_m"], mat[:3, :3]) for name, fit in fits.items()
    }
    obs_check = checks["observed"]
    side.update(
        edge_lengths_mm=obs_check["edge_lengths_mm"],
        center_plane_residual_mm=obs_check["center_plane_residual_mm"],
        max_corner_plane_residual_mm=obs_check["max_corner_plane_residual_mm"],
        upright_zz=obs_check["upright_zz"],
        variant_metric_checks=checks,
    )
    if not obs_check["gates_pass"]:
        return {**side, "reason": obs_check["failed_tests_in_order"][0]}
    center_error = (m["center"] - true_center) * 1000
    rotation_error = ((r - true_rot) @ lever) * 1000
    errors = {k: (v["target"] - true_target) * 1000 for k, v in fits.items()}
    residual = norm(errors["observed"] - center_error - rotation_error)
    require(residual < 1e-8, "single marker center and rotation do not close")
    side.update(
        usable=True,
        reason="metric_accepted",
        center_world_m=m["center"],
        rotation_marker_to_world=r,
        center_error_mm=center_error,
        rotation_lever_error_mm=rotation_error,
        target_world_m=m["target"],
        target_error_mm=errors["observed"],
        target_error_norm_mm=norm(errors["observed"]),
        center_rotation_closure_mm=residual,
        rotation_error_deg=rotation_deg(r, true_rot),
        yaw_error_deg=angle_delta_deg(yaw_deg(r), yaw_deg(true_rot)),
        normal_error_deg=float(
            np.degrees(
                np.arctan2(norm(np.cross(r[:, 2], true_rot[:, 2])), r[:, 2] @ true_rot[:, 2])
            )
        ),
        variant_target_errors_mm=errors,
        variant_yaw_errors_deg={
            k: angle_delta_deg(yaw_deg(v["rotation"]), yaw_deg(true_rot)) for k, v in fits.items()
        },
        replacements_mm=two_orders(errors),
    )
    return side


def pair_row(sides):
    a, b = sides["7"], sides["8"]
    if not a["usable"] or not b["usable"]:
        return None
    vectors = {
        k: a["variant_target_errors_mm"][k] - b["variant_target_errors_mm"][k] for k in VARIANTS
    }
    observed = vectors["observed"]
    distances = {k: norm(v) for k, v in vectors.items()}
    delta_c = a["center_error_mm"] - b["center_error_mm"]
    delta_r = a["rotation_lever_error_mm"] - b["rotation_lever_error_mm"]
    residual = max(
        norm(observed - (delta_c + delta_r)),
        norm(observed - (a["target_world_m"] - b["target_world_m"]) * 1000),
    )
    require(residual < 1e-8, "pair disagrees with signed center and rotation decomposition")
    unit = observed / distances["observed"] if distances["observed"] else None
    return dict(
        delta_7_minus_8_mm=observed,
        distance_mm=distances["observed"],
        delta_center_mm=delta_c,
        delta_rotation_lever_mm=delta_r,
        center_norm_mm=norm(delta_c),
        rotation_lever_norm_mm=norm(delta_r),
        center_along_measured_delta_mm=float(delta_c @ unit) if unit is not None else None,
        rotation_lever_along_measured_delta_mm=float(delta_r @ unit) if unit is not None else None,
        vector_closure_mm=residual,
        variant_deltas_mm=vectors,
        variant_distances_mm=distances,
        variant_metric_valid_ids={
            name: [
                int(code)
                for code, side in sides.items()
                if side["variant_metric_checks"][name]["gates_pass"]
            ]
            for name in VARIANTS
        },
        replacements_mm=two_orders(vectors),
    )


def role_keyed(rows, key):
    out = {row[key]: row for row in rows}
    require(len(out) == len(rows), f"duplicate {key}")
    return out


def case_rows(case_id, load_original, decode, blind_dir, blind_seal):
    case = RAW / "trials" / case_id
    raw = case / "instance"
    allocation = load_original(case / "allocation.json")
    geometry = allocation["geometry"]
    agreement_mm = geometry["development_dual"]["agreement_m"] * 1000
    index = load_original(raw / "pixel-index.json")
    trajectory = load_original(raw / "offline-truth.json")
    run = load_original(raw / "run.json")
    audit = load_original(raw / "online-audit.json")
    token = digest((raw / "pixel-index.json").read_bytes())
    blind = role_keyed(
        read_pinned(blind_dir / (token + ".json"), blind_seal["packets"][token]), "frame_id"
    )
    require(
        index["episode"] == trajectory["episode"]
        and index["scene"] == trajectory["scene"]
        and index["allocation_sha256"]
        == trajectory["allocation_sha256"]
        == digest((case / "allocation.json").read_bytes()),
        "foreign state or assembly",
    )
    samples = role_keyed(trajectory["samples"], "physics_step")
    roles = role_keyed(
        [
            v
            for v in run["frame_roles"]
            if v["acquired_for_this_role"] and v["label"].endswith("/feedback")
        ],
        "frame_id",
    )
    clocks = role_keyed(
        [v for v in run["action_clock_contexts"] if v["phase"] == "FEEDBACK"], "frame_id"
    )
    clocks_pre = role_keyed(
        [v for v in run["action_clock_contexts"] if v["phase"] == "PRE"], "skill"
    )
    shields = role_keyed([v for v in audit if v.get("phase") == "FEEDBACK"], "frame_id")
    accepted = role_keyed(
        [s for v in audit if v.get("phase") == "servo" for s in v["visual_samples"]],
        "observation_id",
    )
    require(set(accepted) == set(clocks) == set(shields), "online accepted identities differ")
    rcpts = [
        v["receipt"]["action_result"] for v in audit if v.get("phase") == "actual_executor_return"
    ]
    fail = [v for v in rcpts if not v["success"]]
    require(
        len(fail) == 1 and fail[0]["error_code"] == "VISUAL_SERVO_REJECTED",
        "unexpected controller return",
    )
    entry = [r for r in index["frames"] if r["label"].endswith("/feedback")]
    require(
        list(roles) == [r["frame_id"] for r in entry]
        and set(roles) - set(clocks) == {entry[-1]["frame_id"]},
        "missing, extra or misordered online feedback",
    )
    rows, previous = [], {}
    for r in entry:
        fid, step = r["frame_id"], r["physics_step"]
        stage = r["label"].split("/")[0]
        state = samples[step]
        frame = load_original(raw / r["file"], r["file_sha256"])
        role = roles[fid]
        require(
            frame["frame_id"] == fid
            and role["label"] == r["label"]
            and role["physics_step"] == step
            and frame["sim_time_s"] == state["sim_time_s"] == role["sim_time_s"]
            and frame["episode_id"] == index["episode"] == state["episode_id"] == role["episode_id"]
            and frame["scene_id"] == index["scene"]
            and frame["checksum_sha256"] == r["checksum_sha256"] == role["checksum_sha256"]
            and all(frame[k] == v for k, v in geometry["camera"].items()),
            "crossed frame/step/calibration",
        )
        with Image.open(io.BytesIO(base64.b64decode(frame["rgb_png_base64"], validate=True))) as im:
            gray = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2GRAY)
        candidates, ambiguous, n_rejected = decode(gray)
        ids = sorted(x["id"] for x in candidates)
        require(
            not ambiguous and set(ids) <= {7, 8} and len(ids) == len(set(ids)),
            "unknown identity during independent readback",
        )
        candidates = {v["id"]: v for v in candidates}
        depth = np.frombuffer(
            base64.b64decode(frame["depth_float32_base64"], validate=True), "<f4"
        ).reshape(gray.shape)
        require(
            frame["depth_convention"] == "optical_z_m"
            and np.array_equal(
                np.frombuffer(
                    base64.b64decode(frame["valid_mask_base64"], validate=True), np.uint8
                ).reshape(gray.shape)
                > 0,
                np.isfinite(depth) & (depth > 0),
            ),
            "invalid optical depth convention or mask",
        )
        object_pose = np.eye(4)
        object_pose[:3, :3] = np.reshape(state["object_geom_rotation_row_major"], (3, 3))
        object_pose[:3, 3] = state["object_geom_position_m"]
        sides = {}
        for code, reg in geometry["development_dual"]["markers"].items():
            side = side_row(
                candidates.get(int(code)),
                reg,
                object_pose,
                np.reshape(geometry["object_to_tcp"], (4, 4)),
                Camera(frame),
                depth,
            )
            if side["usable"] and code in previous:
                prior_step, prior_r, prior_true_r, prior_ordinal = previous[code]
                side.update(
                    previous_usable_step=prior_step,
                    intervening_feedbacks=len(rows) - prior_ordinal - 1,
                    rotation_jump_deg=rotation_deg(prior_r, side["rotation_marker_to_world"]),
                    truth_rotation_jump_deg=rotation_deg(
                        prior_true_r, side["truth_rotation_marker_to_world"]
                    ),
                    yaw_jump_deg=angle_delta_deg(
                        yaw_deg(side["rotation_marker_to_world"]), yaw_deg(prior_r)
                    ),
                )
            if side["usable"]:
                previous[code] = (
                    step,
                    side["rotation_marker_to_world"],
                    side["truth_rotation_marker_to_world"],
                    len(rows),
                )
            sides[code] = side
        usable = sorted(int(k) for k, v in sides.items() if v["usable"])
        pair = pair_row(sides)
        reason = "development_registered_current_rgbd" if usable else "known_marker_not_observed"
        if pair and pair["distance_mm"] > agreement_mm:
            reason = "dual_marker_grasp_conflict"
        if ids and not usable:
            reasons = {sides[str(i)]["reason"] for i in ids}
            reason = next(iter(reasons)) if len(reasons) == 1 else "no_valid_registered_marker"
        archived = blind[fid]
        require(
            (archived["observed_ids"], archived["usable_ids"], archived["reason"])
            == (ids, usable, reason)
            and archived["physics_step"] == step
            and archived["file_sha256"] == r["file_sha256"]
            and archived["checksum_sha256"] == frame["checksum_sha256"],
            "frozen blind readback mismatch",
        )
        blind_error_mm = max(
            (
                norm(sides[str(k)]["target_world_m"] - archived["per_id"][str(k)]["tcp_m"]) * 1000
                for k in usable
            ),
            default=0,
        )
        require(blind_error_mm < 1e-6, "independent per-marker target differs from frozen readback")
        clock = clocks.get(fid)
        if clock:
            online = accepted[fid]["development_dual_marker"]
            require(
                clock["absolute"] == step
                and clock["episode"] == index["episode"]
                and clock["skill"] == stage
                and clock["checksum_sha256"] == frame["checksum_sha256"]
                and shields[fid]["step_id"] == clock["step_id"]
                and online["frame_id"] == fid
                and online["checksum"] == frame["checksum_sha256"]
                and online["observed_ids"] == ids
                and online["usable_ids"] == usable
                and online["selected_id"] == min(usable)
                and reason == "development_registered_current_rgbd"
                and norm(sides[str(min(usable))]["target_world_m"] - online["grasp_world_m"])
                < 1e-9,
                "accepted feedback differs from online evidence",
            )
            online_distance = online["target_disagreement_m"]
            require(
                (online_distance is None and pair is None)
                or (pair is not None and abs(pair["distance_mm"] - online_distance * 1000) < 1e-6),
                "pair disagreement differs from online accepted value",
            )
        else:
            expected_message = (
                "servo registered marker geometry unavailable"
                if reason == "known_marker_not_observed" and not ids
                else "servo registered marker rejected: " + reason
            )
            require(
                run["stop"]["skill"] == stage
                and run["stop"]["physics_step"] == step
                and fail[0]["action_type"] == stage
                and fail[0]["details"]["reason"] == expected_message
                and fail[0]["details"]["physics_steps"] + clocks_pre[stage]["absolute"] == step
                and reason != "development_registered_current_rgbd",
                "refusal receipt and feedback differ",
            )
        rows.append(
            dict(
                case=case_id,
                episode=index["episode"],
                frame_id=fid,
                checksum_sha256=r["checksum_sha256"],
                file_sha256=r["file_sha256"],
                frame_file=r["file"],
                ordinal=len(rows),
                physics_step=step,
                sim_time_s=frame["sim_time_s"],
                stage=stage,
                command_seq=clocks_pre[stage]["command_seq"],
                feedback_clock_recorded=bool(clock),
                online_accepted=bool(clock),
                executor_refusal_message=None if clock else fail[0]["details"]["reason"],
                observed_ids=ids,
                usable_ids=usable,
                rejected_quad_count=n_rejected,
                reason=reason,
                markers=sides,
                pair=pair,
                blind_target_max_delta_mm=blind_error_mm,
            )
        )
    return rows


def compact(row):
    data = {
        k: row[k]
        for k in (
            "ordinal",
            "physics_step",
            "frame_id",
            "frame_file",
            "stage",
            "reason",
            "observed_ids",
            "usable_ids",
            "feedback_clock_recorded",
            "executor_refusal_message",
            "pair",
        )
    }
    data["markers"] = {}
    for k, side in row["markers"].items():
        if not side["usable"]:
            data["markers"][k] = {k: side[k] for k in ("observed", "reason")}
            continue
        s = {
            k: side[k]
            for k in (
                "origins",
                "corner_rms_px",
                "corner_max_px",
                "corner_error_xy_px",
                "variant_yaw_errors_deg",
                "center_error_mm",
                "rotation_lever_error_mm",
                "target_error_mm",
                "target_error_norm_mm",
                "rotation_error_deg",
                "yaw_error_deg",
                "normal_error_deg",
                "center_plane_residual_mm",
                "max_corner_plane_residual_mm",
            )
        }
        s["variant_failed_tests"] = {
            v: check["failed_tests_in_order"] for v, check in side["variant_metric_checks"].items()
        }
        s.update(
            {
                k: side.get(k)
                for k in (
                    "previous_usable_step",
                    "intervening_feedbacks",
                    "rotation_jump_deg",
                    "truth_rotation_jump_deg",
                    "yaw_jump_deg",
                )
            }
        )
        for key in ("detected", "projected"):
            patches = side[key + "_patches"]
            s[key + "_patches"] = {
                "median_minus_true_site_mm": [p["median_minus_true_at_site_mm"] for p in patches],
                "nearer_by_gt5mm_of_9": [p["nearer_than_plane_by_gt5mm"] for p in patches],
                "nearer_by_gt20mm_of_9": [p["nearer_than_plane_by_gt20mm"] for p in patches],
                "farther_by_gt5mm_of_9": [p["farther_than_plane_by_gt5mm"] for p in patches],
            }
        data["markers"][k] = s
    return data


def missing_intervals(rows):
    intervals = []
    for row in rows:
        if row["pair"] is not None:
            continue
        group = (row["stage"], row["usable_ids"])
        if (
            intervals
            and row["ordinal"] == intervals[-1]["last_ordinal"] + 1
            and group == (intervals[-1]["stage"], intervals[-1]["usable_ids"])
        ):
            intervals[-1].update(last_ordinal=row["ordinal"], last_step=row["physics_step"])
            intervals[-1]["feedbacks"] += 1
        else:
            intervals.append(
                dict(
                    first_ordinal=row["ordinal"],
                    last_ordinal=row["ordinal"],
                    first_step=row["physics_step"],
                    last_step=row["physics_step"],
                    feedbacks=1,
                    usable_ids=row["usable_ids"],
                    stage=row["stage"],
                )
            )
    return intervals


def case_summary(rows, reviews):
    available = [r for r in rows if r["pair"]]
    crossed = [r for r in available if r["pair"]["distance_mm"] > 10]
    last = rows[-1]
    case = last["case"]
    review = reviews.get(case)
    if review:
        require(
            len(crossed) == 1
            and crossed[0]["frame_id"] == review["frame_id"] == last["frame_id"]
            and review["physics_step"] == last["physics_step"]
            and review["frame_file_sha256"] == last["file_sha256"]
            and review["agreement_threshold_m"] == 0.010,
            "formal conflict event mismatch",
        )
        old = review["recomputed_distance_m"] * 1000
        computed = last["pair"]["distance_mm"]
        require(
            abs(computed - old) <= 0.001 and round(computed, 3) == round(old, 3),
            "formal distance mismatch",
        )
        check = dict(
            formal_distance_mm=old,
            independent_distance_mm=computed,
            absolute_delta_mm=abs(computed - old),
        )
    else:
        require(not crossed, "unexpected first disagreement above threshold")
        check = None
    before = [r for r in available if r["ordinal"] < last["ordinal"]]
    previous = before[-1]
    distance = [r["pair"]["distance_mm"] for r in before]
    return dict(
        feedbacks=len(rows),
        two_usable=len(available),
        one_usable=sum(len(r["usable_ids"]) == 1 for r in rows),
        zero_usable=sum(not r["usable_ids"] for r in rows),
        online_accepted=sum(r["online_accepted"] for r in rows),
        stages=dict(Counter(r["stage"] for r in rows)),
        first_feedback=compact(rows[0]),
        immediately_before_stop=compact(rows[-2]),
        last_paired_before_stop=compact(previous),
        first_over_10mm_step=crossed[0]["physics_step"] if crossed else None,
        first_stop=compact(last),
        missing_pair_intervals=missing_intervals(rows),
        previous_pair_to_stop={
            "step_gap": last["physics_step"] - previous["physics_step"],
            "time_gap_s": last["sim_time_s"] - previous["sim_time_s"],
            "intervening_feedbacks": last["ordinal"] - previous["ordinal"] - 1,
        },
        prior_pair_distance_mm=dict(
            n=len(distance),
            median=float(np.median(distance)),
            p90=float(np.percentile(distance, 90)),
            maximum=max(distance),
        ),
        frozen_distance_crosscheck=check,
    )


def make_figure(per_case, path):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import font_manager
    from matplotlib import pyplot as plt
    from matplotlib.ticker import MaxNLocator

    font = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    if Path(font).is_file():
        # This collection includes Chinese glyphs at the default face index.
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=font).get_name()
    plt.rcParams["axes.unicode_minus"] = False
    fig, panels = plt.subplots(3, 2, figsize=(12.8, 9.3), height_ratios=(1.35, 1.1, 0.9))
    fig.subplots_adjust(left=0.078, right=0.979, bottom=0.093, top=0.875, wspace=0.22, hspace=0.57)
    fig.suptitle("两次双码拒绝的反馈轨迹与几何分解", x=0.078, y=0.975, ha="left", fontsize=19)
    fig.text(
        0.078,
        0.928,
        "G1 正式仿真冻结帧  ·  ID 7 抓取点减 ID 8 抓取点  ·  单位毫米",
        fontsize=11,
        color="#374151",
    )
    conflict_cases = ("f01-dual", "f04-dual")
    substitution_max = max(
        max(per_case[c][-1]["pair"]["variant_distances_mm"].values()) for c in conflict_cases
    )
    for column, case in enumerate(conflict_cases):
        rows = per_case[case]
        last = rows[-1]
        first_step = max(0, last["physics_step"] - 176)
        subset = [r for r in rows if r["physics_step"] >= first_step]
        ax = panels[0, column]
        xs = [r["physics_step"] for r in subset]
        for r in subset:
            if r["pair"] is None:
                ax.axvspan(r["physics_step"] - 4, r["physics_step"] + 4, color="#e6e9ed", lw=0)
        dist = [r["pair"]["distance_mm"] if r["pair"] else np.nan for r in subset]
        ax.plot(xs, dist, "o-", color="#125a79", ms=3.2, lw=1.7, label="双码点距")
        ax.axhline(10, color="#aa3731", ls="--", lw=1.2, label="冻结上限 10")
        ax.scatter([last["physics_step"]], [dist[-1]], s=39, color="#aa3731", zorder=4)
        ax.set_ylim(0, 15.6)
        ax.set_xlim(xs[0] - 3, xs[-1] + 4)
        ax.xaxis.set_major_locator(MaxNLocator(6, integer=True))
        ax.set_xlabel("复位后物理步（灰色为单码反馈）")
        ax.set_ylabel("抓取点距 (mm)")
        ax.set_title(
            f"{case[:3]}  |  首停第 {last['physics_step']} 步", loc="left", fontweight="bold"
        )
        ax.legend(loc="upper left", fontsize=8.3, ncol=2)
        pair = last["pair"]
        ax = panels[1, column]
        ax.set_title("首停向量分量（世界坐标）", loc="left", fontweight="bold")
        xs = np.arange(3)
        for shift, key, color, label in [
            (-0.24, "delta_center_mm", "#299b86", "标记中心"),
            (0, "delta_rotation_lever_mm", "#d68a3c", "旋转×杆臂"),
            (0.24, "delta_7_minus_8_mm", "#185778", "两码合计"),
        ]:
            ax.bar(xs + shift, pair[key], width=0.23, color=color, label=label)
        ax.set_xticks(xs, ("X", "Y", "Z"))
        ax.axhline(0, color="#797f84", linewidth=0.8)
        ax.set_ylim(-4, 16)
        ax.set_yticks([-4, 0, 4, 8, 12, 16])
        ax.set_ylabel("有符号差 (mm)")
        ax.legend(loc="upper left", ncol=3, fontsize=8.1, handlelength=1.1, columnspacing=0.9)
        ax = panels[2, column]
        ax.set_title("首停两码点距（离线单帧替换）", loc="left", fontweight="bold")
        values = [pair["variant_distances_mm"][k] for k in VARIANTS]
        bar = ax.bar(
            np.arange(4), values, width=0.63, color=["#185778", "#5c9a92", "#cf9458", "#b2b7bd"]
        )
        for patch, name in zip(bar, VARIANTS, strict=True):
            if len(pair["variant_metric_valid_ids"][name]) != 2:
                patch.set_edgecolor("#704d20")
                patch.set_hatch("///")
        ax.bar_label(bar, labels=[f"{n:.3f}" for n in values], padding=2, fontsize=9)
        ax.set_xticks(np.arange(4), ("实测", "真平面深度", "真投影角点", "两项替换"))
        ax.set_ylim(0, substitution_max * 1.18)
        ax.axhline(10, color="#aa3731", ls="--", lw=1.1)
        ax.set_ylabel("抓取点距 (mm)")
    for ax in panels.flat:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.16)
        ax.set_axisbelow(True)
    fig.text(
        0.078,
        0.025,
        "真值取同槽同步物理步。灰色时段仅返回单码。斜线柱为重采后未通过标记几何检验的诊断值。",
        fontsize=10,
        color="#374151",
    )
    fig.savefig(path, dpi=145, metadata={"Software": "G1 frozen feedback conflict diagnosis"})
    plt.close(fig)


def main(output):
    require(
        RAW not in (output.resolve(), *output.resolve().parents), "output overlaps frozen originals"
    )
    plan = read_pinned(ROUND / "plan.json", PLAN_SHA)

    def planned(path):
        return read_pinned(path, plan["inputs_sha256"][str(path.relative_to(REPO))])

    manifest = planned(RAW / "originals-manifest.json")["files"]

    def original(path, extra_sha=None):
        authoritative = manifest[str(path.relative_to(RAW))]["sha256"]
        require(
            extra_sha is None or extra_sha == authoritative,
            "frame index and originals manifest disagree",
        )
        return read_pinned(path, authoritative)

    seal_sha = planned(FORMAL / "scoring-verification.public.json")["blind_seal_sha256"]
    blind_dirs = list(RAW.glob("scoring-*/blind-one"))
    require(len(blind_dirs) == 1, "expected one frozen blind-one directory")
    blind_dir = blind_dirs[0]
    blind_seal = read_pinned(blind_dir / "seal.json", seal_sha)
    reviews = {
        r["id"]: r
        for r in planned(FORMAL / "evidence-verification.public.json")["independent_stop_reviews"]
    }
    decode, decoder_files = frozen_pixel_decoder(plan)
    per_case = {case: case_rows(case, original, decode, blind_dir, blind_seal) for case in CASES}
    summaries = {case: case_summary(rows, reviews) for case, rows in per_case.items()}
    matched_steps = sorted(
        {
            r["physics_step"]
            for c, s in summaries.items()
            if c in reviews
            for r in (s["last_paired_before_stop"], s["immediately_before_stop"], s["first_stop"])
        }
    )
    controls = {
        case: [
            compact(r)
            for r in rows
            if r["stage"] == "MOVE_ABOVE" and r["physics_step"] in matched_steps
        ]
        for case, rows in per_case.items()
    }
    all_rows = [r for rows in per_case.values() for r in rows]
    validated = [r["pair"] for r in all_rows if r["pair"] is not None]
    sides = [s for r in all_rows for s in r["markers"].values() if s["usable"]]
    output.mkdir(parents=True, exist_ok=True)
    packed = gzip.compress(
        json_bytes({"schema": "g1.formal.failure.conflict.feedback.v1", "feedback": all_rows}),
        compresslevel=9,
        mtime=0,
    )
    detail_name = "conflict-feedback.public.json.gz"
    (output / detail_name).write_bytes(packed)
    summary = dict(
        schema="g1.formal.failure.conflict.summary.v1",
        plan_sha256=PLAN_SHA,
        frozen_blind_seal_sha256=seal_sha,
        scope="Retrospective frozen feedback. All substitutions use saved images and state.",
        basis=(
            "World-frame marker-center error plus (R_est-R_truth) times the marker-to-grasp lever. "
            "The signed pair difference is ID 7 minus ID 8. Scalar contributions project onto "
            "the measured pair vector."
        ),
        factors={
            "observed": (
                "Detected ordered corners and mean corner pixel, with archived 3x3 median "
                "optical-z at each site."
            ),
            "true_depth": (
                "Same detected corners with exact optical-z where the continuous ray intersects "
                "the registered printed plane."
            ),
            "true_corners": (
                "Projected ordered true corners with a fresh sample of the archived depth at each "
                "new rounded 3x3 footprint."
            ),
            "both_true": (
                "Projected corners and exact true-plane depth. The fifth site still uses the mean "
                "of projected corners, as in the recorded estimator."
            ),
            "contrast": (
                "Depth-first vectors are observed minus true_depth, then true_depth minus "
                "both_true. Corners-first vectors are observed minus true_corners, then "
                "true_corners minus both_true. Interaction is observed - true_depth - "
                "true_corners + both_true. These are conditional vector differences."
            ),
            "raw_depth_residual": (
                "Raw optical-z minus projected plane optical-z at each integer pixel center, "
                "in mm. A negative value is nearer. Geometry identity is unconstrained."
            ),
        },
        indexing=(
            "One row per consumed /feedback image, including the rejection before its Shield "
            "clock. Same-step terminal, PRE, POST and servo reference images have other roles. "
            "Command sequence comes from that stage's PRE binding. Accepted feedback also matches "
            "its own clock."
        ),
        input_versions={"numpy": np.__version__, "opencv": cv2.__version__},
        frozen_decoder_dependencies_sha256=decoder_files,
        substitution_gates=(
            "All four target vectors retain the unconstrained geometric estimate to evaluate "
            "two-factor interaction. variant_metric_valid_ids identifies which marker estimates "
            "pass the original per-marker geometric checks under each archived-frame substitution."
        ),
        comparison_operators={
            "time": (
                "Previous usable same ID, with gap length. Per-step comparisons match the stage "
                "and retain the individual placement."
            ),
            "corner_rms": "RMS Euclidean pixel error for the four ordered corners.",
            "angle": "Principal SO(3) angle. Yaw is the signed world-Z heading of marker x.",
        },
        total_feedbacks=len(all_rows),
        total_both=len(validated),
        total_usable_sides=len(sides),
        verified_frozen_accepted_and_refusal_events=len(all_rows),
        max_independent_vs_frozen_target_delta_mm=max(
            r["blind_target_max_delta_mm"] for r in all_rows
        ),
        maximum_marker_center_rotation_closure_mm=max(
            s["center_rotation_closure_mm"] for s in sides
        ),
        maximum_pair_vector_closure_mm=max(p["vector_closure_mm"] for p in validated),
        maximum_replacement_order_closure_mm=max(
            p["replacements_mm"]["order_closure_error"] for p in validated
        ),
        file=detail_name,
        file_sha256=digest(packed),
        cases=summaries,
        matched_stage_steps=matched_steps,
        matched_stage_controls=controls,
    )
    (output / "conflict-summary.public.json").write_bytes(json_bytes(summary, indent=2))
    make_figure(per_case, output / "conflict-decomposition.png")
    print(f"{len(all_rows)} feedbacks, {len(validated)} measured pairs, {len(sides)} marker poses")
    for case, s in summaries.items():
        print(
            case, s["two_usable"], s["first_stop"]["physics_step"], s["frozen_distance_crosscheck"]
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROUND)
    main(parser.parse_args().output)
