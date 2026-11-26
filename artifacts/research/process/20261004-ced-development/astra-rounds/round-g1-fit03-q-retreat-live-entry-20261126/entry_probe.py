"""One native Q route and two conditional, non-dispatch RETREAT entry checks."""

# ruff: noqa: E402
import argparse
import gzip
import hashlib
import json
import os
import sys
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch

import cv2
import mujoco
import numpy as np
from scripts.graduation import g1_complete_cv_carried_surface as surface
from scripts.graduation import g1_complete_cv_clearance as clearance
from scripts.graduation import g1_complete_cv_handoff as gate
from scripts.graduation.g1_dual_trials import RegisteredAssemblyBackend, mass_properties
from scripts.graduation.perception_io import ROOT, read, sha

from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD, MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.observations import RGBDObservation

HERE = Path(__file__).resolve().parent
PLAN = read(HERE / "plan.json")
OUT = ROOT / PLAN["output"]
OLD = ROOT / PLAN["source_q"]
ROUNDS = HERE.parent
sys.path[:0] = [
    str(ROUNDS / "round-g1-release-fit03-q-dwell-handoff-20261126"),
    str(ROUNDS / "round-g1-fit03-retreat-directional-sat-20261126"),
]

import directional_retreat as directional
import q_capture as original

dwell = original.dwell
native = dwell.native
require, plain, store = dwell.require, dwell.plain, dwell.store_json
CAL = original.reader.ALLOCATION.parents[3] / "calibration-gpu-01"
PAIR = tuple(PLAN["active_stop_margin_pair"])
STEPS = PLAN["states"]
ROLES = ["PRE", *(f"DWELL-{i:02d}" for i in range(31)), "AUDIT"]
STAGES = ("MOVE_ABOVE", "APPROACH", "GRASP", "LIFT", "MOVE_TO_REGION", "PLACE")
PROJECTIONS = (
    ("robot", clearance.RobotDepthReference, "robot_reference_projections"),
    ("payload", surface.CarriedSurface, "payload_reference_projections"),
)


def pinned():
    for file, expected in PLAN["input_sha256"].items():
        require(sha(ROOT / file) == expected, f"frozen input changed: {file}")


def configure():
    pinned()
    with (
        patch.object(original, "PLAN", original.PLAN | {"baseline": PLAN["baseline"]}),
        patch.object(dwell, "PLAN", dwell.PLAN | {"baseline": PLAN["baseline"]}),
    ):
        context, prefix = original.configure()
    seal = read(OLD / "native-01/capture-seal.json")
    require(seal["complete"] and seal["camera_requests"] == 42, "old Q incomplete")
    original.verified_tree(OLD / "native-01", seal["members"])
    proof = read(OLD / "exposure-witness.json")
    require(
        proof["complete"]
        and proof["source_capture_sha256"] == sha(OLD / "native-01/capture-seal.json")
        and len(proof["route"]["shots"]) == 32,
        "old Q witness does not bind its 32 originals",
    )
    old = OLD / "native-01/q"
    route = read(old / "native.json")
    require(
        route["prefix"] == prefix and route["complete"] and route["rows"] == STEPS["dwell_end"] + 1,
        "old Q no longer matches the source fork",
    )
    require(
        CAL == Path(read(original.reader.ALLOCATION)["calibration_directory"])
        and sha(CAL / "manifest.json") == read(original.reader.ALLOCATION)["calibration_sha256"],
        "wrong calibration authority",
    )
    return context, route, proof["route"]["shots"]


def certificate(observable, isolation):
    identity, geometry = original.reader.fixture(observable)
    alloc = read(original.reader.ALLOCATION)
    require(
        isolation
        == {
            "class": "RegisteredAssemblyBackend",
            "view": "nominal",
            "domain_randomization": False,
            "asset_sha256": alloc["asset_sha256"],
            "asset_path": str(native.ASSET),
        },
        "workspace isolation identity differs",
    )
    return clearance.LocalClearance(
        geometry,
        native.ASSET,
        CAL,
        calibration_sha256=alloc["calibration_sha256"],
        isolated_scene=True,
        optical_identity=identity,
    )


