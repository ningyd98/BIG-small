"""Replay and independently check only the three frozen continuous-payload fitting courses."""

import argparse
import collections
import gzip
import hashlib
import importlib.util
import json
from contextlib import ExitStack
from pathlib import Path

import mujoco
import numpy as np
from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import GripperCommand, JointCommand, PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend


HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "round-g1-continuous-payload-observation-20261125"
BASE = Path("experiments/results/g1-continuous-payload-observation-20261125/physical-03")
OUT = Path("experiments/results/g1-payload-pad-overlap-20261125/fit-pad-physics-01")
GEN = "9ed09852049be122ae5ff684af8d89e20012dcae7486db44e93421e075d57caf"
PLAN_SHA = "af9abc72ffaa9b2b3d5e2e92fbcf99559b2f13411dacaa7d22955b1f6d3ce7b2"
FITS = {"dense-fit-01": 3256, "dense-fit-02": 3144, "dense-fit-03": 3448}
PADS = ("left_finger_geom", "right_finger_geom")


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    with path.open("x") as f:
        json.dump(value, f, allow_nan=False, indent=2, sort_keys=True)
        f.write("\n")


def command(backend, source):
    if not source["accepted"]:
        raise ValueError("unexpected unaccepted command in registered fitting course")
    kind = source["type"]
    if kind == "joint_target":
        backend.apply_joint_targets(JointCommand(positions=source["target_positions_rad"]))
    elif kind == "gripper":
        backend.apply_gripper_command(GripperCommand(open=source["target_open"]))
    elif kind == "hold_current_joints":
        backend.hold_current_joints()
    else:
        raise ValueError(kind)
    applied = backend._command_records[-1]
    worst = 0.0
    for key in source.keys() - {"episode_id"}:
        if key in {"target_positions_rad", "applied_target_positions_rad"}:
            difference = float(max(np.abs(np.asarray(applied[key]) - source[key])))
            worst = max(worst, difference)
            if difference > 1e-10:
                raise ValueError(f"command replay differs at {source['physics_step']} {kind} {key} {difference}")
        elif applied[key] != source[key]:
            raise ValueError(f"command replay differs at {source['physics_step']} {kind} {key}")
    return worst


def patches(model, data):
    pads = [model.geom(x).id for x in PADS]
    obj = model.geom("object_geom").id
    com = data.body("object").xipos.copy()
    rigid = data.geom("object_geom")
    object_R = rigid.xmat.reshape(3, 3)
    rows = []
    for index, contact in enumerate(data.contact):
        pair = (int(contact.geom1), int(contact.geom2))
        pad = next((j for j,i in enumerate(pads) if i in pair), None)
        if pad is None or obj not in pair:
            continue
        frame = contact.frame.reshape(3, 3)
        six = np.zeros(6)
        mujoco.mj_contactForce(model, data, index, six)
        if six[0] <= 1e-7:
            continue
        sign = 1 if pair[1] == obj else -1
        basis = sign * frame
        force = six[:3] @ basis
        torque = np.cross(contact.pos - com, force) + six[3:] @ basis
        gid = pads[pad]
        pad_local = (contact.pos - data.geom_xpos[gid]) @ data.geom_xmat[gid].reshape(3, 3)
        object_local = (contact.pos - rigid.xpos) @ object_R
        rows.append([pad, float(contact.dist), contact.pos.tolist(), pad_local.tolist(),
                    object_local.tolist(), six.tolist(), basis.tolist(), contact.friction.tolist(),
                    force.tolist(), torque.tolist()])
    return rows, com


