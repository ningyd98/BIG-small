"""Exact numeric atoms avoid redundant copying without weakening audit snapshots."""

from dataclasses import dataclass
from types import MappingProxyType

import numpy as np
import pytest

from cloud_edge_robot_arm.simulation.models import SensorFrame
from cloud_edge_robot_arm.simulation.mujoco import backend


def spy_copy(monkeypatch):
    original = backend.deepcopy
    calls = []

    def copy(value):
        calls.append(value)
        return original(value)

    monkeypatch.setattr(backend, "deepcopy", copy)
    return calls


@pytest.mark.parametrize("value", [0, -7, 10**80, 0.25, -0.0, float("inf"), float("nan")])
def test_exact_builtin_numeric_atoms_skip_fallback(monkeypatch, value):
    calls = spy_copy(monkeypatch)
    assert backend._operation_detach(value) is value
    assert calls == []


@pytest.mark.parametrize("value", [True, np.int64(7), np.float64(0.25)])
def test_bool_and_numpy_scalars_keep_original_fallback(monkeypatch, value):
    calls = spy_copy(monkeypatch)
    detached = backend._operation_detach(value)
    assert type(detached) is type(value) and detached == value
    assert len(calls) == 1 and calls[0] is value


@pytest.mark.parametrize("kind", ["int", "float", "error"])
def test_subclass_deepcopy_hooks_and_errors_remain(kind):
    calls = []
    fault = ValueError("original subclass failure")

    class Integer(int):
        def __deepcopy__(self, memo):
            calls.append(self)
            return int(self) + 100

        def __eq__(self, other):
            raise AssertionError("numeric type gate must not call value equality")

    class Floating(float):
        def __deepcopy__(self, memo):
            calls.append(self)
            if kind == "error":
                raise fault
            return float(self) + 100.0

    value = Integer(7) if kind == "int" else Floating(0.25)
    if kind == "error":
        with pytest.raises(ValueError) as error:
            backend._operation_detach(value)
        assert error.value is fault
    else:
        detached = backend._operation_detach(value)
        assert type(detached) is (int if kind == "int" else float)
        assert detached == (107 if kind == "int" else 100.25)
    assert len(calls) == 1 and calls[0] is value


def boundary(result, **changes):
    values = dict(operation_id=1, kind="CAPTURE", phase="END", episode_id="software-only",
                  physics_step=0, sim_time_s=0.0, parameters={}, result=result,
                  error_type=None, error=None)
    values.update(changes)
    return backend.BackendOperationBoundary(**values)


def test_nested_mutable_inputs_are_detached_and_readonly():
    array = np.arange(4, dtype=np.float64).reshape(2, 2)
    original = {"nested": [{"numbers": [1, 0.25]}], "array": array, "pair": ([3], 4.0)}
    event = boundary(original)
    original["nested"][0]["numbers"].append(99)
    original["pair"][0].append(99)
    array[0, 0] = 99
    assert isinstance(event.result, MappingProxyType)
    assert event.result["nested"][0]["numbers"] == (1, 0.25)
    assert event.result["pair"] == ((3,), 4.0)
    assert event.result["array"] == ((0.0, 1.0), (2.0, 3.0))
    with pytest.raises(TypeError):
        event.result["nested"][0]["numbers"] = ()
    with pytest.raises(TypeError):
        event.result["array"][0][0] = 100


def test_dataclass_subclass_and_small_sensor_frame_keep_field_order_and_isolation():
    @dataclass
    class Parent:
        first: list

    @dataclass
    class Child(Parent):
        second: list

    source = Child([{"n": 1}], [0.25])
    detached = backend._operation_detach(source)
    source.first[0]["n"] = 99
    source.second.append(99)
    assert list(detached) == ["first", "second"]
    assert detached["first"][0]["n"] == 1 and detached["second"] == (0.25,)
    frame = SensorFrame("synthetic", 0.0, 2, 2, rgb=b"\x01" * 12,
                        depth=(0.5, 0.6, 0.7, 0.8), object_detections=[{"n": 7}])
    event = boundary({"sensor_frame": frame, "instance_ids": (0, 1, 2, 3)})
    frame.object_detections[0]["n"] = 99
    assert event.result["sensor_frame"]["depth"] == (0.5, 0.6, 0.7, 0.8)
    assert event.result["sensor_frame"]["object_detections"][0]["n"] == 7


def test_model_dump_lookup_order_and_nested_result_are_preserved():
    calls = []

    class Model:
        @property
        def model_dump(self):
            calls.append("lookup")

            def dump(*, mode):
                calls.append(mode)
                return {"numbers": [1, 0.25]}

            return dump

    result = backend._operation_detach(Model())
    assert calls == ["lookup", "lookup", "python"]
    assert result["numbers"] == (1, 0.25)
    with pytest.raises(TypeError):
        result["numbers"] = ()


def test_custom_mutable_object_uses_original_deepcopy():
    class Mutable:
        def __init__(self):
            self.values = [1, 0.25]

    source = Mutable()
    detached = backend._operation_detach(source)
    assert type(detached) is Mutable and detached is not source
    source.values.append(99)
    assert detached.values == [1, 0.25]


def test_original_property_and_dataclass_copy_errors_propagate():
    fault = ValueError("original property/copy failure")

    class PropertyError:
        @property
        def model_dump(self):
            raise fault

    class CopyError:
        def __deepcopy__(self, memo):
            raise fault

    @dataclass
    class Container:
        value: object

    for value in [PropertyError(), Container(CopyError())]:
        with pytest.raises(ValueError) as error:
            backend._operation_detach(value)
        assert error.value is fault


@pytest.mark.parametrize("change", [{"operation_id": 0}, {"kind": "INVALID"}])
def test_invalid_boundary_rejects_before_detachment(monkeypatch, change):
    calls = spy_copy(monkeypatch)
    with pytest.raises(ValueError):
        boundary({"n": 1}, **change)
    assert calls == []
