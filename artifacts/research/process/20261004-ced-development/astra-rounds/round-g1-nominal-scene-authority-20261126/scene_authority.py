"""Audit native nominal scene provenance and actual lifecycle probes."""

import argparse
import hashlib
import inspect
import json
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from pathlib import Path
from xml.etree import ElementTree

import mujoco
import numpy as np
from scripts.graduation.dynamic_vision import plain
from scripts.graduation.perception_io import ROOT, read, sha

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import (
    JointCommand,
    PhysicalFault,
    PhysicalFaultType,
    PhysicalScenarioConfig,
)
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

HERE = Path(__file__).resolve().parent
PLAN = read(HERE / "plan.json")
OUT = ROOT / PLAN["output"]
ASSET = ROOT / PLAN["asset"]
ASSEMBLY = ROOT / PLAN["assignment"]
WORLD_ASSET = PLAN["input_sha256"][PLAN["asset"]]


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def create(path, payload):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, allow_nan=False)
        handle.write("\n")


def verify_sources():
    baseline = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    require(baseline == PLAN["baseline"], "worktree left registered baseline")
    for path, digest in PLAN["input_sha256"].items():
        require(sha(ROOT / path) == digest, f"input changed: {path}")
    root = ROOT / PLAN["source_root"]
    for component, declared in (
        (MuJoCoPhysicsBackend, "simulation/mujoco/backend.py"),
        (SimulatorConfig, "simulation/config.py"),
        (PhysicalScenarioConfig, "simulation/models.py"),
    ):
        require(
            Path(inspect.getfile(component)).resolve()
            == root / "src/cloud_edge_robot_arm" / declared,
            f"wrong source import: {declared}",
        )
    case = read(ASSEMBLY)
    require(
        case["case"]["view"] == "nominal"
        and case["asset_sha256"] == WORLD_ASSET
        and case["geometry"]["asset_path"] == ASSET.relative_to(root).as_posix()
        and case["runtime_build_sha256"] == PLAN["source_generation"]
        and mujoco.__version__ == "3.3.7",
        "frozen allocation, model, or runtime changed",
    )


def admitted_asset(path):
    require(sha(path) == WORLD_ASSET, "source asset bytes are not admitted")
    require(path == ASSET and path.resolve(strict=True) == ASSET, "nonregistered model path")
    root = ElementTree.parse(path).getroot()
    require(root.tag == "mujoco", "unexpected model document")
    unresolved = {
        "include",
        "mesh",
        "texture",
        "material",
        "hfield",
        "plugin",
        "extension",
        "skin",
        "flex",
        "flexcomp",
        "composite",
        "attach",
        "tendon",
        "equality",
        "contact",
    }
    dependencies = [
        node.tag for node in root.iter() if node.tag in unresolved or "file" in node.attrib
    ]
    require(not dependencies, "asset constructor has unresolved dependencies or model extensions")
    return root


def xml_inventory(root):
    tags = {"body", "geom", "joint", "freejoint", "camera", "light", "site"}
    categories = ("body", "geom", "joint", "camera", "light", "site", "actuator")
    rows = {name: {} for name in categories}
    rows["body"]["world"] = "world"

    def visit(node, owner):
        for child in node:
            require(child.tag in tags, f"unregistered world construct: {child.tag}")
            name = child.attrib["name"]
            kind = "joint" if child.tag == "freejoint" else child.tag
            require(name not in rows[kind], "duplicated declared model element")
            rows[kind][name] = owner
            if kind == "body":
                require("mocap" not in child.attrib, "external transform source")
                visit(child, name)

    visit(root.find("worldbody"), "world")
    for actuator in root.find("actuator"):
        require(actuator.tag == "position", "unregistered actuator kind")
        rows["actuator"][actuator.attrib["name"]] = actuator.attrib["joint"]
    return rows


