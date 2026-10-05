"""使用原生编码小夹具验证转换，不依赖 ROS、MongoDB 或网络。"""

import bz2
import hashlib
import io
import json
import struct
import zlib

import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.datasets.external.loaders import read_sample
from cloud_edge_robot_arm.datasets.external.provider import DatasetObservationProvider


def png(array):
    out = io.BytesIO()
    Image.fromarray(array).save(out, format="PNG")
    return out.getvalue()


def vi(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result + bytes([value]))


def pb(number, value):
    if isinstance(value, str):
        value = value.encode()
    return (
        vi(number << 3) + vi(value)
        if isinstance(value, int)
        else vi(number << 3 | 2) + vi(len(value)) + value
    )


def mstring(value):
    value = value.encode()
    return struct.pack("<I", len(value)) + value


def mr(op, payload):
    return struct.pack("<BQ", op, len(payload)) + payload


def mcap_fixture(path, *, compression="", bad_crc=False):
    types = {
        "Image": [("format", 9, False), ("data", 12, False)],
        "Info": [("width", 13, False), ("height", 13, False), ("K", 1, True)],
        "Unit": [("unit_in_mm", 1, False)],
    }
    messages = []
    for name, fields in types.items():
        desc = pb(1, name)
        for index, (key, kind, repeated) in enumerate(fields, 1):
            desc += pb(2, pb(1, key) + pb(3, index) + pb(4, 3 if repeated else 1) + pb(5, kind))
        messages.append(pb(4, desc))
    descriptor = pb(1, pb(2, "fixture") + b"".join(messages))
    topics = [
        (
            "/camera/color/info",
            "Info",
            pb(1, 3) + pb(2, 2) + pb(3, struct.pack("<9d", 2, 0, 1, 0, 2, 1, 0, 0, 1)),
        ),
        (
            "/camera/depth/info",
            "Info",
            pb(1, 2) + pb(2, 2) + pb(3, struct.pack("<9d", 2, 0, 1, 0, 2, 1, 0, 0, 1)),
        ),
        ("/camera/depth/unit_of_depth_in_mm", "Unit", vi(9) + struct.pack("<d", 1.0)),
        (
            "/camera/color/image",
            "Image",
            pb(1, "png") + pb(2, png(np.full((2, 3, 3), 70, np.uint8))),
        ),
        (
            "/camera/depth/image",
            "Image",
            pb(1, "png") + pb(2, png(np.full((2, 2), 1500, np.uint16))),
        ),
    ]
    inner = b""
    for number, (topic, name, payload) in enumerate(topics, 1):
        inner += mr(
            3,
            struct.pack("<H", number)
            + mstring("fixture." + name)
            + mstring("protobuf")
            + struct.pack("<I", len(descriptor))
            + descriptor,
        )
        inner += mr(
            4,
            struct.pack("<HH", number, number)
            + mstring(topic)
            + mstring("protobuf")
            + struct.pack("<I", 0),
        )
        inner += mr(5, struct.pack("<HIQQ", number, 0, 1000000000 + number * 1000000, 0) + payload)
    if compression == "zstd":
        from backports import zstd

        encoded = zstd.compress(inner)
    else:
        encoded = inner
    crc = (zlib.crc32(inner) + int(bad_crc)) & 0xFFFFFFFF
    chunk = struct.pack("<QQQI", 1000000000, 1010000000, len(inner), crc)
    chunk += mstring(compression) + struct.pack("<Q", len(encoded)) + encoded
    magic = b"\x89MCAP0\r\n"
    path.write_bytes(
        magic
        + mr(1, mstring("") + mstring("fixture"))
        + mr(6, chunk)
        + mr(15, struct.pack("<I", 0))
        + mr(2, struct.pack("<QQI", 0, 0, 0))
        + magic
    )


def ros_fields(values):
    out = b""
    for key, value in values.items():
        raw = key.encode() + b"=" + value
        out += struct.pack("<I", len(raw)) + raw
    return out


