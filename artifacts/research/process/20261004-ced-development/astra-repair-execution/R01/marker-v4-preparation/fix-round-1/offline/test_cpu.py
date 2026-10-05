"""SOFTWARE_ONLY: detached JSON/numeric fixtures; no simulator or decoder."""

import copy
import hashlib
import importlib.util
import struct
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "sparse_offline", Path(__file__).with_name("verify_sparse.py")
)
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)


def index_fixture():
    selected = [0, 2]

    def ident(step):
        return dict(episode_id="e", physics_step=step, sim_time_s=step * 0.1)

    rows = []
    for step in range(3):
        rows.append(dict(event="PHYSICAL_CALLBACK", selected=step in selected, **ident(step)))
        if step in selected:
            rows.extend(
                [
                    dict(event="BEGIN", capture_monotonic_begin_ns=10 + step * 10, **ident(step)),
                    dict(event="END", capture_monotonic_end_ns=11 + step * 10, **ident(step)),
                ]
            )
    summary = dict(
        status="COMPLETE",
        expected_physics_steps=2,
        final_step=2,
        final_sim_time_s=0.2,
        episode_id="e",
        recipe_range_status="MATCH",
        physical_callback_attempts=3,
        physical_callbacks=3,
        allocated_steps=selected,
        saved_steps=selected,
        failed_steps=[],
        missing_selected_steps=[],
        publication_errors=[],
    )
    rows.append(dict(event="FINISH", summary=summary))
    return rows, summary, selected


def test_fixed_sparse_horizon_accepts_healthy_fixture():
    rows, summary, selected = index_fixture()
    assert sorted(V.validate_index(rows, summary, selected, 2, "e")) == selected


@pytest.mark.parametrize(
    "variant",
    ["extra_callback", "duplicate_end", "failed", "hanging", "wrong_selected", "wrong_episode"],
)
def test_full_callback_and_selected_denominator_rejects_drift(variant):
    rows, summary, selected = index_fixture()
    if variant == "extra_callback":
        rows.insert(
            -1,
            dict(
                event="PHYSICAL_CALLBACK",
                selected=False,
                episode_id="e",
                physics_step=3,
                sim_time_s=0.3,
            ),
        )
    elif variant == "duplicate_end":
        rows.insert(-1, copy.deepcopy(rows[2]))
    elif variant == "failed":
        rows.insert(-1, dict(event="FAILED", episode_id="e", physics_step=3, sim_time_s=0.3))
    elif variant == "hanging":
        rows.pop(-2)
    elif variant == "wrong_selected":
        rows[0]["selected"] = False
    elif variant == "wrong_episode":
        rows[0]["episode_id"] = "other"
    with pytest.raises(ValueError):
        V.validate_index(rows, summary, selected, 2, "e")


def operation_fixture():
    begin = dict(
        source=dict(
            operation_id=1,
            kind="PHYSICS",
            phase="BEGIN",
            episode_id="e",
            physics_step=0,
            sim_time_s=0.0,
            parameters={},
            result=None,
            error=None,
            error_type=None,
        ),
        record_seq=1,
    )
    end = copy.deepcopy(begin)
    end["source"].update(phase="END", physics_step=1, sim_time_s=0.1)
    end["record_seq"] = 2
    return begin, end


def test_operation_preserves_begin_identity_and_physics_advance():
    V.validate_operation_pair(*operation_fixture(), "e")


@pytest.mark.parametrize(
    "key,value", [("kind", "COMMAND"), ("episode_id", "wrong"), ("physics_step", 999)]
)
def test_operation_rejects_unrelated_begin(key, value):
    begin, end = operation_fixture()
    begin["source"][key] = value
    with pytest.raises(ValueError):
        V.validate_operation_pair(begin, end, "e")


def full_fixture():
    camera = dict(sim_time_s=0.1, qpos=[0.0] * 37, qvel=[0.0] * 33, act=[], ctrl=[0.0] * 9)
    raw = struct.pack("<d", 0.1) + b"".join(
        struct.pack("<I", len(camera[n])) + struct.pack("<" + "d" * len(camera[n]), *camera[n])
        for n in ("qpos", "qvel", "act", "ctrl")
    )
    full = dict(episode_id="e", physics_step=1, sim_time_s=0.1, camera_state=camera)
    before = dict(
        episode_id="e",
        physical_step=1,
        sim_time_s=0.1,
        physics_state_sha256=hashlib.sha256(raw).hexdigest(),
    )
    fields = [
        dict(
            name=n,
            dtype="<f8",
            shape=[len(camera[n])],
            status="DATA_BACKED" if camera[n] else "EMPTY",
            byte_sha256=hashlib.sha256(
                struct.pack("<" + "d" * len(camera[n]), *camera[n])
            ).hexdigest()
            if camera[n]
            else None,
        )
        for n in ("qpos", "qvel", "act", "ctrl")
    ]
    return full, before, fields, dict(episode_id="e", physics_step=1, sim_time_s=0.1)


def test_full_capture_qpos_binds_guard_byte_domain():
    V.validate_full_state(*full_fixture())


@pytest.mark.parametrize("variant", ["qpos_bytes", "missing_qpos", "wrong_step"])
def test_full_capture_state_rejects_forgery(variant):
    full, before, fields, identity = full_fixture()
    if variant == "qpos_bytes":
        full["camera_state"]["qpos"][0] = 1.0
    elif variant == "missing_qpos":
        full["camera_state"]["qpos"].pop()
    else:
        full["physics_step"] = 2
    with pytest.raises(ValueError):
        V.validate_full_state(full, before, fields, identity)


def test_recorded_comparison_excludes_only_episode():
    assert (
        V.compare_recorded(
            [dict(episode_id="old", value=[1.0])], [dict(episode_id="new", value=[1.0])]
        )["different_rows"]
        == 0
    )
    assert (
        V.compare_recorded(
            [dict(episode_id="old", value=[1.0])], [dict(episode_id="new", value=[2.0])]
        )["different_rows"]
        == 1
    )


def test_marker_comparison_retains_unknown_and_exception_denominator():
    r = V.compare_markers(
        [1, 2, 3],
        {1: "UNKNOWN", 2: "OBSERVED", 3: "UNKNOWN"},
        {1: "OBSERVED", 2: "UNKNOWN", 3: "DECODE_ERROR"},
    )
    assert r["selected_denominator"] == 3
    assert r["transitions"] == {
        "UNKNOWN->OBSERVED": 1,
        "OBSERVED->UNKNOWN": 1,
        "UNKNOWN->DECODE_ERROR": 1,
    }
