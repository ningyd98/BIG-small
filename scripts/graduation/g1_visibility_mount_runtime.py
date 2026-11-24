"""Source-addressed registration adapter for the two development-only radial fixtures."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
from scripts.graduation.g1_formal_runtime import require
from scripts.graduation.perception_io import pinned, sha

PARENT_GENERATION = "c3ca24cf1dc459651bd99dc85a997c36d39108c91d3cf7fb73d35e8071487261"
PLAN_SHA = "f73a383f23408f6d53d30677928545ed4e515419ab0ed16da7b391c1275ed015"
PLAN = Path(
    "artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-approach-geometry-20261125/plan.json"
)
HELPER = "scripts/graduation/g1_visibility_radial.py"
ADAPTER = "scripts/graduation/g1_visibility_mount_runtime.py"
READER = "scripts/graduation/g1_dual_pixel_readback.py"
PROVIDER = "scripts/graduation/g1_dual_asset.py"
V2_XML = "assets/robots/franka_panda/scene_g1_development_dual_id7_y100_id8_x100_low_bracket_v2.xml"
V2_SHA = "a0bf24bdf2c7142e9aaeebdaf5dec02255bf06885dde0e2e56f009aaf89f9803"


def replacement(text, old, new):
    require(text.count(old) == 1, "unexpected registered source anchor: " + old)
    return text.replace(old, new)


def spec_for(offset_mm):
    from scripts.graduation import g1_visibility_radial as fixture

    require(type(offset_mm) is int and offset_mm in (15, 30), "unknown radial assembly")
    fields = (
        "offset_mm",
        "family",
        "registration_id",
        "asset_path",
        "asset_sha256",
        "body_mass_kg",
        "centers",
    )
    result = fixture.details(offset_mm)
    return json.loads(json.dumps({k: result[k] for k in fields}, allow_nan=False))


def checked_plan(repo, parent, *, frozen_detectors=False):
    plan = pinned(repo / PLAN, PLAN_SHA)
    require(
        sha(repo / PLAN.with_suffix(".md")) == plan["plan_md_sha256"], "changed mechanical plan"
    )
    prior_inputs = {
        "scripts/graduation/g1_visibility_trials.py",
        "scripts/graduation/g1_visibility_runtime.py",
    }
    if frozen_detectors:
        prior_inputs.update(
            (
                "scripts/graduation/g1_visibility_grid.py",
                "scripts/graduation/g1_visibility_vision.py",
            )
        )
    for name, h in plan["inputs_sha256"].items():
        path = (parent if name in prior_inputs else repo) / name
        require(sha(path) == h, "mechanical plan input changed: " + name)
    return plan


def provider_bytes(original, offset):
    text = original.decode()
    start = text.index("@lru_cache(maxsize=1)\ndef build_xml(r593)")
    end = text.index("def pose_registration(", start)
    text = (
        text[:start]
        + """@lru_cache(maxsize=1)
def build_xml(r593):
    if _sha(r593) != BASE_SHA:
        raise ValueError("exact original r593 asset required")
    original = (Path(__file__).resolve().parents[2] / _low_bracket.ASSET_PATH).read_bytes()
    if _sha(original) != _low_bracket.ASSET_SHA:
        raise ValueError("exact low-bracket V2 source required")
    return _radial.build_xml(original, RADIAL_OFFSET_MM)