def entry_check(cert, frame, marker, packet):
    calls = []
    original_gap = gate.box_gap
    original_call = clearance.handoff_motion

    def scoped(*args, optical=None, volume_check=None):
        require(args[3:5] == ("RETREAT", "PRE"), "unexpected conditional gate invocation")
        (local,) = [box for box in cert.model.object if box.name == PAIR[1]]

        def selected(left, right):
            value = original_gap(left, right)
            if (left.name, right.name) != PAIR:
                return value
            require(optical is not None and not calls, "unbound or repeated directional check")
            rows = directional.lower_support(left, local, optical)
            bound = max(row["initial_gap_lower_m"] for row in rows)
            require(np.isfinite(bound) and bound < 2, "invalid directional bound")
            calls.extend(rows)
            return max(value, bound) if bound > 0 else value

        with patch.object(gate, "box_gap", selected):
            return original_call(*args, optical=optical, volume_check=volume_check)

    x, y, z = packet["tcp_position_m"]
    with patch.object(clearance, "handoff_motion", scoped):
        outcome = cert.check(
            frame, marker, packet, "RETREAT", (x, y, max(0.16, z + 0.10)), _DOWNWARD, phase="PRE"
        )
    return plain({"gate": outcome, "directional_axes": calls})


class ReferenceReadback:
    """Keep only registered optical projection inputs and outputs, apart from native images."""

    def __init__(self, *, rows=None):
        self.replay = rows
        self.rows = []
        self.recorded = []
        self.role = None
        self.counts = {name: 0 for name, _, _ in PROJECTIONS}
        self.stack = ExitStack()

    def tracker(self, name, method, limit):
        def project(instance, *args):
            index = len(self.rows)
            self.counts[name] += 1
            require(self.counts[name] <= PLAN["limits"][limit], "reference projection over budget")
            row = {
                "kind": name,
                "role": self.role,
                "args_sha256": dwell.digest(plain(args)),
                "files": [f"reference-{index}-{i}.npy" for i in range(1 if name == "robot" else 2)],
            }
            if self.replay is None:
                result = method(instance, *args)
                arrays = (result,) if name == "robot" else result
                self.recorded.extend(zip(row["files"], arrays, strict=True))
            else:
                require(
                    index < len(self.replay) and self.replay[index] == row, "foreign projection"
                )
                arrays = tuple(np.load(OUT / path, allow_pickle=False) for path in row["files"])
                result = arrays[0] if name == "robot" else arrays
            require(
                all(np.isfinite(array).all() and array.shape[:2] == (240, 320) for array in arrays),
                "foreign reference array",
            )
            self.rows.append(row)
            return result

        return project

    def seal_arrays(self):
        for path, array in self.recorded:
            with (OUT / path).open("xb") as stream:
                np.save(stream, array, allow_pickle=False)

    def __enter__(self):
        for name, cls, limit in PROJECTIONS:
            if self.replay is not None:

                def initialize(instance, asset, width=320, height=240):
                    instance.boxes = clearance.Model(asset).object
                    instance.width, instance.height = width, height

                self.stack.enter_context(patch.object(cls, "__init__", initialize))
                self.stack.enter_context(patch.object(cls, "close", lambda self: None))
            self.stack.enter_context(
                patch.object(cls, "project", self.tracker(name, cls.project, limit))
            )
        return self

    def __exit__(self, *exc):
        return self.stack.__exit__(*exc)


def audit_frame(cert, history, refs, frame, marker, packet, role):
    refs.role = role
    cert.payload_history = deepcopy(history)
    try:
        return entry_check(cert, frame, marker, packet)
    finally:
        cert.close()


def packet_from(current, frame, encoders, action, gripper):
    return {
        **encoders,
        "physics_step": current["tick"],
        "sim_time_s": frame.sim_time_s,
        "frame_id": frame.frame_id,
        "checksum_sha256": frame.checksum_sha256,
        "joint_positions_rad": current["q"][:7],
        "joint_velocities_rad_s": current["dq"][:7],
        "finger_positions_m": current["q"][7:9],
        "finger_velocities_m_s": current["dq"][7:9],
        "tcp_position_m": current["tcp_xyz_m"],
        "previous_native_successful_skill": action["skill"],
        "previous_native_return_step": action["return_step"],
        "last_accepted_gripper_open": gripper["target_open"],
        "last_accepted_gripper_command_step": gripper["physics_step"],
    }


