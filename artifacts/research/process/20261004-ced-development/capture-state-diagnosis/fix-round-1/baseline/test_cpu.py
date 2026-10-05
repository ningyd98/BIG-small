"""Bounded fake-only contracts; no MuJoCo/model/renderer/physics instantiation."""

import base64
import gzip
import hashlib
import importlib.util
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ced_capture_diagnosis_cpu", HERE / "run_once.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_array_snapshot_detaches_before_live_mutation():
    data = SimpleNamespace(qpos=np.array([1.0, 2.0]), time=0.0)
    arrays = module.copy_arrays(data)
    data.qpos[0] = 9.0
    assert arrays["qpos"].tolist() == [1.0, 2.0]
    assert not np.shares_memory(arrays["qpos"], data.qpos)


def test_snapshot_reads_each_attribute_once():
    class Getter:
        reads = 0

        @property
        def values(self):
            self.reads += 1
            return np.array([self.reads])

    value = Getter()
    assert module.copy_arrays(value)["values"].tolist() == [1]
    assert value.reads == 1


def test_snapshot_preserves_noncontiguous_original_bytes_and_nan_bits():
    bits = np.array([0x8000000000000000, 7, 0x7FF8000000000001, 8], dtype=np.uint64)
    values = bits.view(np.float64)[::2]
    copied = module.copy_arrays(SimpleNamespace(values=values))["values"]
    assert copied.tobytes() == values.tobytes()
    assert copied.flags.c_contiguous
    assert not np.shares_memory(copied, values)


def test_aggregate_matches_frozen_domain():
    arrays = {"qpos": np.array([1.0]), "ctrl": np.array([2], dtype=np.int32)}
    expected = hashlib.sha256()
    for name, array in sorted(arrays.items()):
        expected.update(json.dumps((name, array.shape, array.dtype.str), sort_keys=True).encode())
        expected.update(array.tobytes())
    assert module.describe_arrays(arrays)["aggregate_sha256"] == expected.hexdigest()


def test_changed_members_detects_shape_dtype_and_inventory():
    before = module.describe_arrays({"a": np.array([1]), "b": np.ones((1, 2))})
    after = module.describe_arrays({"a": np.array([1.0]), "b": np.ones((2, 1)), "c": np.array([])})
    assert module.changed_members(before, after) == ["a", "b", "c"]


def test_object_array_is_rejected():
    with pytest.raises(RuntimeError, match="object array"):
        module.copy_arrays(SimpleNamespace(values=np.array([object()], dtype=object)))


def test_topology_records_overlapping_views_without_snapshot_alias():
    original = np.arange(4, dtype=np.float64)
    topology = {}
    copied = module.copy_arrays(SimpleNamespace(a=original[:3], b=original[1:]), topology=topology)
    assert topology["a"]["shares_memory_with"] == ["b"]
    assert topology["b"]["shares_memory_with"] == ["a"]
    assert topology["b"]["data_address"] - topology["a"]["data_address"] == 8
    assert not np.shares_memory(copied["a"], copied["b"])


def test_detached_contract_accepts_equal_independent_arrays():
    live = SimpleNamespace(qpos=np.array([1.0]), time=0.0)
    detached = SimpleNamespace(qpos=live.qpos.copy(), time=0.0)
    assert module.copy_contract(live, detached) == {
        "array_count": 1,
        "all_bytes_equal": True,
        "no_shared_memory": True,
    }


@pytest.mark.parametrize("variant", ["alias", "bytes", "shape", "dtype", "time", "inventory"])
def test_detached_contract_rejects_bad_copy(variant):
    live = SimpleNamespace(qpos=np.array([1.0]), time=0.0)
    detached = SimpleNamespace(qpos=live.qpos.copy(), time=0.0)
    if variant == "alias":
        detached.qpos = live.qpos
    elif variant == "bytes":
        detached.qpos[0] = 3.0
    elif variant == "shape":
        detached.qpos = detached.qpos.reshape(1, 1)
    elif variant == "dtype":
        detached.qpos = detached.qpos.astype(np.float32)
    elif variant == "time":
        detached.time = 1.0
    else:
        detached.extra = np.array([1.0])
    with pytest.raises(RuntimeError):
        module.copy_contract(live, detached)


