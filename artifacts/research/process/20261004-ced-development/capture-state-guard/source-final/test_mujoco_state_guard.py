"""SOFTWARE_ONLY fakes and immutable saved bytes; no MuJoCo model or execution."""

from __future__ import annotations

import gzip
import importlib.util
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
HEADER_ROOT = ROOT / ".venv/lib/python3.12/site-packages/mujoco/include/mujoco"
BINDING_SHA = "8fd6c4e9e92676f4175cde18bebb3d354d3e85aac6971cb194f66be20ff9ecc8"
RAW = (
    ROOT
    / "artifacts/research/process/20261004-ced-development"
    / "capture-state-diagnosis/diagnostic-1/snapshots"
)


@pytest.fixture
def api():
    baseline = os.environ.get("BIGSMALL_STATE_GUARD_RED_BASELINE")
    if baseline:
        spec = importlib.util.spec_from_file_location("guard_red_baseline", baseline)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    from cloud_edge_robot_arm.research import mujoco_state_guard

    return mujoco_state_guard


@pytest.fixture
def contract(api):
    return api.MujocoStateContract(
        mjxmacro_bytes=(HEADER_ROOT / "mjxmacro.h").read_bytes(),
        mjdata_bytes=(HEADER_ROOT / "mjdata.h").read_bytes(),
        binding_sha256=BINDING_SHA,
        version="3.3.7",
    )


def dynamic_specs():
    text = (HEADER_ROOT / "mjxmacro.h").read_text()
    specs = {}
    for family in ("SOLVER", "DUAL", "ISLAND"):
        body = text.split("#define MJDATA_ARENA_POINTERS_" + family, 1)[1].split("\n\n", 1)[0]
        for line in body.splitlines():
            match = re.search(
                r"X(?:NV)?\s*\(\s*(int|mjtNum),\s*(\w+),\s*(MJ_[MD]\(\w+\)),\s*(\d+)\s*\)", line
            )
            if match:
                dtype, name, dimension, width = match.groups()
                specs[name] = (dtype, dimension, int(width))
    return specs


class FakeData:
    def __init__(self, model, **counts):
        self.counts = dict(nefc=0, nJ=0, nA=0, nisland=0, nidof=0) | counts
        self.arrays = {"qpos": np.array([1.0, 2.0]).view()}
        self.changing = set()
        self.reads = {}
        for name, (dtype, dimension, width) in dynamic_specs().items():
            scope, key = re.fullmatch(r"MJ_([MD])\((\w+)\)", dimension).groups()
            size = getattr(model, key) if scope == "M" else self.counts[key]
            shape = (size,) if width == 1 else (size, width)
            self.arrays[name] = np.zeros(shape, dtype="int32" if dtype == "int" else "float64")

    def __dir__(self):
        return list(self.arrays) + list(self.counts)

    def __getattr__(self, name):
        if name in self.counts:
            return self.counts[name]
        if name not in self.arrays:
            raise AttributeError(name)
        self.reads[name] = self.reads.get(name, 0) + 1
        array = self.arrays[name]
        return np.full_like(array, self.reads[name]) if name in self.changing else array


@pytest.fixture
def model():
    return SimpleNamespace(nv=3, nC=5, ntendon=0)


def snap(api, contract, data, model, version="3.3.7"):
    return api.snapshot_data_arrays(data, model, contract=contract, runtime_version=version)


def test_frozen_header_drives_all_dynamic_getter_shapes_and_types(contract):
    declared = dynamic_specs()
    assert len(declared) == len(contract.getters) == 60
    for getter in contract.getters:
        dtype, dimension, width = declared[getter.name]
        assert getter.dtype == ("<i4" if dtype == "int" else "<f8")
        assert "MJ_" + getter.source + "(" + getter.dimension + ")" == dimension
        assert getter.width == width


def test_null_allocation_read_variation_is_not_live_state(api, contract, model):
    data = FakeData(model)
    data.changing = {"iM", "dof_island"}
    left, right = snap(api, contract, data, model), snap(api, contract, data, model)
    assert left.digest == right.digest


def test_dual_null_allocation_read_variation_is_not_live_state(api, contract, model):
    data = FakeData(model, nefc=2)
    data.changing = {"efc_AR_rowadr", "efc_AR_rownnz", "efc_pos"}
    assert snap(api, contract, data, model).digest == snap(api, contract, data, model).digest


def test_unknown_owning_storage_fails_closed(api, contract, model):
    data = FakeData(model)
    data.arrays["unknown_owned"] = np.ones(3)
    with pytest.raises(api.StateGuardError, match="owning"):
        snap(api, contract, data, model)


