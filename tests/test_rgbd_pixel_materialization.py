"""Pixel materialization preserves registered bytes and custom conversion behavior."""

import base64
import hashlib
import io
import json
import math
import struct
from array import array as native_array
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError

from cloud_edge_robot_arm.simulation.mujoco import camera
from cloud_edge_robot_arm.vision import observations

STAMP = datetime(2026, 11, 12, tzinfo=UTC)
MATRIX = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)


class FixedDatetime:
    @staticmethod
    def now(zone):
        assert zone is UTC
        return STAMP


class FakeRenderer:
    def __init__(self, rgb, depth, segmentation, mutate=None):
        self.rgb, self.depth, self.segmentation = rgb, depth, segmentation
        self.mode = "rgb"
        self.calls = []
        self.mutate = mutate

    def disable_depth_rendering(self):
        self.mode = "rgb"

    def disable_segmentation_rendering(self):
        self.mode = "rgb"

    def enable_depth_rendering(self):
        self.mode = "depth"

    def enable_segmentation_rendering(self):
        self.mode = "segmentation"

    def update_scene(self, data, *, camera):
        self.data = data

    def render(self):
        self.calls.append(self.mode)
        if self.mutate:
            self.mutate(self)
        return {"rgb": self.rgb, "depth": self.depth, "segmentation": self.segmentation}[self.mode]


def make_camera(width=3, height=2, *, depth=None, mutate=None):
    count = width * height
    rgb = (np.arange(count * 3, dtype=np.uint32) % 251).astype(np.uint8).reshape(height, width, 3)
    if depth is None:
        depth = (0.4 + np.arange(count, dtype=np.float32) % 769 / 1000).reshape(height, width)
    segmentation = np.empty((height, width, 2), dtype=np.int32)
    segmentation[:, :, 0] = np.arange(count, dtype=np.int32).reshape(height, width) % 4
    segmentation[:, :, 1] = 5
    segmentation.reshape(-1, 2)[::7, 1] = 4
    model = SimpleNamespace(
        cam_fovy=np.array([50.0]),
        vis=SimpleNamespace(map=SimpleNamespace(znear=0.01, zfar=20.0)),
        stat=SimpleNamespace(extent=2.0),
    )
    data = SimpleNamespace(
        time=0.0,
        qpos=np.zeros(2),
        qvel=np.zeros(2),
        act=np.zeros(0),
        ctrl=np.zeros(2),
        cam_xpos=np.array([[0.35, 0.0, 1.4]]),
        cam_xmat=np.eye(3).reshape(1, 9),
    )
    value = object.__new__(camera.MuJoCoRGBDCamera)
    value._width, value._height, value._camera_id = width, height, 0
    value._model = model
    value._mujoco = SimpleNamespace(
        mjtObj=SimpleNamespace(mjOBJ_GEOM=5),
        mj_id2name=lambda model, kind, idx: "synthetic-" + str(idx),
    )
    value._renderer = FakeRenderer(rgb, depth, segmentation, mutate)
    return value, data


def capture(value, data, *, noise=0.001, instances=True):
    with (
        patch.object(camera, "datetime", FixedDatetime),
        patch.object(camera, "uuid4", lambda: SimpleNamespace(hex="synthetic614")),
    ):
        return value._capture(
            data,
            rng=np.random.default_rng(614001),
            noise_std_m=noise,
            scene_id="synthetic-scene",
            episode_id="synthetic-episode",
            include_instances=instances,
        )


