"""CPU-only tests for the explicit frozen-pool producer entrance."""

import json
import subprocess
import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from cloud_edge_robot_arm.datasets.rgbd.models import DatasetConfig, SceneSpec, content_digest
from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene
from cloud_edge_robot_arm.research.protocol import build_scene_pools
from cloud_edge_robot_arm.research.protocol_generation import (
    preflight_generation,
    prepare_generation,
    prepare_successor_generation,
)

CLI = Path(__file__).resolve().parents[1] / "scripts/generate_rgbd_protocol_evidence.py"


def write_json(path, payload):
    path.write_text(json.dumps(payload))
    return path


@pytest.fixture(scope="module")
def assignments():
    return build_scene_pools(1092304, set(), protocol_version="ced.research.v2")


@pytest.fixture
def frozen_inputs(tmp_path, assignments):
    scene = sample_scene(DatasetConfig(dataset_id="frozen-history-test", groups=1), 7751)
    parent_scene = scene.model_dump(mode="json")
    parent_scene["group_id"] = "renamed-historical-parent"
    parent = write_json(
        tmp_path / "parent.json", {"scene": parent_scene, "scene_hash": scene.scene_hash}
    )
    lineage = write_json(
        tmp_path / "lineage.json",
        {
            "group_id": "renamed-historical-child",
            "scene_hash": scene.scene_hash,
            "canonical_physical_group": scene.group_id,
            "parent": "parent.json",
            "parent_sha256": sha256(parent.read_bytes()).hexdigest(),
            "new_independent_calibration_group": False,
        },
    )
    pool_file = write_json(tmp_path / "frozen.json", assignments)
    return pool_file, [parent, lineage], scene