def run(root, case):
    assert sha(HERE/"plan.json") == PLAN_SHA
    plan = read(HERE/"plan.json")
    for name, value in plan["input_sha256"].items():
        if "dense-check" not in name and sha(root/name) != value:
            raise ValueError("fitting source changed " + name)
    runtime = root/"experiments/results/g1-complete-cv-repair-20261125/builds"/GEN/"runtime-source"
    signed = runtime/"runtime-build.json"
    assert sha(signed) == GEN
    source = root/BASE/case
    sink = root/OUT/case
    files = {path: sha(source/path) for path in ("native-commands.json", "native-resets.json",
            "offline-physics.json", "sensor-receipt.json", "rgbd-index.json")}
    report = read(source/"sensor-receipt.json")
    registration = PREVIOUS/"continuous-diagnostic-registration.json"
    assert sha(registration) == report["registration_sha256"]
    assert report["index_sha256"] == files["rgbd-index.json"]
    src = read(registration)
    assert src["original_runtime"] == GEN and any(s["id"] == case for s in src["fit"])
    imported = Path(importlib.util.find_spec(MuJoCoPhysicsBackend.__module__).origin).resolve()
    path = "src/cloud_edge_robot_arm/simulation/mujoco/backend.py"
    assert imported == (runtime/path).resolve() and sha(imported) == read(signed)["runtime_files_sha256"][path]
    asset = runtime/"assets/robots/franka_panda/scene_g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1.xml"
    assert sha(asset) == report["asset_sha256"]
    reset = read(source/"native-resets.json")[0]["parameters"]["requested"]
    observation = read(source/"offline-physics.json")
    rgbd = read(source/"rgbd-index.json")["rows"]
    frames = collections.defaultdict(list)
    labels = {r["frame_id"]:r for r in observation["frame_labels"]}
    for row in rgbd:
        frames[row["robot"]["physics_step"]].append(row)
        truth = labels[row["robot"]["frame_id"]]
        if truth["checksum_sha256"] != row["robot"]["checksum_sha256"]:
            raise ValueError("exposure and offline label are unrelated")
    commands = collections.defaultdict(list)
    for row in read(source/"native-commands.json"):
        commands[row["physics_step"]].append(row)
    actions = {x["skill"]:x for x in report["actions"]}
    incoming = actions["MOVE_TO_REGION"]
    start, stop, selected = incoming["start_step"], incoming["return_step"], FITS[case]
    ids = list(plan["original_failures"])
    first = next(a for a in ids if a["id"] == case)
    assert selected == first["step"] and any(r["robot"]["frame_id"] == first["frame_id"] for r in frames[selected])
    backend = MuJoCoPhysicsBackend()
    backend.initialize(SimulatorConfig(model_path=str(asset), seed=reset["seed"], physics_dt_s=1/240,
        domain_randomization=False, render_rgb=True, render_depth=True))
    # Native conditional camera reset sets joint 1 and its command to -0.8.
    # The historical pixels are already sealed; replay dynamics without new exposures.
    stack = ExitStack()
    stack.enter_context(backend.sensor_capture_on_demand())
    backend.reset(PhysicalScenarioConfig(**{**reset, "object_pose": Pose(**reset["object_pose"]),
                                           "target_region_pose": Pose(**reset["target_region_pose"])}))
    model, data = backend._model, backend._data
    fields = ["arm_q","arm_dq","finger_q","finger_dq","tcp","camera_time","object_centre",
              "object_rotation","object_bottom","effective_command"]
    errors = {k: 0.0 for k in fields}
    def delta(key, actual, reference):
        e = float(np.max(np.abs(np.asarray(actual)-reference)))
        errors[key] = max(errors[key],e)
        if e > 1e-10:
            raise ValueError(f"archive identity failed {case} tick={backend.total_physics_steps} {key} error={e}")
    timeline = []
    all_frames = 0
    stage_touches = collections.Counter()
    try:
        for idx, archived in enumerate(observation["dense"]):
            tick = idx
            for cmd in commands[tick]:
                errors["effective_command"] = max(errors["effective_command"], command(backend, cmd))
            backend.step(1)
            tick += 1
            if tick != archived[0] or tick != backend.total_physics_steps:
                raise ValueError("dense archive gap")
            cube = data.geom("object_geom")
            rot = cube.xmat.reshape(3, 3)
            delta("object_bottom", float(cube.xpos[2]-.035*abs(rot[2]).sum()), archived[1])
            names = {frozenset((c.geom1,c.geom2)) for c in backend.get_contacts()}
            bilateral = all(frozenset((p,"object_geom")) in names for p in PADS)
            if bilateral != archived[2] or any(c.illegal for c in backend.get_contacts()) != archived[3]:
                raise ValueError(f"original dense contact differs {case} {tick}")
            for row in frames.get(tick, []):
                q = row["robot"]
                true = labels[q["frame_id"]]
                delta("arm_q", data.qpos[:7], q["joint_positions_rad"])
                delta("arm_dq", data.qvel[:7], q["joint_velocities_rad_s"])
                delta("finger_q", data.qpos[7:9], q["finger_positions_m"])
                delta("finger_dq", data.qvel[7:9], q["finger_velocities_m_s"])
                delta("tcp", data.site("tcp").xpos, q["tcp_position_m"])
                delta("camera_time", data.time, q["sim_time_s"])
                delta("object_centre", cube.xpos, true["center_m"])
                delta("object_rotation", rot, true["rotation"])
                if sorted(sorted((model.geom(c.geom1).name,model.geom(c.geom2).name)) for c in data.contact) != sorted(true["touching"]):
                    raise ValueError(f"same-frame contacts differ {case} {tick}")
                all_frames += 1
            # Full native dense chronology and input alignment are checked on both sides
            # of transport. Wrench raw covers every transport tick and its starting return.
            if start <= tick <= stop:
                contacts, com = patches(model, data)
                identity = sorted({s[0] for s in contacts})
                stage_touches[tuple(identity)] += 1
                timeline.append([tick, com.tolist(), cube.xpos.tolist(), rot.tolist(),
                    data.qpos[:9].tolist(),data.qvel[:9].tolist(),
                    [(c["phase"],c["robot"]["frame_id"],c["robot"]["native_last_command_seq"]) for c in frames.get(tick, [])],
                    contacts])
        # The successful RETREAT terminal target is emitted on the final physics
        # clock. It has no subsequent integration step in the archived episode.
        terminal = len(observation["dense"])
        for cmd in commands.get(terminal, []):
            errors["effective_command"] = max(errors["effective_command"], command(backend, cmd))
        if all_frames != len(rgbd) or any(t > terminal for t in commands if commands[t]):
            raise ValueError("missing exposure or command")
        for name, old_sha in files.items():
            if old_sha != sha(source/name):
                raise ValueError("source bytes changed in replay")
        sink.mkdir(parents=True,exist_ok=False)
        archive = sink/"transport-contact-manifolds.json.gz"
        packed = {
            "columns": ["step","workpiece_world_com","workpiece_world_geom_center","R_object_to_world",
                        "arm_finger_q","arm_finger_dq","exposures","loaded_contact_rows"],
            "contact_columns": ["pad_side_0_left_1_right","signed_distance_m","world_point_m","pad_local_point_m",
                "object_local_point_m","MuJoCo_contact_force_torque_local","basis_of_force_on_workpiece",
                "friction_coefficients","world_force_on_workpiece_N","world_moment_about_com_Nm_including_contact_torsion"],
            "rows": timeline,
        }
        archive.write_bytes(gzip.compress(json.dumps(packed,ensure_ascii=False,allow_nan=False).encode(),3,mtime=0))
        dump(sink/"replay.json",{
            "case":case,"source_hash":files,"source_dir":str(BASE/case),"dense_ticks":len(observation["dense"]),
            "same_frame_checks":all_frames,"command_count":sum(map(len,commands.values())),"max_abs_errors":errors,
            "xml":sha(asset),"original_runtime":GEN,"interpreter_backend_sha256":sha(imported),"source_sha256":sha(Path(__file__)),
            "transport_range":[start,stop],"transport_samples":len(timeline),"trigger_step":selected,"trigger_frame":first["frame_id"],
            "transport_step_count_by_positive_pad_sides":{str(k):v for k,v in stage_touches.items()},
            "gravity_m_s2":model.opt.gravity.tolist(),"body_mass_kg":float(model.body("object").mass[0]),
            "principal_inertia_kg_m2":model.body("object").inertia.tolist(),
            "pad_half_extents_m":[model.geom(n).size.tolist() for n in PADS],"archive_sha256":sha(archive),
        })
        print(case, len(timeline), all_frames, errors, flush=True)
    finally:
        stack.close()
        backend.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--case", choices=tuple(FITS), required=True)
    args = parser.parse_args()
    run(args.root.resolve(), args.case)
