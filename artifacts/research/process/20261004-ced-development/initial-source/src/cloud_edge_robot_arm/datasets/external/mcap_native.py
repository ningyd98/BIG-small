"""已选 MicroAGI01 MCAP 的受限离线解码；使用容器内嵌 protobuf 描述符。"""

from __future__ import annotations

import struct
import zlib
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

MAGIC = b"\x89MCAP0\r\n"
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_CHUNK_BYTES = 128 * 1024 * 1024


def varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(data) and shift < 70:
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
        shift += 7
    raise ValueError("truncated or invalid protobuf varint")


def wire_fields(data: bytes) -> list[tuple[int, int, Any]]:
    result: list[tuple[int, int, Any]] = []
    value: Any
    offset = 0
    while offset < len(data):
        tag, offset = varint(data, offset)
        number, wire = tag >> 3, tag & 7
        if number == 0:
            raise ValueError("invalid protobuf field number")
        if wire == 0:
            value, offset = varint(data, offset)
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            value = data[offset : offset + size]
            if len(value) != size:
                raise ValueError("truncated fixed-width protobuf value")
            offset += size
        elif wire == 2:
            size, offset = varint(data, offset)
            value = data[offset : offset + size]
            if len(value) != size:
                raise ValueError("truncated protobuf bytes")
            offset += size
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")
        if len(result) >= 100000:
            raise ValueError("protobuf field count limit exceeded")
        result.append((number, wire, value))
    return result


def descriptor_fields(data: bytes) -> dict[int, list[Any]]:
    result: dict[int, list[Any]] = {}
    for number, _, value in wire_fields(data):
        result.setdefault(number, []).append(value)
    return result


def descriptor_messages(data: bytes) -> dict[str, dict[int, dict[str, Any]]]:
    messages: dict[str, dict[int, dict[str, Any]]] = {}

    def add_message(raw: bytes, prefix: str, level: int = 0) -> None:
        if level > 32:
            raise ValueError("protobuf descriptor nesting limit exceeded")
        message = descriptor_fields(raw)
        name = prefix + message[1][0].decode()
        fields = {}
        for raw_field in message.get(2, []):
            field = descriptor_fields(raw_field)
            fields[field[3][0]] = {
                "name": field[1][0].decode(),
                "type": field[5][0],
                "repeated": field.get(4, [1])[0] == 3,
                "type_name": field.get(6, [b""])[0].decode().lstrip("."),
            }
        messages[name] = fields
        for nested in message.get(3, []):
            add_message(nested, name + ".", level + 1)

    for raw_file in descriptor_fields(data).get(1, []):
        file_descriptor = descriptor_fields(raw_file)
        package = file_descriptor.get(2, [b""])[0].decode()
        prefix = package + "." if package else ""
        for raw_message in file_descriptor.get(4, []):
            add_message(raw_message, prefix)
    return messages


def scalar(field_type: int, wire: int, raw: Any) -> Any:
    if field_type == 1:
        return struct.unpack("<d", raw)[0]
    if field_type == 2:
        return struct.unpack("<f", raw)[0]
    if field_type == 9:
        return raw.decode()
    if field_type == 12:
        return raw
    if field_type == 8:
        return bool(raw)
    if wire == 0:
        if field_type in (17, 18):
            return (raw >> 1) ^ -(raw & 1)
        if field_type in (3, 5) and raw >= (1 << 63):
            return raw - (1 << 64)
        return raw
    if field_type in (6, 16):
        return struct.unpack("<q" if field_type == 16 else "<Q", raw)[0]
    if field_type in (7, 15):
        return struct.unpack("<i" if field_type == 15 else "<I", raw)[0]
    raise ValueError(f"unsupported scalar protobuf field {field_type}/{wire}")


def decode_message(
    data: bytes, name: str, descriptors: dict[str, dict[int, dict[str, Any]]], level: int = 0
) -> dict[str, Any]:
    if level > 32:
        raise ValueError("protobuf message nesting limit exceeded")
    fields = descriptors[name]
    result: dict[str, Any] = {}
    for number, wire, raw in wire_fields(data):
        field = fields.get(number)
        if field is None:
            continue
        field_type = field["type"]
        values = []
        if field_type == 11:
            values = [decode_message(raw, field["type_name"], descriptors, level + 1)]
        elif field["repeated"] and wire == 2 and field_type not in (9, 12):
            if field_type in (1, 6, 16):
                size, packed_wire = 8, 1
            elif field_type in (2, 7, 15):
                size, packed_wire = 4, 5
            else:
                size, packed_wire = 0, 0
            offset = 0
            while offset < len(raw):
                if size:
                    part = raw[offset : offset + size]
                    offset += size
                else:
                    part, offset = varint(raw, offset)
                values.append(scalar(field_type, packed_wire, part))
        else:
            values = [scalar(field_type, wire, raw)]
        if field["repeated"]:
            result.setdefault(field["name"], []).extend(values)
        else:
            result[field["name"]] = values[0]
    return result


def string_at(data: bytes, offset: int) -> tuple[str, int]:
    size = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    value = data[offset : offset + size]
    if len(value) != size:
        raise ValueError("truncated MCAP string")
    return value.decode(), offset + size


def records(
    data: bytes, start: int = 0, end: int | None = None
) -> Iterator[tuple[int, int, bytes, int]]:
    end = len(data) if end is None else end
    offset = start
    while offset < end:
        if offset + 9 > end:
            raise ValueError(f"truncated MCAP record header at {offset}")
        opcode, size = struct.unpack_from("<BQ", data, offset)
        next_offset = offset + 9 + size
        if size > MAX_CHUNK_BYTES:
            raise ValueError("MCAP record size limit exceeded")
        if next_offset > end:
            raise ValueError(f"truncated MCAP record {opcode} at {offset}")
        yield offset, opcode, data[offset + 9 : next_offset], next_offset
        offset = next_offset