def test_normal_cli_import_binds_source_order_history_and_first_ordinal(
    tmp_path, assignments, frozen_inputs
):
    pool_file, sources, historical_scene = frozen_inputs
    catalog = write_json(tmp_path / "sources.json", {"sources": [str(p) for p in sources]})
    output = tmp_path / "protocol"
    command = [sys.executable, "-B", str(CLI), "--protocol", str(output)]
    run = subprocess.run(
        command + ["--prepare", "--pools", str(pool_file), "--history-catalog", str(catalog)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr or run.stdout
    prepared = json.loads(run.stdout)
    assert prepared["status"] == "READY_FOR_REVIEW"
    readback = json.loads((output / "pools.json").read_text())
    metadata = readback.pop("_evidence")
    assert content_digest(readback) == content_digest(assignments)
    assert historical_scene.group_id in metadata["excluded_groups"]
    assert metadata["opportunity_sources"] == metadata["recovery_sources"] == {}
    component = next(
        group
        for group in prepared["history"]["components"]
        if f"g:{historical_scene.group_id}" in group
    )
    assert "g:renamed-historical-parent" in component
    assert "g:renamed-historical-child" in component
    assert len([key for key in component if key.startswith("p:")]) == 1
    run = subprocess.run(command, capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stderr or run.stdout
    preflight = json.loads(run.stdout)
    assert preflight["row"] == assignments["recovery"][0]
    assert preflight["seed"] is None
    assert preflight["pool_source"]["sha256"] == sha256(pool_file.read_bytes()).hexdigest()
    assert preflight["attempt"] == 1
    assert preflight["attempted"] == 0
    assert preflight["unattempted"] == 200
    assert not (output / "allocations").exists()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("extra-evidence", "exactly the six registered pool names"),
        ("half-pool", "complete v2 assignment pools"),
        ("reorder", "complete v2 assignment pools"),
        ("extra-field", "assignment row fields"),
        ("bad-ood", "OOD definition"),
        ("historical-group", "previous/excluded group"),
        ("historical-physical", "historical scene or physical"),
        ("cross-pool-physical", "cross-pool physical"),
    ],
)
def test_import_rejects_invalid_rows_without_output(
    tmp_path, assignments, frozen_inputs, change, message
):
    pool_file, sources, historical_scene = frozen_inputs
    pools = deepcopy(assignments)
    selected = pools["selection"][0]
    if change == "extra-evidence":
        pools["_evidence"] = {}
    elif change == "half-pool":
        pools["selection"].pop()
    elif change == "reorder":
        pools["selection"][:2] = reversed(pools["selection"][:2])
    elif change == "extra-field":
        selected["undeclared"] = True
    elif change == "bad-ood":
        pools["ood"][0]["ood_definition"] = None
    else:
        if change == "cross-pool-physical":
            scene = SceneSpec.model_validate(pools["formal"][0]["scene"])
        else:
            scene = historical_scene
        asset_hash = scene.asset_family_hash
        params = deepcopy(scene.scene_parameters)
        params["camera"]["fovy"] = 48.0
        params["depth_noise_m"] = 0.002
        if change != "historical-group":
            asset_hash = "e" * 64
        changed = SceneSpec.from_parameters(params, asset_hash, scene.seed)
        selected["scene"] = changed.model_dump(mode="json")
        selected["scene_hash"] = changed.scene_hash
    write_json(pool_file, pools)
    output = tmp_path / "protocol"
    with pytest.raises(ValueError, match=message):
        prepare_generation(sources, output, pools=pool_file)
    assert not output.exists()


@pytest.mark.parametrize("change", ["absent", "bad-parent-sha", "bad-scene-sha", "wrong-alias"])
def test_import_requires_registered_authentic_lineage(tmp_path, frozen_inputs, change):
    pool_file, sources, _ = frozen_inputs
    if change == "absent":
        sources = sources[1:]
    else:
        key = {
            "bad-parent-sha": "parent_sha256",
            "bad-scene-sha": "scene_hash",
            "wrong-alias": "canonical_physical_group",
        }[change]
        value = json.loads(sources[1].read_text())
        value[key] = "g-forged-lineage" if change == "wrong-alias" else "0" * 64
        write_json(sources[1], value)
    output = tmp_path / "protocol"
    with pytest.raises(ValueError, match="lineage"):
        prepare_generation(sources, output, pools=pool_file)
    assert not output.exists()


@pytest.mark.parametrize("change", ["source-bytes", "resealed-row", "version"])
def test_external_pool_binding_survives_successor_without_permitting_drift(
    tmp_path, frozen_inputs, change
):
    pool_file, sources, _ = frozen_inputs
    initial = tmp_path / "initial"
    successor = tmp_path / "successor"
    prepare = prepare_generation(sources, initial, pools=pool_file)
    result = prepare_successor_generation(
        initial, successor, expected_predecessor_hash=prepare["protocol_hash"]
    )
    first = preflight_generation(initial, "recovery-0001")
    second = preflight_generation(successor, "recovery-0001")
    assert first["pool_source"] == second["pool_source"]
    assert first["allocation_directory"] == second["allocation_directory"]
    assert result["attempted"] == result["actual_calls"] == 0
    if change == "source-bytes":
        pool_file.write_bytes(pool_file.read_bytes() + b"\n")
    else:
        head = initial / "generation.json"
        header = json.loads(head.read_text())
        if change == "version":
            header["pool_source"]["mode"] = "unrecognized"
        else:
            locked = initial / "pools.json"
            value = json.loads(locked.read_text())
            value["recovery"][0]["scene"]["seed"] += 1
            write_json(locked, value)
            header["payload_hashes"]["pools.json"] = sha256(locked.read_bytes()).hexdigest()
        write_json(head, header)
    with pytest.raises(ValueError, match="frozen pool source"):
        preflight_generation(initial, "recovery-0001")
    with pytest.raises(ValueError, match="drift|frozen pool source"):
        preflight_generation(successor, "recovery-0001")
    with pytest.raises(ValueError, match="frozen pool source"):
        prepare_successor_generation(
            initial,
            tmp_path / "another",
            expected_predecessor_hash=content_digest(header)
            if change != "source-bytes"
            else prepare["protocol_hash"],
        )
    assert not (initial / "allocations").exists()
    assert not (tmp_path / "another").exists()


@pytest.mark.parametrize(
    "options",
    [[], ["--execute-once"], ["--prepare", "--successor-of", "prior"]],
)
def test_cli_rejects_pools_outside_normal_prepare(tmp_path, frozen_inputs, options):
    pool_file, _, _ = frozen_inputs
    path = tmp_path / "protocol"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(CLI),
            "--protocol",
            str(path),
            "--pools",
            str(pool_file),
            *options,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 3
    assert "--pools requires normal --prepare" in result.stdout
    assert not path.exists()
