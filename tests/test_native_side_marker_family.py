"""The measured +Y attachment has its own immutable, unreleased identity."""

import copy
import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from cloud_edge_robot_arm.research import native_calibration_collection as collection
from cloud_edge_robot_arm.research.native_collection_grounding import geometry_registration
from cloud_edge_robot_arm.vision import marker_families as families
from cloud_edge_robot_arm.vision.native_calibration import (
    NativeCalibrationRegistration,
    NativeGeometryRegistration,
    required_native_source_paths,
)

ROOT = Path(__file__).resolve().parents[1]
FAMILY = "side_y_plus_id7_75mm_r593"
X_FAMILY = "outboard_id7_75mm_r579"
ASSET = "assets/robots/franka_panda/scene_pose_marker_side_y_plus_75mm_r593.xml"
ASSET_SHA = "1e95054dc74e1c8ff51042290450b5e01e7410dd653870c553f056892efca140"
CONFIG = "configs/research/native_operational_calibration_side_y_plus_75mm_r593.yaml"
CONFIG_SHA = "fa876ce35780fbf98f50aa493199b8e9020b347cd57575fe71ca3a06c117f4c7"
FAMILY_SOURCE = "src/cloud_edge_robot_arm/vision/marker_families.py"
ATTACHMENT = [1, 0, 0, 0, 0, 1, 0, 0.1, 0, 0, 1, 0.03505, 0, 0, 0, 1]
PREFIX = "pose_marker_outboard_v3_"


def test_descriptor_selects_exact_side_attachment_and_preserves_other_geometry():
    family = families.marker_family(FAMILY)
    assert family.family_id == FAMILY
    assert family.registration_id == "native-r593-side-y-plus-75mm"
    assert family.asset_path == ASSET and family.asset_sha256 == ASSET_SHA
    assert family.marker_id == 7 and family.dictionary == "DICT_4X4_50"
    assert family.marker_size_m == 0.075
    assert list(family.marker_to_object) == ATTACHMENT
    with pytest.raises(FrozenInstanceError):
        family.marker_size_m = 0.045
    raw = (ROOT / ASSET).read_bytes()
    assert len(raw) == 13655 and hashlib.sha256(raw).hexdigest() == ASSET_SHA
    assert raw.splitlines(keepends=True)[1] == b"  \n"
    side = geometry_registration(marker_family_id=FAMILY)
    registration = NativeGeometryRegistration(side)
    assert registration.marker_family_id == FAMILY
    registration.validate_asset(ROOT)
    assert side["marker_to_object"] == ATTACHMENT
    legacy = geometry_registration()
    x75 = geometry_registration(marker_family_id=X_FAMILY)
    for key in set(side) - {
        "marker_family",
        "registration_id",
        "asset_path",
        "pose_marker",
        "marker_to_object",
    }:
        assert side[key] == legacy[key] == x75[key]
    assert "marker_family" not in legacy
    assert x75["marker_to_object"][3] == 0.1 and x75["marker_to_object"][7] == 0