def compiled_inventory(model, declared):
    accessor = {
        "body": (model.nbody, model.body, model.body_parentid),
        "geom": (model.ngeom, model.geom, model.geom_bodyid),
        "joint": (model.njnt, model.joint, model.jnt_bodyid),
        "camera": (model.ncam, model.camera, model.cam_bodyid),
        "light": (model.nlight, model.light, model.light_bodyid),
        "site": (model.nsite, model.site, model.site_bodyid),
        "actuator": (model.nu, model.actuator, model.actuator_trnid[:, 0]),
    }
    compiled = {}
    for category, (count, identify, parents) in accessor.items():
        parent_method = model.joint if category == "actuator" else model.body
        compiled[category] = {
            identify(i).name: parent_method(int(parents[i])).name for i in range(count)
        }
    require(compiled == declared, "compiled inventory differs from registered XML tree")
    disallowed = (
        "nmesh",
        "ntex",
        "nmat",
        "nhfield",
        "neq",
        "ntendon",
        "nmocap",
        "nplugin",
        "nflex",
        "nskin",
        "npair",
        "nexclude",
    )
    require(all(getattr(model, name) == 0 for name in disallowed), "extra model resource")
    require(model.cam_mode[0] == model.cam_bodyid[0] == 0, "camera is not world-fixed")
    geom = []
    for n in range(model.ngeom):
        name = model.geom(n).name
        body = compiled["geom"][name]
        if body == "object":
            group = "rigid_payload"
        elif body in {"world", "target_region"}:
            group = "fixed_workcell"
        elif body.startswith("panda_") or body in {"left_finger", "right_finger"}:
            group = "arm_and_fingers"
        else:
            raise ValueError("unmapped geometry owner")
        mask = [int(model.geom_contype[n]), int(model.geom_conaffinity[n])]
        geom.append(
            {
                "name": name,
                "body": body,
                "group": group,
                "geom_type": int(model.geom_type[n]),
                "collision_masks": mask,
                "size_m": model.geom_size[n].tolist(),
                "local_xyz_m": model.geom_pos[n].tolist(),
                "local_quaternion_wxyz": model.geom_quat[n].tolist(),
                "rgba": model.geom_rgba[n].tolist(),
            }
        )
    return {
        "elements": compiled,
        "geom": geom,
        "joint_types": {model.joint(i).name: int(model.jnt_type[i]) for i in range(model.njnt)},
        "nq_nv": [model.nq, model.nv],
        "external_resources": {key: int(getattr(model, key)) for key in disallowed},
        "camera": {
            "position_m": model.cam_pos[0].tolist(),
            "quaternion": model.cam_quat[0].tolist(),
            "fovy_deg": float(model.cam_fovy[0]),
            "samples": int(model.vis.quality.offsamples),
        },
    }


def model_fingerprint(model):
    encoded = np.empty(mujoco.mj_sizeModel(model), dtype=np.uint8)
    mujoco.mj_saveModel(model, None, encoded)
    return hashlib.sha256(encoded.tobytes()).hexdigest()


def state_fingerprint(values):
    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()


def reset_spec():
    requested = read(ROOT / PLAN["source_reset"])[0]["parameters"]["requested"]
    for field in ("object_pose", "target_region_pose"):
        requested[field] = Pose(**requested[field])
    return PhysicalScenarioConfig(**requested)


@contextmanager
def without_camera(backend):
    stop = RuntimeError("registered no-exposure scope completed")
    try:
        try:
            with backend.sensor_capture_on_demand():
                yield
                raise stop
        except RuntimeError as error:
            if error is not stop:
                raise
        require(
            backend._camera is None and not backend._sensor_capture_on_demand,
            "no-exposure scope finished with an active camera",
        )
    finally:
        backend.shutdown()


def model_changes(name, backend, result):
    model, data = backend._model, backend._data
    if name == "direct_freebody_edit":
        address = int(model.joint("object_free").qposadr[0])
        result["before_pose_sha256"] = state_fingerprint(data.qpos[address : address + 7])
        data.qpos[address] += 0.001
        result["after_pose_sha256"] = state_fingerprint(data.qpos[address : address + 7])
        require(
            result["before_pose_sha256"] != result["after_pose_sha256"],
            "free-body test did not change",
        )
    else:
        before = model.geom_pos.copy()
        target = int(model.geom("table").id)
        model.geom_pos[target, 0] += 0.001
        result["changed_model_sha256"] = model_fingerprint(model)
        if name == "transient_compiled_edit":
            model.geom_pos[:] = before
            result["restored_model_sha256"] = model_fingerprint(model)
    backend.step(0)