def test_active_bytes_and_support_transition_are_guarded(api, contract, model):
    data = FakeData(model)
    before = snap(api, contract, data, model)
    data.arrays["iM"] = data.arrays["iM"].view()
    active = snap(api, contract, data, model)
    with pytest.raises(api.StateGuardError, match="changed"):
        api.assert_unchanged(before, active)
    data.arrays["iM"][0] += 1
    changed = snap(api, contract, data, model)
    with pytest.raises(api.StateGuardError, match="changed"):
        api.assert_unchanged(active, changed)
    field = next(f for f in active.fields if f.name == "iM")
    assert field.status == "DATA_BACKED" and field.byte_sha256 is not None


@pytest.mark.parametrize("change", ["byte", "shape", "dtype", "inventory"])
def test_all_real_view_changes_are_detected(api, contract, model, change):
    data = FakeData(model)
    before = snap(api, contract, data, model)
    if change == "byte":
        data.arrays["qpos"][0] += 1
    elif change == "shape":
        data.arrays["qpos"] = data.arrays["qpos"].reshape(1, 2)
    elif change == "dtype":
        data.arrays["qpos"] = np.array([1, 2], dtype="int64").view()
    else:
        data.arrays["new_live"] = np.ones(2).view()
    with pytest.raises(api.StateGuardError, match="changed"):
        api.assert_unchanged(before, snap(api, contract, data, model))


@pytest.mark.parametrize("change", ["shape", "dtype", "missing", "not_array", "dimension"])
def test_dynamic_contract_drift_fails_closed(api, contract, model, change):
    data = FakeData(model)
    if change == "shape":
        data.arrays["iM"] = np.zeros(4)
    elif change == "dtype":
        data.arrays["iM"] = np.zeros(5, dtype="float32")
    elif change == "missing":
        del data.arrays["iM"]
    elif change == "not_array":
        data.arrays["iM"] = [1, 2]
    else:
        data.counts["nefc"] = True
    with pytest.raises(api.StateGuardError):
        snap(api, contract, data, model)


@pytest.mark.parametrize("version", ["3.3.6", "3.4.0", None, True])
def test_runtime_version_drift_fails_closed(api, contract, model, version):
    with pytest.raises(api.StateGuardError, match="version"):
        snap(api, contract, FakeData(model), model, version)


@pytest.mark.parametrize("key", ["mjxmacro_bytes", "mjdata_bytes", "binding_sha256", "version"])
def test_contract_pin_drift_fails_closed(api, key):
    kwargs = dict(
        mjxmacro_bytes=(HEADER_ROOT / "mjxmacro.h").read_bytes(),
        mjdata_bytes=(HEADER_ROOT / "mjdata.h").read_bytes(),
        binding_sha256=BINDING_SHA,
        version="3.3.7",
    )
    kwargs[key] = b"wrong" if key.endswith("bytes") else "wrong"
    with pytest.raises(api.StateGuardError):
        api.MujocoStateContract(**kwargs)


def test_empty_known_fields_and_shape_support_changes_are_structural(api, contract, model):
    data = FakeData(model)
    data.arrays["act"] = np.zeros(0)
    before = snap(api, contract, data, model)
    empty = next(f for f in before.fields if f.name == "act")
    assert empty.status == "EMPTY" and empty.byte_count == 0
    data.arrays["act"] = np.ones(1).view()
    with pytest.raises(api.StateGuardError, match="changed"):
        api.assert_unchanged(before, snap(api, contract, data, model))
    data.arrays["unknown_empty"] = np.zeros(0)
    with pytest.raises(api.StateGuardError, match="owning"):
        snap(api, contract, data, model)


def protected():
    return dict(
        model_arrays_sha256="a" * 64,
        model_options_sha256="b" * 64,
        controller_state_sha256="c" * 64,
        rng_state_sha256="d" * 64,
        physics_state_sha256="e" * 64,
        sensor_cache_object_id=1,
        camera_object_id=2,
        physical_step=0,
        command_count=0,
        sensor_noise_std_m=0.0,
        sim_time_s=0.0,
    )


@pytest.mark.parametrize("key", sorted(protected()))
def test_original_protected_components_remain_guarded(api, contract, model, key):
    data = snap(api, contract, FakeData(model), model)
    original = protected()
    before = api.attach_protected_state(data, original)
    original[key] = "f" * 64 if key.endswith("sha256") else 3
    after = api.attach_protected_state(data, original)
    with pytest.raises(api.StateGuardError, match="changed"):
        api.assert_unchanged(before, after)
    assert before.protected_json != after.protected_json


