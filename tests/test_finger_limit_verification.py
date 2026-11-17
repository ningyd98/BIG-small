"""离线手指修复核验不能用部分轨迹或未绑定诊断冒充一致重放。"""

import hashlib
import importlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

_COMPATIBLE_CURRENT_COMMIT = "5e68e2f9f1ed7d865f483f41534dec9404c83394"
_SCENE_ASSET = "assets/robots/franka_panda/scene_pose_marker_side_y_plus_75mm_component_v1.xml"
_BACKEND_PATH = "src/cloud_edge_robot_arm/simulation/mujoco/backend.py"


def verifier():
    return importlib.import_module("scripts.verify_finger_limit_fix")


@pytest.mark.parametrize(
    "damage,stop,want",
    [
        (None, None, True),
        (None, 122, True),
        ("missing_first", 122, False),
        ("missing_last", 122, False),
        ("extra", 122, False),
        ("value", None, False),
        ("missing_field", None, False),
        ("extra_field", None, False),
        ("wrong_step", 122, False),
        ("short_full", None, False),
    ],
)
def test_physical_replay_requires_the_exact_expected_prefix(damage, stop, want):
    original = [
        {"episode_id": "old", "physics_step": step, "joint_limit_violation": step >= 122}
        for step in (120, 121, 122, 123)
    ]
    replay = [{**row, "episode_id": "new"} for row in original[: 3 if stop else 4]]
    if damage == "missing_first":
        replay.pop(0)
    elif damage in {"missing_last", "short_full"}:
        replay.pop()
    elif damage == "extra":
        replay.append({**original[-1], "episode_id": "new"})
    elif damage == "value":
        replay[0]["joint_limit_violation"] = True
    elif damage == "missing_field":
        del replay[0]["joint_limit_violation"]
    elif damage == "extra_field":
        replay[0]["fabricated"] = 1
    elif damage == "wrong_step":
        replay[-1]["physics_step"] = 124
    assert verifier().physical_prefix_matches(replay, original, truncated_at=stop) is want


def make_evidence(tmp_path):
    episode = tmp_path / "original" / "development-043003"
    diagnosis = tmp_path / "diagnosis" / episode.name
    (episode / "component").mkdir(parents=True)
    (diagnosis / "component").mkdir(parents=True)
    values = {
        "result.json": {"episode_id": "original-id"},
        "component/physical-evidence.json": [
            {"physics_step": 120, "joint_limit_violation": False},
            {"physics_step": 121, "joint_limit_violation": True},
        ],
    }
    manifest = []
    hashes = {}
    for name, value in values.items():
        raw = json.dumps(value).encode()
        (episode / name).write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        hashes[name] = digest
        manifest.append({"path": name, "sha256": digest, "bytes": len(raw)})
    raw_manifest = json.dumps({"files": manifest}).encode()
    (episode / "evidence-manifest.json").write_bytes(raw_manifest)
    hashes["evidence-manifest.json"] = hashlib.sha256(raw_manifest).hexdigest()
    document = {
        "schema": "joint-limit-diagnostics.v1",
        "source_case": episode.name,
        "original_episode_id": "original-id",
        "episode_id": "diagnosis-id",
        "violations": [{"physics_step": 121}],
    }
    raw = json.dumps(document).encode()
    (diagnosis / "component/joint-limit-diagnostics.json").write_bytes(raw)
    verification = {
        "case": episode.name,
        "original_episode_id": "original-id",
        "replay_episode_id": "diagnosis-id",
        "replay_matches_original": True,
        "original_evidence_unchanged": True,
        "all_physical_fields_exact_except_new_episode_id": True,
        "source_evidence_hashes": hashes,
        "original_flagged_steps": [121],
        "replayed_flagged_steps": [121],
        "diagnostic_file_sha256": hashlib.sha256(raw).hexdigest(),
        "diagnostic_content_sha256": hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest(),
    }
    (diagnosis / "replay-verification.json").write_text(json.dumps(verification))
    return episode, diagnosis, document, verification


