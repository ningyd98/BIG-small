"""Qualified CPU-only record boundary checks; import no MuJoCo/backend."""

from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path

import pytest

from cloud_edge_robot_arm.research import mujoco_state_guard as guard

ROOT = Path(__file__).resolve().parents[5]


def valid_record():
    return guard.ArrayField(
        "qpos", "DATA_BACKED", "VIEW", (2,), "<f8", '[["","<f8"]]', 16, "a" * 64
    )


@pytest.mark.parametrize("description", ('0', '[["","<i4"]]', '[["","|O"]]'))
def test_inconsistent_or_non_dtype_description_fails_closed(description):
    record = valid_record()
    with pytest.raises(guard.StateGuardError):
        replace(record, dtype_descr_json=description)


def test_genuine_snapshot_revalidation_rejects_forged_canonical_description():
    path = ROOT / "tests/test_mujoco_state_guard.py"
    spec = importlib.util.spec_from_file_location("guard_review_cpu_helpers", path)
    assert spec and spec.loader
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    contract = guard.MujocoStateContract(
        (helpers.HEADER_ROOT / "mjxmacro.h").read_bytes(),
        (helpers.HEADER_ROOT / "mjdata.h").read_bytes(),
        helpers.BINDING_SHA,
        "3.3.7",
    )
    model = helpers.SimpleNamespace(nv=3, nC=5, ntendon=0)
    snapshot = guard.snapshot_data_arrays(
        helpers.FakeData(model), model, contract=contract, runtime_version="3.3.7"
    )
    record = next(item for item in snapshot.fields if item.name == "qpos")
    object.__setattr__(record, "dtype_descr_json", '0')
    with pytest.raises(guard.StateGuardError):
        guard.assert_unchanged(snapshot, snapshot)