def test_protected_payload_must_be_complete_finite_and_detached(api, contract, model):
    data = snap(api, contract, FakeData(model), model)
    payload = protected() | {"extra": [1]}
    before = api.attach_protected_state(data, payload)
    payload["extra"][0] = 2
    assert json.loads(before.protected_json)["extra"] == [1]
    for invalid in [
        protected() | {"sim_time_s": float("nan")},
        {"physical_step": 0},
        protected() | {"data_arrays_sha256": "legacy"},
    ]:
        with pytest.raises(api.StateGuardError):
            api.attach_protected_state(data, invalid)


def test_single_getter_reads_and_no_array_aliases(api, contract, model):
    data = FakeData(model)
    before = snap(api, contract, data, model)
    assert set(data.reads.values()) == {1}
    data.arrays["qpos"][0] += 1
    assert before.digest != snap(api, contract, data, model).digest
    with pytest.raises((AttributeError, TypeError)):
        before.fields[0].name = "mutated"


def test_immutable_contract_is_revalidated_before_use(api, contract, model):
    object.__setattr__(contract, "binding_sha256", "wrong")
    with pytest.raises(api.StateGuardError):
        snap(api, contract, FakeData(model), model)
    with pytest.raises(api.StateGuardError):
        snap(api, SimpleNamespace(), FakeData(model), model)


def test_snapshot_nested_record_is_revalidated_and_cannot_alias(api, contract, model):
    snapshot = snap(api, contract, FakeData(model), model)
    object.__setattr__(snapshot.fields[0], "shape", [1])
    with pytest.raises(api.StateGuardError):
        api.assert_unchanged(snapshot, snapshot)


@pytest.mark.parametrize("change", ["byte_count", "dtype_descr_json"])
def test_record_structural_metadata_is_validated(api, contract, model, change):
    from dataclasses import replace

    snapshot = snap(api, contract, FakeData(model), model)
    record = next(f for f in snapshot.fields if f.name == "qpos")
    value = record.byte_count + 1 if change == "byte_count" else "not-json"
    with pytest.raises(api.StateGuardError):
        replace(record, **{change: value})


def test_structured_dtype_description_is_in_full_byte_domain(api, contract, model):
    data = FakeData(model)
    data.arrays["structured_view"] = np.zeros(2, dtype=[("left", "i4")]).view()
    before = snap(api, contract, data, model)
    data.arrays["structured_view"] = np.zeros(2, dtype=[("right", "i4")]).view()
    with pytest.raises(api.StateGuardError, match="changed"):
        api.assert_unchanged(before, snap(api, contract, data, model))


def test_object_or_ndarray_subclass_cannot_supply_plain_state(api, contract, model):
    data = FakeData(model)
    for invalid in [np.ones(2, dtype=object), np.ones(2).view(np.ma.MaskedArray)]:
        data.arrays["qpos"] = invalid
        with pytest.raises(api.StateGuardError, match="plain numeric"):
            snap(api, contract, data, model)


@pytest.mark.parametrize(
    "left_file,right_file",
    [("0001-snapshot.gz", "0002-snapshot.gz"), ("0122-snapshot.gz", "0123-snapshot.gz")],
)
def test_original_saved_snapshot_null_semantics_software_only(api, contract, left_file, right_file):
    snapshots = [
        json.loads(gzip.decompress((RAW / f).read_bytes())) for f in (left_file, right_file)
    ]
    import base64

    def restore(saved):
        arrays = {}
        for name, desc in saved["data_arrays"]["members"].items():
            dtype = (
                np.dtype(desc["dtype"])
                if desc["dtype"].startswith(("<", ">", "|", "="))
                and not desc["dtype"].startswith("|V")
                else np.dtype([tuple(x) for x in desc["dtype_descr"]])
            )
            value = (
                np.frombuffer(base64.b64decode(saved["array_bytes_base64"][name]), dtype=dtype)
                .copy()
                .reshape(desc["shape"])
            )
            arrays[name] = (
                value.copy() if saved["data_array_topology"][name]["owns_data"] else value.view()
            )
            assert (
                bool(arrays[name].flags.owndata) == saved["data_array_topology"][name]["owns_data"]
            )
        model = SimpleNamespace(
            nv=arrays["qvel"].size, nC=arrays["M"].size, ntendon=arrays["tendon_efcadr"].size
        )
        data = FakeData(
            model,
            nefc=arrays["efc_force"].size,
            nJ=arrays["efc_J"].size,
            nA=arrays["efc_AR"].size,
            nisland=arrays["island_nv"].size,
            nidof=arrays["iacc"].size,
        )
        data.arrays = arrays
        return snap(api, contract, data, model)

    left, right = map(restore, snapshots)
    api.assert_unchanged(left, right)
    assert left.digest == right.digest