"""
        + text[end:]
    )
    anchor = "from scripts.graduation import g1_dual_asset_v2 as _low_bracket"
    text = replacement(
        text,
        anchor,
        anchor
        + "\nfrom scripts.graduation import g1_visibility_radial as _radial\n"
        + f"RADIAL_OFFSET_MM = {offset}\n_radial_spec = _radial.details(RADIAL_OFFSET_MM)",
    )
    for old, field in {
        "FAMILY": "family",
        "REGISTRATION_ID": "registration_id",
        "ASSET_PATH": "asset_path",
        "ASSET_SHA": "asset_sha256",
        "BODY_MASS_KG": "body_mass_kg",
    }.items():
        text = replacement(
            text, old + " = _low_bracket." + old, old + ' = _radial_spec["' + field + '"]'
        )
    text = replacement(
        text,
        "CENTERS = {7: (0.0, 0.1, 0.03505), 8: (0.1, 0.0, 0.03505)}",
        'CENTERS = {int(k): tuple(v) for k,v in _radial_spec["centers"].items()}',
    )
    text = replacement(text, "POSES = (", f"SOURCE_FILES += ({HELPER!r}, {ADAPTER!r})\nPOSES = (")
    text = replacement(
        text,
        'schema="g1.development.dual-registration.v2",',
        (
            'schema="g1.development.dual-registration.radial.v3",\n'
            "                radial_offset_mm=RADIAL_OFFSET_MM,"
        ),
    )
    text = replacement(
        text, "_low_bracket.verify_parts(xml)", "_radial.verify_parts(xml, RADIAL_OFFSET_MM)"
    )
    text = replacement(
        text,
        "_low_bracket.compiled_faces(model)",
        "_radial.compiled_faces(model, RADIAL_OFFSET_MM)",
    )
    return text.encode()


def rigid_geometry(marker_center, rotation, marker_id, geometry):
    """Independently invert the preallocated rigid attachment; never read the online pose."""
    attachment = np.reshape(
        geometry["development_dual"]["markers"][str(marker_id)]["object_T_marker"], (4, 4)
    )
    world_marker = np.eye(4)
    world_marker[:3, :3] = np.reshape(rotation, (3, 3))
    world_marker[:3, 3] = marker_center
    world_object = world_marker @ np.linalg.inv(attachment)
    height = geometry["object_half_extent_m"][2]
    tcp = world_object @ np.reshape(geometry["object_to_tcp"], (4, 4))
    return world_object[:3, 3], (world_object @ [0, 0, height, 1])[:3], tcp[:3, 3]


def reader_bytes(original):
    text = original.decode()
    text = replacement(
        text,
        "def dual_read(frame, geometry):",
        """def dual_read(frame, geometry):
    from scripts.graduation import g1_dual_asset as bound_asset
    from scripts.graduation.g1_visibility_mount_runtime import rigid_geometry
    bound_asset.validate_geometry(geometry)""",
    )
    before = (
        '            measure["marker_center_world_m"], measure["rotation_marker_to_world"], marker'
    )
    text = replacement(
        text,
        "obj, top, tcp = rigid_points(\n" + before + "\n",
        "obj, top, tcp = rigid_geometry(\n" + before + ", geometry\n",
    )
    return text.encode()


def verify_geometry(old, actual, spec, catalog):
    """Reconstruct each authorized difference. All remaining original fields must compare equal."""
    from scripts.graduation import g1_dual_asset as asset

    from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration

    baseline = copy.deepcopy(old)
    require(
        old["asset_path"] == V2_XML
        and old["pose_marker"]["marked_asset_sha256"] == V2_SHA
        and old["development_dual"]["structure_parts_per_side"] == ["plate", "crossbar", "upright"],
        "wrong frozen reference assembly",
    )
    for k, field in (
        ("registration_id", "registration_id"),
        ("marker_family", "family"),
        ("asset_path", "asset_path"),
    ):
        baseline[k] = spec[field]
    baseline["pose_marker"]["marked_asset_sha256"] = spec["asset_sha256"]
    dual = baseline["development_dual"]
    dual.update(
        schema="g1.development.dual-registration.radial.v3",
        radial_offset_mm=spec["offset_mm"],
        scene_asset_sha256=spec["asset_sha256"],
        structure_mass_kg=spec["body_mass_kg"] - 0.08,
    )
    for code in (7, 8):
        marker = dual["markers"][str(code)]
        dims = [0.0, 0.0, 0.03505]
        dims[1 if code == 7 else 0] = (100 + spec["offset_mm"]) / 1000
        require(
            np.allclose(spec["centers"][str(code)], dims, atol=1e-15, rtol=0),
            "foreign marker translation",
        )
        matrix = marker["object_T_marker"]
        matrix[3], matrix[7], matrix[11] = spec["centers"][str(code)]
        marker["marker_registration_hash"] = PoseMarkerRegistration(
            code, 0.075, spec["asset_sha256"]
        ).digest()
    baseline["marker_to_object"] = list(dual["markers"]["7"]["object_T_marker"])
    needed = set(asset.SOURCE_FILES)
    require(
        needed <= catalog.keys() and catalog.get(spec["asset_path"]) == spec["asset_sha256"],
        "candidate source or XML absent",
    )
    sources = {k: catalog[k] for k in sorted(needed)}
    dual["development_sources_sha256"] = sources
    dual["development_source_generation"] = hashlib.sha256(
        json.dumps(sources, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    require(baseline == actual, "candidate geometry has an unregistered difference")
    return actual


def wrong_calibration_witness(directory, row):
    """Accept the two observed native refusal sites for the exact diagnostic mutation."""
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    measured = row.get("measurement") or {}
    servo_error = "servo MuJoCo calibration does not match frame intrinsics and pose"
    target_errors = {
        "initial registered geometry unavailable: registered_camera_mismatch",
        "registered collection geometry unavailable: observation_calibration_version_changed",
    }
    zero_counts = ("servo_accepted", "commands", "physics_steps", "source_step")
    if not (
        measured.get("reason") == "registered_camera_mismatch"
        and measured.get("usable") is False
        and row.get("servo_refusal") == servo_error
        and row.get("target_refusal") in target_errors
        and row.get("target_emitted") is False
        and all(row.get(key) == 0 for key in zero_counts)
    ):
        return False
    try:
        source = pinned(directory / "source.rgbd.json", row.get("source_sha256"))
        tested = pinned(directory / "tested.rgbd.json", row.get("tested_sha256"))
        original = RGBDObservation.model_validate(source)
        current = RGBDObservation.model_validate(tested)
    except ValueError:
        return False
    expected_frame = "dev-wrong-calibration-" + original.frame_id
    expected_packet = {
        **source,
        "frame_id": expected_frame,
        "observation_id": expected_frame,
        "calibration_version": "g1-intentional-foreign-calibration",
        "checksum_sha256": current.checksum_sha256,
    }
    return (
        original.calibration_version == "f33940579c533afe"
        and source["checksum_sha256"] == original.checksum_sha256
        and original.sim_time_s == 0
        and tested == expected_packet
        and row.get("id")
        == measured.get("observation_id")
        == measured.get("frame_id")
        == expected_frame
        and row.get("checksum") == measured.get("checksum") == current.checksum_sha256
        and measured.get("scene_id") == current.scene_id
        and measured.get("episode_id") == current.episode_id
    )


def negative_controls(
    directory, backend, registration, catalog, owner, original, state, color, grounding, endpoint
):
    from scripts.graduation import dynamic_vision as native
    from scripts.graduation import g1_dual_observer as observer
    from scripts.graduation import g1_dual_probe as probe
    from scripts.graduation.perception_io import write

    from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration

    directory.mkdir()
    geometry = registration.to_payload()
    rows = {}
    for kind in probe.NEGATIVE:
        folder = directory / kind
        folder.mkdir()
        if kind in ("wrong-transform", "wrong-asset", "wrong-source"):
            altered, identities = probe.protect_sources(kind, geometry, catalog)
            frame = probe.capture(backend, "both", segmented=False)

            def checked(altered=altered, frame=frame, identities=identities):
                other = NativeGeometryRegistration(altered)
                other.validate_asset(Path.cwd())
                return probe.registered_tracker(frame, other, identities)

            value, reason = probe.result_of(checked)
            result = dict(
                native_refusal=reason,
                target_emitted=value is not None,
                refusal_at_pinned_registration=reason
                in (
                    "development dual camera, marker, transform, asset or source binding differs",
                    "development dual registration and runtime sources differ",
                ),
                source_step=backend.total_physics_steps,
            )
            current = frame
        else:
            reference = probe.capture(backend, "both", segmented=False)
            provider = native.OpenCVServoFeedback(
                reference,
                color,
                grounding,
                skill="MOVE_ABOVE",
                initial_target=endpoint,
                marker_family_id=registration.marker_family_id,
                verify_mujoco_calibration=True,
            )
            frame, labels, instances, _ = probe.capture(backend, kind, segmented=True)
            current = probe.fault_packet(frame, kind, labels, instances)
            feedback, servo_reason = probe.result_of(
                lambda provider=provider, current=current: provider.update(current)
            )

            def target(current=current):
                tracker = probe.registered_tracker(current, registration, catalog)
                return probe.target(owner, original, tracker, current, state)

            emitted, target_reason = probe.result_of(target)
            measurement = observer.measure_frame(current, geometry)
            expected = probe.expected_refusal(kind, measurement, servo_reason, target_reason)
            result = dict(
                original_guard_evidence=expected,
                servo_refusal=servo_reason,
                target_refusal=target_reason,
                measurement=measurement,
                target_emitted=emitted is not None or feedback is not None,
                servo_accepted=len(provider.records),
                source_step=backend.total_physics_steps,
            )
        write(folder / "source.rgbd.json", frame.model_dump(mode="json"))
        write(folder / "tested.rgbd.json", current.model_dump(mode="json"))
        result.update(
            source_sha256=sha(folder / "source.rgbd.json"),
            tested_sha256=sha(folder / "tested.rgbd.json"),
            id=current.frame_id,
            checksum=current.checksum_sha256,
            physics_steps=backend.total_physics_steps,
            commands=len(backend.command_records),
        )
        if kind == "wrong-calibration":
            result["frozen_probe_guard_evidence"] = result["original_guard_evidence"]
            result["original_guard_evidence"] = wrong_calibration_witness(folder, result)
        write(folder / "result.json", result)
        rows[kind] = dict(
            sha256=sha(folder / "result.json"),
            blocked=(
                not result["target_emitted"]
                and result.get(
                    "refusal_at_pinned_registration", result.get("original_guard_evidence", False)
                )
                and result["physics_steps"] == result["commands"] == 0
            ),
        )
    write(directory / "seal.json", rows)
    require(
        all(r["blocked"] for r in rows.values()),
        "radial qualification negative controls: "
        + ", ".join(k for k, r in rows.items() if not r["blocked"]),
    )


def radial_blind(directory, geometry):
    import os

    from scripts.graduation import g1_dual_batch_score as scorer
    from scripts.graduation.perception_io import ROOT, read, write

    pixels = directory / "blind-input"
    pixels.mkdir()
    bundles = {}
    for kind in ("positive", "only-7", "only-8", "full-occlusion"):
        folder = directory / kind
        trace = read(folder / "trace.json")
        original = folder / "tested.rgbd.json"
        token = sha(original)
        dest = pixels / token
        dest.mkdir()
        os.link(original, dest / "0000.json")
        packet = read(original)
        bundles[token] = dict(
            episode=trace["episode"],
            scene=trace["scene"],
            registered_scene=trace["scene"],
            geometry=geometry,
            mode="dual",
            frames=[
                dict(
                    file="0000.json",
                    file_sha256=token,
                    frame_id=packet["frame_id"],
                    checksum_sha256=packet["checksum_sha256"],
                    physics_step=0,
                )
            ],
        )
    index = pixels / "index.json"
    write(index, bundles)
    seals = []
    for name in ("blind-one", "blind-two"):
        scorer.blind_reader(ROOT, index, directory / name)
        seals.append(sha(directory / name / "seal.json"))
    require(len(set(seals)) == 1, "new assembly's independent score seals disagree")
    return dict(index_sha256=sha(index), seals_sha256=seals)


def radial_preflight(repo, private, generation, lock):
    import shutil
    import sys
    import tempfile

    from scripts.graduation import g1_dual_asset as asset
    from scripts.graduation import g1_dual_trials as dual
    from scripts.graduation import g1_formal_trials as formal
    from scripts.graduation import g1_visibility_runtime as build
    from scripts.graduation import g1_visibility_trials as trials
    from scripts.graduation.g1_formal_runtime import bind_scene
    from scripts.graduation.perception_io import ROOT, read, write

    mechanical, prior = build.verify_build(private, PARENT_GENERATION)
    timing = lock.get("radial_timing")
    checked_plan(repo, mechanical, frozen_detectors=timing is not None)
    if lock.get("radial_contact") is not None:
        from scripts.graduation import g1_visibility_radial_contact as contact

        parent, parent_pf = contact.verify(repo, private, generation, lock)
        parent_generation = contact.PARENT
        expected_detectors = parent_pf["radial_timing"]["detector_files_sha256"]
    elif timing is not None:
        parent, parent_pf = build.verify_timing_build(repo, private, lock)
        parent_generation = build.TIMING_PARENT
        expected_detectors = timing["detector_files_sha256"]
    else:
        parent, parent_generation = mechanical, PARENT_GENERATION
        parent_pf = pinned(
            parent.parent / "preflight.json",
            "ed3771d25a59535c1c4f3f5eb6511bb8c0b1e31dcd05a80b7f79528fa551d5bc",
        )
        expected_detectors = prior["detector_files_sha256"]
    frozen_pf = parent.parent / "preflight.json"
    inherited = build.check_history(repo, read(repo / build.PLAN))
    first, old, full = trials.template(repo, lock)
    geom = old["geometry"]
    registration = dual.NativeGeometryRegistration(geom)
    registration.validate_asset(ROOT)
    witness = trials.qualified_preflight_pose(repo)
    root = private / "builds" / generation
    directory = Path(tempfile.mkdtemp(prefix="zero-step-radial-", dir=root))
    scene = trials.RELEASE + "/" + directory.name + "-qualification"
    ver = dict(
        python=sys.version,
        mujoco=dual.runtime.mujoco.__version__,
        opencv=dual.runtime.cv2.__version__,
        numpy=dual.runtime.np.__version__,
        pillow=dual.runtime.PIL.__version__,
    )
    require(
        ver == parent_pf["versions"]
        and sha(Path(sys.executable)) == parent_pf["interpreter_sha256"]
        and expected_detectors == lock["detector_files_sha256"],
        "parent software, environment or detector differs",
    )
    sw = trials.diagnostic_owner_software(directory / "software", scene, full, generation)
    with trials.device(private), bind_scene(scene):
        mass = formal.ready_device({"dual": (first, old, full)}, 16 * 2**30, private)
        audited = asset.audit_asset(ROOT)
        write(directory / "compiled-geometry.json", audited)
        cases = {
            kind: trials.occlusion_control(
                directory / kind,
                kind,
                registration,
                full,
                witness,
                generation,
                scene,
                radial_checks=True,
            )
            for kind in ("positive", "only-7", "only-8", "full-occlusion")
        }
    blind = radial_blind(directory, geom)
    require(
        inherited == build.check_history(repo, read(repo / build.PLAN)),
        "frozen formal originals changed",
    )
    neg = directory / "positive/negative-controls/seal.json"
    write(
        directory / "seal.json",
        dict(
            cases=cases,
            negative_controls_sha256=sha(neg),
            compiled_geometry_sha256=sha(directory / "compiled-geometry.json"),
            blind=blind,
        ),
    )
    data = dict(
        schema="g1.visibility.development-preflight.radial.v1",
        eligible=True,
        plan_sha256=build.PLAN_SHA,
        radial_plan_sha256=PLAN_SHA,
        runtime_build_sha256=generation,
        parent_runtime_build_sha256=parent_generation,
        parent_preflight_sha256=sha(frozen_pf),
        history=inherited,
        radial_assembly=lock["radial_assembly"],
        registration=geom,
        compiled=mass,
        versions=ver,
        qualification_pose=witness["pose_xyzyaw"],
        qualification_seed=witness["seed"],
        negative_controls_sha256=sha(neg),
        independent_pixel_readback=blind,
        imported_project_files=dual.g1_mount_trials.project_imports(lock),
        interpreter_sha256=sha(Path(sys.executable)),
        available_bytes=shutil.disk_usage(private).free,
        software_owner_sha256=sw,
        calibration=geom["camera"],
        full_occlusion_directory=directory.name,
        probe_seal_sha256=sha(directory / "seal.json"),
        physics_steps=0,
        motion_commands=0,
        hold_commands=1,
        diagnostic_resets=4,
        development_trials=0,
        hardware_actions=0,
        formal_claims=0,
    )
    if timing is not None:
        data["radial_timing"] = timing
    if "radial_contact" in lock:
        data["radial_contact"] = lock["radial_contact"]
    output = root / "preflight.json"
    if not output.exists():
        write(output, data)
    require(read(output)["runtime_build_sha256"] == generation, "foreign radial preflight")
    return sha(output)