class FakeRenderer:
    def __init__(self):
        self.calls = []

    def update_scene(self, *args, **kwargs):
        self.calls.append(("update_scene", args, kwargs))
        return None

    def render(self):
        self.calls.append(("render", (), {}))
        return np.ones((2, 2), dtype=np.float32)


def test_renderer_wrappers_delegate_once_preserve_return_and_restore():
    renderer = FakeRenderer()
    dictionary = dict(renderer.__dict__)
    events = []
    with module.renderer_phases(
        renderer,
        lambda name, ordinal: events.append((name, ordinal, "before")),
        lambda name, ordinal, token, value, error: events.append((name, ordinal, "after")),
    ) as counts:
        renderer.update_scene("data", camera=4)
        returned = renderer.render()
        assert returned.dtype == np.float32
    assert counts == {"update_scene": 1, "render": 1}
    assert renderer.calls == [("update_scene", ("data",), {"camera": 4}), ("render", (), {})]
    assert "update_scene" not in renderer.__dict__ and "render" not in renderer.__dict__
    assert renderer.__dict__.keys() == dictionary.keys()
    assert events == [
        ("update_scene", 1, "before"),
        ("update_scene", 1, "after"),
        ("render", 1, "before"),
        ("render", 1, "after"),
    ]


def test_renderer_failure_retains_original_exception_and_restores():
    renderer = FakeRenderer()
    failure = ValueError("original render failure")
    calls = []

    def failing():
        calls.append("delegate")
        raise failure

    renderer.render = failing
    ended = []
    with pytest.raises(ValueError) as result:
        with module.renderer_phases(
            renderer, lambda *_: None, lambda *args: ended.append(args[-1])
        ):
            renderer.render()
    assert result.value is failure and ended == [failure] and calls == ["delegate"]
    assert renderer.render is failing and "update_scene" not in renderer.__dict__


def test_original_exception_survives_after_phase_failure():
    renderer = FakeRenderer()
    original = ValueError("original")

    def render():
        raise original

    def after(*args):
        raise RuntimeError("diagnostic")

    renderer.render = render
    with pytest.raises(ValueError) as result:
        with module.renderer_phases(renderer, lambda *_: None, after):
            renderer.render()
    assert result.value is original
    assert original.__notes__ == ["after-phase diagnostic failed: RuntimeError('diagnostic')"]
    assert renderer.render is render and "update_scene" not in renderer.__dict__


class PassiveBackend:
    def __init__(self):
        self.total_physics_steps = 0
        self.command_records = []
        self._in_observer_callback = False
        self.step_calls = []
        self.observer = None

    def current_physics_observation(self):
        return SimpleNamespace(physics_step=self.total_physics_steps)

    @contextmanager
    def observe_physics_steps(self, callback):
        self.observer = callback
        try:
            yield
        finally:
            self.observer = None

    def step(self, *, steps):
        self.step_calls.append(steps)
        for _ in range(steps):
            self.total_physics_steps += 1
            self._in_observer_callback = True
            try:
                self.observer(self.current_physics_observation())
            finally:
                self._in_observer_callback = False


def test_passive_horizon_has_exact_0_to_10_callbacks_one_executor_call():
    backend, seen = PassiveBackend(), []

    def observe(snapshot):
        assert backend._in_observer_callback
        seen.append(snapshot.physics_step)

    module.passive_horizon(backend, observe)
    assert seen == list(range(11)) and backend.step_calls == [10]
    assert backend.total_physics_steps == 10 and backend.command_records == []
    assert backend.observer is None and not backend._in_observer_callback


