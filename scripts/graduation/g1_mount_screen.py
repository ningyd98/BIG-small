"""Sealed same-state RGB-D screening and real zero-step registration of the three G1 mounts."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import mujoco
import numpy as np
from scripts.graduation import dynamic_vision as runtime
from scripts.graduation import g1_mount_geometry as geo
from scripts.graduation import proposal_camera as cam
from scripts.graduation import proposal_translated as translated
from scripts.graduation.dynamic_vision_score import checked_steps, frame_from_row
from scripts.graduation.perception_io import ROOT, check_sources, pinned, read, sha, write
from scripts.graduation.perception_pixels import biased_observation
from scripts.graduation.proposal_terminal_visibility import HAND

from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame

PLAN_SHA = "62e4c93a03f37fcb1ebd20ac660c09837c225f2b9651960701725c742914bef7"
FILES = [
    f"scripts/graduation/{n}.py"
    for n in (
        "g1_mount_geometry",
        "g1_mount_screen",
        "g1_mount_screen_pixels",
        "g1_mount_screen_score",
    )
]
MOUNT_IDS = ("original", "r579", "component_v1")


def choose(rows):
    geo.require(set(rows) == set(MOUNT_IDS), "incomplete mount candidates")
    for row in rows.values():
        geo.require(row["evaluated"] == 8 and 0 <= row["usable"] <= 8, "incomplete screen")
    candidates = [m for m in MOUNT_IDS[1:] if rows[m]["native"] and rows[m]["probe_successes"]]
    if not candidates:
        geo.require(rows["r579"]["native"], "legal fallback family missing")
        return "r579"
    return max(candidates, key=lambda m: (rows[m]["usable"], m == "r579"))


def plan(raw, path):
    p = pinned(path, PLAN_SHA)
    geo.require(sha(path.with_suffix(".md")) == p["plan_md_sha256"], "plan markdown changed")
    check_sources({"sources_sha256": p["input_sha256"]})
    geo.require(
        os.environ.get("MUJOCO_GL") == "egl" and shutil.disk_usage(raw).free >= 16 * 2**30,
        "EGL and 16 GiB trial budget required",
    )
    prior = Path(p["private_source"]) / "terminal-visibility"
    old = pinned(
        ROOT / prior / "observation-allocation.json",
        p["input_sha256"][str(prior / "observation-allocation.json")],
    )
    sources = old["source_terminals"]
    geo.require(
        sorted((s["id"], s["step"], s["label"]) for s in sources)
        == sorted(tuple(v) for v in p["source_terminal"]),
        "wrong registered terminals",
    )
    families, mechanics = {}, {}
    for m in p["mounts"]:
        g, reason = geo.descriptor(m)
        families[m["id"]] = {"descriptor": g, "native_error": reason}
        mechanics[m["id"]] = geo.audit_mount(m)
        geo.require(
            (reason is None) == m["expected_native_family_admissible"], "native policy differs"
        )
    geo.require(
        len({s["compiled_physics_sha256"] for s in mechanics.values()}) == 1
        and families["original"]["descriptor"] == old["geometry"]["nominal"]
        and tuple(families) == MOUNT_IDS,
        "compiled physics or old geometry changed",
    )
    write(
        raw / "allocation.json",
        {
            "schema": "g1.marker-mount.screen.v1",
            "plan_sha256": PLAN_SHA,
            "plan_md_sha256": p["plan_md_sha256"],
            "plan": str(path.relative_to(ROOT)),
            "sources_sha256": {n: sha(ROOT / n) for n in FILES},
            "mounts": p["mounts"],
            "families": families,
            "mechanics": mechanics,
            "source_terminals": sources,
            "episodes": old["episodes"],
            "prior": str(prior),
            "historical_geometry": old["geometry"],
            "old_original_asset_sha256": old["asset_sha256"],
            "noise_std_m": p["paired_noise_std_m"],
            "seed_offset": old["paired_seed_offset"],
            "probe_poses": p["qualification_probe_poses_xyz_yaw"],
            "state_limits": cam.CHECK_LIMITS,
            "verified_plan_input_files": len(p["input_sha256"]),
        },
    )


class FrameStore:
    """Opaque raw-frame index for the reader, separate binding/provenance for scoring."""

    def __init__(self, raw):
        self.raw = raw
        self.pixels = raw / "pixels"
        self.pixels.mkdir()
        self.frames, self.roles = {}, {}

    def add(self, role, f, **facts):
        audit = {
            "episode": f.episode_id,
            "scene": f.scene_id,
            "frame_id": f.frame_id,
            "checksum": f.checksum_sha256,
            "sim_time_s": f.sim_time_s,
            "calibration_version": f.calibration_version,
        }
        key = uuid4().hex
        geo.require(role not in self.roles and key not in self.frames, "duplicate frame role")
        path = self.pixels / (key + ".json")
        write(path, f.model_dump(mode="json"))
        self.frames[key] = {"file": path.name, "sha256": sha(path)}
        self.roles[role] = {"key": key, **audit, **facts}
        return self.roles[role]

    def seal(self, a, h):
        write(
            self.pixels / "index.json",
            {
                "allocation_sha256": h,
                "frames": self.frames,
                "hypotheses": {m: d["descriptor"] for m, d in a["families"].items()},
            },
        )
        write(self.raw / "roles.json", {"allocation_sha256": h, "roles": self.roles})
        write(
            self.raw / "capture-seal.json",
            {
                "allocation_sha256": h,
                "index_sha256": sha(self.pixels / "index.json"),
                "roles_sha256": sha(self.raw / "roles.json"),
            },
        )


def source_states(a, s):
    root = ROOT / a["episodes"] / s["id"] / "instance"
    acquisition = pinned(root / "acquisition-seal.json", s["seal_sha256"])
    index = pinned(root / "pixel-index.json", acquisition["index_sha256"])
    truth = pinned(root / "offline-truth.json", acquisition["truth_sha256"])
    geo.require(
        index["frames"][-3:] == s["references"]
        and index["episode"] == s["episode"]
        and index["scene"] == s["scene"]
        and truth["episode"] == s["episode"]
        and index["allocation_sha256"] == s["registration_sha256"],
        "source terminal changed",
    )
    states = checked_steps(
        truth["samples"], s["episode"], a["old_original_asset_sha256"], truth["asset_sha256"]
    )
    geo.require(max(states) == s["step"], "wrong terminal step")
    return root, states


def capture(camera, data, rng_seed, noise, scene, episode):
    sensor, ids, labels, hashes = camera.capture_with_instances(
        data,
        rng=np.random.default_rng(rng_seed),
        noise_std_m=noise,
        scene_id=scene,
        episode_id=episode,
    )
    geo.require(len(hashes) == 3 and len(set(hashes)) == 1, "RGB/depth/instance pose differs")
    f = observation_from_sensor_frame(sensor, source="mujoco_camera")
    return f, np.asarray(ids, dtype="<i2").reshape(f.height, f.width), labels, hashes[0]


def restore_and_capture(backend, camera, row, seed, noise, episode, view, geometry):
    backend.set_camera_position(translated.POSITION[view])
    model, data = backend._model, backend._data
    residuals = cam.restore(model, data, row)
    q = model.joint("object_free").dofadr[0]
    data.qvel[q : q + 6] = row["object_linear_velocity_m_s"] + row["object_angular_velocity_rad_s"]
    mujoco.mj_forward(model, data)
    output = capture(camera, data, seed, noise, "G1_SCREEN", episode)
    runtime.validate_camera(output[0], geometry)
    geo.require(
        all(residuals[k] <= cam.CHECK_LIMITS[k] for k in residuals)
        and data.time == row["sim_time_s"],
        "unreconstructed source pose",
    )
    return output, residuals


def geometry_at_frame(model, data):
    quiet = model.geom(geo.PREFIX + "quiet").id
    finger_distances = {}
    for name in HAND:
        distance = mujoco.mj_geomDistance(model, data, quiet, model.geom(name).id, 5.0, None)
        finger_distances[name] = float(distance)
    return {
        "object_center_m": data.geom("object_geom").xpos.tolist(),
        "object_rotation": data.geom("object_geom").xmat.tolist(),
        "tcp_m": data.site("tcp").xpos.tolist(),
        "board_to_hand_surface_distance_m": finger_distances,
    }


def capture_screen(raw, a, h):
    store = FrameStore(raw)
    segments = raw / "segmentation"
    segments.mkdir()
    old = ROOT / a["prior"]
    old_capture = read(old / "observation-seal.json")
    old_roles = pinned(old / "observation/roles.json", old_capture["roles_sha256"])
    old_pixels = old / "observation/pixels"
    old_index = pinned(old_pixels / "index.json", old_capture["frames_sha256"])
    states = {}
    for s in a["source_terminals"]:
        ident = s["id"]
        root, series = source_states(a, s)
        states[ident] = {k: series[k] for k in (s["step"] - 8, s["step"])}
        for role, ref in zip(("previous", "rejected", "terminal"), s["references"], strict=True):
            f = frame_from_row(
                root, ref, s["episode"], s["scene"], a["historical_geometry"][s["source_view"]]
            )
            runtime.validate_camera(f, a["historical_geometry"][s["source_view"]])
            store.add(
                f"{ident}/source/{role}",
                f,
                original_sha256=ref["file_sha256"],
                step=ref["physics_step"],
            )
        role = f"{ident}/nominal/normal"
        idx = old_index["frames"][old_roles["role_map"][role]]
        store.add(
            f"{ident}/archived-nominal",
            cam.load_frame(old_pixels, idx),
            original_sha256=idx["sha256"],
        )
    for m in a["mounts"]:
        name = m["id"]
        g = a["families"][name]["descriptor"]
        backend = MuJoCoPhysicsBackend()
        backend.initialize(translated.config({"geometry": g}, 24112900))
        model, data = backend._model, backend._data
        renderer = MuJoCoRGBDCamera(mujoco, model, width=320, height=240)
        try:
            arm_names = list(cam.arm_geometries(model).values())
            for i, s in enumerate(a["source_terminals"]):
                ident = s["id"]
                step = s["step"]
                seed = a["seed_offset"] + 2 * i
                episode = uuid4().hex
                (f, mask, labels, state_hash), residuals = restore_and_capture(
                    backend,
                    renderer,
                    states[ident][step],
                    seed,
                    a["noise_std_m"],
                    episode,
                    "nominal",
                    g,
                )
                mask_path = segments / (uuid4().hex + ".npy")
                with mask_path.open("xb") as stream:
                    np.save(stream, mask, allow_pickle=False)
                store.add(
                    f"{ident}/{name}/normal",
                    f,
                    source_episode=s["episode"],
                    step=step,
                    state_sha256=state_hash,
                    residuals=residuals,
                    seed=seed,
                    segmentation={
                        "file": mask_path.name,
                        "sha256": sha(mask_path),
                        "labels": labels,
                    },
                    arm_geoms=arm_names,
                    geometry=geometry_at_frame(model, data),
                )
                if name == "original":
                    view = s["source_view"]
                    for role, at in (("previous", step - 8), ("rejected", step)):
                        if role == "rejected" and view == "nominal":
                            continue
                        (f, _, _, st), errs = restore_and_capture(
                            backend,
                            renderer,
                            states[ident][at],
                            seed + int(view == "translated"),
                            a["noise_std_m"],
                            episode,
                            view,
                            a["historical_geometry"][view],
                        )
                        store.add(
                            f"{ident}/replay/{role}",
                            f,
                            step=at,
                            source_episode=s["episode"],
                            state_sha256=st,
                            residuals=errs,
                        )
        finally:
            renderer.close()
            backend.shutdown()
    store.seal(a, h)


def bootstrap(f, g, sources):
    try:
        registration = NativeGeometryRegistration(g)
        registration.validate_asset(ROOT)
    except ValueError as exc:
        return {"ok": False, "stage": "native_geometry", "reason": str(exc)}
    try:
        tracker = runtime.bootstrap_registered_collection_tracker_v2(
            f,
            registration,
            source_root=ROOT,
            source_hashes=sources,
            nominal_policy=runtime.registered_nominal_region_policy_v1(sources),
        )
    except ValueError as exc:
        return {"ok": False, "stage": "tracker_bootstrap", "reason": str(exc)}
    return {
        "ok": True,
        "stage": "tracker_bootstrap",
        "reason": None,
        "tracker": type(tracker).__name__,
    }


def probes(raw, a, h):
    decision = read(raw / "decision-seal.json")
    geo.require(sha(raw / "capture-seal.json") == decision["capture_sha256"], "unsealed screen")
    dest = raw / "probes"
    dest.mkdir()
    store = FrameStore(dest)
    results = {}
    for m in a["mounts"]:
        name = m["id"]
        g = a["families"][name]["descriptor"]
        sources = (
            runtime.source_inventory(marker_family_id=m["family"])
            if a["families"][name]["native_error"] is None
            else None
        )
        if sources is not None:
            write(dest / f"{name}-native-inventory.json", sources)
        backend = MuJoCoPhysicsBackend()
        backend.initialize(translated.config({"geometry": g}, 24112900))
        model, data = backend._model, backend._data
        camera = MuJoCoRGBDCamera(mujoco, model, width=320, height=240)
        marker_ids = [i for i in range(model.ngeom) if model.geom(i).name.startswith(geo.PREFIX)]
        geo.require(len(marker_ids) == 37, "absent-marker intervention incomplete")
        try:
            for i, (x, y, z, yaw) in enumerate(a["probe_poses"]):
                seed = 24112900 + i
                backend.reset(
                    runtime.PhysicalScenarioConfig(
                        scenario_id="G1_ZERO_STEP",
                        seed=seed,
                        object_pose=runtime.Pose(x=x, y=y, z=z),
                        object_yaw_rad=yaw,
                    )
                )
                state = camera._physics_state_hash(data)
                normal_rgba = model.geom_rgba.copy()
                for kind in ("normal", "absent"):
                    if kind == "absent":
                        model.geom_rgba[marker_ids, 3] = 0
                    try:
                        f, _, labels, observed = capture(
                            camera,
                            data,
                            seed,
                            a["noise_std_m"],
                            "G1_ZERO_STEP",
                            backend._episode_id,
                        )
                    finally:
                        model.geom_rgba[:] = normal_rgba
                    runtime.validate_camera(f, g)
                    geo.require(
                        state == observed
                        and f.sim_time_s == 0
                        and (
                            kind == "normal"
                            or not any(n.startswith(geo.PREFIX) for n in labels.values())
                        ),
                        "zero-step paired image, state, or absent-marker control changed",
                    )
                    live = bootstrap(f, g, sources)
                    key = f"{name}/{i}/{kind}"
                    results[key] = live
                    store.add(
                        key,
                        f,
                        state_sha256=state,
                        seed=seed,
                        step=0,
                        geometry=geometry_at_frame(model, data),
                    )
                    if kind == "normal":
                        invalid = biased_observation(f, None)
                        key = f"{name}/{i}/invalid-depth"
                        results[key] = bootstrap(invalid, g, sources)
                        store.add(
                            key,
                            invalid,
                            parent_checksum=f.checksum_sha256,
                            state_sha256=state,
                            step=0,
                        )
                geo.require(
                    backend.total_physics_steps == 0
                    and not backend.command_records
                    and camera._physics_state_hash(data) == state,
                    "probe dispatched/advanced",
                )
        finally:
            camera.close()
            backend.shutdown()
    store.seal(a, h)
    write(
        dest / "registration.json",
        {
            "results": results,
            "capture_sha256": sha(dest / "capture-seal.json"),
            "screen_decisions_sha256": decision["decisions_sha256"],
            "native_inventory_sha256": {p.name: sha(p) for p in dest.glob("*-inventory.json")},
            "physics_steps": 0,
            "dispatched_actions": 0,
        },
    )


def main():
    from scripts.graduation import g1_mount_screen_pixels as px
    from scripts.graduation import g1_mount_screen_score as scoring

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("prepare", "capture", "pixels", "probe", "probe-pixels", "score")
    )
    parser.add_argument("raw", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw, path = args.raw.resolve(), args.plan.resolve()
    write(
        raw / (args.mode + "-invocation.json"),
        {
            "argv": sys.argv,
            "utc": datetime.now(UTC).isoformat(),
            "interpreter": sys.executable,
            "runtime_module": runtime.__file__,
            "geometry_module": geo.__file__,
            "cwd": str(Path.cwd()),
            "gl": os.environ.get("MUJOCO_GL"),
            "PYTHONPATH": os.environ.get("PYTHONPATH"),
        },
    )
    if args.mode == "prepare":
        plan(raw, path)
        return
    h = sha(raw / "allocation.json")
    if args.mode in {"pixels", "probe-pixels"}:
        px.decide(raw / "probes" if args.mode == "probe-pixels" else raw, h)
        return
    a = pinned(raw / "allocation.json", h)
    check_sources(a)
    geo.require(sha(path) == PLAN_SHA == a["plan_sha256"], "wrong plan")
    if args.mode == "capture":
        capture_screen(raw, a, h)
    elif args.mode == "probe":
        probes(raw, a, h)
    else:
        scoring.score(raw, a, h, args.output)


if __name__ == "__main__":
    main()
