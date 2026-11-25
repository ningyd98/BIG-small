"""The unchanged issuer must sign the chosen endpoint; diagnostics never authorize motion."""
import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
Q = (math.sqrt(0.5), 0.0, math.sqrt(0.5), 0.0)


def implementation():
    name = 'binding'
    assert importlib.util.find_spec(name), "missing same-frame developer target binding"
    return __import__(name)


def row(offset=7, **kw):
    return dict({
        'candidate_id': f'existing_tool_closure_axis:{offset:+.6f}',
        'direction': 'existing_tool_closure_axis', 'tangent_mm': offset,
        'offset_object_m': [offset / 1000, 0, 0], 'orientation_wxyz': list(Q),
        'clearance': 'CLEAR', 'proof_sha256': 'b' * 64,
    }, **kw)


def test_sealed_table_rejects_foreign_frame_offset_direction_and_unproved_clear():
    api = implementation()
    packet = dict(frame_id='unit-frame-1', checksum_sha256='a' * 64)
    table = {**packet, 'rows': [row()]}
    assert api.select_row(table, packet, row()['candidate_id'])['offset_object_m'] == [0.007, 0, 0]
    for bad, frame, candidate, reason in [
        (table, dict(packet, checksum_sha256='e' * 64), row()['candidate_id'], 'frame'),
        (table, packet, 'missing', 'registered'),
        ({**table, 'rows': [row(7, clearance='UNKNOWN')]}, packet, row()['candidate_id'], 'CLEAR'),
        ({**table, 'rows': [row(7, orientation_wxyz=[1, 0, 0, 0])]}, packet, row()['candidate_id'], 'direction'),
        ({**table, 'rows': [row(7, tangent_mm=250)]}, packet, row()['candidate_id'], 'offset'),
        ({**table, 'rows': [row(7, proof_sha256='')]}, packet, row()['candidate_id'], 'proof'),
        ({**table, 'rows': [row(), row()]}, packet, row()['candidate_id'], 'registered'),
    ]:
        with pytest.raises(ValueError, match=reason):
            api.select_row(bad, frame, candidate)


def test_immutable_selection_and_rotating_object_offset(tmp_path):
    api = implementation()
    path = tmp_path / 'bindings.sqlite'
    record = dict(owner='lease-1', row=row())
    api.claim(path, 'scope1', record)
    api.claim(path, 'scope1', record)
    with pytest.raises(ValueError, match='already'):
        api.claim(path, 'scope1', dict(record, row=row(-7)))
    assert api.recall(path, 'scope1') == record
    center = [0.4, 0.0, 0.045]
    turn = [0, -1, 0, 1, 0, 0, 0, 0, 1]
    np.testing.assert_allclose(api.selected_tcp(center, turn, [0.007, 0, 0]), [0.4, 0.007, 0.045])
    np.testing.assert_array_equal(api.selected_tcp(center, turn, [0, 0, 0]), center)


def test_oblique_object_face_cannot_request_tool_yaw_change():
    api = implementation()
    rotated = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
    with pytest.raises(ValueError, match='direction'):
        api.require_fixed_face(row(7, direction='object_Y'), rotated)
    api.require_fixed_face(row(7, direction='object_X'), rotated)


def test_blind_servo_reconstructs_rotation_without_relabeling_central_tcp():
    api = __import__('binding_score') if implementation() else None
    from numpy.testing import assert_allclose
    def frame(rotation):
        return dict(usable=True, selected_id=7, per_id={'7': {'rotation_object_to_world': rotation}},
                    tcp_m=[0.4, 0, 0.045])
    source = frame(np.eye(3).ravel().tolist())
    new = frame([0, -1, 0, 1, 0, 0, 0, 0, 1])
    assert_allclose(api.offset_delta(row(), source, new), [-0.007, 0.007, 0])
    assert source['tcp_m'] == new['tcp_m'] == [0.4, 0, 0.045]


def test_development_generation_preserves_frozen_safety_and_control(tmp_path):
    api = implementation()
    builder = __import__('binding_build')
    root = HERE.parents[5]
    tree, catalog = builder.create(root, tmp_path / 'dev-source')
    for rel in ['src/cloud_edge_robot_arm/vision/servo.py',
                'src/cloud_edge_robot_arm/edge/safety/shield.py',
                'src/cloud_edge_robot_arm/simulation/mujoco/visual_servo.py',
                'src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py']:
        assert builder.sha(tree / rel) == builder.sha(builder.parent_tree(root) / rel)
    assert catalog['scripts/graduation/binding.py'] == builder.sha(Path(api.__file__))
    assert (tree / 'binding-generation.json').is_file()


def test_fresh_native_issuance_has_an_independent_raw_reader():
    import importlib.util
    assert importlib.util.find_spec('binding_probe'), 'missing actual fresh-sensor/SQLite fixture'
    probe = __import__('binding_probe')
    assert callable(probe.acquire_controls) and callable(probe.blind_readback)