def run_probe(name, scenario, config, declared):
    backend = MuJoCoPhysicsBackend()
    operations = []
    witnesses = []
    result = {"name": name, "operations": operations, "scope_witnesses": witnesses}
    backend.initialize(config)

    def native_event(event):
        row = {
            "kind": event.kind,
            "phase": event.phase,
            "operation_id": event.operation_id,
            "step": event.physics_step,
            "episode": event.episode_id,
            "error": event.error,
        }
        if event.kind == "COMMAND":
            row["command_type"] = event.parameters.get("command_type")
        operations.append(row)
        require(event.kind != "CAPTURE", "unexpected native capture")

    def test_request():
        if name == "native_one_step":
            require(backend.step(1).physics_steps == 1, "native step did not complete")
        elif name == "active_reset":
            backend.reset(scenario)
        elif name == "active_reinitialize":
            backend.initialize(config)
        elif name == "active_camera_move":
            backend.set_camera_position((0.35, 0, 1.41))
        elif name == "active_on_demand":
            with backend.sensor_capture_on_demand():
                raise AssertionError("active scope executed")
        elif name == "active_fault":
            backend.inject_fault(PhysicalFault(PhysicalFaultType.OBJECT_SLIP))
        elif name == "other_thread_command":
            target = JointCommand(positions=backend.get_joint_state().positions)
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(backend.apply_joint_targets, target).result(timeout=4)
        else:
            model_changes(name, backend, result)

    with without_camera(backend), backend.observe_operation_boundaries(native_event):
        backend.reset(scenario)
        require(
            backend.get_sim_time() == 0 and backend._data.qpos[0] == -0.8, "original reset changed"
        )
        require(
            backend._mjspec_xml_sha256 == "" and not backend._model_parameters,
            "registered direct load bypassed",
        )
        owner_model = backend._model
        owner_pid = threading.get_native_id()
        episode = backend._episode_id
        stamp = model_fingerprint(owner_model)
        result.update(episode=episode, initial_model_sha256=stamp, scenario=scenario.scenario_id)
        if name == "native_one_step":
            result["inventory"] = compiled_inventory(owner_model, declared)

        def boundary(check):
            model_hash = model_fingerprint(backend._model)
            witnesses.append(
                {
                    "kind": check.kind,
                    "phase": check.phase,
                    "step": check.physics_step,
                    "episode": check.episode_id,
                    "model_sha256": model_hash,
                }
            )
            require(
                check.episode_id == episode
                and threading.get_native_id() == owner_pid
                and backend._model is owner_model
                and model_hash == stamp,
                "registered compiled model, episode or owner changed",
            )
            require(
                backend._target_motion is None
                and not np.any(backend._data.xfrc_applied)
                and not np.any(backend._data.qfrc_applied),
                "unregistered external actuator source",
            )

        try:
            with backend.enforce_execution_guard(
                boundary, termination_scope=lambda _: nullcontext()
            ):
                test_request()
        except (ValueError, RuntimeError) as error:
            result["request"] = {
                "accepted": False,
                "type": type(error).__name__,
                "error": str(error),
            }
        else:
            result["request"] = {"accepted": True}
        result["final_model_sha256"] = model_fingerprint(backend._model)
        result["physical_steps"] = backend.total_physics_steps
        result["guard_events"] = plain(backend.execution_guard_events)
        result["commands"] = [dict(row) for row in backend.command_records]
        result["estop"] = backend.estop_engaged
        result["guard_settled"] = backend.guard_stop_settled
        result["camera_instances"] = int(backend._camera is not None)
    result["shutdown_complete"] = backend._data is None and backend._camera is None
    return result


def foreign_xml(path, declared):
    tree = ElementTree.parse(ASSET)
    needle = ElementTree.SubElement(tree.getroot().find("worldbody"), "geom")
    needle.attrib.update(
        name="diagnostic_foreign_needle", type="box", size="0.001 0.001 0.01", pos="0.38 -0.10 0.01"
    )
    with path.open("xb") as stream:
        tree.write(stream, encoding="utf-8")
    try:
        admitted_asset(path)
    except ValueError as error:
        reason = str(error)
    else:
        raise ValueError("foreign asset entered nominal admission")
    model = mujoco.MjModel.from_xml_path(str(path))
    geom = model.geom("diagnostic_foreign_needle")
    require(
        model.ngeom == len(declared["geom"]) + 1 and geom.bodyid[0] == 0, "missing foreign solid"
    )
    return {
        "sha256": sha(path),
        "nominal_refusal": reason,
        "additional_geom": geom.name,
        "additional_geom_collision_masks": [int(geom.contype[0]), int(geom.conaffinity[0])],
        "additional_backend_resets": 0,
    }