def wire_payload(bits=(0, 0x80000000, 1, 0x007FFFFF, 0x00800000, 0x3F800000, 0x7F7FFFFF)):
    image = io.BytesIO()
    Image.new("RGB", (len(bits), 1), (17, 29, 43)).save(image, format="PNG")
    return dict(
        frame_id="synthetic-r614-test",
        captured_at=STAMP,
        sim_time_s=0.0,
        width=len(bits),
        height=1,
        rgb_png_base64=base64.b64encode(image.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(struct.pack("<" + "I" * len(bits), *bits)).decode(),
        intrinsics=(2.0, 2.0, 0.0, 0.0),
        camera_to_world=MATRIX,
        source="rgbd_camera",
    )


def test_supported_depth_validation_avoids_scalar_unpack(monkeypatch):
    payload = wire_payload()

    def unexpected(*args):
        pytest.fail("supported float32 validation still allocates per-pixel unpack tuples")

    monkeypatch.setattr(observations.struct, "iter_unpack", unexpected)
    result = observations.RGBDObservation.model_validate(payload)
    assert result.valid_mask_bytes() == bytes((0, 0, 1, 1, 1, 1, 1))


def test_supported_camera_pixels_avoid_python_scalar_coercion(monkeypatch):
    value, data = make_camera()
    calls = []

    def counted_float(value):
        if type(value) is np.float32:
            calls.append("float32")
        return float(value)

    def counted_int(value):
        if type(value) is np.int32:
            calls.append("int32")
        return int(value)

    monkeypatch.setattr(camera, "float", counted_float, raising=False)
    monkeypatch.setattr(camera, "int", counted_int, raising=False)
    frame, ids, labels, hashes = capture(value, data, noise=0)
    assert frame.depth == tuple(float(v) for v in value._renderer.depth.ravel())
    assert ids == (-1, 1, 2, 3, 0, 1)
    assert labels == {0: "synthetic-0", 1: "synthetic-1", 2: "synthetic-2", 3: "synthetic-3"}
    assert len(hashes) == 3 and len(set(hashes)) == 1
    assert calls == []


def independent_checksum(payload, mask):
    fields = {
        key: payload.get(key)
        for key in (
            "frame_id",
            "sim_time_s",
            "source",
            "scene_id",
            "episode_id",
            "calibration_version",
            "width",
            "height",
            "intrinsics",
            "camera_to_world",
        )
    }
    fields.update(
        captured_at=STAMP.isoformat(),
        depth_convention="optical_z_m",
        rgb_sha256=hashlib.sha256(base64.b64decode(payload["rgb_png_base64"])).hexdigest(),
        depth_sha256=hashlib.sha256(base64.b64decode(payload["depth_float32_base64"])).hexdigest(),
        mask_sha256=hashlib.sha256(mask).hexdigest(),
    )
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


@pytest.mark.parametrize("supplied", [False, True])
def test_wire_bits_mask_checksum_and_roundtrip_are_preserved(supplied):
    body = wire_payload()
    mask = bytes((0, 0, 1, 1, 1, 1, 1))
    if supplied:
        body["valid_mask_base64"] = base64.b64encode(mask).decode()
    result = observations.RGBDObservation.model_validate(body)
    assert result.depth_float32_base64 == body["depth_float32_base64"]
    assert result.valid_mask_bytes() == mask
    assert result.checksum_sha256 == independent_checksum(body, mask)
    assert math.copysign(1, result.depth_values()[1]) == -1
    assert observations.RGBDObservation.model_validate_json(result.model_dump_json()) == result
    changed = wire_payload((0, 0, 1, 0x007FFFFF, 0x00800000, 0x3F800000, 0x7F7FFFFF))
    other = observations.RGBDObservation.model_validate(changed)
    assert other.valid_mask_bytes() == mask and other.checksum_sha256 != result.checksum_sha256


@pytest.mark.parametrize(
    "bits",
    [
        0x80000001,
        0xBF800000,
        0xFF7FFFFF,
        0x7F800000,
        0xFF800000,
        0x7FC00001,
        0xFFC00001,
        0x7F800001,
        0xFF800001,
    ],
)
def test_negative_and_nonfinite_bits_keep_original_rejection(bits):
    body = wire_payload((bits,))
    body.update(valid_mask_base64="bad mask", intrinsics=(0, 0, 0, 0), checksum_sha256="wrong")
    with pytest.raises(ValidationError, match="depth must be finite nonnegative metres"):
        observations.RGBDObservation.model_validate(body)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"rgb_png_base64": "bad", "depth_float32_base64": "AAAA"}, "invalid RGB-D image encoding"),
        ({"depth_float32_base64": "AAAA", "valid_mask_base64": "bad"}, "depth size must equal"),
        ({"valid_mask_base64": "bad"}, "invalid depth mask encoding"),
        ({"valid_mask_base64": base64.b64encode(bytes(7)).decode()}, "valid mask must match"),
        ({"intrinsics": (0, 2, 0, 0), "checksum_sha256": "bad"}, "invalid camera intrinsics"),
        ({"checksum_sha256": "bad"}, "RGB-D checksum mismatch"),
    ],
)
def test_validation_error_precedence(change, message):
    body = wire_payload()
    body.update(change)
    with pytest.raises(ValidationError, match=message):
        observations.RGBDObservation.model_validate(body)


def test_big_endian_adapter_swaps_decoded_storage_only(monkeypatch):
    body = wire_payload()
    swaps = []

    class BigArray:
        itemsize = 4

        def __init__(self, typecode):
            assert typecode == "f"
            self.values = native_array("f")

        def frombytes(self, raw):
            self.values.frombytes(raw)
            self.values.byteswap()  # emulate opposite native float interpretation

        def byteswap(self):
            swaps.append(True)
            self.values.byteswap()

        def __len__(self):
            return len(self.values)

        def __iter__(self):
            return iter(self.values)

    monkeypatch.setattr(observations, "array", BigArray)
    monkeypatch.setattr(observations, "sys", SimpleNamespace(byteorder="big"))
    result = observations.RGBDObservation.model_validate(body)
    assert swaps == [True] and result.valid_mask_bytes() == bytes((0, 0, 1, 1, 1, 1, 1))
    assert result.depth_float32_base64 == body["depth_float32_base64"]
    assert result.checksum_sha256 == independent_checksum(body, result.valid_mask_bytes())