def entry_scope(packet, frame, current, drive):
    return {
        "source_skill": "RELEASE",
        "destination_skill": "RETREAT",
        "prior_end_step": current["tick"],
        "entry_step": current["tick"],
        "current_step": current["tick"],
        "entry_command_seq": drive["command_seq"],
        "last_command_seq": drive["command_seq"],
        "entry_gripper_open": current["open_command"],
        "entry_frame_id": frame.frame_id,
        "entry_checksum_sha256": frame.checksum_sha256,
        "entry_target_rad": current["control"][:7],
        "entry_finger_target_m": current["control"][7:],
        "effective_joint_target_rad": current["control"][:7],
        "effective_finger_target_m": current["control"][7:],
        "entry_effective_arm_goal_rad": drive["goal"],
        "entry_native_arm_velocity_rad_s": drive["velocity"],
        **{
            f"entry_{key}": packet[key]
            for key in (
                "joint_positions_rad",
                "joint_velocities_rad_s",
                "finger_positions_m",
                "finger_velocities_m_s",
            )
        },
    }


def check_slot(slot, event, frame, expected):
    packet = slot["robot"]
    require(
        event["phase"] == "END"
        and event["explicit_role"] == slot["role"]
        and event["error"] is None
        and event["instance_count"] == 0
        and event["episode_id"] == frame.episode_id
        and event["physics_step"] == packet["physics_step"]
        and event["sim_time_s"] == packet["camera_encoder_sim_time_s"] == frame.sim_time_s
        and event["frame_id"] == packet["frame_id"] == frame.frame_id
        and packet["checksum_sha256"] == frame.checksum_sha256
        and original.replay.encoder_bits(packet) == expected["encoder_f64_hex"]
        and event["pass_state_hashes"] == [expected["camera_state_sha256"]] * 2
        and slot["integration_sha256"] == expected["integration_sha256"]
        and packet["physics_step"] == expected["tick"],
        "Q clock, RGB/depth pass, archived encoder or integration witness differs",
    )