def capture():
    verify_sources()
    require(
        not OUT.exists() and OUT.resolve() == OUT, "attempt already exists or resolves elsewhere"
    )
    root = admitted_asset(ASSET)
    declared = xml_inventory(root)
    scenario = reset_spec()
    config = SimulatorConfig(
        model_path=str(ASSET),
        seed=scenario.seed,
        physics_dt_s=1 / 240,
        domain_randomization=False,
        render_rgb=True,
        render_depth=True,
    )
    OUT.mkdir(parents=True)
    create(
        OUT / "registration.json",
        {
            "plan_sha256": sha(HERE / "plan.json"),
            "plan_md_sha256": sha(HERE / "plan.md"),
            "code_sha256": sha(Path(__file__).resolve()),
            "xml_tree": declared,
            "runtime": PLAN["source_generation"],
            "config": config.model_dump(mode="json"),
            "asset_sha256": WORLD_ASSET,
            "guard_scope": "one native owner thread, development only",
        },
    )
    complete = False
    try:
        create(OUT / "foreign-probe.json", foreign_xml(OUT / "foreign-probe.xml", declared))
        for name in PLAN["probes"]:
            create(OUT / f"{name}.json", run_probe(name, scenario, config, declared))
        complete = True
    except BaseException as error:
        create(OUT / "aborted.json", {"type": type(error).__name__, "error": str(error)})
        raise
    finally:
        create(
            OUT / "capture-seal.json",
            {
                "complete": complete,
                "sha256": {
                    path.name: sha(path) for path in sorted(OUT.iterdir()) if path.is_file()
                },
            },
        )


def registered_refusals():
    path = next(
        ROOT / key for key in PLAN["input_sha256"] if key.endswith("/pixel-envelope.public.json")
    )
    raw = read(path)
    previous = raw["preceding_clear_same_pixels_intersecting_complete_envelope"]
    stopped = raw["stop_pixels_intersecting_complete_envelope"]
    first = raw["old_t02"]["old_no_pin_stop_with_pin_geometry"]
    pixel_alias = raw["old_t02"]["native_optical_alias"]["bare_and_pin_RGB_depth_mask_identical"]
    volume = next(row for row in raw["volume_control"] if row["step"] == 2000)
    require(
        raw["compared_stop_clear_pairs"] == 5
        and stopped == previous == [10, 10]
        and first["first_intersection_stop_step"] == 176
        and first["intersecting_discrete_poses"] == 65
        and first["native_discrete_pose_count"] == 241
        and pixel_alias is True
        and volume["reason"] == "payload_horizon_outside_registered_volume"
        and 0.00110 < volume["minimum_gap_m"] < 0.00112,
        "frozen hazard and registered-volume controls changed",
    )
    return {
        "pairs": raw["compared_stop_clear_pairs"],
        "stopped_pixel_overlaps": stopped,
        "previous_clear_same_pixel_overlaps": previous,
        "old_needle_native_first_step": first["first_intersection_stop_step"],
        "old_needle_colliding_discrete_states": first["intersecting_discrete_poses"],
        "old_original_resolution_pair_identical": pixel_alias,
        "volume_rejection": volume,
        "complete_potential_occupancy_separation_proven": False,
        "new_current_optical_attribution": False,
    }


def inspect_probe(name, row):
    require(
        row["name"] == name
        and row["shutdown_complete"]
        and row["guard_settled"]
        and row["estop"]
        and row["camera_instances"] == 0,
        f"incomplete or unreleased backend: {name}",
    )
    require(
        not any(event["kind"] == "CAPTURE" for event in row["operations"]), "new exposure present"
    )
    require(
        all(
            command["type"] in {"hold_current_joints", "emergency_stop"}
            for command in row["commands"]
        ),
        "guard admitted an unplanned command",
    )
    trace = [(event["kind"], event["phase"]) for event in row["scope_witnesses"]]
    if name == "native_one_step":
        require(
            row["request"]["accepted"]
            and row["physical_steps"] == 1
            and row["initial_model_sha256"] == row["final_model_sha256"]
            and trace
            == [
                ("RETURN", "BEFORE"),
                ("CONTROL", "BEFORE"),
                ("CONTROL", "AFTER"),
                ("PHYSICS", "BEFORE"),
                ("PHYSICS", "AFTER"),
                ("RETURN", "AFTER"),
            ],
            "native CONTROL/PHYSICS/RETURN proof differs",
        )
        return "original_owner_step_reproduced"
    require(
        not row["request"]["accepted"] and row["physical_steps"] == 0, f"negative moved: {name}"
    )
    error = row["request"]["error"]
    if name == "other_thread_command":
        require("belongs to another thread" in error, "different cause for foreign owner refusal")
    elif name == "persistent_compiled_edit":
        require(
            "registered compiled model, episode or owner changed" in error
            and row["changed_model_sha256"] != row["initial_model_sha256"]
            and trace == [("RETURN", "BEFORE")]
            and row["scope_witnesses"][0]["model_sha256"] == row["changed_model_sha256"],
            "persistent model edit was not caught by the read boundary",
        )
        return "persistent_model_edit_detected"
    elif name in {"transient_compiled_edit", "direct_freebody_edit"}:
        require(
            error == "steps must be positive" and trace == [("RETURN", "BEFORE")],
            "scope unexpectedly saw an unauthorized low-level edit",
        )
        require(
            row["scope_witnesses"][0]["model_sha256"] == row["initial_model_sha256"],
            "scope digest unexpectedly records restored or direct state edit",
        )
        if name == "transient_compiled_edit":
            require(
                row["changed_model_sha256"]
                != row["restored_model_sha256"]
                == row["initial_model_sha256"],
                "transient model edit did not restore",
            )
        else:
            require(
                row["before_pose_sha256"] != row["after_pose_sha256"],
                "freebody negative control did not change",
            )
        return "low_level_change_not_seen_by_scope_boundary"
    else:
        require(
            "guarded backend lifecycle cannot be reset or reinitialized" in error,
            f"public mutation produced a different refusal: {name}",
        )
    return "original_public_mutation_blocked"