def test_nonfourbyte_array_keeps_original_decoder(monkeypatch):
    class OtherArray:
        itemsize = 8

        def __init__(self, typecode):
            assert typecode == "f"

        def frombytes(self, raw):
            pytest.fail("unsupported native Cfloat must not decode")

    original = observations.struct.iter_unpack
    calls = []

    def unpack(*args):
        calls.append(args)
        return original(*args)

    monkeypatch.setattr(observations, "array", OtherArray)
    monkeypatch.setattr(observations.struct, "iter_unpack", unpack)
    assert observations.RGBDObservation.model_validate(wire_payload()).valid_mask_bytes() == bytes(
        (0, 0, 1, 1, 1, 1, 1)
    )
    with pytest.raises(ValidationError, match="finite nonnegative"):
        observations.RGBDObservation.model_validate(wire_payload((0xFF800000,)))
    assert len(calls) == 2 and all(row[0] == "<f" for row in calls)


def assert_float_tuple(actual, expected):
    assert all(type(v) is float for v in actual)
    assert struct.pack("<" + "d" * len(actual), *actual) == struct.pack(
        "<" + "d" * len(expected), *expected
    )


@pytest.mark.parametrize("dtype", ["<f4", ">f4", "<f8", ">f8"])
@pytest.mark.parametrize("layout", ["contiguous", "strided", "empty"])
def test_supported_float_arrays_equal_scalar_reference(dtype, layout):
    values = np.array(
        [0.0, -0.0, 1e-40, 1.0, np.finfo(np.dtype(dtype)).max, np.inf, -np.inf, np.nan], dtype=dtype
    )
    if layout == "strided":
        values = values[::-2]
    if layout == "empty":
        values = values[:0]
    assert_float_tuple(camera._depth_tuple(values), tuple(float(v) for v in values.ravel()))


@pytest.mark.parametrize(
    "dtype",
    [
        "i1",
        "u1",
        "<i2",
        ">i2",
        "<u2",
        ">u2",
        "<i4",
        ">i4",
        "<u4",
        ">u4",
        "<i8",
        ">i8",
        "<u8",
        ">u8",
    ],
)
@pytest.mark.parametrize("layout", ["contiguous", "strided", "empty"])
def test_supported_integer_arrays_preserve_full_range(dtype, layout):
    limits = np.iinfo(np.dtype(dtype))
    values = np.array([limits.min, 0, limits.max], dtype=dtype)
    if layout == "strided":
        values = values[::-2]
    if layout == "empty":
        values = values[:0]
    result = camera._instance_tuple(values)
    assert result == tuple(int(v) for v in values.ravel())
    assert all(type(v) is int for v in result)


@pytest.mark.parametrize("dtype", [np.float16, np.longdouble, np.bool_])
def test_unsupported_float_scalar_dtypes_keep_reference(dtype):
    values = np.array([0.0, -0.0, 1.0], dtype=dtype)
    assert_float_tuple(camera._depth_tuple(values), tuple(float(v) for v in values.ravel()))


@pytest.mark.parametrize(
    ("helper", "method"), [("_depth_tuple", "__float__"), ("_instance_tuple", "__int__")]
)
@pytest.mark.parametrize("raising", [False, True])
def test_object_conversion_hooks_and_original_exceptions(helper, method, raising):
    calls = []
    fault = ValueError("synthetic conversion failure")

    class Scalar:
        def convert(self):
            calls.append(True)
            if raising:
                raise fault
            return 2.5 if method == "__float__" else 2

    setattr(Scalar, method, Scalar.convert)
    values = np.array([Scalar(), Scalar()], dtype=object)
    if raising:
        with pytest.raises(ValueError) as caught:
            getattr(camera, helper)(values)
        assert caught.value is fault and calls == [True]
    else:
        result = getattr(camera, helper)(values)
        assert calls == [True, True]
        calls.clear()
        reference = tuple((float if method == "__float__" else int)(v) for v in values.ravel())
        assert result == reference and calls == [True, True]


@pytest.mark.parametrize(
    ("helper", "dtype", "converter"),
    [("_depth_tuple", np.float32, float), ("_instance_tuple", np.int32, int)],
)
def test_ndarray_subclass_keeps_original_iteration(helper, dtype, converter):
    calls = []

    class CustomArray(np.ndarray):
        def tolist(self):
            pytest.fail("subclass must keep scalar iteration")

        def __iter__(self):
            calls.append(True)
            return super().__iter__()

    values = np.array([0, 1, 2], dtype=dtype).view(CustomArray)
    assert getattr(camera, helper)(values) == tuple(
        converter(v) for v in np.asarray(values).ravel()
    )
    assert calls == [True]


