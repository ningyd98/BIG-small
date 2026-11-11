"""Versioned marker preparation binds geometry without releasing execution."""

import copy
import hashlib
import json
from dataclasses import FrozenInstanceError
from importlib import import_module, util
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from cloud_edge_robot_arm.research import native_calibration_collection as collection
from cloud_edge_robot_arm.research.native_collection_grounding import geometry_registration
from cloud_edge_robot_arm.vision.native_calibration import (
    NativeCalibrationRegistration,
    NativeGeometryRegistration,
    required_native_source_paths,
)

ROOT = Path(__file__).resolve().parents[1]
FAMILY = "outboard_id7_75mm_r579"
ASSET = "assets/robots/franka_panda/scene_pose_marker_outboard_75mm_r579.xml"
ASSET_SHA = "bc7a40dc3cfcb843154375feb1c0689749f1376be32da3d9aef0bb96472a18bd"
CONFIG = "configs/research/native_operational_calibration_75mm_r579.yaml"
FAMILY_SOURCE = "src/cloud_edge_robot_arm/vision/marker_families.py"
PREFIX = "pose_marker_outboard_v3_"


def families():
    name = "cloud_edge_robot_arm.vision.marker_families"
    assert util.find_spec(name) is not None, "versioned marker families are missing"
    return import_module(name)


def prepare(tmp_path):
    destination = tmp_path / "protocol"
    receipt = collection.prepare_native_calibration(ROOT / CONFIG, output=destination)
    return destination, receipt, collection.load_json(destination / "protocol.json")


def test_explicit_family_binds_exact_asset_size_and_keeps_legacy_default():
    family = families().marker_family(FAMILY)
    with pytest.raises(FrozenInstanceError):
        family.marker_size_m = 0.045
    with pytest.raises(ValueError):
        families().marker_family("caller-defined-family")
    geometry = geometry_registration(marker_family_id=FAMILY)
    NativeGeometryRegistration(geometry).validate_asset(ROOT)
    assert geometry["marker_family"] == FAMILY
    assert geometry["registration_id"] == "native-r579-outboard-75mm"
    assert geometry["asset_path"] == ASSET
    assert geometry["pose_marker"]["marker_size_m"] == 0.075
    assert geometry["pose_marker"]["marked_asset_sha256"] == ASSET_SHA
    assert hashlib.sha256((ROOT / ASSET).read_bytes()).hexdigest() == ASSET_SHA
    legacy = geometry_registration()
    assert "marker_family" not in legacy
    assert legacy["pose_marker"]["marker_size_m"] == 0.045
    assert legacy["asset_path"] == collection.MARKED_ASSET
    assert hashlib.sha256((ROOT / collection.MARKED_ASSET).read_bytes()).hexdigest() == (
        "ddc34b13d8df403f3fdeeab94be75ca988541f2eac0a3e534704f68200c39a23"
    )


@pytest.mark.parametrize(
    "case",
    [
        "dropped_tag",
        "legacy_tag",
        "unknown_tag",
        "legacy_asset",
        "alias",
        "legacy_hash",
        "resealed_hash",
        "legacy_size",
        "marker_id",
        "dictionary",
        "registration_id",
        "attachment",
        "untagged_known_registration",
    ],
)
def test_new_family_cannot_downgrade_or_mix_geometry(case):
    geometry = geometry_registration(marker_family_id=FAMILY)
    if case == "dropped_tag":
        del geometry["marker_family"]
    elif case in {"legacy_tag", "unknown_tag"}:
        geometry["marker_family"] = "outboard_id7_45mm_v3" if case == "legacy_tag" else "unknown"
    elif case == "legacy_asset":
        geometry["asset_path"] = collection.MARKED_ASSET
    elif case == "alias":
        geometry["asset_path"] = "assets/copy.xml"
    elif case in {"legacy_hash", "resealed_hash"}:
        geometry["pose_marker"]["marked_asset_sha256"] = (
            collection.MARKED_SHA if case == "legacy_hash" else "1" * 64
        )
    elif case == "legacy_size":
        geometry["pose_marker"]["marker_size_m"] = 0.045
    elif case == "marker_id":
        geometry["pose_marker"]["marker_id"] = 8
    elif case == "dictionary":
        geometry["pose_marker"]["dictionary"] = "DICT_5X5_50"
    elif case == "registration_id":
        geometry["registration_id"] = "native-r439-outboard-v3"
    elif case == "attachment":
        geometry["marker_to_object"][3] += 0.001
    else:
        geometry = geometry_registration()
        geometry["registration_id"] = "native-r579-outboard-75mm"
    with pytest.raises(ValueError):
        NativeGeometryRegistration(geometry)