def execute(backend, context, old, witnesses, results, refs):
    terminal, prior_plan, roots, case, cal, _ = context
    reset = read(dwell.FIT / "native-resets.json")[0]["parameters"]["requested"]
    scenario = terminal.prepare_backend(backend, reset, case, roots, prior_plan)
    rows, slots, events, actions = (results[key] for key in ("rows", "slots", "events", "actions"))
    explicit = None
    controller = MuJoCoSkillRobot(backend)
    plan = dwell.PLAN
    old_rows = gzip.open(OLD / "native-01/q/physical.jsonl.gz", "rt")
    stats = results["stats"]
    measure = dwell.optics.sealed_optics()
    certificates = ExitStack()

    def watch(event):
        if event.kind != "CAPTURE":
            return
        row = native.observe_pass(event) | {"explicit_role": explicit}
        events.append(row)
        if event.phase == "END" and event.error is None:
            require(
                len(set(row["pass_state_hashes"])) == 1
                and len(row["pass_state_hashes"]) == 2
                and row["instance_count"] == 0,
                "inconsistent RGB-D passes",
            )

    def snapshot(_event=None):
        row = terminal.capture_state(backend, mujoco)
        require(row["tick"] == len(rows), "missing native step")
        rows.append(row)
        archived = json.loads(next(old_rows))
        stats["physical_max_error"] = max(
            stats["physical_max_error"], dwell.physical_comparison(row, archived)
        )
        require(not any(c["illegal"] for c in row["contacts"]), "illegal contact")
        if row["tick"] >= STEPS["release_return"]:
            gaps, _, inside = terminal.gap_and_table(row, sizes)
            require(not terminal.dwell_issues(row, gaps, inside), "physical dwell refusal")

    def operate(skill):
        start = backend.total_physics_steps
        if skill == "RELEASE":
            action = controller.release(timeout_ms=plan["release_timeout_ms"])
        else:
            action = dwell.motion(plan, backend, controller, skill, PLAN["q_xy_m"])
        row = {
            "skill": skill,
            "start_step": start,
            "return_step": backend.total_physics_steps,
            "success": action.success,
            "result": plain(action),
        }
        actions.append(row)
        old_action = old["actions"][len(actions) - 1]
        fields = ("skill", "start_step", "return_step", "success")
        require(
            action.success and all(row[key] == old_action[key] for key in fields),
            f"{skill} native return changed",
        )

    def expose(role, seed):
        nonlocal explicit
        backend._rng = np.random.default_rng(seed)
        explicit = role

        def integration():
            return terminal.integration_digest(backend, mujoco)["mujoco_integration_sha256"]

        before = integration()
        started = perf_counter_ns()
        try:
            frame = native.observation_from_sensor_frame(
                backend.capture_sensor_frame(), source="mujoco_camera", png_compress_level=1
            )
        finally:
            explicit = None
        capture_end = perf_counter_ns()
        path = f"{len(slots):02d}.json.gz"
        results["raw_frames"].append((path, frame))
        current = rows[-1]
        gripper = next(
            cmd
            for cmd in reversed(backend.command_records)
            if cmd["type"] == "gripper" and cmd["accepted"]
        )
        require(
            before == integration()
            and current["tick"] == backend.total_physics_steps
            and current["time_s"] == backend.get_sim_time() == frame.sim_time_s,
            "capture changed integrated state or clock",
        )
        packet = packet_from(
            current,
            frame,
            native.camera_encoder_pose(backend._model, backend._data),
            actions[-1],
            gripper,
        )
        slot = {
            "role": role,
            "robot": packet,
            "seed": seed,
            "integration_sha256": before,
            "path": path,
        }
        check_slot(slot, events[-1], frame, witnesses[min(len(slots), 31)])
        require(role == ROLES[len(slots)], "wrong native role")
        if role.startswith("DWELL"):
            marker = measure(frame, cert.geometry)
            results["dwell_live"].append(
                plain(cert.observe_payload_frame(frame, marker, packet, "RELEASE", "DWELL"))
            )
        if role in ("DWELL-30", "AUDIT"):
            state = backend.get_joint_command_state()
            drive = {
                "command_seq": backend.next_command_sequence - 1,
                "goal": backend._target_positions.tolist(),
                "velocity": list(state.velocity_rad_s),
            }
            require(
                tuple(drive["goal"]) == state.positions_rad
                and drive["command_seq"] == gripper["command_seq"],
                "current effective drive is not bound to the true arm hold and OPEN",
            )
            results["endpoint_drive"] = drive
            slot["robot"]["handoff"] = entry_scope(packet, frame, current, drive)
            if role == "DWELL-30":
                marker_for_entry = marker
            else:
                marker_for_entry = measure(frame, cert.geometry)
            # The primary observer keeps its true 31 DWELL frames. Each preview
            # gets its own certificate and history copy; neither enters an owner.
            preview = previews[role]
            outcome = audit_frame(
                preview, cert.payload_history, refs, frame, marker_for_entry, packet, role
            )
            outcome["capture_to_local_result_ms"] = (perf_counter_ns() - started) / 1e6
            results["audits"][role] = outcome
        slot["capture_ms"] = (capture_end - started) / 1e6
        slots.append(slot)

    try:
        require(
            abs(mass_properties(backend._model)["mass_kg"] - scenario.object_mass_kg) <= 1e-12
            and scenario.object_mass_kg == backend.registered_mass,
            "registered mass differs from old fitted Q",
        )
        backend.reset(scenario)
        allocation = read(original.reader.ALLOCATION)
        results["isolation"] = {
            "class": type(backend).__name__,
            "view": backend.view,
            "domain_randomization": backend._config.domain_randomization,
            "asset_sha256": sha(Path(backend._config.model_path)),
            "asset_path": str(native.ASSET),
        }
        require(
            type(backend) is RegisteredAssemblyBackend
            and Path(backend._config.model_path).resolve()
            == (roots["runtime"] / allocation["geometry"]["asset_path"]).resolve()
            and sha(Path(backend._config.model_path)) == allocation["asset_sha256"],
            "original isolated backend predicate failed",
        )
        reset_record = {"resets": read(OUT / "reset-observed.json"), "episode": backend._episode_id}
        results["reset"] = original.minimal.reset_identity_only(reset_record)
        native.verify_camera_model(backend._model, backend._data, cal)
        results["renderer"] = native.gl_identity(cal)
        cert = certificate(results["reset"], results["isolation"])
        certificates.callback(cert.close)
        previews = {}
        for role in ("DWELL-30", "AUDIT"):
            preview = certificate(results["reset"], results["isolation"])
            certificates.callback(preview.close)
            previews[role] = preview
        backend._rng = np.random.default_rng(plan["depth_seed_initial"])
        backend._last_contacts = backend._read_contacts()
        sizes = {geom: backend._model.geom(geom).size.tolist() for geom in terminal.DATA_GEOMS}
        snapshot()
        with backend.observe_operation_boundaries(watch), backend.observe_physics_steps(snapshot):
            with backend.sensor_capture_on_demand():
                backend.step(120)
            for skill in STAGES[:4]:
                operate(skill)
            with backend.sensor_capture_on_demand():
                backend.step(120)
            require(
                backend.total_physics_steps == STEPS["common"]
                and controller.get_state().holding_object_id == "object"
                and dwell.digest(dwell.peeled(backend.command_records))
                == old["prefix"]["commands_sha256"]
                and dwell.digest(rows) == old["prefix"]["physics_sha256"]
                and terminal.integration_digest(backend, mujoco)["mujoco_integration_sha256"]
                == old["prefix"]["integration_sha256"],
                "original fork state or true HOLD changed",
            )
            for skill in STAGES[4:]:
                operate(skill)
            current = rows[-1]
            _, _, in_destination = terminal.gap_and_table(current, sizes)
            require(
                current["tick"] == STEPS["open"] == STEPS["place"]
                and controller.get_state().holding_object_id == "object"
                and not current["open_command"]
                and in_destination
                and any(
                    set(c["names"]) == {terminal.OBJECT, terminal.TABLE} and c["normal_n"] > 0
                    for c in current["contacts"]
                ),
                "isolated physical opening admission refused",
            )
            # Unchanged renderable model and native controller; no extra final-refresh image.
            with native.on_demand_with_camera_cleanup(backend):
                expose("PRE", plan["pre_noise_seed"])
                q = backend._data.qpos[:7].tolist()
                require(
                    backend.command_records[-1]["type"] == "joint_target", "final PLACE missing"
                )
                backend.hold_current_joints()
                hold = backend.command_records[-1]
                require(
                    hold["type"] == "hold_current_joints"
                    and hold["accepted"]
                    and hold["physics_step"] == STEPS["open"]
                    and hold["applied_target_positions_rad"] == q
                    and not backend._pending_joint_targets,
                    "original terminal hold differs",
                )
                operate("RELEASE")
                opened = backend.command_records[-1]
                require(
                    opened["type"] == "gripper"
                    and opened["accepted"]
                    and opened["target_open"] is True
                    and opened["physics_step"] == STEPS["open"]
                    and backend.total_physics_steps == STEPS["release_return"],
                    "native opening and return did not join",
                )
                results["commands"] = plain(backend.command_records)
                require(
                    dwell.peeled(results["commands"]) == dwell.peeled(old["commands"]),
                    "Q commands differ",
                )
                for n in range(31):
                    if n:
                        backend.step(8)
                    require(
                        backend.total_physics_steps == STEPS["release_return"] + 8 * n,
                        "dwell cadence differs",
                    )
                    expose(
                        f"DWELL-{n:02d}", plan["dwell_seed_first"] + n * plan["dwell_seed_stride"]
                    )
                expose("AUDIT", PLAN["fresh_audit_seed"])
                require(
                    len(slots) == 33
                    and slots[-1]["robot"]["frame_id"] != slots[-2]["robot"]["frame_id"]
                    and backend.total_physics_steps == STEPS["dwell_end"]
                    and plain(backend.command_records) == results["commands"]
                    and next(old_rows, None) is None,
                    "fresh audit advanced state, reused a frame or dispatched a command",
                )
                cert.close()
    finally:
        old_rows.close()
        certificates.close()
        results["commands"] = results.get("commands", plain(backend.command_records))
        if backend._data is not None:
            backend.shutdown()


