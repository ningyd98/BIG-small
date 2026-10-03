"""Offline ROS1 bag v2 integrity and RGB-D verification, with no ROS dependency.

This verifies every record, compressed chunk, per-connection chunk index, and
chunk-info count. It only deserializes standard sensor_msgs Image/CameraInfo
messages and does not infer missing calibration or timestamps.
"""

from __future__ import annotations

import argparse
import bz2
import collections
import ctypes
import ctypes.util
import hashlib
import io
import json
import os
import struct
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

MAGIC = b"#ROSBAG V2.0\n"


def u32(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def u64(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def ros_time(data: bytes, offset: int = 0) -> int:
    seconds, nanoseconds = struct.unpack_from("<II", data, offset)
    if nanoseconds >= 1_000_000_000:
        raise ValueError("ROS timestamp has out-of-range nanoseconds")
    return seconds * 1_000_000_000 + nanoseconds


def fields(data: bytes) -> dict[str, bytes]:
    output = {}
    cursor = 0
    while cursor < len(data):
        if cursor + 4 > len(data):
            raise ValueError("Truncated field-length word")
        size = u32(data, cursor)
        cursor += 4
        if cursor + size > len(data):
            raise ValueError("Truncated header field")
        key, value = data[cursor : cursor + size].split(b"=", 1)
        cursor += size
        name = key.decode("ascii")
        if name in output:
            raise ValueError(f"Duplicate header field: {name}")
        output[name] = value
    return output


def exact_read(stream: Any, size: int) -> bytes:
    value = stream.read(size)
    if len(value) != size:
        raise ValueError(f"Truncated record: expected {size}, got {len(value)}")
    return value


def record(stream: Any) -> tuple[dict[str, bytes], bytes] | None:
    word = stream.read(4)
    if not word:
        return None
    if len(word) != 4:
        raise ValueError("Truncated header-length word")
    header_size = u32(word)
    if header_size > 16 * 1024 * 1024:
        raise ValueError("Unreasonable bag header size")
    header = fields(exact_read(stream, header_size))
    data_size = u32(exact_read(stream, 4))
    if data_size > 256 * 1024 * 1024:
        raise ValueError("Chunk exceeds this verifier's 256 MiB safety limit")
    return header, exact_read(stream, data_size)


class Lz4Frames:
    """Bounded liblz4 frame decoder (ROS lz4 bag chunks use LZ4 frames)."""

    def __init__(self) -> None:
        library_path = ctypes.util.find_library("lz4")
        if not library_path:
            raise RuntimeError("lz4-compressed bag needs system liblz4")
        self.library = ctypes.CDLL(library_path)
        self.library.LZ4F_createDecompressionContext.argtypes = [
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_uint,
        ]
        self.library.LZ4F_createDecompressionContext.restype = ctypes.c_size_t
        self.library.LZ4F_freeDecompressionContext.argtypes = [ctypes.c_void_p]
        self.library.LZ4F_decompress.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_void_p,
        ]
        self.library.LZ4F_decompress.restype = ctypes.c_size_t
        self.library.LZ4F_isError.argtypes = [ctypes.c_size_t]
        self.library.LZ4F_isError.restype = ctypes.c_uint
        self.library.LZ4F_getErrorName.argtypes = [ctypes.c_size_t]
        self.library.LZ4F_getErrorName.restype = ctypes.c_char_p

    def check(self, result: int) -> None:
        if self.library.LZ4F_isError(result):
            raise ValueError(self.library.LZ4F_getErrorName(result).decode())

    def decode(self, data: bytes, expected_size: int) -> bytes:
        context = ctypes.c_void_p()
        self.check(self.library.LZ4F_createDecompressionContext(ctypes.byref(context), 100))
        source = ctypes.create_string_buffer(data)
        destination = ctypes.create_string_buffer(expected_size + 1)
        source_offset = 0
        target_offset = 0
        try:
            while True:
                source_size = ctypes.c_size_t(len(data) - source_offset)
                target_size = ctypes.c_size_t(expected_size + 1 - target_offset)
                result = self.library.LZ4F_decompress(
                    context,
                    ctypes.byref(destination, target_offset),
                    ctypes.byref(target_size),
                    ctypes.byref(source, source_offset),
                    ctypes.byref(source_size),
                    None,
                )
                self.check(result)
                source_offset += source_size.value
                target_offset += target_size.value
                if result == 0:
                    break
                if not source_size.value and not target_size.value:
                    raise ValueError("Truncated or stalled LZ4 chunk")
                if target_offset > expected_size or source_offset >= len(data):
                    raise ValueError("LZ4 chunk size mismatch or truncation")
            if source_offset != len(data) or target_offset != expected_size:
                raise ValueError("LZ4 frame contains trailing data or wrong output size")
            return destination.raw[:target_offset]
        finally:
            self.library.LZ4F_freeDecompressionContext(context)


class Message:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.cursor = 0

    def take(self, size: int) -> bytes:
        if self.cursor + size > len(self.data):
            raise ValueError("Truncated ROS message")
        value = self.data[self.cursor : self.cursor + size]
        self.cursor += size
        return value

    def integer(self) -> int:
        return u32(self.take(4))

    def string(self) -> str:
        return self.take(self.integer()).decode("utf-8")

    def header(self) -> dict[str, Any]:
        return {
            "seq": self.integer(),
            "stamp_ns": ros_time(self.take(8)),
            "frame_id": self.string(),
        }

    def doubles(self, count: int) -> list[float]:
        return list(struct.unpack(f"<{count}d", self.take(count * 8)))

    def finish(self) -> None:
        if self.cursor != len(self.data):
            raise ValueError("Trailing bytes in standard ROS message")


def camera_info(data: bytes) -> dict[str, Any]:
    message = Message(data)
    result = message.header()
    result.update(
        height=message.integer(),
        width=message.integer(),
        distortion_model=message.string(),
        D=message.doubles(message.integer()),
        K=message.doubles(9),
        R=message.doubles(9),
        P=message.doubles(12),
        binning_x=message.integer(),
        binning_y=message.integer(),
    )
    result["roi"] = {
        name: message.integer() for name in ("x_offset", "y_offset", "height", "width")
    }
    result["roi"]["do_rectify"] = bool(message.take(1)[0])
    message.finish()
    return result


def image_message(data: bytes) -> tuple[dict[str, Any], np.ndarray]:
    message = Message(data)
    result = message.header()
    result.update(height=message.integer(), width=message.integer(), encoding=message.string())
    result["is_bigendian"] = message.take(1)[0]
    result["step"] = message.integer()
    payload = message.take(message.integer())
    message.finish()
    height, width, step = result["height"], result["width"], result["step"]
    if len(payload) != height * step:
        raise ValueError("sensor_msgs/Image payload length disagrees with height/step")
    encoding = result["encoding"]
    if encoding in ("16UC1", "mono16"):
        dtype = np.dtype(">u2" if result["is_bigendian"] else "<u2")
        if step < width * 2 or step % 2:
            raise ValueError("Invalid uint16 image row stride")
        array = np.frombuffer(payload, dtype=dtype).reshape(height, step // 2)[:, :width]
        return result, array.astype(np.uint16, copy=False)
    channels = {"rgb8": 3, "bgr8": 3, "rgba8": 4, "bgra8": 4, "mono8": 1}.get(encoding)
    if channels is None:
        raise ValueError(f"Unsupported image encoding: {encoding}")
    if step < width * channels:
        raise ValueError("Invalid color image row stride")
    rows = np.frombuffer(payload, dtype=np.uint8).reshape(height, step)
    array = rows[:, : width * channels].reshape(height, width, channels)
    if encoding in ("bgr8", "bgra8"):
        array = array[..., [2, 1, 0]]
    if channels == 4:
        array = array[..., :3]
    if channels == 1:
        array = array[..., 0]
    return result, array


def compressed_image(data: bytes) -> tuple[dict[str, Any], np.ndarray]:
    message = Message(data)
    result = message.header()
    result["format"] = message.string()
    payload = message.take(message.integer())
    message.finish()
    with Image.open(io.BytesIO(payload)) as image:
        array = np.asarray(image)
    result.update(height=int(array.shape[0]), width=int(array.shape[1]), encoding="compressed")
    return result, array


def verify(path: Path, output: Path) -> dict[str, Any]:
    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)
    connections: dict[int, dict[str, Any]] = {}
    chunks: dict[int, dict[str, Any]] = {}
    topic_counts: collections.Counter[str] = collections.Counter()
    compression_counts: collections.Counter[str] = collections.Counter()
    top_counts: collections.Counter[int] = collections.Counter()
    infos: dict[str, dict[str, Any]] = {}
    images: dict[str, list[tuple[dict[str, Any], np.ndarray]]] = collections.defaultdict(list)
    skipped_image_encodings: collections.Counter[str] = collections.Counter()
    record_boundaries = set()
    bag_header = None
    last_chunk = None
    lz4 = None
    message_count = 0

    def add_connection(header: dict[str, bytes], data: bytes) -> None:
        identifier = u32(header["conn"])
        metadata = fields(data)
        descriptor = {
            "id": identifier,
            "topic": header["topic"].decode(),
            "type": metadata["type"].decode(),
            "md5sum": metadata["md5sum"].decode(),
            "message_definition_sha256": hashlib.sha256(metadata["message_definition"]).hexdigest(),
        }
        if identifier in connections and connections[identifier] != descriptor:
            raise ValueError(f"Connection definition changed for {identifier}")
        connections[identifier] = descriptor

    def add_message(header: dict[str, bytes], data: bytes) -> None:
        nonlocal message_count
        identifier = u32(header["conn"])
        descriptor = connections[identifier]
        topic = descriptor["topic"]
        topic_counts[topic] += 1
        message_count += 1
        if descriptor["type"] == "sensor_msgs/CameraInfo" and topic not in infos:
            infos[topic] = camera_info(data)
        if descriptor["type"] not in ("sensor_msgs/Image", "sensor_msgs/CompressedImage"):
            return
        if len(images[topic]) >= 8:
            return
        try:
            parser = (
                image_message if descriptor["type"] == "sensor_msgs/Image" else compressed_image
            )
            metadata, array = parser(data)
        except ValueError as exc:
            if "Unsupported image encoding" not in str(exc):
                raise
            skipped_image_encodings[str(exc)] += 1
            return
        metadata["bag_stamp_ns"] = ros_time(header["time"])
        images[topic].append((metadata, array.copy()))

    with path.open("rb") as stream:
        if exact_read(stream, len(MAGIC)) != MAGIC:
            raise ValueError("Not a ROS bag v2 file")
        while True:
            position = stream.tell()
            value = record(stream)
            if value is None:
                break
            record_boundaries.add(position)
            header, data = value
            operation = header["op"][0]
            top_counts[operation] += 1
            if operation == 3:
                if bag_header is not None or position != len(MAGIC):
                    raise ValueError("Unexpected duplicate or misplaced bag header")
                bag_header = {
                    "index_pos": u64(header["index_pos"]),
                    "conn_count": u32(header["conn_count"]),
                    "chunk_count": u32(header["chunk_count"]),
                }
            elif operation == 7:
                add_connection(header, data)
            elif operation == 5:
                compression = header["compression"].decode()
                size = u32(header["size"])
                if size > 256 * 1024 * 1024:
                    raise ValueError("Declared chunk size exceeds memory limit")
                if compression == "none":
                    uncompressed = data
                elif compression == "bz2":
                    uncompressed = bz2.decompress(data)
                elif compression == "lz4":
                    if lz4 is None:
                        lz4 = Lz4Frames()
                    uncompressed = lz4.decode(data, size)
                else:
                    raise ValueError(f"Unsupported compression: {compression}")
                if len(uncompressed) != size:
                    raise ValueError("Uncompressed chunk size mismatch")
                compression_counts[compression] += 1
                nested = io.BytesIO(uncompressed)
                index_rows: dict[int, list[tuple[int, int]]] = collections.defaultdict(list)
                times = []
                while nested.tell() < size:
                    offset = nested.tell()
                    child = record(nested)
                    if child is None:
                        raise ValueError("Premature chunk EOF")
                    child_header, child_data = child
                    child_operation = child_header["op"][0]
                    if child_operation == 7:
                        add_connection(child_header, child_data)
                    elif child_operation == 2:
                        stamp = ros_time(child_header["time"])
                        index_rows[u32(child_header["conn"])].append((stamp, offset))
                        times.append(stamp)
                        add_message(child_header, child_data)
                    else:
                        raise ValueError(f"Unexpected chunk record operation {child_operation}")
                chunks[position] = {
                    "rows": dict(index_rows),
                    "indexed": set(),
                    "info_verified": False,
                    "start_time_ns": min(times) if times else None,
                    "end_time_ns": max(times) if times else None,
                }
                last_chunk = position
            elif operation == 4:
                if last_chunk is None or u32(header["ver"]) != 1:
                    raise ValueError("Unexpected index-data version/position")
                count = u32(header["count"])
                identifier = u32(header["conn"])
                if len(data) != count * 12:
                    raise ValueError("Index-data payload length mismatch")
                rows = [(ros_time(data, i * 12), u32(data, i * 12 + 8)) for i in range(count)]
                chunk = chunks[last_chunk]
                expected = chunk["rows"].get(identifier, [])
                if sorted(rows) != sorted(expected) or identifier in chunk["indexed"]:
                    raise ValueError("Chunk message index mismatch or duplicate")
                chunk["indexed"].add(identifier)
            elif operation == 6:
                if u32(header["ver"]) != 1:
                    raise ValueError("Unexpected chunk-info version")
                chunk = chunks[u64(header["chunk_pos"])]
                count = u32(header["count"])
                if len(data) != count * 8:
                    raise ValueError("Chunk-info payload length mismatch")
                counts = {u32(data, i * 8): u32(data, i * 8 + 4) for i in range(count)}
                if counts != {identifier: len(rows) for identifier, rows in chunk["rows"].items()}:
                    raise ValueError("Chunk-info connection counts disagree with actual messages")
                if chunk["info_verified"]:
                    raise ValueError("Duplicate chunk-info")
                if chunk["start_time_ns"] is not None and (
                    ros_time(header["start_time"]) != chunk["start_time_ns"]
                    or ros_time(header["end_time"]) != chunk["end_time_ns"]
                ):
                    raise ValueError("Chunk-info time range disagrees with actual messages")
                chunk["info_verified"] = True
            else:
                raise ValueError(f"Unexpected top-level record operation {operation}")
    if bag_header is None:
        raise ValueError("Missing bag header")
    if bag_header["conn_count"] != len(connections) or bag_header["chunk_count"] != len(chunks):
        raise ValueError("Bag-header counts disagree with complete file")
    if bag_header["index_pos"] not in record_boundaries:
        raise ValueError("Bag index_pos does not point to a record boundary")
    for chunk in chunks.values():
        if chunk["indexed"] != set(chunk["rows"]) or not chunk["info_verified"]:
            raise ValueError("Missing chunk message index or chunk-info")
    with path.open("rb") as stream:
        sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
    sampled_images = []
    depth_choices = []
    color_choices = []
    for topic, samples in images.items():
        metadata, array = samples[0]
        sampled_images.append(
            {"topic": topic, **metadata, "shape": list(array.shape), "dtype": str(array.dtype)}
        )
        for metadata, array in samples:
            if array.ndim == 2 and array.dtype == np.uint16:
                depth_choices.append((topic, metadata, array))
            elif array.ndim == 3 and array.dtype == np.uint8 and array.shape[2] == 3:
                color_choices.append((topic, metadata, array))
    pair = None
    if depth_choices and color_choices:
        # Some bags store colorized depth as rgb8 as well as actual RGB. Prefer
        # explicit camera/color or camera/rgb topics and the standard aligned
        # numeric depth topic. The encoding alone does not establish modality.
        def color_rank(topic: str) -> int:
            if "/color/" in topic or "/rgb/" in topic:
                return 0
            return 2 if "depth" in topic.lower() else 1

        def depth_rank(topic: str) -> int:
            if "/aligned_depth_to_color/" in topic:
                return 0
            return 2 if "colorizer" in topic.lower() else 1

        depth, color = min(
            ((depth, color) for depth in depth_choices for color in color_choices),
            key=lambda item: (
                color_rank(item[1][0]),
                depth_rank(item[0][0]),
                abs(item[0][1]["stamp_ns"] - item[1][1]["stamp_ns"]),
            ),
        )
        depth_topic, depth_meta, depth_array = depth
        color_topic, color_meta, color_array = color
        Image.fromarray(color_array).save(output / "rgb.png")
        Image.fromarray(depth_array).save(output / "depth_uint16.png")
        np.save(output / "depth_uint16.npy", depth_array, allow_pickle=False)
        positive = depth_array[depth_array > 0]
        if not len(positive):
            raise ValueError("Extracted depth frame contains no positive numeric depth")
        lo, hi = np.percentile(positive, [2, 98])
        view = np.clip((depth_array.astype(float) - lo) / max(hi - lo, 1), 0, 1)
        view[depth_array == 0] = 0
        Image.fromarray(np.uint8(view * 255)).save(output / "depth_preview.png")
        pair = {
            "rgb_topic": color_topic,
            "depth_topic": depth_topic,
            "rgb": color_meta,
            "depth": depth_meta,
            "timestamp_difference_ns": abs(depth_meta["stamp_ns"] - color_meta["stamp_ns"]),
            "rgb_shape": list(color_array.shape),
            "depth_shape": list(depth_array.shape),
            "depth_dtype": str(depth_array.dtype),
            "depth_nonzero_ratio": float(np.count_nonzero(depth_array) / depth_array.size),
            "depth_positive_min": int(positive.min()),
            "depth_positive_max": int(positive.max()),
            "depth_positive_percentiles_1_50_99": np.percentile(positive, [1, 50, 99]).tolist(),
            "depth_units": (
                "not inferred from numeric array; consult source calibration/documentation"
            ),
            "rgb_path": str(output / "rgb.png"),
            "numeric_depth_png_path": str(output / "depth_uint16.png"),
            "numeric_depth_npy_path": str(output / "depth_uint16.npy"),
            "depth_preview_path": str(output / "depth_preview.png"),
        }
    return {
        "status": "PASS" if pair else "BAG_INTEGRITY_PASS_RGBD_EXTRACTION_UNAVAILABLE",
        "source_file": str(path.resolve()),
        "size_bytes": path.stat().st_size,
        "sha256": sha256,
        "sha256_scope": "computed locally over complete file; no publisher checksum available",
        "bag_header": bag_header,
        "verified_chunk_count": len(chunks),
        "compression_counts": dict(compression_counts),
        "top_record_counts": dict(top_counts),
        "total_message_count": message_count,
        "topics": [
            {**connection, "message_count": topic_counts[connection["topic"]]}
            for connection in sorted(connections.values(), key=lambda item: item["id"])
        ],
        "camera_info": infos,
        "camera_info_available_in_bag": bool(infos),
        "sampled_image_topics": sampled_images,
        "unsupported_image_encodings": dict(skipped_image_encodings),
        "rgbd_pair": pair,
        "calibration_policy": "CameraInfo only when present; no fabricated K/extrinsics",
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.bag, args.output)
    except Exception as exc:
        result = {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        raise
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
