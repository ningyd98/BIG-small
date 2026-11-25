"""Freeze and independently test a finite candidate table on whole physical placements."""

import argparse
import math
import time
from pathlib import Path

import numpy as np

import physics_selection_study as s


TANGENTS = s.HERE / "physics_selection_tangent_seal.public.json"
FREEZE = s.HERE / "physics_selection_freeze.public.json"


def label(dest, case, cid, *, owner=True):
    source = dest / "physical-reader" / case / cid
    mech = s.read(source / "physical.json")
    wrench = s.read(source / "wrench.json")
    opt = dest / "optical-reader" / case / (cid + ".json")
    capture = s.read(opt)
    passing = wrench["true_mechanical_pass"]
    bindings = [s.sha(source/"wrench.json"), s.sha(opt)]
    if owner:
        path = dest/"owner-registered-physics"/"labels"/case/(cid+".json")
        registered = s.read(path)
        passing = bool(registered["complete_settled_240"] and mech["stable_50mm_for_120"]
                       and min(mech["closed_normals_N"] or [0]) >= 2
                       and wrench["wrenches"].get("GRASP", {}).get("weights", 0) > 1
                       and mech["max_backtracking_m"] is not None and mech["max_backtracking_m"] <= .001)
        bindings.append(s.sha(path))
    lateral = mech["lateral_peak_m"]
    corridor = .001 - lateral if lateral is not None else -.001
    if not passing:
        corridor = min(corridor, -1e-9)
    return {
        "mechanical": passing, "all_three": capture["all_pass"], "optical_frame_passes": sum(f["status"] == "PASS" for f in capture["frames"]),
        "frame_count": len(capture["frames"]), "lateral_peak_m": lateral, "corridor_signed_m": corridor,
        "optical_signed": capture["worst_optical_margin"], "source_sha256": bindings,
    }


def tangent_seal(root):
    dest = root / s.RAW
    reg, fits, blind = s.inputs(root)
    if any((dest / "prefix" / n).exists() for n in blind):
        raise ValueError("independent placements already opened")
    cases = {r["name"]: r["placement_group"] for r in reg["fit"]}
    table, enabled = {}, []
    for h in reg["heights_mm"]:
        rows = {n: label(dest, n, s.code(h, 0), owner=False) for n in fits}
        groups = {cases[n] for n, v in rows.items() if v["mechanical"] and v["all_three"]}
        table[str(h)] = {"joint_groups": sorted(groups), "rows": rows}
        if len(groups) >= 2:
            enabled.append(h)
    s.write(TANGENTS, {"registration_sha256": s.sha(s.REG), "heights": enabled, "center_fit": table})


def distance(blocks, current, scales):
    squared = [np.mean(((np.asarray(v) - query) / scale) ** 2, axis=1)
               for v, query, scale in zip(blocks, current, scales, strict=True)]
    return np.sqrt(np.mean(squared, axis=0))


def margin(bank, cid, distances, exclude=None):
    groups = bank["groups"]
    minimum = [(t, float(min(distances[i] for i in rows))) for t, rows in groups.items() if t != exclude]
    nearest = sorted(minimum, key=lambda p: (p[1], p[0]))[:3]
    rows = [bank["group_labels"][cid][t] for t, _ in nearest]
    weights = 1 / np.maximum([d for _, d in nearest], 1e-6)
    weights /= sum(weights)
    p = np.array([r["physical_margin_m"] for r in rows])
    o = np.array([r["optical_margin"] for r in rows])
    return {"groups": [t for t, _ in nearest], "nearest": nearest[0][1], "p": float(weights@p), "o": float(weights@o),
            "min_p": float(min(p)), "min_o": float(min(o)), "all_joint": all(r["joint"] for r in rows)}