def live():
    context, old, witnesses = configure()
    require(
        os.environ.get("MUJOCO_GL") == os.environ.get("PYOPENGL_PLATFORM") == "egl", "EGL required"
    )
    require(not OUT.exists() and OUT.resolve() == OUT, "Q entry acquisition already attempted")
    before = dwell.inputs.originals()
    results = dict(
        rows=[],
        raw_frames=[],
        slots=[],
        events=[],
        dwell_live=[],
        actions=[],
        audits={},
        stats={"camera_requests": 0, "physical_max_error": 0.0},
    )
    advance, capture = (
        native.MuJoCoPhysicsBackend._advance_unobserved_physics_step,
        native.MuJoCoRGBDCamera._capture,
    )

    def limited_step(backend):
        require(backend.total_physics_steps < STEPS["dwell_end"], "integration ceiling reached")
        return advance(backend)

    def limited_capture(camera, *args, **kwargs):
        results["stats"]["camera_requests"] += 1
        require(
            results["stats"]["camera_requests"] <= PLAN["limits"]["native_rgbd_calls"],
            "capture ceiling reached",
        )
        return capture(camera, *args, **kwargs)

    complete = False
    refs = ReferenceReadback()
    with native.device((ROOT / native.NATIVE["exclusive_lock"]).parent):
        OUT.mkdir(parents=True)
        store(
            OUT / "registration.json",
            {
                "plan": sha(HERE / "plan.json"),
                "source": sha(Path(__file__)),
                "limits": PLAN["limits"],
                "before": before,
                "native_return": old["actions"][-1]["return_step"],
                "dispatch": False,
            },
        )
        try:
            allocation = read(original.reader.ALLOCATION)
            backend = RegisteredAssemblyBackend(OUT, allocation["case"])
            with (
                patch.object(
                    native.MuJoCoPhysicsBackend, "_advance_unobserved_physics_step", limited_step
                ),
                patch.object(native.MuJoCoRGBDCamera, "_capture", limited_capture),
                refs,
            ):
                execute(backend, context, old, witnesses, results, refs)
            require(
                results["stats"]["camera_requests"] == 43
                and refs.counts["robot"] <= 2
                and refs.counts["payload"] <= 2
                and dwell.inputs.originals() == before,
                "resource ledger or frozen original changed",
            )
            complete = True
        except BaseException as error:
            store(OUT / "aborted.json", {"type": type(error).__name__, "reason": str(error)})
            raise
        finally:
            refs.seal_arrays()
            digests = {}
            for path, frame in results.pop("raw_frames"):
                data = gzip.compress(frame.model_dump_json().encode(), 2, mtime=0)
                with (OUT / path).open("xb") as raw:
                    raw.write(data)
                digests[path] = hashlib.sha256(data).hexdigest()
            for slot in results["slots"]:
                slot["sha256"] = digests[slot["path"]]
            with (
                (OUT / "physical.jsonl.gz").open("xb") as stream,
                gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as compressed,
            ):
                for row in results.pop("rows"):
                    compressed.write(dwell.encode(row) + b"\n")
            results["reference_projections"] = refs.rows
            store(
                OUT / "observable.json",
                {
                    key: results[key]
                    for key in ("reset", "isolation", "slots", "events", "reference_projections")
                    if key in results
                },
            )
            store(OUT / "native.json", results)
            store(OUT / "capture-seal.json", {"complete": complete, "members": dwell.hashes(OUT)})


