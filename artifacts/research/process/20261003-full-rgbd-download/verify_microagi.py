#!/usr/bin/env python3
"""Offline verification of MicroAGI MCAP, using its embedded protobuf schemas.

Requires only the already installed numpy, Pillow and backports.zstd. The
descriptor decoder is limited to ordinary protobuf fields used by this source;
it does not depend on generated ROS/protobuf modules or perform any network I/O.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import struct
import zlib
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from backports import zstd
from PIL import Image

MAGIC = b"\x89MCAP0\r\n"
EXPECTED_SHA256 = "e1f0d81d90b5fd8fea7f1b293d51b3e18091618949e195cd141232770c784875"


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


def wire_fields(data: bytes) -> list[tuple[int, int, int | bytes]]:
    result = []
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
        result.append((number, wire, value))
    return result


def descriptor_fields(data: bytes) -> dict[int, list[Any]]:
    result: dict[int, list[Any]] = {}
    for number, _, value in wire_fields(data):
        result.setdefault(number, []).append(value)
    return result


def descriptor_messages(data: bytes) -> dict[str, dict[int, dict[str, Any]]]:
    messages: dict[str, dict[int, dict[str, Any]]] = {}

    def add_message(raw: bytes, prefix: str) -> None:
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
            add_message(nested, name + ".")

    for raw_file in descriptor_fields(data).get(1, []):
        file_descriptor = descriptor_fields(raw_file)
        package = file_descriptor.get(2, [b""])[0].decode()
        prefix = package + "." if package else ""
        for raw_message in file_descriptor.get(4, []):
            add_message(raw_message, prefix)
    return messages


def scalar(field_type: int, wire: int, raw: int | bytes) -> Any:
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
    data: bytes, name: str, descriptors: dict[str, dict[int, dict[str, Any]]]
) -> dict[str, Any]:
    fields = descriptors[name]
    result: dict[str, Any] = {}
    for number, wire, raw in wire_fields(data):
        field = fields.get(number)
        if field is None:
            continue
        field_type = field["type"]
        values = []
        if field_type == 11:
            values = [decode_message(raw, field["type_name"], descriptors)]
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


def records(data: bytes, start: int = 0, end: int | None = None):
    end = len(data) if end is None else end
    offset = start
    while offset < end:
        if offset + 9 > end:
            raise ValueError(f"truncated MCAP record header at {offset}")
        opcode, size = struct.unpack_from("<BQ", data, offset)
        next_offset = offset + 9 + size
        if next_offset > end:
            raise ValueError(f"truncated MCAP record {opcode} at {offset}")
        yield offset, opcode, data[offset + 9 : next_offset], next_offset
        offset = next_offset


def verify(path: Path, output: Path) -> dict[str, Any]:
    data = path.read_bytes()
    actual_sha = hashlib.sha256(data).hexdigest()
    if actual_sha != EXPECTED_SHA256:
        raise ValueError("whole-file SHA-256 differs from upstream file-tree hash")
    if not data.startswith(MAGIC) or not data.endswith(MAGIC):
        raise ValueError("missing MCAP start/end magic")
    schemas: dict[int, tuple[str, str, bytes]] = {}
    channels: dict[int, tuple[int, str, str]] = {}
    descriptors: dict[str, dict[int, dict[str, Any]]] = {}
    counts: Counter[str] = Counter()
    top_counts: Counter[int] = Counter()
    first: dict[str, tuple[int, dict[str, Any]]] = {}
    log_times: list[int] = []
    chunk_checks = []
    data_end = None
    footer = None
    required = {
        "/camera/color/info",
        "/camera/depth/info",
        "/camera/depth/unit_of_depth_in_mm",
        "/tf_static",
        "/camera/color/image",
        "/camera/depth/image",
        "/meta",
    }

    def consume(opcode: int, payload: bytes) -> None:
        if opcode == 3:
            schema_id = struct.unpack_from("<H", payload)[0]
            name, offset = string_at(payload, 2)
            encoding, offset = string_at(payload, offset)
            size = struct.unpack_from("<I", payload, offset)[0]
            blob = payload[offset + 4 :]
            if len(blob) != size or encoding != "protobuf":
                raise ValueError("invalid/unsupported schema record")
            schema = (name, encoding, blob)
            if schema_id in schemas and schemas[schema_id] != schema:
                raise ValueError("conflicting repeated schema ID")
            schemas[schema_id] = schema
            descriptors.update(descriptor_messages(blob))
        elif opcode == 4:
            channel_id, schema_id = struct.unpack_from("<HH", payload)
            topic, offset = string_at(payload, 4)
            encoding, offset = string_at(payload, offset)
            metadata_size = struct.unpack_from("<I", payload, offset)[0]
            if offset + 4 + metadata_size != len(payload):
                raise ValueError("malformed channel metadata length")
            channel = (schema_id, topic, encoding)
            if channel_id in channels and channels[channel_id] != channel:
                raise ValueError("conflicting repeated channel ID")
            channels[channel_id] = channel
        elif opcode == 5:
            if len(payload) < 22:
                raise ValueError("truncated message header")
            channel_id, _, log_time, _ = struct.unpack_from("<HIQQ", payload)
            schema_id, topic, encoding = channels[channel_id]
            if encoding != "protobuf":
                raise ValueError("unsupported channel encoding")
            counts[topic] += 1
            log_times.append(log_time)
            if topic in required and topic not in first:
                first[topic] = (
                    log_time,
                    decode_message(payload[22:], schemas[schema_id][0], descriptors),
                )

    for offset, opcode, payload, next_offset in records(data, 8, len(data) - 8):
        top_counts[opcode] += 1
        if opcode == 6:
            start, end, uncompressed_size, crc = struct.unpack_from("<QQQI", payload)
            compression, cursor = string_at(payload, 28)
            compressed_size = struct.unpack_from("<Q", payload, cursor)[0]
            compressed = payload[cursor + 8 :]
            if len(compressed) != compressed_size:
                raise ValueError("incorrect MCAP compressed chunk size")
            if compression == "zstd":
                expanded = zstd.decompress(compressed)
            elif compression == "":
                expanded = compressed
            else:
                raise ValueError(f"unsupported compression {compression}")
            if len(expanded) != uncompressed_size:
                raise ValueError("incorrect MCAP uncompressed chunk size")
            computed = zlib.crc32(expanded)
            if crc and computed != crc:
                raise ValueError("MCAP chunk CRC mismatch")
            for _, inner_opcode, inner_payload, _ in records(expanded):
                consume(inner_opcode, inner_payload)
            chunk_checks.append(
                {
                    "offset": offset,
                    "start_time_ns": start,
                    "end_time_ns": end,
                    "uncompressed_bytes": uncompressed_size,
                    "crc32": crc,
                    "crc32_verified": bool(crc),
                }
            )
        elif opcode == 15:
            if len(payload) != 4:
                raise ValueError("invalid DataEnd record")
            expected = struct.unpack("<I", payload)[0]
            computed = zlib.crc32(data[8:offset])
            if expected and expected != computed:
                raise ValueError("MCAP data section CRC mismatch")
            data_end = {"offset": offset, "crc32": expected, "crc32_verified": bool(expected)}
        elif opcode == 2:
            if len(payload) != 20 or next_offset != len(data) - 8:
                raise ValueError("invalid MCAP footer location or size")
            summary_start, summary_offset_start, expected = struct.unpack("<QQI", payload)
            if summary_start and not (data_end and data_end["offset"] < summary_start < offset):
                raise ValueError("invalid summary offset")
            if summary_offset_start and not (summary_start <= summary_offset_start < offset):
                raise ValueError("invalid summary-offset section")
            computed = zlib.crc32(data[summary_start or offset : offset + 25])
            if expected and expected != computed:
                raise ValueError("MCAP summary CRC mismatch")
            footer = {
                "summary_start": summary_start,
                "summary_offset_start": summary_offset_start,
                "crc32": expected,
                "crc32_verified": bool(expected),
            }
        else:
            consume(opcode, payload)
    if top_counts[1] != 1 or top_counts[15] != 1 or top_counts[2] != 1:
        raise ValueError("MCAP must have exactly one Header, DataEnd and Footer")
    missing = required - first.keys()
    if missing:
        raise ValueError(f"required RGBD topics missing: {sorted(missing)}")
    output.mkdir(parents=True, exist_ok=True)
    image_results = {}
    for kind in ("color", "depth"):
        log_time, message = first[f"/camera/{kind}/image"]
        encoded = message["data"]
        format_name = message["format"].lower()
        destination = output / ("rgb_first.jpg" if kind == "color" else "depth_first.png")
        with Image.open(io.BytesIO(encoded)) as image:
            image.load()
            array = np.asarray(image)
        if kind == "color":
            if format_name not in ("jpeg", "jpg") or array.ndim != 3 or array.shape[2] != 3:
                raise ValueError("invalid color JPEG format or decoded RGB shape")
        elif format_name != "png" or array.ndim != 2 or array.dtype != np.uint16:
            raise ValueError("depth must decode to a single-channel uint16 PNG")
        destination.write_bytes(encoded)
        info = first[f"/camera/{kind}/info"][1]
        if array.shape[1] != info["width"] or array.shape[0] != info["height"]:
            raise ValueError("image dimensions disagree with camera calibration")
        calibration_k = info.get("K", info.get("k"))
        if calibration_k is None or len(calibration_k) != 9:
            raise ValueError("missing 3x3 K camera intrinsic matrix")
        image_results[kind] = {
            "log_time_ns": log_time,
            "format": format_name,
            "shape": list(array.shape),
            "dtype": str(array.dtype),
            "path": str(destination),
            "encoded_sha256": hashlib.sha256(encoded).hexdigest(),
            "calibration": info,
        }
        if kind == "depth":
            nonzero = array > 0
            valid_depth = array[nonzero]
            if not valid_depth.size:
                raise ValueError("depth contains no positive samples")
            unit_message = first["/camera/depth/unit_of_depth_in_mm"][1]
            unit = unit_message["unit_in_mm"]
            if not np.isfinite(unit) or unit <= 0:
                raise ValueError("invalid recorded depth unit")
            image_results[kind].update(
                {
                    "unit_of_depth_in_mm_message": unit_message,
                    "unit_mm_per_raw_value": unit,
                    "positive_raw_min": int(valid_depth.min()),
                    "positive_raw_max": int(valid_depth.max()),
                    "nonzero_ratio": float(nonzero.mean()),
                    "count_uint16_max": int((array == 65535).sum()),
                    "positive_depth_m_percentiles_5_50_95": (
                        np.percentile(valid_depth, [5, 50, 95]) * unit / 1000
                    ).tolist(),
                }
            )
            scaled = np.zeros(array.shape, dtype=np.uint8)
            lo, hi = np.percentile(valid_depth, [2, 98])
            if hi > lo:
                scaled[nonzero] = np.clip((array[nonzero] - lo) / (hi - lo) * 255, 0, 255).astype(
                    np.uint8
                )
            Image.fromarray(scaled).save(output / "depth_preview.png")
    static_transforms = first["/tf_static"][1]
    result = {
        "status": "VERIFIED_OFFLINE_RGBD_SAMPLE",
        "source": "MicroAGI-Labs/MicroAGI01",
        "relative_source_path": "uncut_mcaps/open-source-12.mcap",
        "path": str(path),
        "bytes": len(data),
        "sha256": actual_sha,
        "upstream_sha256_verified": True,
        "mcap_structure": {
            "start_and_end_magic_verified": True,
            "all_record_boundaries_verified": True,
            "top_level_record_counts": dict(sorted(top_counts.items())),
            "chunk_count": len(chunk_checks),
            "chunk_crcs_verified": sum(c["crc32_verified"] for c in chunk_checks),
            "data_end": data_end,
            "footer": footer,
            "message_count": sum(counts.values()),
            "time_span_seconds": (max(log_times) - min(log_times)) / 1e9,
        },
        "topics": dict(sorted(counts.items())),
        "first_images": image_results,
        "first_image_log_time_difference_ms": abs(
            image_results["color"]["log_time_ns"] - image_results["depth"]["log_time_ns"]
        )
        / 1e6,
        "static_transforms": static_transforms,
        "meta": first["/meta"][1],
        "chunk_checks": chunk_checks,
        "limitations": [
            "First RGB/depth images retain native unequal resolutions; "
            "no pixel alignment is assumed.",
            "Camera and hand pose health flags must be checked before using poses.",
            "Human manipulation data does not provide native robot actuator commands.",
            "Depth preview is contrast-stretched; depth_first.png preserves numeric uint16 depth.",
            "The source-specific maginoresell license is not assumed to be MIT/Apache.",
            "Protobuf fields omitted in decoded messages have source schema defaults, "
            "including zero-valued transform components.",
        ],
    }
    (output / "verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    (output / "index.html").write_text(
        '<!doctype html><html lang="zh"><meta charset="utf-8">'
        "<title>MicroAGI01 RGBD 离线样例</title>"
        "<body><h1>MicroAGI01 / open-source-12</h1><p>完整 MCAP SHA-256 与结构校验通过。"
        "RGB 与深度保留各自原始分辨率；此页面未进行像素配准。</p>"
        '<h2>RGB</h2><img src="rgb_first.jpg" width="640">'
        '<h2>数值深度的可视化</h2><img src="depth_preview.png" width="640">'
        '<p><a href="depth_first.png">原始 uint16 深度 PNG</a> · '
        '<a href="verification.json">标定、深度单位及校验证据</a></p></body></html>',
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mcap", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/home/ningyd/datasets/BIGsmall/reports/microagi01_small"),
    )
    parser.add_argument("--summary-json", type=Path)
    args = parser.parse_args()
    result = verify(args.mcap, args.output)
    if args.summary_json:
        args.summary_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": result["status"],
                "bytes": result["bytes"],
                "chunks": result["mcap_structure"]["chunk_count"],
                "messages": result["mcap_structure"]["message_count"],
                "report": str(args.output / "verification.json"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