def ros_record(values, data):
    header = ros_fields(values)
    return struct.pack("<I", len(header)) + header + struct.pack("<I", len(data)) + data


def ros_image(stamp, array, encoding):
    h, w = array.shape[:2]
    return (
        struct.pack("<III", stamp, 1, stamp)
        + mstring("camera")
        + struct.pack("<II", h, w)
        + mstring(encoding)
        + bytes([0])
        + struct.pack("<II", array.strides[0], array.nbytes)
        + array.tobytes()
    )


def bag_fixture(path, *, wrong_depth=False, compression="bz2"):
    topics = [
        ("/camera/color/image_raw", "rgb8"),
        ("/camera/aligned_depth_to_color/image_raw", "rgb8" if wrong_depth else "16UC1"),
        ("/camera/depth/image_rect_raw", "rgb8"),
    ]
    inner = b""
    for conn, (topic, encoding) in enumerate(topics):
        inner += ros_record(
            {"op": b"\x07", "conn": struct.pack("<I", conn), "topic": topic.encode()},
            ros_fields(
                {"type": b"sensor_msgs/Image", "md5sum": b"060021388200f6f0f447d0fcd9c64743"}
            ),
        )
        for stamp in [10, 20] if conn == 0 else [10]:
            array = (
                np.full((2, 3, 3), 80, np.uint8)
                if encoding == "rgb8"
                else np.full((2, 3), 1500, np.uint16)
            )
            inner += ros_record(
                {
                    "op": b"\x02",
                    "conn": struct.pack("<I", conn),
                    "time": struct.pack("<II", 2, stamp),
                },
                ros_image(stamp, array, encoding),
            )
    compressed = bz2.compress(inner) if compression == "bz2" else inner
    path.write_bytes(
        b"#ROSBAG V2.0\n"
        + ros_record({"op": b"\x03"}, b"")
        + ros_record(
            {
                "op": b"\x05",
                "compression": compression.encode(),
                "size": struct.pack("<I", len(inner)),
            },
            compressed,
        )
    )


