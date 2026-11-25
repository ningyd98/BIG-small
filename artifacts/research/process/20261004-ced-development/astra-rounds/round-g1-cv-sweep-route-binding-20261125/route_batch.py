"""Run the identical per-frame program in isolated cold processes and compare complete outputs."""

import argparse
import base64
import gzip
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROUND = Path(__file__).resolve().parent
PARENT = ROUND.parent / "round-g1-cv-grasp-validation-20261125"
PLAN = "3548bacb98e5b4196d0ef84e2f31f1c5c49e09a5581455231180e3aa947a1e9c"
PARENT_PLAN = "596158c29f9d43573a92c2be22a5b9db55e5d8b21f08cc8382e65e3d8b7ffb1a"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_bytes())


def encode(v):
    return (
        json.dumps(v, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


def pinned(p, v):
    if sha(p) != v:
        raise ValueError(f"source mismatch {p}")
    return read(p)


def packets(outdir):
    sp = pinned(ROUND / "plan.json", PLAN)
    assert all(sha(Path(k)) == v for k, v in sp["input_sha256"].items())
    parent = pinned(PARENT / "plan.json", PARENT_PLAN)
    for i, a in enumerate(parent["planning_frames"]):
        pins = parent["inputs_sha256"]
        p = Path(a["file"])
        x = Path(a["assembly_xml"])
        ra = Path(a["registration_file"])
        frame = pinned(p, pins[str(p)])
        allocation = pinned(ra, pins[str(ra)])
        assert (
            frame["frame_id"] == a["frame_id"] and frame["checksum_sha256"] == a["payload_sha256"]
        )
        idx = p.parent.parent / "pixel-index.json"
        index = pinned(idx, pins[str(idx)])
        [entry] = [e for e in index["frames"] if e["frame_id"] == frame["frame_id"]]
        assert p == idx.parent / entry["file"] and pins[str(p)] == entry["file_sha256"]
        assert (entry["physics_step"], entry["label"]) == (a["step"], a["role"])
        assert sha(x) == pins[str(x)] == allocation["asset_sha256"]
        # The worker never receives the allocation, scene seed, plan or other observations.
        name = f"H{i + 1:02d}"
        g = outdir / (name + "-geometry.json")
        g.write_bytes(encode(allocation["geometry"]))
        yield name, p, g, x, None
    blind = Path("experiments/results/g1-cv-grasp-validation-20261125/capture-v2/blind")
    x = Path(
        "assets/robots/franka_panda/scene_g1_development_dual_id7_y130_id8_x130_low_bracket_v3.xml"
    )
    assert sha(x) == "14a1a9fc2d2993fa28fbb873e25d1e9672c07b7433b3cb9ad27f07434c75efbe"
    for name in ("A", "B"):
        yield (
            name,
            blind / name / "frame.json",
            blind / "geometry.json",
            x,
            blind / name / "proprio.json",
        )


def run(outdir, which):
    folder = outdir / which
    folder.mkdir(exist_ok=False)
    record = []
    for name, p, g, x, robot in packets(folder):
        out = folder / (name + ".json")
        cmd = [
            sys.executable,
            "-B",
            str(ROUND / "route_screen.py"),
            "--frame",
            str(p),
            "--geometry",
            str(g),
            "--xml",
            str(x),
            "--output",
            str(out),
        ]
        if robot:
            cmd += ["--robot-measurement", str(robot)]
        start = time.perf_counter()
        proc = subprocess.Popen(cmd, env=os.environ | {"OPENBLAS_NUM_THREADS": "1"})
        if proc.wait() != 0:
            raise RuntimeError(f"frame {name} failed")
        record.append(
            dict(
                key=name,
                frame_sha256=sha(p),
                geometry_sha256=sha(g),
                xml_sha256=sha(x),
                proprio_sha256=sha(robot) if robot else None,
                elapsed_ms=(time.perf_counter() - start) * 1000,
                worker_pid=proc.pid,
                sha256=sha(out),
            )
        )
    (folder / "manifest.json").write_bytes(encode(record))


def seal(folder):
    a = read(folder / "first/manifest.json")
    b = read(folder / "second/manifest.json")
    results = []
    for first_read, second_read in zip(a, b, strict=True):
        assert first_read["worker_pid"] != second_read["worker_pid"]
        assert {k: v for k, v in first_read.items() if k not in ("worker_pid", "elapsed_ms")} == {
            k: v for k, v in second_read.items() if k not in ("worker_pid", "elapsed_ms")
        }
        name = first_read["key"]
        first = folder / "first" / (name + ".json")
        second = folder / "second" / (name + ".json")
        assert first.read_bytes() == second.read_bytes()
        if name in ("A", "B"):
            assert first.read_bytes() == (folder / (name + ".json")).read_bytes()
        results.append(read(first))
    entire = encode(results)
    compressed = gzip.compress(entire, compresslevel=9, mtime=0)
    package = dict(
        schema="g1.grasp.direct-route.candidates.v2",
        plan_sha256=PLAN,
        source_sha256=results[0]["source_sha256"],
        readback_first=a,
        readback_second=b,
        full_uncompressed_sha256=hashlib.sha256(entire).hexdigest(),
        full_gzip_sha256=hashlib.sha256(compressed).hexdigest(),
        encoding="UTF8 JSON array, LF, gzip, base64",
        data_base64=base64.b64encode(compressed).decode(),
        new_robot_commands=0,
        new_physics_steps=0,
        formal_attempts=0,
    )
    with (ROUND / "route-candidates.public.json").open("xb") as dst:
        dst.write(encode(package))
    print(package["full_uncompressed_sha256"], sha(ROUND / "route-candidates.public.json"))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("dir", type=Path)
    p.add_argument("mode", choices=["first", "second", "seal"])
    a = p.parse_args()
    seal(a.dir) if a.mode == "seal" else run(a.dir, a.mode)