def fit(root):
    dest = root / s.RAW
    reg, fits, blind = s.inputs(root)
    if any((dest/"prefix"/n).exists() for n in blind):
        raise ValueError("independent prefix already exists")
    seal = s.read(TANGENTS)
    ids = [c["id"] for c in s.root_candidates(reg["heights_mm"], [0])]
    confirmed_heights = []
    fitgroups = {r["name"]: r["placement_group"] for r in reg["fit"]}
    for h in seal["heights"]:
        supported = {fitgroups[name] for name in fits
                     if (row := label(dest, name, s.code(h, 0)))["mechanical"] and row["all_three"]}
        if len(supported) >= 2:
            confirmed_heights.append(h)
    ids += [c["id"] for c in s.root_candidates(confirmed_heights, reg["tangents_mm"])]
    groups = {}
    for index, slot in enumerate(reg["fit"]):
        groups.setdefault(slot["placement_group"], []).append(index)
    features = [s.read(dest/"prefix"/n/"measured-input.json")["features"] for n in fits]
    blocks = [np.stack(x) for x in zip(*features, strict=True)]
    floors = ([.003, .003, .002], .015, .008, .001, .00025, .00005, .01)
    scales = [np.maximum(np.ptp(v, axis=0)/2, f) for v, f in zip(blocks, floors, strict=True)]
    all_labels = {cid: [label(dest, n, cid) for n in fits] for cid in ids}
    bank = {
        "registration_sha256": s.sha(s.REG), "tangent_seal_sha256": s.sha(TANGENTS),
        "selection_source_sha256": s.sha(Path(__file__)), "observer_source_sha256": s.sha(s.HERE/"physics_selection_observers.py"),
        "adapter_source_sha256": s.sha(s.HERE/"physics_selection_study.py"),
        "names": fits, "groups": groups, "candidate_ids": ids, "confirmed_owner_heights": confirmed_heights,
        "owner_reader_sha256": s.sha(s.HERE/"physics_selection_owner_readback.py"), "fit_observations": all_labels,
        "group_labels": {}, "errors": {}, "blocks": [b.tolist() for b in blocks], "scales": [v.tolist() for v in scales],
        "neighbor_policy": "three distinct placement groups; repeat group outcome and optical exposure use worst value",
        "input_fields": ["current_optical_object_center","observed_arm_q","observed_arm_dq","effective_arm_target_minus_q","observed_fingers","observed_finger_velocity","observed_object_X_axis"],
    }
    for cid in ids:
        z = all_labels[cid]
        bank["group_labels"][cid] = {
            t: {"physical_margin_m": min(z[i]["corridor_signed_m"] for i in indices),
                "optical_margin": min(z[i]["optical_signed"] for i in indices),
                "joint": all(z[i]["mechanical"] and z[i]["all_three"] for i in indices)}
            for t, indices in groups.items()}
    all_dist = [distance(blocks, obs, scales) for obs in features]
    max_nearest = 0
    for cid in ids:
        data = bank["group_labels"][cid]
        loo_p, loo_o, rep_p, rep_o = [], [], [], []
        for group, indices in groups.items():
            p_obs = [all_labels[cid][i]["corridor_signed_m"] for i in indices]
            o_obs = [all_labels[cid][i]["optical_signed"] for i in indices]
            rep_p.append(max(p_obs)-min(p_obs))
            rep_o.append(max(o_obs)-min(o_obs))
            for i in indices:
                est = margin(bank, cid, all_dist[i], exclude=group)
                max_nearest = max(max_nearest, est["nearest"])
                loo_p.append(est["p"] - data[group]["physical_margin_m"])
                loo_o.append(est["o"] - data[group]["optical_margin"])
        bank["errors"][cid] = {
            "physical_repeat_m": max(rep_p), "optical_repeat": max(rep_o),
            "physical_loo_m": max(0, max(loo_p)), "optical_loo": max(0, max(loo_o)),
            "physical_m": max(0, max(loo_p), max(rep_p)),
            "optical": max(0, max(loo_o), max(rep_o)),
        }
    bank["max_distance"] = max_nearest
    fixed = []
    for cid in ids:
        g = list(bank["group_labels"][cid].values())
        if all(r["joint"] for r in g):
            p = min(r["physical_margin_m"] for r in g) - bank["errors"][cid]["physical_m"]
            o = min(r["optical_margin"] for r in g) - bank["errors"][cid]["optical"]
            if min(p, o) > 0:
                fixed.append((min(p/.001, o), cid))
    bank["fixed"] = best(fixed)
    bank["stop_qualification"] = "No nonnominal candidate inherits a centre stop. Re-evaluate original signed state-dependent certificate/actual branch before reporting dispatch."
    s.write(FREEZE, bank)


def best(options):
    if not options:
        return None
    def key(item):
        value, cid = item
        height, tangent = cid.split("_t")
        return -value, abs(int(tangent)), abs(int(height[1:])-10), cid
    return min(options, key=key)[1]


def predict(bank, features):
    distances = distance(bank["blocks"], features, [np.array(v) for v in bank["scales"]])
    scores = {}
    supported = []
    for cid in bank["candidate_ids"]:
        value = margin(bank, cid, distances)
        error = bank["errors"][cid]
        p = min(value["min_p"], value["p"]-error["physical_m"])
        o = min(value["min_o"], value["o"]-error["optical"])
        score = min(p/.001, o)
        if value["all_joint"] and value["nearest"] <= bank["max_distance"] and score > 0:
            supported.append((score, cid))
        scores[cid] = {**value, "lower_physical_m": p, "lower_optical": o}
    return {"provisional_physical_optical_choice": bank["fixed"] or best(supported), "scores": scores,
            "externally_authorized": False, "stop_status": "separate_binding_required"}


def decisions(root):
    dest = root / s.RAW
    bank = s.read(FREEZE)
    _, _, blind = s.inputs(root)
    if any((dest/"courses"/n).exists() for n in blind):
        raise ValueError("opened an independent mechanical outcome before blind selection freeze")
    for name in blind:
        anchor = dest/"prefix"/name/"measured-input.json"
        input_data = s.read(anchor)
        begin = time.monotonic_ns()
        decision = predict(bank, input_data["features"])
        elapsed = (time.monotonic_ns() - begin)/1e6
        s.write(anchor.with_name("decision.json"), {"case": name, "freeze_sha256": s.sha(FREEZE),
                "measured_input_sha256": s.sha(anchor), "selection_ms": elapsed, **decision})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--mode", choices=("tangent-seal", "fit", "decisions"), required=True)
    args = parser.parse_args()
    {"tangent-seal": tangent_seal, "fit": fit, "decisions": decisions}[args.mode](args.root.resolve())
