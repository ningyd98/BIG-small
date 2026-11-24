"""Reload the archive twice and check critical geometry against box vertices."""

import argparse
import gzip
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from contact_geometry import PLAN, ROUND, canonical, prior, sha


def run(script, paths, egl=False):
    env = dict(os.environ)
    if egl:
        env.update(MUJOCO_GL="egl", PYOPENGL_PLATFORM="egl")
    p = subprocess.Popen([sys.executable, "-B", str(ROUND / script), *map(str, paths)], env=env)
    assert p.wait() == 0
    return p.pid


def check(data):
    intervals, contacts, max_error = 0, 0, 0.0
    for track in data["trajectories"].values():
        for mount in track["poses"].values():
            for row in mount["states"]:
                for p in row["pairs"].values():
                    a, b = p["boxes"]

                    def vertices(q):
                        return (prior.SIGNS * np.asarray(q["h"])) @ np.asarray(q["r"]).T + q["c"]

                    av, bv = vertices(a), vertices(b)
                    for axis in p["axes"]:
                        if axis["degenerate"]:
                            continue
                        u = np.asarray(axis["unit_world"])
                        first, second = av @ u, bv @ u
                        gap = 1000 * max(second.min() - first.max(), first.min() - second.max())
                        max_error = max(max_error, abs(gap - axis["signed_gap_mm"]))
                        intervals += 1
                for c in row["contacts"]:
                    for k in ("geom1_surface", "geom2_surface"):
                        q, h = (np.array(c[k][f]) for f in ("local_mm", "half_extents_mm"))
                        assert (abs(q) <= h + 0.0001).all()
                        assert np.min(abs(abs(q) - h)) <= 0.0001
                    contacts += 1
    assert max_error < 1e-8
    q = data["strict_common_intersection"]
    # Reserve more than the declared 0.0001 mm face-reporting tolerance.
    assert q["radius_mm"] - 0.1485 > 0.0001
    assert min(n for s in q["half_face_distances_in_larger_finger_and_beam_mm"] for n in s) > 0.1486
    return dict(
        independent_vertex_interval_checks=intervals,
        max_gap_difference_mm=max_error,
        contact_surface_pair_checks=contacts,
        strict_interior_ball_radius_mm=0.1485,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("private", type=Path)
    parser.add_argument("output", type=Path)
    a = parser.parse_args()
    outputs = [
        a.output / "local-contact-geometry.public.json.gz",
        a.output / "local-render.public.json",
        a.output / "local-repeat.public.json",
    ]
    assert not any(p.exists() for p in outputs)
    a.private.mkdir(exist_ok=False)
    records = []
    datasets = []
    for i in range(2):
        work = a.private / f"read-{i + 1}"
        work.mkdir()
        g = work / "geometry.json"
        render = work / "render"
        pid = run("contact_geometry.py", [g])
        rid = run("contact_render.py", [g, render], egl=True)
        tables = {
            str(p.relative_to(work)): prior.sha(p) for p in sorted(work.rglob("*")) if p.is_file()
        }
        records.append(dict(geometry_pid=pid, render_pid=rid, files_sha256=tables))
        datasets.append((g.read_bytes(), (render / "witness.json").read_bytes()))
    assert len({x[k] for x in records for k in ("geometry_pid", "render_pid")}) == 4
    assert records[0]["files_sha256"] == records[1]["files_sha256"] and datasets[0] == datasets[1]
    g, r = datasets[0]
    checked = check(json.loads(g))
    with outputs[0].open("xb") as fp:
        fp.write(gzip.compress(g, mtime=0))
    with outputs[1].open("xb") as fp:
        fp.write(r)
    final = dict(
        schema="g1.dual-support.fresh-process-equality.v1",
        plan_sha256=PLAN,
        source_sha256=prior.sha(Path(__file__)),
        workers=records,
        independent_checks=checked,
        duplicate_geometry_sha256=sha(g),
        duplicate_render_sha256=sha(r),
        public_geometry_gzip_sha256=prior.sha(outputs[0]),
        private_directory=str(a.private),
        zero_integrated_physics_steps=0,
        commands_sent=0,
    )
    with outputs[2].open("xb") as fp:
        fp.write(canonical(final) + b"\n")


if __name__ == "__main__":
    main()
