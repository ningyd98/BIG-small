from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image
from read_whole_evidence import (
    ASSIGNMENT,
    PARENT_FREEZE_SHA256,
    SCHEMA,
    SCOPE,
    SEED,
    WALL_NS,
    base,
    check_png,
    digest,
    exact_reference,
    registration,
    result_window,
    sha_file,
)


@pytest.fixture
def release(tmp_path):
    protocol = {
        "schema_version": SCHEMA,
        "scope": SCOPE,
        "assignment_id": ASSIGNMENT,
        "seed": SEED,
        "qualification_credit": 0,
        "step_wall_budget_ns": WALL_NS,
        "step_wall_budget_kind": "ORIGINAL_POST_STEP_TIMEOUT",
        "png_compress_level": 1,
        "first_action": "MOVE_ABOVE",
        "parent_source_freeze_sha256": PARENT_FREEZE_SHA256,
        "registration_directory": str(tmp_path),
        "output": str(tmp_path / "run"),
        "recipe": {
            "scope": SCOPE,
            "assignments": [{"assignment_id": ASSIGNMENT, "seed": SEED}],
            "released_assignments": [],
            "settings": {"png_compress_level": 1},
            "actions": [
                {
                    "skill": "MOVE_ABOVE",
                    "original_timeout_ms": 8000,
                    "horizon": {"total_steps": 1920},
                }
            ],
            "role": {"model_requests": 0},
        },
    }
    claim = {
        "scope": SCOPE,
        "assignment_id": ASSIGNMENT,
        "seed": SEED,
        "output": str(tmp_path / "run"),
        "registration_sha256": digest(protocol),
    }
    return protocol, claim, tmp_path


def test_registered_only_first_development_action(release):
    protocol, claim, path = release
    assert registration(protocol, claim, path) == claim["registration_sha256"]


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("scope", "CHECKPOINT_EGL_DEVELOPMENT"),
        ("scope", "TEACHER_COLLECTION"),
        ("qualification_credit", 1),
        ("step_wall_budget_ns", WALL_NS + 1),
        ("png_compress_level", 6),
        ("parent_source_freeze_sha256", "0" * 64),
    ],
)
def test_valid_self_hash_does_not_override_release_boundary(release, field, replacement):
    protocol, claim, path = release
    protocol[field] = replacement
    claim["registration_sha256"] = digest(protocol)
    with pytest.raises(ValueError, match="foreign or changed"):
        registration(protocol, claim, path)


def test_claim_cannot_join_another_registration(release):
    protocol, claim, path = release
    claim["output"] = str(path / "copied")
    with pytest.raises(ValueError, match="claim does not bind"):
        registration(protocol, claim, path)


def test_frame_bytes_distinguish_level_one_and_six_at_equal_pixels():
    image = Image.new("RGB", (63, 41), (18, 92, 183))
    lo, hi = BytesIO(), BytesIO()
    image.save(lo, format="PNG", compress_level=1)
    image.save(hi, format="PNG", compress_level=6)
    assert Image.open(lo).tobytes() == Image.open(hi).tobytes()
    assert check_png(lo.getvalue(), level=1) == {"width": 63, "height": 41}
    with pytest.raises(ValueError, match="registered encoder bytes"):
        check_png(hi.getvalue(), level=1)


@pytest.mark.parametrize(
    ("now", "expected_ms", "status"),
    [(136.0, 8000, "ALLOW"), (136.125, 8125, "REJECT")],
)
def test_original_post_strict_step_limit(now, expected_ms, status):
    pre = SimpleNamespace(step_started_at=128.0, monotonic_now=128.25)
    post = SimpleNamespace(step_started_at=128.0, monotonic_now=now)
    original = {
        "original_rules": [{"id": "STEP_TIMEOUT", "decision": status}],
        "limiting_rule": None,
    }
    if status == "REJECT":
        original["limiting_rule"] = {
            "rule_id": "STEP_TIMEOUT",
            "measured_value": expected_ms,
            "limit_value": 8000,
        }
    answer = result_window(pre, post, original)
    assert answer["elapsed_ms"] == expected_ms and answer["step_timeout"] == (status == "REJECT")
    if status == "REJECT":
        wrong = deepcopy(original)
        wrong["limiting_rule"]["measured_value"] -= 1
        with pytest.raises(ValueError, match="stored STEP_TIMEOUT measurement differs"):
            result_window(pre, post, wrong)


def test_post_cannot_get_new_start_to_hide_elapsed():
    pre = SimpleNamespace(step_started_at=128.0, monotonic_now=128.25)
    post = SimpleNamespace(step_started_at=134.0, monotonic_now=141.0)
    original = {"original_rules": [], "limiting_rule": None}
    with pytest.raises(ValueError, match="different or invalid PRE"):
        result_window(pre, post, original)


def test_inventory_original_size_hash_and_reference(tmp_path):
    data = tmp_path / "frame.png"
    data.write_bytes(b"")
    check = {"bytes": 2, "sha256": sha_file(data)}
    files = {data.name: check}
    inventory = {
        "schema_version": "native.registered.full-horizon.inventory.v2",
        "native_qualification": "UNKNOWN",
        "files": files,
        "file_count": 1,
        "inventory_sha256": digest(files),
        "original_bytes": 2,
    }
    assert base.verify_inventory(tmp_path, inventory) == files
    assert (
        exact_reference(tmp_path, files, {"path": data.name, "sha256": check["sha256"]})
        == data.name
    )
    with pytest.raises(ValueError, match="does not join"):
        exact_reference(tmp_path, files, {"path": data.name, "sha256": "0" * 64})
    data.write_bytes(b"")
    with pytest.raises(ValueError, match="file hash mismatch"):
        base.verify_inventory(tmp_path, inventory)
