"""Recompute all complete candidate stop comparisons from sealed raw state."""

import argparse
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import mujoco
import numpy as np
import qualify_midcourse as q
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_payload import AXES
from scripts.graduation.perception_io import read, sha, write


def load_branch(dest, result, tick, reuse, history):
    tag = str(tick)
    if tag in result["archives"]:
        key = result["archives"][tag]
        raw = dest / f"stop-{tick}.npz"
        contacts = raw.with_suffix(".json")
        q.require(
            sha(raw) == key["state_sha256"] and sha(contacts) == key["contacts_sha256"],
            "candidate branch changed",
        )
        with np.load(raw, allow_pickle=False) as f:
            result_q, r_dq = f["q"], f["dq"]
        return result_q, r_dq, read(contacts), [], key
    stop = q.stop_from_refit(tick, reuse, history[: tick - q.ENTRY + 1])
    q.require(stop[-1] == result["reused"][tag], "reused candidate stop differs")
    return stop


def entry_check(raw, hist, branch, instrument, helper, b):
    tick = raw["trigger"]
    i = tick - q.ENTRY
    qp, qv, contacts, *_ = branch
    normals = hist[:i]
    d = b._data

    def geometry(a, v):
        d.qpos[:] = a
        d.qvel[:] = v
        return instrument.sample(b)[0]

    baseline = geometry(hist[0]["q"], hist[0]["dq"])
    prefix = [geometry(x["q"], x["dq"]) for x in normals]
    geom = [geometry(a, v) for a, v in zip(qp, qv, strict=True)]
    active = read(q.source("profiles/g1_complete_cv_handoff_profile.json"))["stages"]["LIFT"]
    comparison = helper.compare_handoff(active, instrument, baseline, [*prefix, *geom])
    comparison["handoff_pair"]["pair"] = list(comparison["handoff_pair"]["pair"])
    first_bad = next(
        (
            k
            for k, cs in enumerate(contacts)
            if not q.BILATERAL <= set(map(tuple, cs)) <= q.BILATERAL | {q.TABLE}
        ),
        None,
    )
    q.require(
        comparison == raw["minima"] and first_bad == raw["first_invalid_contact"],
        f"recomputed entry components differ at {tick}",
    )


def ordinary_check(raw, hist, branch, parent, new):
    tick, anchor = raw["trigger"], raw["anchor"]
    i, j = anchor - q.ENTRY, tick - q.ENTRY
    sample = hist[i]
    world, reg, contacts = q.check_step(
        new.motion, new.axes, np.asarray(sample["q"]), np.asarray(sample["dq"]), branch, hist[i:j]
    )
    for row in raw["modes"]:
        kind = row["mode"]
        klass = row["speed_class"]
        stage = new.data["LIFT"]["classes"][klass]
        if kind == "generic":
            W = stage["world"]
            W0 = W
            allowed = q.BILATERAL
        else:
            c = kind.removeprefix("source_")
            W0 = parent.source_classes[c][0]
            W = new.source_classes[c][0]
            allowed = q.BILATERAL | {q.TABLE}
        after = W - world
        a, b = np.unravel_index(after.argmin(), after.shape)
        missing = next(
            (k for k, x in enumerate(contacts) if not q.BILATERAL <= set(map(tuple, x)) <= allowed),
            None,
        )
        q.require(
            row["world_min_m"] == float(after[a, b])
            and row["relative_min_m"] == float((stage["relative"] - reg).min())
            and row["old_world_min_m"] == float((W0 - world).min())
            and row["worst_part"] == new.motion.names[a]
            and row["world_axis"] == AXES[b].tolist()
            and row["first_invalid_contact"] == missing,
            f"recomputed native geometry differs at {anchor}/{tick}",
        )


def reread(reader):
    dest = q.OUT / "native"
    receipt = q.OUT / f"{reader}.json"
    if receipt.is_file():
        pins = read(receipt)
        q.require(
            pins["normal_sha256"] == sha(dest / "normal.json")
            and pins["result_sha256"] == sha(dest / "result.json"),
            "sealed candidate summary no longer matches the native evidence",
        )
    else:
        q.cold(reader)
    hist = read(dest / "normal.json")
    result = read(dest / "result.json")
    originals = q.ROOTS["refit_raw"] / "fit/grid04"
    old_package = read(originals / "seal.json")
    q.require(
        sha(originals / "normal.npz") == old_package["normal_sha256"], "changed reuse package"
    )
    with np.load(originals / "normal.npz", allow_pickle=False) as f:
        reuse = (old_package, {k: f[k] for k in ("q", "dq", "ctrl")}, originals)
    module = q.module(q.source("rounds/round-g1-skill-handoff-20261125/handoff-physics-stops.py"))
    helper = q.module(
        q.source("rounds/round-g1-t01-lift55-native-qualification-20261126/stop_readback.py")
    )
    asset = (
        q.ROOTS["runtime"]
        / "assets/robots/franka_panda"
        / ("scene_g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1.xml")
    )
    model = mujoco.MjModel.from_xml_path(str(asset))
    pseudo = SimpleNamespace(_model=model, _data=mujoco.MjData(model))
    instrument = module.Instrument(pseudo)
    instrument.io_names = module.io.NAMES
    parent, new = q.prepare_profiles(MotionGeometry(Model(asset)))
    cache = {}
    for entry in result["entry_checks"]:
        branch = load_branch(dest, result, entry["trigger"], reuse, hist)
        entry_check(entry, hist, branch, instrument, helper, pseudo)
    for window in result["ordinary_windows"]:
        tick = window["trigger"]
        if tick not in cache:
            cache[tick] = load_branch(dest, result, tick, reuse, hist)
        ordinary_check(window, hist, cache[tick], parent, new)
    write(
        q.OUT / f"geometry-{reader}.json",
        {
            "recomputed_entry_delays": len(result["entry_checks"]),
            "recomputed_window_delays": len(result["ordinary_windows"]),
            "reader_sha256": sha(q.OUT / f"{reader}.json"),
            "code_sha256": sha(Path(__file__)),
            "result_sha256": sha(dest / "result.json"),
            "new_native_steps": 0,
            "new_exposures": 0,
        },
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("reader", choices=("reader-1", "reader-2"))
    parsed = cli.parse_args()
    with patch.multiple(
        mujoco,
        Renderer=q.deny,
        mjr_render=q.deny,
        mj_step=q.deny,
        mj_step1=q.deny,
        mj_step2=q.deny,
    ):
        reread(parsed.reader)