def test_identical_alias_and_resealed_altered_bytes_do_not_bypass_family(tmp_path):
    geometry = geometry_registration(marker_family_id=FAMILY)
    alias = tmp_path / "assets/copy.xml"
    alias.parent.mkdir()
    alias.write_bytes((ROOT / ASSET).read_bytes())
    geometry["asset_path"] = "assets/copy.xml"
    with pytest.raises(ValueError):
        NativeGeometryRegistration(geometry).validate_asset(tmp_path)
    geometry = geometry_registration(marker_family_id=FAMILY)
    changed = tmp_path / ASSET
    changed.parent.mkdir(parents=True)
    changed.write_bytes((ROOT / ASSET).read_bytes().replace(b'rgba="0.01', b'rgba="0.02', 1))
    geometry["pose_marker"]["marked_asset_sha256"] = hashlib.sha256(
        changed.read_bytes()
    ).hexdigest()
    with pytest.raises(ValueError):
        NativeGeometryRegistration(geometry).validate_asset(tmp_path)


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "duplicate",
        "extra",
        "grid",
        "size",
        "bit",
        "quiet_size",
        "quiet_color",
        "mass",
        "density",
        "contact",
        "affinity",
        "group",
        "rotation",
        "material",
        "nested",
        "camera",
        "controller",
        "object",
    ],
)
def test_structure_validation_rejects_marker_or_nonmarker_changes(case):
    validator = families()._validate_75mm_structure
    original = (ROOT / ASSET).read_bytes()
    legacy = (ROOT / collection.MARKED_ASSET).read_bytes()
    validator(original, legacy)
    tree = ET.fromstring(original)
    body = tree.find("./worldbody/body[@name='object']")
    cell = body.find(f"geom[@name='{PREFIX}r0c0']")
    quiet = body.find(f"geom[@name='{PREFIX}quiet']")
    if case == "missing":
        body.remove(cell)
    elif case == "duplicate":
        body.append(copy.deepcopy(cell))
    elif case == "extra":
        extra = copy.deepcopy(cell)
        extra.set("name", PREFIX + "r6c0")
        body.append(extra)
    elif case == "grid":
        cell.set("pos", "0.09 0.03125 0.03504")
    elif case == "size":
        cell.set("size", "0.00375 0.00625 0.00001")
    elif case == "bit":
        cell.set("rgba", "0.98 0.98 0.98 1")
    elif case == "quiet_size":
        quiet.set("size", "0.04 0.05 0.00001")
    elif case == "quiet_color":
        quiet.set("rgba", "0.01 0.01 0.01 1")
    elif case in {"mass", "density", "contact", "affinity", "group"}:
        key = {"contact": "contype", "affinity": "conaffinity"}.get(case, case)
        cell.set(key, "1")
    elif case == "rotation":
        cell.set("quat", "0 0 0 1")
    elif case == "material":
        cell.set("material", "substitute")
    elif case == "nested":
        body.remove(cell)
        child = ET.SubElement(body, "body", name="marker_attachment")
        ET.SubElement(child, "joint", type="hinge")
        child.append(cell)
    elif case == "camera":
        tree.find("./worldbody/camera").set("fovy", "51")
    elif case == "controller":
        tree.find("./default/position").set("kp", "21")
    else:
        body.find("geom[@name='object_geom']").set("size", "0.04 0.035 0.035")
    with pytest.raises(ValueError):
        validator(ET.tostring(tree), legacy)


def test_new_sources_and_release_reference_follow_selected_asset(tmp_path):
    _, receipt, protocol = prepare(tmp_path)
    assert receipt["released_assignments"] == []
    sources = protocol["source_hashes"]
    assert {ASSET, CONFIG, FAMILY_SOURCE, collection.MARKED_ASSET} <= sources.keys()
    required = required_native_source_paths(marker_family_id=FAMILY)
    assert ASSET in required and FAMILY_SOURCE in required
    assert ASSET not in required_native_source_paths()
    release = protocol["release_reference"]
    assert release["marked_asset_sha256"] == ASSET_SHA
    assert release["source_hashes"][ASSET] == ASSET_SHA
    assert release["base_asset_sha256"] == collection.BASE_SHA
    assert release["measured_tcp_rotation"] is False
    assert release["source_generation"] == protocol["source_generation"]
    collection.check_sources(sources, marker_family_id=FAMILY)


