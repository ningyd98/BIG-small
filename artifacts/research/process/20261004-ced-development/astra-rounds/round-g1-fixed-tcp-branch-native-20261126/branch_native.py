"""Acquire one registered fixed-TCP static RGB-D diagnostic, then cold-read it."""

import argparse
import base64
from copy import deepcopy
import inspect
import io
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import cv2
import mujoco
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
AB = HERE.parent / "round-g1-release-camera-ab-20261126"
GEOMETRY = HERE.parent / "round-g1-fixed-tcp-branch-visibility-20261126"
sys.path[:0] = [str(AB), str(GEOMETRY)]

import release_camera_ab_capture as native
import release_camera_ab_inputs as inputs
import release_camera_ab_optics as optics
import release_camera_ab_readback as old
import screen_branch as branch

ROOT = inputs.ROOT
PLAN = inputs.read(HERE / "plan.json")
ROUNDS = ROOT / "experiments/results"
ARCHIVE = ROUNDS / "g1-release-camera-ab-20261126/static-fit-01"
VECTORS = ROUNDS / "g1-fixed-tcp-branch-visibility-20261126/branch-01"
PRIVATE = ROUNDS / PLAN["round"] / "static-fit-01"
DIRECTORIES = {"ab": AB, "archive": ARCHIVE, "geometry": GEOMETRY, "vectors": VECTORS}
read, sha, write, require = inputs.read, inputs.sha, inputs.write, inputs.require


def verify_pin_set():
    for alias, expected in PLAN["sha256"].items():
        base, name = alias.split("/", 1)
        require(sha(inputs.inside(DIRECTORIES[base], name)) == expected, f"frozen input changed: {alias}")
    seal = read(ARCHIVE / "capture-seal.json")
    for filename, digest in seal["sealed_sha256"].items():
        require(sha(inputs.inside(ARCHIVE, filename)) == digest, f"original capture member changed: {filename}")
    manifest, slots, calibration = inputs.verify_inputs()
    require(manifest == read(ARCHIVE / "input-manifest.json"), "old input manifest changed")
    require({key: slot["source"] for key, slot in slots.items()} == read(ARCHIVE / "source-slots.json"),
            "old trace/source join changed")
    return slots, calibration


def keys(condition):
    return [f"{condition}/{cid}/{tick}" for cid, ticks in PLAN["cases"].items() for tick in ticks]


def check_encoder(expected, actual):
    require(np.array_equal(expected, actual), "candidate encoder vector does not match frozen assignment")


def static_states(slots, calibration):
    frozen = read(VECTORS / "first.json")["states"]
    model = mujoco.MjModel.from_xml_path(str(native.ASSET))
    model.opt.timestep = 1 / 240
    selected, checks = {}, {}
    for condition, degrees in PLAN["conditions"].items():
        for key in keys(condition):
            source_key = "B/" + key.split("/", 1)[1]
            original = slots[source_key]
            slot = deepcopy(original)
            data = mujoco.MjData(model)
            native.restore(model, data, original, calibration)
            state = branch.State(model, data, calibration)
            sealed = frozen[source_key]
            check_encoder(state.root, sealed["baseline"]["arm_q_rad"])
            sample = sealed["branches"]["1"]["samples"][f"{degrees}.0"] if degrees else sealed["baseline"]
            q = np.asarray(sample["arm_q_rad"])
            if degrees:
                require(sample["unique_ID7_original_orientation"] and not sample["both_sides_clear_ideal_depth"],
                        f"registered geometry predicate changed: {key}")
            state.set_geometry(q)
            static = state.screen(q)
            pos, rot = branch.original.residuals(data, state.target)
            dx, dr = float(np.linalg.norm(pos)), float(np.linalg.norm(rot))
            require(dx <= PLAN["limits"]["tcp_m"] and dr <= PLAN["limits"]["tcp_rad"], f"TCP moved: {key}")
            for name in ("left_finger_geom", "right_finger_geom"):
                geom = data.geom(name)
                slot["row"]["geom"][name] = [geom.xpos.tolist(), geom.xmat.reshape(3, 3).tolist()]
            if degrees:
                tcp = data.site("tcp")
                slot["row"]["tcp_xyz_m"] = tcp.xpos.tolist()
                slot["row"]["tcp_R"] = tcp.xmat.reshape(3, 3).tolist()
                slot["row"]["q"][:7] = q.tolist()
            closure = native.restore(model, mujoco.MjData(model), slot, calibration)
            selected[key] = slot
            checks[key] = {"source": source_key, "q": slot["row"]["q"], "tcp_m": dx, "tcp_rad": dr,
                           "static": static, "candidate_fk_residual": closure}
    return selected, checks