def cold(output):
    pinned()
    seal = read(OUT / "capture-seal.json")
    require(seal["complete"] and not output.exists(), "incomplete or reused cold allocation")
    original.verified_tree(OUT, seal["members"])
    registration = read(OUT / "registration.json")
    require(
        registration["source"] == sha(Path(__file__))
        and registration["plan"] == sha(HERE / "plan.json"),
        "foreign live registration",
    )
    data = read(OUT / "observable.json")
    slots = data["slots"]
    require([slot["role"] for slot in slots] == ROLES, "foreign slot ordering")
    for n, slot in enumerate(slots):
        require(
            slot["path"] == f"{n:02d}.json.gz" and sha(OUT / slot["path"]) == slot["sha256"],
            "foreign packet",
        )
    witness = read(OLD / "exposure-witness.json")["route"]["shots"]
    cert = certificate(data["reset"], data["isolation"])
    measure = dwell.optics.sealed_optics()
    dwell_rows, audits = [], {}
    refs = ReferenceReadback(rows=data["reference_projections"])
    with refs:
        for i, slot in enumerate(slots):
            frame = RGBDObservation.model_validate_json(
                gzip.decompress((OUT / slot["path"]).read_bytes())
            )
            packet, role = slot["robot"], slot["role"]
            (event,) = [row for row in data["events"] if row.get("frame_id") == frame.frame_id]
            check_slot(slot, event, frame, witness[min(i, 31)])
            if role == "PRE":
                continue
            marker = measure(frame, cert.geometry)
            if role.startswith("DWELL"):
                dwell_rows.append(
                    plain(cert.observe_payload_frame(frame, marker, packet, "RELEASE", "DWELL"))
                )
            if role in ("DWELL-30", "AUDIT"):
                preview = certificate(data["reset"], data["isolation"])
                audits[role] = audit_frame(
                    preview, cert.payload_history, refs, frame, marker, packet, role
                )
                del audits[role]["gate"]["check_ms"]
    cert.close()
    require(
        refs.rows == data["reference_projections"] and len(dwell_rows) == 31,
        "cold input coverage differs",
    )
    store(
        output,
        {
            "capture": sha(OUT / "capture-seal.json"),
            "audits": audits,
            "dwell": dwell_rows,
            "same_tick_distinct_frames": (
                slots[-1]["robot"]["physics_step"] == slots[-2]["robot"]["physics_step"]
                and slots[-1]["robot"]["frame_id"] != slots[-2]["robot"]["frame_id"]
            ),
            "native_dispatch_authorized": False,
        },
    )