def iter_mcap_messages(path: Path) -> Iterator[dict[str, Any]]:
    """只消费数据区消息；检查所有边界、非零 CRC 和解压资源上限。"""
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("selected MCAP exceeds 128 MiB file limit")
    data = path.read_bytes()
    if not data.startswith(MAGIC) or not data.endswith(MAGIC):
        raise ValueError("MCAP magic missing")
    schemas: dict[int, tuple[str, bytes]] = {}
    channels: dict[int, tuple[int, str]] = {}
    descriptors: dict[str, dict[int, dict[str, Any]]] = {}
    counts: Counter[int] = Counter()
    data_end = None

    def consume(opcode: int, payload: bytes) -> dict[str, Any] | None:
        if opcode == 3:
            identifier = struct.unpack_from("<H", payload)[0]
            name, cursor = string_at(payload, 2)
            encoding, cursor = string_at(payload, cursor)
            size = struct.unpack_from("<I", payload, cursor)[0]
            blob = payload[cursor + 4 :]
            if encoding != "protobuf" or len(blob) != size or size > 4 * 1024 * 1024:
                raise ValueError("unsupported or malformed protobuf schema")
            schema = (name, blob)
            if identifier in schemas and schemas[identifier] != schema:
                raise ValueError("conflicting MCAP schema")
            schemas[identifier] = schema
            parsed = descriptor_messages(blob)
            if any(k in descriptors and descriptors[k] != v for k, v in parsed.items()):
                raise ValueError("conflicting protobuf descriptors")
            descriptors.update(parsed)
        elif opcode == 4:
            identifier, schema_id = struct.unpack_from("<HH", payload)
            topic, cursor = string_at(payload, 4)
            encoding, cursor = string_at(payload, cursor)
            size = struct.unpack_from("<I", payload, cursor)[0]
            if encoding != "protobuf" or cursor + 4 + size != len(payload):
                raise ValueError("unsupported or malformed channel")
            channel = (schema_id, topic)
            if identifier in channels and channels[identifier] != channel:
                raise ValueError("conflicting MCAP channel")
            channels[identifier] = channel
        elif opcode == 5:
            if data_end is not None or len(payload) < 22:
                raise ValueError("message outside MCAP data section or truncated")
            identifier, sequence, log_time, publish_time = struct.unpack_from("<HIQQ", payload)
            schema_id, topic = channels[identifier]
            # 未使用的人体动作/IMU 消息不进入模型观察，也不加载进内存。
            if topic.startswith("/camera/") or topic in {"/tf_static", "/meta"}:
                return {
                    "topic": topic,
                    "timestamp_ns": log_time,
                    "publish_time_ns": publish_time,
                    "sequence": sequence,
                    "message": decode_message(payload[22:], schemas[schema_id][0], descriptors),
                }
        return None

    try:
        for offset, opcode, payload, next_offset in records(data, 8, len(data) - 8):
            counts[opcode] += 1
            if opcode == 6:
                if data_end is not None:
                    raise ValueError("chunk outside MCAP data section")
                _, _, expected_size, crc = struct.unpack_from("<QQQI", payload)
                if expected_size > MAX_CHUNK_BYTES:
                    raise ValueError("MCAP expanded chunk size limit exceeded")
                compression, cursor = string_at(payload, 28)
                compressed_size = struct.unpack_from("<Q", payload, cursor)[0]
                compressed = payload[cursor + 8 :]
                if len(compressed) != compressed_size:
                    raise ValueError("MCAP compressed chunk size mismatch")
                if compression == "zstd":
                    from backports import zstd  # type: ignore[import-not-found]

                    decoder = zstd.ZstdDecompressor()
                    expanded = decoder.decompress(compressed, max_length=expected_size + 1)
                    if not decoder.eof or decoder.unused_data:
                        raise ValueError("MCAP compressed frame truncated or size limit exceeded")
                elif compression == "":
                    expanded = compressed
                else:
                    raise ValueError("unsupported MCAP compression")
                if len(expanded) != expected_size:
                    raise ValueError("MCAP expanded chunk size mismatch")
                if crc and crc != zlib.crc32(expanded):
                    raise ValueError("MCAP chunk CRC mismatch")
                for _, inner_op, inner_payload, _ in records(expanded):
                    if inner_op not in {3, 4, 5}:
                        raise ValueError("unsupported record inside MCAP chunk")
                    message = consume(inner_op, inner_payload)
                    if message is not None:
                        yield message
            elif opcode == 15:
                (expected,) = struct.unpack("<I", payload)
                if expected and expected != zlib.crc32(data[8:offset]):
                    raise ValueError("MCAP data CRC mismatch")
                data_end = offset
            elif opcode == 2:
                start, offsets, expected = struct.unpack("<QQI", payload)
                if next_offset != len(data) - 8 or data_end is None:
                    raise ValueError("MCAP footer location invalid")
                if start and not data_end < start < offset:
                    raise ValueError("MCAP summary location invalid")
                if offsets and not start <= offsets < offset:
                    raise ValueError("MCAP summary offset invalid")
                if expected and expected != zlib.crc32(data[start or offset : offset + 25]):
                    raise ValueError("MCAP summary CRC mismatch")
            else:
                message = consume(opcode, payload)
                if message is not None:
                    yield message
        if any(counts[k] != 1 for k in (1, 2, 15)):
            raise ValueError("MCAP requires one Header, DataEnd and Footer")
    except (struct.error, KeyError, UnicodeError) as exc:
        raise ValueError("malformed MCAP/protobuf record") from exc