@pytest.mark.parametrize(
    "case",
    [
        "drop_tag",
        "null_tag",
        "unknown_tag",
        "legacy_tag",
        "x75_tag",
        "x75_path",
        "x75_hash",
        "x75_registration",
        "x75_attachment",
        "missing_attachment",
        "negative_y",
        "rotation",
        "marker_id",
        "dictionary",
        "size",
        "alias",
        "only_path",
        "only_hash",
        "only_registration",
        "only_side_attachment",
        "reverse_mix",
    ],
)
def test_descriptor_rejects_partial_identity_and_cross_family_geometry(case):
    side = geometry_registration(marker_family_id=FAMILY)
    x75 = geometry_registration(marker_family_id=X_FAMILY)
    if case == "drop_tag":
        del side["marker_family"]
    elif case.endswith("tag"):
        side["marker_family"] = {
            "null_tag": None,
            "unknown_tag": "unknown",
            "legacy_tag": families.LEGACY_FAMILY,
            "x75_tag": X_FAMILY,
        }[case]
    elif case in {"x75_path", "x75_hash", "x75_registration", "x75_attachment"}:
        key = {
            "x75_path": "asset_path",
            "x75_registration": "registration_id",
            "x75_attachment": "marker_to_object",
        }.get(case)
        if key:
            side[key] = x75[key]
        else:
            side["pose_marker"]["marked_asset_sha256"] = x75["pose_marker"]["marked_asset_sha256"]
    elif case == "missing_attachment":
        del side["marker_to_object"]
    elif case == "negative_y":
        side["marker_to_object"][7] = -0.1
    elif case == "rotation":
        side["marker_to_object"][0] = side["marker_to_object"][5] = -1
    elif case in {"marker_id", "dictionary", "size"}:
        key, value = {
            "marker_id": ("marker_id", 8),
            "dictionary": ("dictionary", "DICT_5X5_50"),
            "size": ("marker_size_m", 0.045),
        }[case]
        side["pose_marker"][key] = value
    elif case == "alias":
        side["asset_path"] = "assets/alias.xml"
    elif case.startswith("only_"):
        original = side
        side = geometry_registration()
        key = {
            "only_path": "asset_path",
            "only_hash": "pose_marker",
            "only_registration": "registration_id",
            "only_side_attachment": "marker_to_object",
        }[case]
        side[key] = original[key]
    else:
        x75["marker_to_object"] = side["marker_to_object"]
        side = x75
    with pytest.raises(ValueError):
        NativeGeometryRegistration(side)


def test_descriptor_rejects_identical_alias_and_resealed_altered_asset(tmp_path):
    geometry = geometry_registration(marker_family_id=FAMILY)
    alias = tmp_path / "assets/alias.xml"
    alias.parent.mkdir()
    alias.write_bytes((ROOT / ASSET).read_bytes())
    geometry["asset_path"] = "assets/alias.xml"
    with pytest.raises(ValueError):
        NativeGeometryRegistration(geometry).validate_asset(tmp_path)
    changed = tmp_path / ASSET
    changed.parent.mkdir(parents=True)
    changed.write_bytes((ROOT / ASSET).read_bytes().replace(b'rgba="0.01', b'rgba="0.02', 1))
    geometry = geometry_registration(marker_family_id=FAMILY)
    geometry["pose_marker"]["marked_asset_sha256"] = hashlib.sha256(
        changed.read_bytes()
    ).hexdigest()
    with pytest.raises(ValueError):
        NativeGeometryRegistration(geometry).validate_asset(tmp_path)


@pytest.mark.parametrize(
    "case",
    [
        "x75_center",
        "cell_center",
        "bit",
        "missing",
        "duplicate",
        "quiet_offset",
        "quiet_size",
        "quiet_color",
        "nested",
        "rotation",
        "contact",
        "mass",
        "camera",
        "object",
    ],
)
def test_descriptor_static_structure_rejects_visual_and_physical_mutations(case):
    candidate = (ROOT / ASSET).read_bytes()
    legacy = (ROOT / collection.MARKED_ASSET).read_bytes()
    validate = families._validate_75mm_structure
    validate(candidate, legacy, family_id=FAMILY)
    validate((ROOT / families.marker_family(X_FAMILY).asset_path).read_bytes(), legacy)
    for unknown in (families.LEGACY_FAMILY, "unknown"):
        with pytest.raises(ValueError):
            validate(candidate, legacy, family_id=unknown)
    tree = ET.fromstring(candidate)
    body = tree.find("./worldbody/body[@name='object']")
    cell = body.find(f"geom[@name='{PREFIX}r0c0']")
    quiet = body.find(f"geom[@name='{PREFIX}quiet']")
    if case == "x75_center":
        for node in body:
            if node.get("name", "").startswith(PREFIX):
                x, y, z = map(float, node.get("pos").split())
                node.set("pos", f"{x + 0.1} {y - 0.1} {z}")
    elif case == "cell_center":
        cell.set("pos", "-0.030 0.13125 0.03504")
    elif case == "bit":
        cell.set("rgba", "0.98 0.98 0.98 1")
    elif case == "missing":
        body.remove(cell)
    elif case == "duplicate":
        body.append(copy.deepcopy(cell))
    elif case == "quiet_offset":
        quiet.set("pos", "0 0.099 0.03502")
    elif case == "quiet_size":
        quiet.set("size", "0.049 0.05 0.00001")
    elif case == "quiet_color":
        quiet.set("rgba", "0.01 0.01 0.01 1")
    elif case == "nested":
        body.remove(cell)
        ET.SubElement(body, "body", name="attachment").append(cell)
    elif case == "rotation":
        cell.set("quat", "1 0 0 0")
    elif case in {"contact", "mass"}:
        cell.set("contype" if case == "contact" else "mass", "1")
    elif case == "camera":
        tree.find("./worldbody/camera").set("fovy", "51")
    else:
        body.find("geom[@name='object_geom']").set("size", "0.04 0.035 0.035")
    with pytest.raises(ValueError):
        validate(ET.tostring(tree), legacy, family_id=FAMILY)