def file_hashes():
    return {name: sha(HERE / name) for name in ("plan.md", "plan.json", "branch_native.py")}


def check_native():
    original = inputs.expand("{M}") / "src/cloud_edge_robot_arm"
    for component, relative in (
        (native.MuJoCoPhysicsBackend, "simulation/mujoco/backend.py"),
        (native.MuJoCoRGBDCamera, "simulation/mujoco/camera.py"),
        (native.observation_from_sensor_frame, "vision/observations.py"),
    ):
        require(Path(inspect.getfile(component)).resolve() == original / relative, f"non-frozen runtime: {relative}")
    require(mujoco.__version__ == native.NATIVE["mujoco_version"], "MuJoCo version changed")
    require(subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() == PLAN["head"],
            "capture planning baseline changed")


def prepare():
    check_native()
    slots, calibration = verify_pin_set()
    _, checks = static_states(slots, calibration)
    control = optics.historical_controls(slots)
    reference = checks[keys("r1")[0]]["q"]
    baseline = checks[keys("r0")[0]]["q"]
    control["swapped_candidate_rejected"] = optics.rejected(check_encoder, reference, baseline)
    require(control["swapped_candidate_rejected"], "candidate swap negative control failed")
    return {"sources": file_hashes(), "baseline": PLAN["head"], "calibration": calibration,
            "formal_originals": inputs.originals(),
            "checks": checks, "controls": control, "limits": {"exposure_attempts": 27, "integration": 0},
            "versions": {"mujoco": mujoco.__version__, "cv2": cv2.__version__, "numpy": np.__version__}}


def rgb(frame):
    with Image.open(io.BytesIO(base64.b64decode(frame.rgb_png_base64))) as image:
        return np.array(image.convert("RGB"))


def identical_baseline(actual, original):
    mask = old.mask(actual)
    present = mask & old.mask(original)

    def depth_bits(frame):
        return np.frombuffer(base64.b64decode(frame.depth_float32_base64), dtype="<u4")

    return {
        "rgb_exact": bool(np.array_equal(rgb(actual), rgb(original))),
        "mask_exact": bool(np.array_equal(mask, old.mask(original))),
        "valid_depth_bits_exact": bool(np.array_equal(depth_bits(actual)[present], depth_bits(original)[present])),
        "valid_pixels": int(present.sum()),
    }


def assert_baseline(row, key):
    require(all(row[name] for name in ("rgb_exact", "mask_exact", "valid_depth_bits_exact")),
            f"sealed B native baseline did not reproduce: {key}")


def optics_command(condition, registration):
    subprocess.run([sys.executable, "-B", __file__, "predict", condition, registration], check=True)


def seal_members():
    return {path.relative_to(PRIVATE).as_posix(): sha(path)
            for path in sorted(PRIVATE.rglob("*")) if path.is_file() and path.name != "capture-seal.json"}


def attempt(stage, selected, calibration, reg_sha):
    require(os.environ.get("MUJOCO_GL") == os.environ.get("PYOPENGL_PLATFORM") == "egl", "EGL not selected")
    cases = {case["id"]: case for case in native.PLAN["cases"]}
    originals = read(ARCHIVE / "B/index.json")["rows"]
    past = read(ARCHIVE / "B/predictions.json")["predictions"]
    original_create = native.create
    frame_ids = set()

    def save_packet(path, payload):
        original_create(path, payload)
        fresh = inputs.packet(path)
        require(fresh.frame_id not in frame_ids, "duplicate native frame")
        frame_ids.add(fresh.frame_id)
        require(len(frame_ids) <= PLAN["max_rgbd"], "native exposure ceiling exceeded")
        if stage[0] == "r0":
            tick = path.name.removesuffix(".json.gz")
            key = f"B/{path.parent.name}/{tick}"
            original = inputs.packet(inputs.inside(ARCHIVE / "B", originals[key]["packet"]))
            receipt = identical_baseline(fresh, original)
            write(path.with_name(f"{tick}-baseline.json"), receipt)
            assert_baseline(receipt, key)

    def forbid_step(*args, **kwargs):
        raise RuntimeError("registered static capture prohibits integration")

    with (
        native.device((ROOT / native.NATIVE["exclusive_lock"]).parent),
        patch.object(mujoco, "mj_step", forbid_step),
        patch.object(mujoco, "mj_step1", forbid_step),
        patch.object(mujoco, "mj_step2", forbid_step),
    ):
        for condition in PLAN["conditions"]:
            rows, resets = {}, {}
            for cid, ticks in PLAN["cases"].items():
                stage[:] = [condition, cid]
                require(ticks == cases[cid]["ticks"], f"candidate source ticks do not match case {cid}")
                with patch.object(native, "create", save_packet):
                    captured, resets[cid] = native.capture_case(
                        PRIVATE, condition, cases[cid], {tick: selected[f"{condition}/{cid}/{tick}"] for tick in ticks},
                        calibration,
                    )
                rows.update(captured)
            write(PRIVATE / condition / "index.json",
                  {"registration_sha256": reg_sha, "cases": resets, "rows": rows})
            stage[:] = [condition, "optical prediction"]
            optics_command(condition, reg_sha)
            if condition == "r0":
                predictions = read(PRIVATE / condition / "predictions.json")
                for key, row in predictions.items():
                    prior = past["B/" + key.split("/", 1)[1]]
                    for name in ("observed_ids", "usable_ids", "pose_method", "gaps_m",
                                 "observed_support_and_rim", "static_frame_eligible", "reason_codes"):
                        require(row[name] == prior[name], f"sealed B optical refusal changed: {key} {name}")