@pytest.mark.parametrize("interrupt_step", [0, 5])
def test_interruption_preserves_partial_denominator_and_does_not_retry(interrupt_step):
    backend, seen = PassiveBackend(), []

    def stop(snapshot):
        seen.append(snapshot.physics_step)
        if snapshot.physics_step == interrupt_step:
            raise KeyboardInterrupt("preserved")

    with pytest.raises(KeyboardInterrupt, match="preserved"):
        module.passive_horizon(backend, stop)
    assert seen == list(range(interrupt_step + 1))
    assert backend.total_physics_steps == interrupt_step
    assert backend.step_calls == ([] if interrupt_step == 0 else [10])
    assert backend.observer is None and not backend._in_observer_callback


def test_existing_commands_reject_before_physics():
    backend = PassiveBackend()
    backend.command_records.append("command")
    with pytest.raises(RuntimeError, match="without commands"):
        module.passive_horizon(backend, lambda *_: None)
    assert backend.step_calls == []


def fake_reference():
    def encode(value):
        return json.dumps(
            value, sort_keys=True, allow_nan=False, default=lambda item: item.tolist()
        ).encode()

    def save(path, value):
        raw = json.dumps(value).encode()
        zipped = gzip.compress(raw, mtime=0)
        path.write_bytes(zipped)
        return {
            "file": path.name,
            "original_sha256": module.digest(raw),
            "compressed_sha256": module.digest(zipped),
        }

    return SimpleNamespace(
        scalar_struct=lambda item: {},
        json_bytes=encode,
        array_state=lambda value: module.describe_arrays(module.copy_arrays(value))[
            "aggregate_sha256"
        ],
        MuJoCoRGBDCamera=SimpleNamespace(
            _physics_state_hash=lambda data: module.digest(
                data.qpos.tobytes() + data.ctrl.tobytes()
            )
        ),
        observation_from_sensor_frame=lambda frame, **_: {"fake_raw": True},
        save_observation_gzip=save,
    )


def fake_backend():
    return SimpleNamespace(
        _data=SimpleNamespace(
            qpos=np.array([1.0]), ctrl=np.array([2.0]), derived=np.array([0.0]), time=0.0
        ),
        _model=SimpleNamespace(mass=np.array([1.0])),
        _target_positions=np.array([0.0]),
        _pending_joint_targets=[],
        _gripper_open=True,
        _estop_engaged=False,
        _actuator_delay_steps=0,
        _rng=np.random.default_rng(3),
        _sensor_frame=object(),
        _camera=None,
        total_physics_steps=0,
        command_records=[],
        _sensor_noise_std_m=0.0,
        _scenario=SimpleNamespace(scenario_id="fake"),
        _episode_id="fake",
    )


def test_snapshot_storage_roundtrips_exact_array_bytes(tmp_path):
    backend, reference = fake_backend(), fake_reference()
    store = module.SnapshotStore(tmp_path / "snapshots", reference)
    saved = store.save(backend, "BEFORE")
    payload = json.loads(gzip.decompress((tmp_path / saved["saved"]["file"]).read_bytes()))
    assert base64.b64decode(payload["array_bytes_base64"]["qpos"]) == backend._data.qpos.tobytes()
    assert saved["state"]["data_arrays_sha256"] == reference.array_state(backend._data)
    backend._data.qpos[0] = 9
    assert base64.b64decode(payload["array_bytes_base64"]["qpos"]) != backend._data.qpos.tobytes()


def test_storage_budget_failure_drops_no_fields_and_creates_no_file(tmp_path, monkeypatch):
    store = module.SnapshotStore(tmp_path / "snapshots", fake_reference())
    monkeypatch.setattr(module, "MAX_STORED_BYTES", 1)
    with pytest.raises(RuntimeError, match="storage budget"):
        store.save(fake_backend(), "BEFORE")
    assert store.ordinal == 0 and list(store.directory.iterdir()) == []