def cold(output):
    verify_sources()
    seal_path = OUT / "capture-seal.json"
    seal = read(seal_path)
    require(seal["complete"], "incomplete scene authority probe")
    require(all(sha(OUT / key) == digest for key, digest in seal["sha256"].items()), "seal changed")
    reg = read(OUT / "registration.json")
    require(
        reg["plan_sha256"] == sha(HERE / "plan.json")
        and reg["plan_md_sha256"] == sha(HERE / "plan.md")
        and reg["code_sha256"] == sha(Path(__file__).resolve()),
        "registration changed",
    )
    declaration = xml_inventory(admitted_asset(ASSET))
    require(declaration == reg["xml_tree"], "parse closure differs")
    model = mujoco.MjModel.from_xml_path(str(ASSET))
    measured = compiled_inventory(model, declaration)
    original = read(OUT / "native_one_step.json")["inventory"]
    require(
        measured == original, "independent compile inventory differs from actual native backend"
    )
    foreign = read(OUT / "foreign-probe.json")
    extra = (
        ElementTree.parse(OUT / "foreign-probe.xml")
        .getroot()
        .find("./worldbody/geom[@name='diagnostic_foreign_needle']")
    )
    require(
        extra is not None
        and foreign["sha256"] == sha(OUT / "foreign-probe.xml")
        and foreign["nominal_refusal"] == "source asset bytes are not admitted"
        and foreign["additional_geom"] == extra.attrib["name"]
        and foreign["additional_geom_collision_masks"] == [1, 1]
        and foreign["additional_backend_resets"] == 0,
        "foreign geometry or refusal changed",
    )
    rows = [read(OUT / f"{name}.json") for name in PLAN["probes"]]
    require(
        len({row["episode"] for row in rows})
        == len(rows)
        <= PLAN["bounds"]["backend_instances_max"],
        "shared or unregistered native episode",
    )
    checks = {}
    for name, row in zip(PLAN["probes"], rows, strict=True):
        result = inspect_probe(name, row)
        checks[name] = {
            "result": result,
            "request": row["request"],
            "physical_steps": row["physical_steps"],
            "native_cleanup_commands": [command["type"] for command in row["commands"]],
            "scope_boundaries": len(row["scope_witnesses"]),
        }
    require(sum(row["physical_steps"] for row in rows) == 1, "wrong native budget")
    create(
        output,
        {
            "schema": "g1.research.nominal-scene-authority.readback.v1",
            "capture_seal_sha256": sha(seal_path),
            "actual_original_nominal_inventory": {
                k: len(v) for k, v in measured["elements"].items()
            },
            "compiled_model": measured,
            "foreign": foreign,
            "checks": checks,
            "native_backend_instances": len(rows),
            "native_steps": 1,
            "declared_asset_source_and_public_lifecycle_proven": True,
            "continuous_closed_scope_proven": False,
            "optical_gate_new_authorization": False,
            "frozen_counterevidence": registered_refusals(),
            "new_exposures": 0,
            "new_formal_trials": 0,
            "whole_trials": 0,
            "hardware": 0,
            "remote": 0,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "capture", "cold"))
    parser.add_argument("output", type=Path, nargs="?")
    args = parser.parse_args()
    if args.mode == "capture":
        capture()
    elif args.mode == "cold":
        cold(args.output)
    else:
        verify_sources()
        declared = xml_inventory(admitted_asset(ASSET))
        registered_refusals()
        print(
            json.dumps({name: len(records) for name, records in declared.items()}, sort_keys=True)
        )


if __name__ == "__main__":
    main()