@pytest.mark.parametrize("missing", [FAMILY_SOURCE, ASSET])
def test_native_registry_requires_selected_family_implementation_and_asset(tmp_path, missing):
    from tests.test_native_calibration_source import registration

    old, payload = registration(tmp_path)
    payload["geometry"] = geometry_registration(marker_family_id=FAMILY)
    payload["source_hashes"] = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in required_native_source_paths(marker_family_id=FAMILY)
    }
    path = old.artifact_root / old.registry_path
    path.write_text(json.dumps(payload))
    current = NativeCalibrationRegistration(
        old.artifact_root, ROOT, old.registry_path, hashlib.sha256(path.read_bytes()).hexdigest()
    )
    current.revalidate()
    del payload["source_hashes"][missing]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="inventory incomplete"):
        NativeCalibrationRegistration(
            old.artifact_root,
            ROOT,
            old.registry_path,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )


def test_preparation_is_unreleased_and_roundtrips_without_authority(tmp_path):
    directory, receipt, protocol = prepare(tmp_path)
    assert protocol["schema_version"] == "native.calibration.operational.v3"
    assert protocol["marker_family"] == FAMILY
    assert protocol["execution_release"] == "PREPARE_ONLY_NOT_RELEASED"
    assert receipt["native_qualification"] == protocol["native_qualification"] == "UNKNOWN"
    assert protocol["future_wall_bound"] is None
    assert protocol["budget_basis"] == "RECIPE_ESTIMATES_ONLY"
    assert protocol["physical_budget"] == 12960
    assert protocol["authorized_actual_budget"] and all(
        type(n) is int and n == 0 for n in protocol["authorized_actual_budget"].values()
    )
    rows = protocol["assignments"]
    assert [r["assignment_id"] for r in rows] == [f"native-r579-{i:04d}" for i in range(1, 10)]
    assert [r["seed"] for r in rows] == list(range(579001, 579010))
    assert all(r["status"] == "PREASSIGNED_NOT_RUN" for r in rows)
    assert all(r["pool"] == "CALIBRATION_ONLY" for r in rows)
    assert [r["ancestors"] for r in rows] == [
        [f"native-r579-preregistered-{i:04d}"] for i in range(1, 10)
    ]
    assert not (directory / "claims").exists()
    for current in (False, True):
        assert collection.read_protocol(directory, current_sources=current) == protocol


@pytest.mark.parametrize(
    "case",
    [
        "family",
        "schema",
        "settings_family",
        "settings_asset",
        "geometry_tag",
        "geometry_size",
        "release_hash",
        "source_config",
        "source_asset",
        "source_code",
        "source_generation",
        "assignment_seed",
        "assignment_ancestor",
        "assignment_status",
        "execution_release",
        "actual_budget",
        "released_setting",
        "unknown_field",
    ],
)
def test_both_protocol_read_modes_reject_cross_family_or_forged_release(tmp_path, case):
    directory, _, protocol = prepare(tmp_path)
    if case == "family":
        protocol["marker_family"] = "outboard_id7_45mm_v3"
    elif case == "schema":
        protocol["schema_version"] = "native.calibration.operational.v2"
    elif case in {"settings_family", "settings_asset", "released_setting"}:
        key, value = {
            "settings_family": ("marker_family", "unknown"),
            "settings_asset": ("model_path", collection.MARKED_ASSET),
            "released_setting": ("released_assignment", "native-r579-0001"),
        }[case]
        protocol["settings"][key] = value
    elif case == "geometry_tag":
        del protocol["geometry"]["marker_family"]
    elif case == "geometry_size":
        protocol["geometry"]["pose_marker"]["marker_size_m"] = 0.045
    elif case == "release_hash":
        protocol["release_reference"]["marked_asset_sha256"] = collection.MARKED_SHA
    elif case in {"source_config", "source_asset", "source_code"}:
        del protocol["source_hashes"][
            {
                "source_config": CONFIG,
                "source_asset": ASSET,
                "source_code": FAMILY_SOURCE,
            }[case]
        ]
        protocol["source_generation"] = collection.digest(protocol["source_hashes"])
    elif case == "source_generation":
        protocol["source_generation"] = "0" * 64
    elif case == "assignment_seed":
        protocol["assignments"][0]["seed"] = 439001
    elif case == "assignment_ancestor":
        protocol["assignments"][0]["ancestors"] = ["native-r439-preregistered-0001"]
    elif case == "assignment_status":
        protocol["assignments"][0]["status"] = "RELEASED"
    elif case == "execution_release":
        protocol["execution_release"] = "RELEASED"
    elif case == "actual_budget":
        protocol["authorized_actual_budget"]["physics_steps"] = 1
    else:
        protocol["extra"] = 0
    (directory / "protocol.json").write_text(json.dumps(protocol))
    for current in (False, True):
        with pytest.raises(ValueError):
            collection.read_protocol(directory, current_sources=current)