def prepare(tmp_path, *, config=CONFIG):
    destination = tmp_path / "protocol"
    receipt = collection.prepare_native_calibration(ROOT / config, output=destination)
    return destination, receipt, collection.load_json(destination / "protocol.json")


def write_protocol(directory, protocol):
    (directory / "protocol.json").write_text(json.dumps(protocol))


def assert_rejected(directory, protocol):
    write_protocol(directory, protocol)
    for current in (False, True):
        with pytest.raises(ValueError):
            collection.read_protocol(directory, current_sources=current)


def test_protocol_preparation_binds_side_sources_lineage_and_zero_authority(tmp_path):
    directory, receipt, protocol = prepare(tmp_path)
    assert protocol["schema_version"] == "native.calibration.operational.v4"
    assert protocol["marker_family"] == FAMILY
    assert protocol["config_sha256"] == CONFIG_SHA
    assert protocol["execution_release"] == "PREPARE_ONLY_NOT_RELEASED"
    assert protocol["budget_basis"] == "RECIPE_ESTIMATES_ONLY"
    assert protocol["future_wall_bound"] is None
    assert receipt["native_qualification"] == protocol["native_qualification"] == "UNKNOWN"
    assert protocol["admission"]["execution_admitted"] is False
    assert protocol["physical_budget"] == 12960
    assert collection.canonical(protocol["actions"]) == collection.canonical(
        collection.action_horizons()
    )
    assert protocol["authorized_actual_budget"] and all(
        type(n) is int and n == 0 for n in protocol["authorized_actual_budget"].values()
    )
    assert receipt["released_assignments"] == []
    assert protocol["settings"]["released_assignment"] is None
    rows = protocol["assignments"]
    assert [r["assignment_id"] for r in rows] == [f"native-r593-{i:04d}" for i in range(1, 10)]
    assert [r["seed"] for r in rows] == list(range(593001, 593010))
    assert [r["ancestors"] for r in rows] == [
        [f"native-r593-preregistered-{i:04d}"] for i in range(1, 10)
    ]
    assert all(
        r["pool"] == "CALIBRATION_ONLY" and r["status"] == "PREASSIGNED_NOT_RUN" for r in rows
    )
    sources = protocol["source_hashes"]
    x75 = families.marker_family(X_FAMILY)
    assert {ASSET, CONFIG, FAMILY_SOURCE, collection.MARKED_ASSET} <= sources.keys()
    assert x75.asset_path not in sources and collection._PREPARE_CONFIG not in sources
    assert sources[ASSET] == ASSET_SHA and sources[CONFIG] == CONFIG_SHA
    assert protocol["source_generation"] == collection.digest(sources)
    collection.check_sources(sources, marker_family_id=FAMILY)
    required = required_native_source_paths(marker_family_id=FAMILY)
    assert {ASSET, FAMILY_SOURCE, collection.MARKED_ASSET} <= set(required)
    assert ASSET not in required_native_source_paths(marker_family_id=X_FAMILY)
    release = protocol["release_reference"]
    assert release["marked_asset_sha256"] == release["source_hashes"][ASSET] == ASSET_SHA
    assert release["base_asset_sha256"] == collection.BASE_SHA
    assert release["measured_tcp_rotation"] is False
    _, _, legacy = prepare(tmp_path / "reference", config=collection.CONFIG)
    assert release["command_tcp_rotation"] == legacy["release_reference"]["command_tcp_rotation"]
    assert release["command_tcp_rotation"] == pytest.approx(
        [0, 0, 1, 0, 1, 0, -1, 0, 0], abs=1e-14, rel=0
    )
    assert release["source_generation"] == protocol["source_generation"]
    assert not (directory / "claims").exists()
    assert not (directory / "native_calibration_sources.json").exists()
    for current in (False, True):
        assert collection.read_protocol(directory, current_sources=current) == protocol