@pytest.mark.parametrize(
    ("helper", "dtype", "converter"),
    [("_depth_tuple", "c16", float), ("_instance_tuple", "U3", int), ("_instance_tuple", "?", int)],
)
def test_other_conversion_results_or_errors_are_not_broadened(helper, dtype, converter):
    values = np.array([0, 1], dtype=dtype)
    try:
        expected = tuple(converter(v) for v in values.ravel())
    except (ValueError, TypeError, OverflowError) as error:
        with pytest.raises(type(error)):
            getattr(camera, helper)(values)
    else:
        assert getattr(camera, helper)(values) == expected


@pytest.mark.parametrize("instances", [False, True])
@pytest.mark.parametrize("noise", [0.0, 0.001, "invalidate"])
def test_full_fake_capture_preserves_filter_noise_masks_labels_and_sources(instances, noise):
    depth = np.array([[0.0, -0.1, np.nan, np.inf], [9.999, 10.0, 1.0, 2.0]], dtype=np.float32)
    value, data = make_camera(4, 2, depth=depth)
    renderer = value._renderer
    rgb_before = renderer.rgb.copy()
    depth_before = depth.copy()
    seg_before = renderer.segmentation.copy()
    expected = depth.copy()
    valid = np.isfinite(expected) & (expected > 0) & (expected < 10.0)
    if noise == "invalidate":

        class InvalidatingRng:
            def normal(self, *args, **kwargs):
                return np.full(kwargs["size"], -20.0)

        rng = InvalidatingRng()
        sigma = 0.001
        expected[valid] -= 20.0
    else:
        rng = np.random.default_rng(614001)
        sigma = noise
        if sigma:
            expected[valid] += np.random.default_rng(614001).normal(0, sigma, size=int(valid.sum()))
    expected[~valid | (expected <= 0)] = 0
    mask = (np.isfinite(expected) & (expected > 0)).astype(np.uint8).tobytes()
    with (
        patch.object(camera, "datetime", FixedDatetime),
        patch.object(camera, "uuid4", lambda: SimpleNamespace(hex="synthetic614")),
    ):
        frame, ids, labels, hashes = value._capture(
            data,
            rng=rng,
            noise_std_m=sigma,
            scene_id="synthetic-scene",
            episode_id="synthetic-episode",
            include_instances=instances,
        )
    assert_float_tuple(frame.depth, tuple(float(v) for v in expected.ravel()))
    assert frame.valid_mask == mask and frame.rgb == rgb_before.tobytes()
    assert frame.frame_id == "rgbd-synthetic614" and frame.captured_at == STAMP
    assert (frame.width, frame.height, frame.scene_id, frame.episode_id, frame.sim_time_s) == (
        4,
        2,
        "synthetic-scene",
        "synthetic-episode",
        0.0,
    )
    focal = 1 / math.tan(math.radians(50) / 2)
    assert frame.intrinsics == (focal, focal, 1.5, 0.5)
    matrix = (1.0, 0.0, 0.0, 0.35, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0, -1.0, 1.4, 0.0, 0.0, 0.0, 1.0)
    assert frame.camera_to_world == matrix
    expected_calib = hashlib.sha256(
        np.asarray((*frame.intrinsics, *matrix), dtype="<f8").tobytes()
    ).hexdigest()[:16]
    assert frame.calibration_version == expected_calib and frame.latency_ms >= 0
    expected_ids = (
        tuple(int(v) for v in np.where(seg_before[:, :, 1] == 5, seg_before[:, :, 0], -1).ravel())
        if instances
        else ()
    )
    assert ids == expected_ids
    assert labels == (
        {idx: "synthetic-" + str(idx) for idx in set(expected_ids) - {-1}} if instances else {}
    )
    assert hashes == (camera.MuJoCoRGBDCamera._physics_state_hash(data),) * (3 if instances else 2)
    assert renderer.calls == ["rgb", "depth"] + (["segmentation"] if instances else [])
    np.testing.assert_array_equal(depth, depth_before)
    np.testing.assert_array_equal(renderer.rgb, rgb_before)
    np.testing.assert_array_equal(renderer.segmentation, seg_before)


@pytest.mark.parametrize("kind", ["physics", "calibration"])
def test_mutation_during_fake_render_still_rejects_mixed_frame(kind):
    def mutate(renderer):
        if kind == "physics":
            renderer.data.qpos[0] += 1
        else:
            renderer.data.cam_xpos[0, 0] += 0.1

    value, data = make_camera(mutate=mutate)
    with pytest.raises(
        RuntimeError,
        match="physics state changed during RGB render"
        if kind == "physics"
        else "camera calibration changed during capture",
    ):
        capture(value, data)
    assert value._renderer.calls == ["rgb"]