def test_new_config_cannot_be_created_by_changing_legacy_size_or_path(tmp_path):
    settings = collection.load_json(ROOT / collection.CONFIG)
    settings["model_path"] = ASSET
    settings["marked_asset_sha256"] = ASSET_SHA
    altered = tmp_path / "unregistered.json"
    altered.write_text(json.dumps(settings))
    with pytest.raises(ValueError):
        collection.prepare_native_calibration(altered, output=tmp_path / "protocol")
    assert not (tmp_path / "protocol").exists()


@pytest.mark.parametrize("assignment", ["native-r579-0001", "native-r439-0001", "unknown"])
def test_prepare_only_protocol_refuses_before_any_output_or_application(
    tmp_path, monkeypatch, assignment
):
    from cloud_edge_robot_arm.research import native_collection_application as application

    directory, _, _ = prepare(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("prepare-only protocol reached application side effects")

    monkeypatch.setattr(application, "fresh_directory", forbidden)
    output = tmp_path / "run"
    with pytest.raises(ValueError, match="prepare.only"):
        application.NativeCollectionApplication.from_startup(
            directory, assignment_id=assignment, output=output
        )
    with pytest.raises(ValueError, match="prepare.only"):
        collection.collect_native_calibration_once(
            directory, assignment_id=assignment, output=output
        )
    assert not output.exists()
    assert not (directory / "claims").exists()


def legacy_protocol(tmp_path):
    directory = tmp_path / "legacy"
    collection.prepare_native_calibration(ROOT / collection.CONFIG, output=directory)
    return directory, collection.load_json(directory / "protocol.json")


def assert_protocol_rejected(directory, protocol):
    (directory / "protocol.json").write_text(json.dumps(protocol))
    for current in (False, True):
        with pytest.raises(ValueError):
            collection.read_protocol(directory, current_sources=current)


@pytest.mark.parametrize("remove_tags", [False, True])
def test_protocol_downgrade_cannot_replace_headers_and_keep_new_family(tmp_path, remove_tags):
    directory, _, protocol = prepare(tmp_path)
    protocol["schema_version"] = "native.calibration.operational.v2"
    protocol["settings"] = collection.load_json(ROOT / collection.CONFIG)
    protocol["config_sha256"] = hashlib.sha256((ROOT / collection.CONFIG).read_bytes()).hexdigest()
    if remove_tags:
        for key in (
            "marker_family",
            "execution_release",
            "budget_basis",
            "authorized_actual_budget",
        ):
            del protocol[key]
        del protocol["geometry"]["marker_family"]
        protocol["source_generation"] = collection.digest(protocol["source_hashes"])
        protocol["release_reference"]["source_generation"] = protocol["source_generation"]
    assert_protocol_rejected(directory, protocol)


@pytest.mark.parametrize(
    "identity",
    [
        "geometry_tag",
        "geometry_path",
        "geometry_hash",
        "geometry_registration",
        "geometry_size",
        "top_tag",
        "execution_release",
        "budget_basis",
        "authorized_actual_budget",
        "config_sha",
        "source_asset",
        "source_config",
        "source_alias_asset",
        "source_alias_config",
        "release_hash",
        "release_tag",
        "release_source_asset",
        "release_source_config",
        "release_source_alias_asset",
        "release_source_alias_config",
    ],
)
def test_protocol_downgrade_rejects_single_residual_identity_after_resealing(tmp_path, identity):
    directory, protocol = legacy_protocol(tmp_path)
    config_sha = "621624088a9d3e3df7fe9de522b960abd8ea9c1c45193067b6978665fd88b6f3"
    if identity == "geometry_tag":
        protocol["geometry"]["marker_family"] = "outboard_id7_45mm_v3"
    elif identity == "geometry_path":
        protocol["geometry"]["asset_path"] = ASSET
    elif identity == "geometry_hash":
        protocol["geometry"]["pose_marker"]["marked_asset_sha256"] = ASSET_SHA
    elif identity == "geometry_registration":
        protocol["geometry"]["registration_id"] = "native-r579-outboard-75mm"
    elif identity == "geometry_size":
        protocol["geometry"]["pose_marker"]["marker_size_m"] = 0.075
    elif identity in {"top_tag", "execution_release", "budget_basis", "authorized_actual_budget"}:
        key = "marker_family" if identity == "top_tag" else identity
        protocol[key] = None if identity != "authorized_actual_budget" else {}
    elif identity == "config_sha":
        protocol["config_sha256"] = config_sha
    elif identity == "release_hash":
        protocol["release_reference"]["marked_asset_sha256"] = ASSET_SHA
    elif identity == "release_tag":
        protocol["release_reference"]["marker_family"] = "outboard_id7_45mm_v3"
    else:
        sources = (
            protocol["release_reference"]["source_hashes"]
            if identity.startswith("release_")
            else protocol["source_hashes"]
        )
        name = identity.removeprefix("release_")
        path, sha = {
            "source_asset": (ASSET, "0" * 64),
            "source_config": (CONFIG, "0" * 64),
            "source_alias_asset": ("assets/alias.xml", ASSET_SHA),
            "source_alias_config": ("configs/alias.json", config_sha),
        }[name]
        sources[path] = sha
    protocol["source_generation"] = collection.digest(protocol["source_hashes"])
    protocol["release_reference"]["source_generation"] = protocol["source_generation"]
    assert_protocol_rejected(directory, protocol)


@pytest.mark.parametrize(
    "field,value",
    [
        ("marker_family", FAMILY),
        ("model_path", ASSET),
        ("marked_asset_sha256", ASSET_SHA),
    ],
)
def test_protocol_downgrade_settings_are_not_legacy_recipe(tmp_path, field, value):
    directory, protocol = legacy_protocol(tmp_path)
    protocol["settings"][field] = value
    assert_protocol_rejected(directory, protocol)


def test_legacy_historical_source_generation_remains_readable(tmp_path):
    directory, protocol = legacy_protocol(tmp_path)
    assert FAMILY_SOURCE in protocol["source_hashes"]
    protocol["source_hashes"]["src/cloud_edge_robot_arm/vision/native_calibration.py"] = "1" * 64
    protocol["source_generation"] = collection.digest(protocol["source_hashes"])
    protocol["release_reference"]["source_generation"] = protocol["source_generation"]
    (directory / "protocol.json").write_text(json.dumps(protocol))
    assert collection.read_protocol(directory, current_sources=False) == protocol
    with pytest.raises(ValueError):
        collection.read_protocol(directory, current_sources=True)


@pytest.mark.parametrize("indent", [None, 4])
def test_new_config_input_bytes_reject_reformatting_before_output(tmp_path, monkeypatch, indent):
    original = (ROOT / CONFIG).read_bytes()
    supplied = tmp_path / "same-values.json"
    supplied.write_text(json.dumps(json.loads(original), indent=indent))
    assert json.loads(supplied.read_bytes()) == json.loads(original)
    assert hashlib.sha256(supplied.read_bytes()).digest() != hashlib.sha256(original).digest()
    output_calls = []
    original_fresh = collection.fresh_directory

    def record_output(path):
        output_calls.append(path)
        return original_fresh(path)

    monkeypatch.setattr(collection, "fresh_directory", record_output)
    output = tmp_path / "protocol"
    with pytest.raises(ValueError):
        collection.prepare_native_calibration(supplied, output=output)
    assert output_calls == []
    assert not output.exists()


def test_new_config_input_bytes_exact_copy_roundtrips_from_another_path(tmp_path):
    supplied = tmp_path / "exact-copy.json"
    supplied.write_bytes((ROOT / CONFIG).read_bytes())
    output = tmp_path / "protocol"
    receipt = collection.prepare_native_calibration(supplied, output=output)
    protocol = collection.load_json(output / "protocol.json")
    assert protocol["config_sha256"] == (
        "621624088a9d3e3df7fe9de522b960abd8ea9c1c45193067b6978665fd88b6f3"
    )
    assert receipt["protocol_sha256"] == collection.digest(protocol)
    for current in (False, True):
        assert collection.read_protocol(output, current_sources=current) == protocol


def test_legacy_config_input_bytes_keep_existing_admission(tmp_path):
    directory, protocol = legacy_protocol(tmp_path)
    for current in (False, True):
        assert collection.read_protocol(directory, current_sources=current) == protocol
    supplied = tmp_path / "compact-legacy.json"
    supplied.write_text(json.dumps(collection.load_json(ROOT / collection.CONFIG)))
    output = tmp_path / "compact-output"
    collection.prepare_native_calibration(supplied, output=output)
    compact = collection.load_json(output / "protocol.json")
    assert compact["config_sha256"] == hashlib.sha256(supplied.read_bytes()).hexdigest()
    assert collection.read_protocol(output, current_sources=False) == compact
    with pytest.raises(ValueError):
        collection.read_protocol(output, current_sources=True)
