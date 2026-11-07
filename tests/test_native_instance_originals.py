"""Real recorder graph schema checks; SOFTWARE_ONLY, no actual collection."""

import hashlib
import shutil
import struct

import pytest

from cloud_edge_robot_arm.research.native_calibration_collection import load_json
from tests.native_collection_source_graph import (
    frame_audit,
    recorded_frame_graph,
    reseal_software_inventory,
    write_software_json,
)


def test_recorded_camera_background_needs_no_label(tmp_path):
    protocol, (explicit, implicit) = recorded_frame_graph(tmp_path / "original")
    audit = frame_audit(tmp_path / "original", protocol)
    instance_path = audit.directory / f"frames/{explicit}/instances.i32"
    original_bytes = instance_path.read_bytes()
    observation, metadata, _ = audit.frame(explicit)
    assert set(struct.unpack(f"<{observation.width * observation.height}i", original_bytes)) == {
        -1,
        7,
    }
    assert metadata["instance_labels"] == {"7": "software_geometry"}
    _, cached, _ = audit.frame(implicit)
    assert cached["instance_count"] == 0 and cached["pass_count"] == 2
    assert cached["instance_labels"] == {}
    assert instance_path.read_bytes() == original_bytes
    assert not audit.source_ok and not audit.horizon_ok

    shutil.copytree(tmp_path / "original", tmp_path / "unknown-negative")
    directory = tmp_path / "unknown-negative/originals"
    name = f"frames/{explicit}/instances.i32"
    altered = struct.pack("<i", -2) + original_bytes[4:]
    (directory / name).write_bytes(altered)
    path = directory / f"frames/{explicit}/source-frame.json"
    changed = load_json(path)
    changed["frame"]["file_hashes"][name] = hashlib.sha256(altered).hexdigest()
    write_software_json(path, changed)
    reseal_software_inventory(directory)
    with pytest.raises(ValueError, match="unknown negative instance ID"):
        frame_audit(tmp_path / "unknown-negative", protocol).frame(explicit)
    assert instance_path.read_bytes() == original_bytes


def test_recorded_nonbackground_missing_label_is_rejected(tmp_path):
    protocol, (explicit, _) = recorded_frame_graph(tmp_path / "original")
    shutil.copytree(tmp_path / "original", tmp_path / "mutated")
    directory = tmp_path / "mutated/originals"
    path = directory / f"frames/{explicit}/source-frame.json"
    metadata = load_json(path)
    del metadata["instance_labels"]["7"]
    write_software_json(path, metadata)
    reseal_software_inventory(directory)
    audit = frame_audit(tmp_path / "mutated", protocol)
    with pytest.raises(ValueError, match="instance label original missing"):
        audit.frame(explicit)
