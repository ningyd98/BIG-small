"""Calibration registration and exclusive assignment collection contracts."""

import json
from importlib import import_module, util
from pathlib import Path

import pytest

from cloud_edge_robot_arm.research import native_calibration_collection as collection


def test_collection_prepare_api_required():
    name = "cloud_edge_robot_arm.research.native_calibration_collection"
    module = import_module(name) if util.find_spec(name) else None
    assert callable(getattr(module, "prepare_native_calibration", None)), (
        "collector prepare missing"
    )


def test_prepare_is_physics_free_and_preserves_nine_denominator(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

    def forbidden(*args, **kwargs):
        raise AssertionError("preparation initialized actual physics")

    monkeypatch.setattr(MuJoCoPhysicsBackend, "initialize", forbidden)
    result = collection.prepare_native_calibration(
        collection.ROOT / collection.CONFIG, output=tmp_path / "protocol"
    )
    protocol = collection.read_protocol(Path(result["protocol"]))
    assert result["assigned_groups"] == 9
    assert protocol["physical_budget"] == 12960
    assert protocol["explicit_acquisition_budget"] == 12976
    assert protocol["implicit_capture_budget"] == 12962
    assert protocol["render_pass_budget"] == 3 * 12976 + 2 * 12962
    assert [row["seed"] for row in protocol["assignments"]] == list(range(439001, 439010))
    assert sum(row["status"] == "RELEASED" for row in protocol["assignments"]) == 1
    assert protocol["role"]["model"] is None and protocol["role"]["model_requests"] == 0
    assert protocol["native_qualification"] == "UNKNOWN"
    assert protocol["admission"]["execution_admitted"] is False
    assert protocol["actions"][3]["horizon"]["total_steps"] == 2040
    assert protocol["actions"][6]["horizon"]["total_steps"] == 480
    with pytest.raises(ValueError, match="fresh"):
        collection.prepare_native_calibration(
            collection.ROOT / collection.CONFIG, output=tmp_path / "protocol"
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("raw_bytes", 2**50),
        ("task_timeout_s", 3600),
        ("settle_steps", 0),
        ("scope", "NATIVE_EXECUTION"),
    ],
)
def test_policy_changes_cannot_grant_collection(tmp_path, field, value):
    config = collection.load_json(collection.ROOT / collection.CONFIG)
    config[field] = value
    source = tmp_path / "policy.json"
    source.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="fixed registered"):
        collection.prepare_native_calibration(source, output=tmp_path / "protocol")


def test_protocol_mutated_assignment_rejected(tmp_path):
    collection.prepare_native_calibration(
        collection.ROOT / collection.CONFIG, output=tmp_path / "p"
    )
    file = tmp_path / "p/protocol.json"
    protocol = collection.load_json(file)
    protocol["assignments"][0]["seed"] += 1
    file.write_text(json.dumps(protocol))
    with pytest.raises(ValueError, match="registration"):
        collection.read_protocol(tmp_path / "p")


def test_symlink_duplicate_json_and_existing_output_fail(tmp_path):
    raw = tmp_path / "raw.json"
    raw.write_text('{"x":1,"x":2}')
    with pytest.raises(ValueError, match="duplicate"):
        collection.load_json(raw)
    link = tmp_path / "linked.json"
    link.symlink_to(raw)
    with pytest.raises(ValueError, match="regular"):
        collection.load_json(link)
    with pytest.raises(FileExistsError):
        collection.save_exclusive(raw, {})


def test_protocol_canonical_json_roundtrip(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

    def forbidden(*args, **kwargs):
        raise AssertionError("no actual initialization")

    monkeypatch.setattr(MuJoCoPhysicsBackend, "initialize", forbidden)
    directory = tmp_path / "protocol"
    receipt = collection.prepare_native_calibration(
        collection.ROOT / collection.CONFIG, output=directory
    )
    disk = collection.read_protocol(directory)
    memory = collection.action_horizons()
    for key in ("horizon", "tail_basis"):
        assert isinstance(memory[0][key]["registered_dt_ratio"], tuple)
        assert isinstance(disk["actions"][0][key]["registered_dt_ratio"], list)
    assert collection.canonical(disk["actions"]) == collection.canonical(memory)
    assert receipt["protocol_sha256"] == collection.digest(disk)
    (directory / "protocol.json").write_text(
        json.dumps(dict(reversed(list(disk.items()))), indent=3)
    )
    assert collection.canonical(collection.read_protocol(directory)) == collection.canonical(disk)


def test_protocol_recipe_and_settings_tampering_rejected(tmp_path):
    directory = tmp_path / "protocol"
    collection.prepare_native_calibration(collection.ROOT / collection.CONFIG, output=directory)
    file = directory / "protocol.json"
    original = file.read_bytes()

    def mutate(case, obj):
        if case == 0:
            obj["actions"][0]["horizon"]["registered_dt_ratio"][0] += 1
        elif case == 1:
            obj["actions"][0]["original_timeout_ms"] = 8000.0
        elif case == 2:
            obj["actions"][0]["recipe"]["builtin_tail_included"] = 0
        elif case == 3:
            obj["actions"][0]["original_timeout_ms"] += 1
        elif case == 4:
            obj["actions"].reverse()
        elif case == 5:
            obj["actions"][0]["extra"] = None
        else:
            obj["settings"]["max_attempts"] = True

    for case in range(7):
        for current_sources in (False, True):
            payload = json.loads(original)
            mutate(case, payload)
            file.write_text(json.dumps(payload))
            with pytest.raises(ValueError, match="recipe"):
                collection.read_protocol(directory, current_sources=current_sources)


def test_protocol_registration_typed_metadata_and_source_tampering_rejected(tmp_path):
    directory = tmp_path / "protocol"
    collection.prepare_native_calibration(collection.ROOT / collection.CONFIG, output=directory)
    file = directory / "protocol.json"
    original = file.read_bytes()
    for case in range(7):
        payload = json.loads(original)
        expected = "registration"
        if case == 0:
            payload["assignments"][0]["seed"] += 1
        elif case == 1:
            payload["assignments"][1]["status"] = "RELEASED"
        elif case == 2:
            payload["extra"] = False
        elif case == 3:
            payload["admission"]["execution_admitted"] = 0
        elif case == 4:
            payload["physical_budget"] = 12960.0
        else:
            payload["source_hashes"][next(iter(payload["source_hashes"]))] = "0" * 64
            if case == 5:
                expected = "source generation"
            else:
                payload["source_generation"] = collection.digest(payload["source_hashes"])
        file.write_text(json.dumps(payload))
        with pytest.raises(ValueError, match=expected):
            collection.read_protocol(directory)