@pytest.mark.parametrize(
    "damage", [None, "bytes", "identity", "coverage", "original", "unfaithful"]
)
def test_diagnostic_snapshots_require_frozen_identity_hashes_and_full_coverage(tmp_path, damage):
    episode, diagnosis, document, verification = make_evidence(tmp_path)
    if damage == "bytes":
        with (diagnosis / "component/joint-limit-diagnostics.json").open("a") as stream:
            stream.write(" ")
    elif damage in {"identity", "coverage"}:
        changed = deepcopy(document)
        if damage == "identity":
            changed["original_episode_id"] = "another-original"
        else:
            changed["violations"] = []
        raw = json.dumps(changed).encode()
        (diagnosis / "component/joint-limit-diagnostics.json").write_bytes(raw)
        verification["diagnostic_file_sha256"] = hashlib.sha256(raw).hexdigest()
        verification["diagnostic_content_sha256"] = hashlib.sha256(
            json.dumps(changed, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
    elif damage == "original":
        (episode / "result.json").write_text('{"episode_id":"changed"}')
    elif damage == "unfaithful":
        verification["replay_matches_original"] = False
    (diagnosis / "replay-verification.json").write_text(json.dumps(verification))
    if damage is None:
        assert verifier().verified_diagnostics(episode, diagnosis) == document
    else:
        with pytest.raises(ValueError):
            verifier().verified_diagnostics(episode, diagnosis)


@pytest.fixture
def compatible_current_sources(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.research.sol_molmo_single_episode import SOURCE_PATHS

    module = verifier()
    repo = module.SOURCE
    source = tmp_path / "compatible-sources"
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    common_git_dir = Path(subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        text=True,
    ).strip())
    (source / ".git/objects/info/alternates").write_text(f"{common_git_dir / 'objects'}\n")
    for name in (*SOURCE_PATHS, _SCENE_ASSET):
        fixture_file = source / name
        fixture_file.parent.mkdir(parents=True, exist_ok=True)
        fixture_file.write_bytes(subprocess.check_output(
            ["git", "-C", str(source), "show", f"{_COMPATIBLE_CURRENT_COMMIT}:{name}"]
        ))

    monkeypatch.setattr(module, "SOURCE", source)
    module.original_source_bytes.cache_clear()
    module.original_source_sha.cache_clear()
    try:
        yield
    finally:
        module.original_source_bytes.cache_clear()
        module.original_source_sha.cache_clear()


def source_bound_episode(tmp_path, *, has_actions=False, damage=None):
    from cloud_edge_robot_arm.research.sol_molmo_single_episode import SOURCE_PATHS

    module = verifier()
    pins = {
        name: hashlib.sha256(
            subprocess.check_output(
                ["git", "-C", str(module.SOURCE), "show", module.BASE_COMMIT + ":" + name]
            )
        ).hexdigest()
        for name in (*SOURCE_PATHS, _SCENE_ASSET)
    }
    if damage == "backend_pin":
        pins[_BACKEND_PATH] = "0" * 64
    elif damage == "current_guard_as_original":
        pins[module.GUARD_PATH] = hashlib.sha256(
            (module.SOURCE / module.GUARD_PATH).read_bytes()
        ).hexdigest()
    elif damage == "missing_pin":
        del pins[_BACKEND_PATH]
    elif damage == "extra_path":
        pins["../unbound.py"] = "0" * 64
    episode = tmp_path / "fixed-042001"
    (episode / "component").mkdir(parents=True)
    files = {
        "result.json": {
            "episode_id": "old",
            "physical_success": False,
            "scene_file": _SCENE_ASSET,
            "seed": 42001,
        },
        "source-hashes.json": {"scope": "SELECTED_ENTRY_SOURCES", "files": pins},
        "component/episode.json": {
            "actions": [{}] if has_actions else [],
            "terminal_reason": "original-refusal",
            "scene_application": {"requested_scene": None},
        },
        "component/physical-evidence.json": [{"physics_step": 120, "joint_limit_violation": False}],
    }
    entries = []
    for name, value in files.items():
        raw = json.dumps(value).encode()
        (episode / name).write_bytes(raw)
        entries.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    (episode / "evidence-manifest.json").write_text(json.dumps({"files": entries}))
    return episode


@pytest.mark.parametrize("has_actions", [False, True])
@pytest.mark.parametrize(
    "damage", ["backend_pin", "current_guard_as_original", "missing_pin", "extra_path"]
)
def test_self_consistent_manifest_cannot_hide_original_source_pin_drift(
    tmp_path, monkeypatch, compatible_current_sources, has_actions, damage
):
    # The old verifier ignored Python source pins; even evidence-only records must fail closed.
    episode = source_bound_episode(tmp_path, has_actions=has_actions, damage=damage)

    def cannot_initialize(_self, _config):
        pytest.fail("unverified original runtime reached physics initialization")

    monkeypatch.setattr(verifier().MuJoCoPhysicsBackend, "initialize", cannot_initialize)
    expected = {
        "backend_pin": "original runtime source pin mismatch: " + _BACKEND_PATH,
        "current_guard_as_original": (
            "original runtime source pin mismatch: " + verifier().GUARD_PATH
        ),
        "missing_pin": "original runtime source inventory does not match",
        "extra_path": "original runtime source inventory does not match",
    }
    with pytest.raises(ValueError) as rejected:
        verifier().replay_case(episode, tmp_path / "derived")
    assert str(rejected.value) == expected[damage]
    assert not (tmp_path / "derived").exists()


def test_unchanged_original_source_pins_allow_evidence_only_record(
    tmp_path, compatible_current_sources,
):
    episode = source_bound_episode(tmp_path)
    report = verifier().replay_case(episode, tmp_path / "derived")
    assert report["verified"]
    assert report["original_runtime_verified"]
    assert report["scope"] == "EVIDENCE_ONLY_NO_RECORDED_ACTIONS"
    assert not report["fresh_planning_test"]


def test_legacy_verifier_refuses_drifted_live_source_before_output(tmp_path, monkeypatch):
    def cannot_initialize(_self, _config):
        pytest.fail("drifted runtime reached physics initialization")

    module = verifier()
    monkeypatch.setattr(module.MuJoCoPhysicsBackend, "initialize", cannot_initialize)
    episode = source_bound_episode(tmp_path, has_actions=True)
    with pytest.raises(ValueError, match="original runtime source differs from current source"):
        module.replay_case(episode, tmp_path / "derived")
    assert not (tmp_path / "derived").exists()