def preflight():
    context, old, _ = configure()
    cal = context[-2]
    stage = gate.profile()["stages"]["RETREAT"]
    reserve = dict(zip(map(tuple, stage["pairs"]), stage["pair_closing_m"], strict=True))[PAIR]
    require(
        reserve == 0.0007523402905361923
        and cal["primary_camera"]["width"] == 320
        and cal["primary_camera"]["height"] == 240
        and len(old["actions"]) == 7
        and not OUT.exists(),
        "frozen reserve, source prerequisites or exclusive destination changed",
    )
    terminal, prior_plan, roots, case, _, _ = context
    allocation = read(original.reader.ALLOCATION)
    backend = RegisteredAssemblyBackend(OUT, allocation["case"])
    reset = read(dwell.FIT / "native-resets.json")[0]["parameters"]["requested"]
    try:
        scenario = terminal.prepare_backend(backend, reset, case, roots, prior_plan)
        require(
            backend._camera is None
            and backend.total_physics_steps == 0
            and abs(mass_properties(backend._model)["mass_kg"] - scenario.object_mass_kg) <= 1e-12
            and scenario.object_mass_kg == backend.registered_mass,
            "compiled mass or zero-reset asset preflight differs",
        )
        observed = original.minimal.reset_identity_only(
            {"resets": old["resets"], "episode": old["episode"]}
        )
        identity = {
            "class": type(backend).__name__,
            "view": backend.view,
            "domain_randomization": backend._config.domain_randomization,
            "asset_sha256": sha(Path(backend._config.model_path)),
            "asset_path": str(native.ASSET),
        }
        certificate(observed, identity).close()
    finally:
        backend.shutdown()
    print("Frozen Q inputs, original controls, and projection reserve verified")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "live", "cold"))
    parser.add_argument("output", type=Path, nargs="?")
    args = parser.parse_args()
    cv2.setNumThreads(1)
    if args.mode == "cold":
        require(
            args.output in (OUT / "cold-primary.json", OUT / "cold-secondary.json"),
            "unexpected cold destination",
        )
        cold(args.output)
    else:
        require(args.output is None, "unexpected output path")
        globals()[args.mode]()


if __name__ == "__main__":
    main()
