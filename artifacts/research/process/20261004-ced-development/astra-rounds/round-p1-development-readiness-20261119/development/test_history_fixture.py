from pathlib import Path

import development_plan as history
import pytest


def test_known_malformed_negative_fixture_is_kept_without_identities(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "LEGACY_FIXTURE_ROOT", tmp_path)
    known = tmp_path / history.LEGACY_FIXTURE
    known.parent.mkdir(parents=True)
    known.write_bytes(b"{")
    data, sha, role = history.read_history_document(known, lines=False)
    assert role == "ATTESTED_MALFORMED_PYTEST_FIXTURE"
    assert sha == history.LEGACY_FIXTURE_SHA
    assert history.collect_identities(data) == (set(), set())
    known.write_bytes(b'{"seed":123}')
    with pytest.raises(ValueError, match="fixture changed"):
        history.read_history_document(known, lines=False)


@pytest.mark.parametrize("fixture", ["another/protocol.json", "unbound/assignments.json"])
def test_unregistered_bad_json_remains_a_hard_error(fixture, tmp_path, monkeypatch):
    monkeypatch.setattr(history, "LEGACY_FIXTURE_ROOT", tmp_path)
    path = tmp_path / fixture
    path.parent.mkdir()
    path.write_bytes(b"{")
    with pytest.raises(ValueError, match="unregistered malformed history index"):
        history.read_history_document(path, lines=False)


def test_unknown_bad_jsonl_has_no_exemption(tmp_path):
    document = tmp_path / "samples.jsonl"
    document.write_bytes(b'{"seed":123}\n{')
    with pytest.raises(ValueError, match="unregistered malformed history index"):
        history.read_history_document(document, lines=True)


def test_real_json_identity_contributes_and_refuses_a_collision(tmp_path: Path):
    document = tmp_path / "scene-assignment.json"
    document.write_bytes(b'{"seed":321,"object_position_m":[0.4,0.05,0.035]}')
    data, _, role = history.read_history_document(document, lines=False)
    assert role == "PARSED_HISTORY"
    identities = history.collect_identities(data)
    assert identities == ({321}, {(0.4, 0.05, 0.035)})
    slot = {"pose_seed": 321, "scene": {"object_position_m": [0.1, 0.0, 0.035]}}
    with pytest.raises(ValueError, match="verified.*seed"):
        history.assert_no_conflicts([slot], {"verified": identities})
