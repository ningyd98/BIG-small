"""Orchestrate isolated current-frame reads and seal every historical candidate before audit."""

import argparse
import base64
import gzip
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROUND = Path(__file__).resolve().parent
PLAN = "596158c29f9d43573a92c2be22a5b9db55e5d8b21f08cc8382e65e3d8b7ffb1a"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(obj):
    return (
        json.dumps(obj, sort_keys=True, allow_nan=False, ensure_ascii=False, separators=(",", ":"))
        + "\n"
    ).encode()


def pinned(p, sha):
    data = Path(p).read_bytes()
    if digest(data) != sha:
        raise ValueError(f"input mismatch {p}")
    return json.loads(data)


def compact(row):
    offsets = row["candidates"]
    nominal = [r for r in offsets if r["geometric_status"] == "CLEAR"]
    raw = [r for r in offsets if r["clearance"] == "CLEAR"]

    def rank(e):
        return (
            -e["registered_min_sep_bound_mm"],
            -min(e["patch"]["contact_area_each_mm2"]),
            abs(e["tangent_mm"]),
        )

    def features(e):
        return {
            k: e[k]
            for k in (
                "candidate_id",
                "tangent_mm",
                "clearance",
                "full_physical_clearance",
                "registered_min_sep_bound_mm",
                "known_components_inflated_sep_bound_mm",
                "hits",
                "unknown_volume_upper_mm3",
                "ray_counts",
                "patch",
                "load_support",
            )
        }

    return dict(
        frame_id=row["frame_id"],
        checksum=row["checksum"],
        candidate_count=len(offsets),
        counts=row["counts"],
        current_surface_status=row["color"]["status"],
        usable_markers=row["marker"]["usable_ids"],
        top_delta_mm=row["current_top_delta_mm"],
        yaw_deg=row.get("object_yaw_deg"),
        nominal_geometry=row["nominal_counts"],
        current_ray_sweep=row["observed_sweep_counts"],
        orientation_matches=sum(e["original_orientation"] for e in offsets),
        nominal_patch_and_gap_by_direction=dict(Counter(e["direction"] for e in nominal)),
        ranked_nominal_best=features(min(nominal, key=rank)) if nominal else None,
        current_ray_clear_best=features(min(raw, key=rank)) if raw else None,
        center_each=[features(e) for e in offsets if e["tangent_mm"] == 0],
        selected=row["selected"],
    )


def run(output):
    spec = pinned(ROUND / "plan.json", PLAN)
    pins = spec["inputs_sha256"]
    records = []
    summary = []
    clocks = []
    with tempfile.TemporaryDirectory(prefix="bigsmall-g1-cv-sweep-") as d:
        tmp = Path(d)
        for i, a in enumerate(spec["planning_frames"]):
            fp = Path(a["file"])
            xp = Path(a["assembly_xml"])
            alloc = pinned(a["registration_file"], pins[a["registration_file"]])
            if (
                digest(xp.read_bytes()) != pins[a["assembly_xml"]]
                or alloc["asset_sha256"] != pins[a["assembly_xml"]]
            ):
                raise ValueError("assembly pin changed")
            frame = pinned(fp, pins[str(fp)])
            assert (
                frame["frame_id"] == a["frame_id"]
                and frame["checksum_sha256"] == a["payload_sha256"]
            )
            index_file = fp.parent.parent / "pixel-index.json"
            index = pinned(index_file, pins[str(index_file)])
            [match] = [m for m in index["frames"] if m["frame_id"] == a["frame_id"]]
            assert fp == index_file.parent / match["file"] and (
                match["physics_step"],
                match["label"],
            ) == (a["step"], a["role"])
            inp = tmp / f"image-{i}.json"
            geo = tmp / f"geometry-{i}.json"
            out = tmp / f"out-{i}.json"
            inp.write_bytes(fp.read_bytes())
            geo.write_bytes(encoded(alloc["geometry"]))
            args = [
                sys.executable,
                "-B",
                str(ROUND / "sweep_replay.py"),
                "frame",
                "--frame",
                str(inp),
                "--geometry",
                str(geo),
                "--xml",
                str(xp),
                "--output",
                str(out),
            ]
            t = time.perf_counter()
            subprocess.run(args, check=True, env=os.environ | {"OPENBLAS_NUM_THREADS": "1"})
            clocks.append((time.perf_counter() - t) * 1000)
            row = json.loads(out.read_bytes())
            assert row["frame_id"] == a["frame_id"] and row["checksum"] == a["payload_sha256"]
            records.append(row)
            summary.append(
                compact(row)
                | dict(
                    frame_file=str(fp),
                    class_role=a["role"],
                    step=a["step"],
                    frame_sha256=pins[str(fp)],
                    xml_sha256=pins[a["assembly_xml"]],
                )
            )
    packed = encoded(records)
    archive = gzip.compress(packed, compresslevel=9, mtime=0)
    blob = dict(
        schema="g1-grasp-candidates.v1",
        encoding="base64(gzip(canonical JSON UTF8 LF)); decode to an array of 12 full reports",
        plan_sha256=PLAN,
        uncompressed_sha256=digest(packed),
        compressed_sha256=digest(archive),
        bytes=len(packed),
        gzip_base64=base64.b64encode(archive).decode(),
    )
    (output / "sweep-candidates.public.json").write_bytes(encoded(blob))
    metadata = dict(
        schema="g1-grasp-sweep-history.v1",
        plan_sha256=PLAN,
        source_sha256=records[0]["source_sha256"],
        runner_sha256=digest(Path(__file__).read_bytes()),
        candidate_archive_sha256=digest(encoded(blob)),
        per_frame_subprocess_wall_ms=clocks,
        measured_time_scope="cold process including interpreter startup and writing all evidence",
        physics_steps=0,
        robot_commands=0,
        frames=summary,
    )
    (output / "sweep-history.public.json").write_bytes(
        (
            json.dumps(metadata, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
            + "\n"
        ).encode()
    )
    print(
        [(x["candidate_count"], x["nominal_geometry"], x["current_ray_sweep"]) for x in summary],
        flush=True,
    )
    print("canonical candidate SHA", digest(packed))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    run(p.parse_args().output)