@pytest.mark.parametrize("missing", [ASSET, FAMILY_SOURCE])
def test_protocol_native_source_registry_requires_selected_side_asset_and_code(tmp_path, missing):
    from tests.test_native_calibration_source import registration

    old, payload = registration(tmp_path)
    payload["geometry"] = geometry_registration(marker_family_id=FAMILY)
    payload["source_hashes"] = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in required_native_source_paths(marker_family_id=FAMILY)
    }
    path = old.artifact_root / old.registry_path
    path.write_text(json.dumps(payload))
    NativeCalibrationRegistration(
        old.artifact_root, ROOT, old.registry_path, hashlib.sha256(path.read_bytes()).hexdigest()
    ).revalidate()
    del payload["source_hashes"][missing]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="inventory incomplete"):
        NativeCalibrationRegistration(
            old.artifact_root,
            ROOT,
            old.registry_path,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )


@pytest.mark.parametrize("formatting", ["compact", "indent4", "order", "newline"])
def test_protocol_equivalent_config_bytes_reject_before_output(tmp_path, monkeypatch, formatting):
    original = (ROOT / CONFIG).read_bytes()
    payload = json.loads(original)
    changed = {
        "compact": json.dumps(payload).encode(),
        "indent4": json.dumps(payload, indent=4).encode(),
        "order": (json.dumps(dict(reversed(list(payload.items()))), indent=2) + "\n").encode(),
        "newline": original[:-1],
    }[formatting]
    assert json.loads(changed) == payload and changed != original
    supplied = tmp_path / "same-values.json"
    supplied.write_bytes(changed)
    calls = []

    def forbidden(path):
        calls.append(path)
        raise AssertionError("invalid config reached output creation")

    monkeypatch.setattr(collection, "fresh_directory", forbidden)
    with pytest.raises(ValueError):
        collection.prepare_native_calibration(supplied, output=tmp_path / "protocol")
    assert calls == [] and not (tmp_path / "protocol").exists()


def test_protocol_exact_config_copy_roundtrips_at_another_path(tmp_path):
    supplied = tmp_path / "exact.json"
    supplied.write_bytes((ROOT / CONFIG).read_bytes())
    output = tmp_path / "protocol"
    receipt = collection.prepare_native_calibration(supplied, output=output)
    protocol = collection.load_json(output / "protocol.json")
    assert protocol["config_sha256"] == CONFIG_SHA
    assert receipt["protocol_sha256"] == collection.digest(protocol)
    for current in (False, True):
        assert collection.read_protocol(output, current_sources=current) == protocol