@pytest.mark.parametrize("protected_change", [False, True])
def test_probe_localizes_derived_change_and_rejects_protected_change(tmp_path, protected_change):
    backend, reference = fake_backend(), fake_reference()
    renderer = FakeRenderer()
    original_update = renderer.update_scene

    def update(data, **kwargs):
        original_update(data, **kwargs)
        getattr(data, "qpos" if protected_change else "derived")[0] += 1

    renderer.update_scene = update

    def capture(data, **kwargs):
        assert kwargs["include_instances"] is False and kwargs["noise_std_m"] == 0.0
        renderer.update_scene(data, camera=0)
        renderer.render()
        renderer.render()
        return SimpleNamespace(latency_ms=0.0), (), {}, ("equal", "equal")

    backend._camera = SimpleNamespace(_renderer=renderer, _capture=capture)
    rows = []
    journal = SimpleNamespace(
        ensure=lambda _: None,
        emit=lambda event, **payload: rows.append({"event": event, **payload}),
    )
    store = module.SnapshotStore(tmp_path / "snapshots", reference)
    probe = module.CaptureProbe(backend, reference, store, journal, tmp_path)
    if protected_change:
        with pytest.raises(RuntimeError, match="protected physics"):
            probe.capture()
        assert probe.failed == 1 and probe.completed == 0
        assert rows[-1]["event"] == "CAPTURE_FAILED"
    else:
        probe.capture()
        assert probe.failed == 0 and probe.completed == 1 and probe.state_differences == 1
        assert rows[-1]["changed_members"] == ["derived"]
        assert rows[-1]["original_whole_step_guard_would_accept"] is False
    phases = [row for row in rows if row["event"] == "RENDER_PHASE"]
    assert phases[0]["changed_members"] == (["qpos"] if protected_change else ["derived"])
    assert renderer.update_scene is update and "render" not in renderer.__dict__
    assert len(renderer.calls) == 3


@pytest.mark.parametrize("copy_variant", ["detached", "alias", "bytes"])
def test_terminal_copy_gate_never_backfills_rejected_copy(tmp_path, monkeypatch, copy_variant):
    backend, reference = fake_backend(), fake_reference()
    store = module.SnapshotStore(tmp_path / "snapshots", reference)
    rows, captures, copies = [], [], []

    def make_copy(data):
        copies.append(data)
        replica = SimpleNamespace(**vars(data))
        if copy_variant != "alias":
            for name, values in module.copy_arrays(data).items():
                setattr(replica, name, values)
        if copy_variant == "bytes":
            replica.qpos[0] += 2
        return replica

    monkeypatch.setattr(module.copy, "copy", make_copy)
    journal = SimpleNamespace(emit=lambda event, **values: rows.append({"event": event, **values}))
    probe = SimpleNamespace(capture=lambda *args, **kwargs: captures.append((args, kwargs)))
    counts = {
        "terminal_copy_attempts": 0,
        "terminal_copy_rejected": 0,
        "terminal_clone_capture_calls": 0,
    }
    module.terminal_copy_probe(backend, probe, store, journal, counts)
    assert len(copies) == 1 and counts["terminal_copy_attempts"] == 1
    assert backend.total_physics_steps == 0 and backend.command_records == []
    if copy_variant == "detached":
        assert len(captures) == 1 and captures[0][1] == {"detached": True}
        assert counts["terminal_clone_capture_calls"] == 1 and counts["terminal_copy_rejected"] == 0
        assert rows[-1]["event"] == "DETACHED_CAPTURE_END"
    else:
        assert captures == [] and counts["terminal_clone_capture_calls"] == 0
        assert counts["terminal_copy_rejected"] == 1
        assert rows[-1]["event"] == "DETACHED_COPY_REJECTED" and rows[-1]["retry"] is False