def simple_plan(dataset, path):
    return dict(
        dataset_id=dataset,
        revision="fixture-pinned",
        minimum_free_bytes=0,
        files=[
            dict(
                path=path.name,
                size=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        ],
        reader_metadata={},
    )


@pytest.mark.parametrize("compression", ["", "zstd"])
def test_mcap_embedded_protobuf_and_native_sizes(tmp_path, compression):
    from cloud_edge_robot_arm.datasets.external.native_sources import convert_microagi

    path = tmp_path / "sample.mcap"
    mcap_fixture(path, compression=compression)
    refs, report = convert_microagi(
        simple_plan("microagi01_small", path), tmp_path, tmp_path / "out"
    )
    sample = read_sample(refs[0])
    assert len(refs) == 1 and report["pairing"]["max_delta_ns"] == 1000000
    assert sample.rgb.shape == (2, 3, 3) and sample.depth_raw.shape == (2, 2)
    assert sample.depth_m[0, 0] == pytest.approx(1.5) and sample.K_depth[0, 0] == 2
    assert sample.rgb_depth_aligned is False and sample.temporal_alignment is None
    assert sample.timestamp == 1004000000 and sample.time_basis == "mcap_log_time_ns"
    assert sample.action is None and sample.official_split is None
    assert DatasetObservationProvider(refs).next_observation()["acquisition_time_unknown"] is True


def test_mcap_corrupt_crc_fails(tmp_path):
    from cloud_edge_robot_arm.datasets.external.mcap_native import iter_mcap_messages

    path = tmp_path / "bad.mcap"
    mcap_fixture(path, bad_crc=True)
    with pytest.raises(ValueError, match="CRC"):
        list(iter_mcap_messages(path))


def test_mcap_resource_limit_is_checked_before_decompression(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.datasets.external import mcap_native

    path = tmp_path / "bounded.mcap"
    mcap_fixture(path, compression="zstd")
    monkeypatch.setattr(mcap_native, "MAX_CHUNK_BYTES", 32)
    with pytest.raises(ValueError, match="size limit"):
        list(mcap_native.iter_mcap_messages(path))


def test_ros_bz2_truncation_cannot_produce_accepted_images(tmp_path):
    from cloud_edge_robot_arm.datasets.external.rosbag_native import iter_ros1_images

    path = tmp_path / "truncated.bag"
    bag_fixture(path)
    path.write_bytes(path.read_bytes()[:-10])
    with pytest.raises(ValueError, match="Truncated|truncated"):
        list(iter_ros1_images(path))


@pytest.mark.parametrize("compression", ["bz2", "none"])
def test_ros_numeric_depth_exact_header_pair_and_unmatched_frame(tmp_path, compression):
    from cloud_edge_robot_arm.datasets.external.native_sources import convert_vins

    path = tmp_path / "Normal.bag"
    bag_fixture(path, compression=compression)
    refs, report = convert_vins(simple_plan("vins_rgbd_small", path), tmp_path, tmp_path / "out")
    sample = read_sample(refs[0])
    assert len(refs) == 1 and report["pairing"]["unpaired_rgb"] == [1]
    assert sample.timestamp == 1000000010 and sample.time_basis == "ros_header_stamp_ns"
    assert sample.metadata["rgb_bag_time_ns"] == 2000000010
    assert sample.depth_m is None and sample.K_rgb is None
    assert sample.depth_raw.dtype == np.uint16 and sample.temporal_alignment is True
    assert sample.rgb_depth_aligned is None and sample.action is None
    assert refs[0]["episode_length"] == 2


def test_ros_visualization_on_numeric_topic_is_rejected(tmp_path):
    from cloud_edge_robot_arm.datasets.external.native_sources import convert_vins

    path = tmp_path / "bad.bag"
    bag_fixture(path, wrong_depth=True)
    with pytest.raises(ValueError, match="numeric|uint16"):
        convert_vins(simple_plan("vins_rgbd_small", path), tmp_path, tmp_path / "out")


def test_industry_keeps_source_test_intrinsics_pose_and_raw_depth(tmp_path):
    from cloud_edge_robot_arm.datasets.external.native_sources import convert_industry

    (tmp_path / "rgb.png").write_bytes(png(np.full((2, 3, 3), 80, np.uint8)))
    (tmp_path / "depth.png").write_bytes(
        png(np.array([[1000, 0, 65535], [300, 600, 900]], np.uint16))
    )
    record = dict(
        filepath="rgb.png",
        depth={"map_path": "depth.png"},
        dataset_subset="classic",
        split="test",
        scene_id="000001",
        image_id="000004",
        depth_scale=1,
        camera_intrinsics=[[2, 0, 1], [0, 2, 1], [0, 0, 1]],
        metadata={"height": 2, "width": 3},
        ground_truth={
            "detections": [
                dict(obj_id=1, rotation_matrix=np.eye(3).tolist(), translation_mm=[10, 20, 500])
            ]
        },
    )
    path = tmp_path / "samples.json"
    path.write_text(json.dumps({"samples": [record]}))
    plan = simple_plan("industryshapes_real", path)
    for name in ("rgb.png", "depth.png"):
        plan["files"].extend(simple_plan("industryshapes_real", tmp_path / name)["files"])
    refs, report = convert_industry(plan, tmp_path, tmp_path / "out")
    sample = read_sample(refs[0])
    assert report["instances"] == 1 and sample.official_split == "test"
    assert sample.frame_index == 4 and sample.timestamp is None
    assert sample.K_rgb[0, 0] == 2 and sample.K_depth is None
    assert sample.depth_m[0, 0] == 1.0 and sample.depth_raw[0, 2] == 65535
    assert not sample.depth_valid_mask[0, 2] and not sample.capabilities["camera_geometry"]
    pose = sample.annotations["instances"][0]["model_to_camera"]
    assert pose["matrix"][2][3] == 0.5 and "annotations" not in sample.model_input()