@pytest.mark.parametrize("change", ["unknown_family", "dropped_family", "legacy_schema"])
def test_protocol_unregistered_config_does_not_create_output(tmp_path, change):
    settings = collection.load_json(ROOT / CONFIG)
    if change == "unknown_family":
        settings["marker_family"] = "unknown"
    elif change == "dropped_family":
        del settings["marker_family"]
    else:
        settings["schema_version"] = "native.calibration.operational.v2"
    supplied = tmp_path / "unregistered.json"
    supplied.write_text(json.dumps(settings))
    with pytest.raises(ValueError):
        collection.prepare_native_calibration(supplied, output=tmp_path / "protocol")
    assert not (tmp_path / "protocol").exists()


@pytest.mark.parametrize(
    "case",
    [
        "v3_schema",
        "v3_identity",
        "v2_schema",
        "geometry_tag",
        "geometry_attachment",
        "geometry_x75",
        "release_hash",
        "source_asset",
        "source_config",
        "source_code",
        "assignment_id",
        "seed",
        "ancestor",
        "status",
        "actual_budget",
        "release",
        "released_setting",
        "unknown_field",
    ],
)
def test_protocol_rejects_mixed_families_or_forged_release_in_both_read_modes(tmp_path, case):
    directory, _, protocol = prepare(tmp_path)
    if case in {"v3_schema", "v2_schema", "v3_identity"}:
        protocol["schema_version"] = (
            "native.calibration.operational.v2"
            if case == "v2_schema"
            else ("native.calibration.operational.v3")
        )
        if case == "v3_identity":
            protocol["marker_family"] = X_FAMILY
            protocol["settings"] = collection.load_json(ROOT / collection._PREPARE_CONFIG)
            protocol["config_sha256"] = collection._PREPARE_CONFIG_SHA
    elif case == "geometry_tag":
        del protocol["geometry"]["marker_family"]
    elif case == "geometry_attachment":
        protocol["geometry"]["marker_to_object"] = geometry_registration()["marker_to_object"]
    elif case == "geometry_x75":
        protocol["geometry"] = geometry_registration(marker_family_id=X_FAMILY)
    elif case == "release_hash":
        protocol["release_reference"]["marked_asset_sha256"] = families.marker_family(
            X_FAMILY
        ).asset_sha256
    elif case.startswith("source_"):
        del protocol["source_hashes"][
            {"source_asset": ASSET, "source_config": CONFIG, "source_code": FAMILY_SOURCE}[case]
        ]
    elif case in {"assignment_id", "seed", "ancestor", "status"}:
        key, value = {
            "assignment_id": ("assignment_id", "native-r579-0001"),
            "seed": ("seed", 579001),
            "ancestor": ("ancestors", ["native-r579-preregistered-0001"]),
            "status": ("status", "RELEASED"),
        }[case]
        protocol["assignments"][0][key] = value
    elif case == "actual_budget":
        protocol["authorized_actual_budget"]["physics_steps"] = 1
    elif case == "release":
        protocol["execution_release"] = "RELEASED"
    elif case == "released_setting":
        protocol["settings"]["released_assignment"] = "native-r593-0001"
    else:
        protocol["extra"] = 0
    protocol["source_generation"] = collection.digest(protocol["source_hashes"])
    protocol["release_reference"]["source_generation"] = protocol["source_generation"]
    assert_rejected(directory, protocol)