def capture():
    registration = prepare()
    selected, checks = static_states(*verify_pin_set())
    require(registration["checks"] == checks, "static selection is not repeatable")
    require(PRIVATE.resolve() == PRIVATE and not PRIVATE.exists(), "registered attempt already exists or aliases a path")
    PRIVATE.mkdir(parents=True, exist_ok=False)
    write(PRIVATE / "registration.json", registration)
    reg_sha = sha(PRIVATE / "registration.json")
    stage = ["EGL lock"]
    try:
        attempt(stage, selected, registration["calibration"], reg_sha)
        stage[:] = ["formal original digest"]
        require(registration["formal_originals"] == inputs.originals(), "formal original changed")
    except BaseException as failure:
        write(PRIVATE / "aborted.json", {"stage": stage, "type": type(failure).__name__, "detail": str(failure)})
        raise
    finally:
        members = seal_members()
        requests = sum(name.endswith("-request.json") for name in members)
        packets = sum(name.endswith(".json.gz") for name in members)
        write(PRIVATE / "capture-seal.json", {"registration_sha256": reg_sha, "requests": requests,
              "packets": packets, "complete": requests == packets == 27 and not (PRIVATE / "aborted.json").exists(),
              "sealed_sha256": members})


def predict(condition, reg_sha):
    directory = PRIVATE / condition
    index = read(directory / "index.json")
    entries = index["rows"]
    require(index["registration_sha256"] == reg_sha and list(entries) == keys(condition), "capture index differs")
    require(len({row["frame_id"] for row in entries.values()}) == len(entries), "duplicated capture identity")
    allow = {directory / "predictions.json", *(directory / cid / "native-resets.json" for cid in PLAN["cases"])}
    allow.update(inputs.expand(name) for name in ("{D}/runtime-build.json",
        "{D}/scripts/graduation/g1_visibility_vision.py", "{G}/batches/train-full-04/allocation.json",
        "{G}/batches/train-full-04/cvfix-t02/allocation.json"))
    for key, row in entries.items():
        _, cid, tick = key.split("/")
        expected = directory / cid / f"{tick}.json.gz"
        require(inputs.inside(directory, row["packet"]) == expected, f"unexpected packet: {key}")
        allow.add(expected)

    def deny_truth(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path.is_relative_to(ROUNDS) and path not in allow:
                raise PermissionError("outside frozen optical input allowlist")

    sys.addaudithook(deny_truth)
    for blocked in (VECTORS / "first.json", PRIVATE / "registration.json",
                    inputs.expand("{F}/physical-03/dense-fit-01/offline-physics.json")):
        try:
            blocked.open("rb").close()
        except PermissionError:
            continue
        raise ValueError(f"optical truth/condition access barrier failed: {blocked.name}")

    measure = optics.sealed_optics()
    cache, predictions = {}, {}
    for key, row in entries.items():
        source = row["source"]
        cid = source["case"]
        folder = directory / cid
        meta = index["cases"][cid]
        if cid not in cache:
            require(sha(folder / "native-resets.json") == meta["reset_sha256"], "reset digest differs")
            identity, geometry = optics.bind_fixture(folder, {"id": cid, "episode_id": meta["episode_id"]})
            cache[cid] = identity, geometry, optics.Model(ROOT / geometry["asset_path"])
        identity, geometry, model = cache[cid]
        path = inputs.inside(directory, row["packet"])
        require(sha(path) == row["file_sha256"], "frame packet digest differs")
        frame = inputs.packet(path)
        marker = measure(frame, geometry)
        optics.associate(row, source, frame, identity, marker, geometry)
        require(frame.frame_id == row["frame_id"] and frame.checksum_sha256 == row["checksum_sha256"],
                "index frame identity differs")
        result = optics.observe(frame, marker, geometry, row["robot"], identity, source["source_open"],
                                model, diagnostics=True)
        predictions[key] = dict(result, source_trace_sha256=source["source_trace_sha256"], source_tick=source["source_tick"],
                                frame_id=frame.frame_id, new_episode=frame.episode_id, checksum_sha256=frame.checksum_sha256)
    write(directory / "predictions.json", predictions)


def cold_read():
    seal = read(PRIVATE / "capture-seal.json")
    for name, digest in seal["sealed_sha256"].items():
        require(sha(inputs.inside(PRIVATE, name)) == digest, f"capture member changed: {name}")
    require(seal["complete"] and seal["requests"] == seal["packets"] == 27, "capture incomplete")
    registration = inputs.checked_json(PRIVATE / "registration.json", seal["registration_sha256"])
    require(registration["sources"] == file_hashes()
            and registration["formal_originals"] == inputs.originals(), "registered source or formal original changed")
    slots, calibration = verify_pin_set()
    selected, checks = static_states(slots, calibration)
    require(checks == registration["checks"] and calibration == registration["calibration"], "registered preflight changed")
    terminal = inputs.source_module("branch_terminal", inputs.expand("{T}/terminal_rebound.py"))
    archived = read(ARCHIVE / "B/index.json")["rows"]
    report, frame_ids = {}, set()
    for condition in PLAN["conditions"]:
        directory = PRIVATE / condition
        index = read(directory / "index.json")
        predictions = read(directory / "predictions.json")
        require(index["registration_sha256"] == seal["registration_sha256"]
                and list(index["rows"]) == list(predictions) == keys(condition), "sealed slot id changed")
        for cid, ticks in PLAN["cases"].items():
            folder = directory / cid
            old.native_identity(directory, cid, index["cases"][cid], selected[f"{condition}/{cid}/{ticks[0]}"]["reset"])
            events = read(folder / "native-operation-events.json")
            require([(x["kind"], x["phase"]) for x in events] ==
                    [("RESET", "BEGIN"), ("RESET", "END")] + [("CAPTURE", x) for _ in ticks for x in ("BEGIN", "END")],
                    "operation sequence changed")
            for position, tick in enumerate(ticks):
                key = f"{condition}/{cid}/{tick}"
                row, pred = index["rows"][key], predictions[key]
                req = read(folder / f"{tick}-request.json")
                pair = events[2+2*position:4+2*position]
                require(pair[0]["operation_id"] == pair[1]["operation_id"] and pair[1]["frame_id"] == row["frame_id"]
                        and all(x["physics_step"] == 0 and x["error"] is None for x in pair), f"capture boundary mismatch: {key}")
                require(row["frame_id"] not in frame_ids, f"duplicate frame: {key}")
                frame_ids.add(row["frame_id"])
                check_encoder(selected[key]["row"]["q"],
                              row["robot"]["camera_joint_positions_rad"] + row["robot"]["camera_finger_positions_m"])
                seed = np.random.default_rng(649300 + tick).bit_generator.state
                require(req["initial_rng_sha256"] == inputs.sha_data(inputs.canonical(seed)), f"wrong RNG state: {key}")
                fresh, report[key] = old.read_slot(PRIVATE, row, key, pred, selected[key], calibration, terminal)
                if condition == "r0":
                    source = archived[f"B/{cid}/{tick}"]
                    original = inputs.packet(inputs.inside(ARCHIVE / "B", source["packet"]))
                    assert_baseline(identical_baseline(fresh, original), key)
    return {"registration_sha256": seal["registration_sha256"], "capture_seal_sha256": sha(PRIVATE / "capture-seal.json"),
            "counts": {"exposures": 27, "integration": 0, "control": 0, "formal": 0, "remote": 0, "hardware": 0},
            "arc_degrees": PLAN["conditions"], "slots": report}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "capture", "predict", "read"))
    parser.add_argument("args", nargs="*")
    cli = parser.parse_args()
    if cli.mode == "preflight":
        result = prepare()
        print(f"Frozen sources, {len(result['checks'])} restores and historical control suite passed")
    elif cli.mode == "capture":
        capture()
    elif cli.mode == "predict":
        predict(*cli.args)
    else:
        write(Path(cli.args[0]), cold_read())
