"""VINS 所选 ROS1 bag 的流式 RGBD 解码；只支持已验证的 none/bz2 容器。"""

from __future__ import annotations

import bz2
import io
import struct
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np

MAGIC = b"#ROSBAG V2.0\n"
RGB_TOPIC = "/camera/color/image_raw"
DEPTH_TOPIC = "/camera/aligned_depth_to_color/image_raw"


def u32(data: bytes, offset: int = 0) -> int:
    return int(struct.unpack_from("<I", data, offset)[0])


def u64(data: bytes, offset: int = 0) -> int:
    return int(struct.unpack_from("<Q", data, offset)[0])


def ros_time(data: bytes, offset: int = 0) -> int:
    seconds, nanoseconds = struct.unpack_from("<II", data, offset)
    if nanoseconds >= 1_000_000_000:
        raise ValueError("ROS timestamp has out-of-range nanoseconds")
    return int(seconds * 1_000_000_000 + nanoseconds)


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
    return bytes(value)


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


def image_message(data: bytes) -> tuple[dict[str, Any], np.ndarray]:
    array: np.ndarray
    message = Message(data)
    result = message.header()
    result.update(height=message.integer(), width=message.integer(), encoding=message.string())
    result["is_bigendian"] = message.take(1)[0]
    result["step"] = message.integer()
    payload = message.take(message.integer())
    message.finish()
    height, width, step = result["height"], result["width"], result["step"]
    if not 0 < height <= 8192 or not 0 < width <= 8192:
        raise ValueError("image dimensions exceed supported bounds")
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


def iter_ros1_images(path: Path) -> Iterator[dict[str, Any]]:
    """逐块读取标准 Image 消息，完全跳过 rgb8 的深度可视化话题。"""
    connections: dict[int, tuple[str, dict[str, bytes]]] = {}

    def consume(header: dict[str, bytes], payload: bytes) -> dict[str, Any] | None:
        op = header["op"]
        if op == b"\x07":
            identifier = u32(header["conn"])
            value = (header["topic"].decode(), fields(payload))
            if identifier in connections and connections[identifier] != value:
                raise ValueError("ROS connection definition changed")
            connections[identifier] = value
        elif op == b"\x02":
            topic, descriptor = connections[u32(header["conn"])]
            if topic not in {RGB_TOPIC, DEPTH_TOPIC}:
                return None
            if descriptor.get("type") != b"sensor_msgs/Image":
                raise ValueError("selected ROS topic must contain sensor_msgs/Image")
            if descriptor.get("md5sum") != b"060021388200f6f0f447d0fcd9c64743":
                raise ValueError("ROS Image schema MD5 mismatch")
            metadata, array = image_message(payload)
            if topic == DEPTH_TOPIC and (array.ndim != 2 or array.dtype != np.uint16):
                raise ValueError("numeric depth topic must contain uint16 depth")
            if topic == RGB_TOPIC and (array.ndim != 3 or array.shape[2] != 3):
                raise ValueError("RGB topic must contain color image")
            return {
                "topic": topic,
                "timestamp_ns": metadata["stamp_ns"],
                "bag_time_ns": ros_time(header["time"]),
                "header": metadata,
                "array": array,
            }
        return None

    try:
        with path.open("rb") as stream:
            if exact_read(stream, len(MAGIC)) != MAGIC:
                raise ValueError("ROS bag v2 magic missing")
            first = True
            while item := record(stream):
                header, payload = item
                if first and header.get("op") != b"\x03":
                    raise ValueError("ROS bag header missing")
                first = False
                if header["op"] == b"\x05":
                    expected = u32(header["size"])
                    if expected > 256 * 1024 * 1024:
                        raise ValueError("ROS expanded chunk size limit exceeded")
                    compression = header["compression"]
                    if compression == b"bz2":
                        decoder = bz2.BZ2Decompressor()
                        expanded = decoder.decompress(payload, max_length=expected + 1)
                        if not decoder.eof or decoder.unused_data:
                            raise ValueError("ROS bz2 chunk truncated or size limit exceeded")
                    elif compression == b"none":
                        expanded = payload
                    else:
                        raise ValueError("selected ROS reader supports only none/bz2 compression")
                    if len(expanded) != expected:
                        raise ValueError("ROS expanded chunk size mismatch")
                    chunk = io.BytesIO(expanded)
                    while inner := record(chunk):
                        if inner[0]["op"] not in {b"\x02", b"\x07"}:
                            raise ValueError("unsupported nested ROS record")
                        message = consume(*inner)
                        if message is not None:
                            yield message
                else:
                    message = consume(header, payload)
                    if message is not None:
                        yield message
    except (struct.error, KeyError, UnicodeError, EOFError) as exc:
        raise ValueError("malformed ROS bag record") from exc