@pytest.mark.parametrize(
    "residue",
    [
        "path",
        "hash",
        "registration",
        "attachment",
        "size",
        "config_sha",
        "source_asset",
        "source_config",
        "source_alias_asset",
        "source_alias_config",
        "release_hash",
        "release_source_asset",
        "release_source_config",
        "release_source_alias_asset",
        "release_source_alias_config",
    ],
)
def test_protocol_single_side_residue_cannot_be_relabelled_legacy_after_resealing(
    tmp_path, residue
):
    # Exact legacy settings and no family tags; only the named residue differs.
    directory, _, protocol = prepare(tmp_path, config=collection.CONFIG)
    if residue == "path":
        protocol["geometry"]["asset_path"] = ASSET
    elif residue == "hash":
        protocol["geometry"]["pose_marker"]["marked_asset_sha256"] = ASSET_SHA
    elif residue == "registration":
        protocol["geometry"]["registration_id"] = "native-r593-side-y-plus-75mm"
    elif residue == "attachment":
        protocol["geometry"]["marker_to_object"] = ATTACHMENT
    elif residue == "size":
        protocol["geometry"]["pose_marker"]["marker_size_m"] = 0.075
    elif residue == "config_sha":
        protocol["config_sha256"] = CONFIG_SHA
    elif residue == "release_hash":
        protocol["release_reference"]["marked_asset_sha256"] = ASSET_SHA
    else:
        sources = (
            protocol["release_reference"]["source_hashes"]
            if residue.startswith("release_")
            else (protocol["source_hashes"])
        )
        name = residue.removeprefix("release_")
        path, sha = {
            "source_asset": (ASSET, "0" * 64),
            "source_config": (CONFIG, "0" * 64),
            "source_alias_asset": ("assets/alias.xml", ASSET_SHA),
            "source_alias_config": ("configs/alias.json", CONFIG_SHA),
        }[name]
        sources[path] = sha
    protocol["source_generation"] = collection.digest(protocol["source_hashes"])
    protocol["release_reference"]["source_generation"] = protocol["source_generation"]
    assert_rejected(directory, protocol)


@pytest.mark.parametrize(
    "config,version",
    [(collection.CONFIG, 2), (collection._PREPARE_CONFIG, 3), (CONFIG, 4)],
)
def test_protocol_current_and_synthetic_historical_sources_keep_versioned_key_sets(
    tmp_path, config, version
):
    directory, _, protocol = prepare(tmp_path, config=config)
    assert protocol["schema_version"] == f"native.calibration.operational.v{version}"
    if version != 4:
        assert ASSET not in protocol["source_hashes"] and CONFIG not in protocol["source_hashes"]
    if version == 3:
        assert protocol["assignments"][0]["seed"] == 579001
        assert protocol["assignments"][0]["assignment_id"] == "native-r579-0001"
    for current in (False, True):
        assert collection.read_protocol(directory, current_sources=current) == protocol
    # Synthetic historical implementation hash, not replay of an original run.
    protocol["source_hashes"][FAMILY_SOURCE] = "1" * 64
    protocol["source_generation"] = collection.digest(protocol["source_hashes"])
    protocol["release_reference"]["source_generation"] = protocol["source_generation"]
    write_protocol(directory, protocol)
    assert collection.read_protocol(directory, current_sources=False) == protocol
    with pytest.raises(ValueError):
        collection.read_protocol(directory, current_sources=True)


@pytest.mark.parametrize(
    "assignment",
    [f"native-r593-{i:04d}" for i in range(1, 10)]
    + ["native-r579-0001", "native-r439-0001", "unknown"],
)
def test_protocol_startup_refuses_before_output_repository_worker_or_claim(
    tmp_path, monkeypatch, assignment
):
    from cloud_edge_robot_arm.research import native_collection_application as application
    from cloud_edge_robot_arm.simulation_runtime import sqlite_repository, worker

    directory, _, _ = prepare(tmp_path)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("prepare-only protocol reached application side effects")

    monkeypatch.setattr(application, "fresh_directory", forbidden)
    monkeypatch.setattr(sqlite_repository, "SQLiteSimulationJobRepository", forbidden)
    monkeypatch.setattr(worker, "SimulationWorker", forbidden)
    output = tmp_path / "run"
    with pytest.raises(ValueError, match="prepare.only"):
        application.NativeCollectionApplication.from_startup(
            directory, assignment_id=assignment, output=output
        )
    with pytest.raises(ValueError, match="prepare.only"):
        collection.collect_native_calibration_once(
            directory, assignment_id=assignment, output=output
        )
    assert calls == [] and not output.exists() and not (directory / "claims").exists()
