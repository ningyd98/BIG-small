"""Build and independently check a stage-entry motion envelope using native stop archives."""

import argparse
import hashlib
from pathlib import Path

import numpy as np
from scripts.graduation import g1_complete_cv_handoff as gate
from scripts.graduation.g1_complete_trials import write_once
from scripts.graduation.perception_io import read, sha


def capture_source(root, case):
    return root / "physical-capture-01" / case


def stop_source(root, case):
    return root / "physical-stops-01" / case


def feature_record(h, normal, idx):
    a = h["actual_active_commands"]
    q, dq = np.asarray(a["q"]), np.asarray(a["qvel"])
    x = gate.features(
        q[:7],
        dq[:7],
        q[7:9],
        dq[7:9],
        np.asarray(a["ctrl"][:7]),
        np.asarray(a["command_q"]),
        np.asarray(a["native_sent_arm_velocity_rad_s"]),
        a["ctrl"][7:9],
        normal["tcp"][idx],
        normal["tcp_rotation"][idx],
        np.asarray(h["native_object_pose"]),
        np.asarray(h["native_object_rotation"]),
    )
    return dict(features=x.tolist(), open=a["command_open"])


def observations(root, case):
    cp = capture_source(root, case)
    summary = read(cp / "summary.json")
    accepted = {r["stage"] for r in summary["skill_summaries"] if r["success"]}
    with np.load(cp / "physical-geometries.npz") as solids:
        local = solids["local_vertices"]
        names = solids["names"].tolist()
    with np.load(cp / "normal.npz") as file:
        normal = {k: file[k] for k in ("centers", "rotation", "step", "tcp", "tcp_rotation")}
    for h in read(cp / "handoffs.json"):
        skill = h["incoming"]
        area = stop_source(root, case) / skill
        limits = read(area / "limits.json")
        assert limits["trajectory"] == case and limits["outgoing"] == h["outgoing"]
        assert {r["delay"] for r in limits["delays"]} == gate.required_delays(skill)
        start = h["start_step"]
        assert normal["step"][start] == start
        anchor = normal["centers"][start, :, None] + local @ normal["rotation"][start].transpose(
            0, 2, 1
        )
        minimum = np.full(len(limits["geometry_pairs"]), np.inf)
        gap_half_step = np.zeros_like(minimum)
        pad = np.zeros((len(names), 3))
        baseline = None
        physical_contact = False
        hashes = hashlib.sha256()
        for d in limits["delays"]:
            path = area / ("stop-" + d["delay"] + ".npz")
            hashes.update((path.name + " " + sha(path) + "\n").encode())
            assert d["start_step"] == start + (0 if d["delay"] == "pre" else int(d["delay"]))
            assert d["geometry_at_start_error_m"] < 1e-12
            with np.load(path) as raw:
                gaps = raw["pair_gap"]
                assert gaps.shape == (241, len(minimum)) and np.isfinite(gaps).all()
                # Incorporate motion before the stop at its own physical tick and
                # motion after the stop relative to that same snapshot.
                s = d["start_step"]
                delta = (
                    normal["centers"][s, :, None] + local @ normal["rotation"][s].transpose(0, 2, 1)
                ) - anchor
                bounds = raw["world_corner_xyz_signed_extrema"][-1]
                pad = np.maximum(
                    pad, np.maximum(abs(delta.min(1) + bounds[0]), abs(delta.max(1) + bounds[1]))
                )
            minimum = np.minimum(minimum, gaps.min(axis=0))
            gap_half_step = np.maximum(gap_half_step, 0.5 * abs(np.diff(gaps, axis=0)).max(axis=0))
            if d["delay"] == "0":
                baseline = gaps[0]
            physical_contact |= bool(d["forbidden_contacts"])
        assert baseline is not None and np.isfinite(pad).all()
        assert names == limits["body_names"]
        yield (
            skill,
            dict(
                features=feature_record(h, normal, start),
                names=names,
                pairs=limits["geometry_pairs"],
                closing=np.maximum(0.0, baseline - minimum) + gap_half_step,
                minimum=minimum,
                initial=baseline,
                pad=pad,
                contact=physical_contact,
                stage_passed=skill in accepted,
                samples=len(limits["delays"]),
                normal_sha256=sha(cp / "normal.npz"),
                limits_sha256=sha(area / "limits.json"),
                raw_catalog_sha256=hashes.hexdigest(),
            ),
        )


def fit(root, cases):
    physical = {}
    receipts = {}
    for case in cases:
        for skill, row in observations(root, case):
            receipts[case + "/" + skill] = {
                k: row[k]
                for k in (
                    "normal_sha256",
                    "limits_sha256",
                    "raw_catalog_sha256",
                    "stage_passed",
                    "contact",
                )
            }
            if row["contact"] or not row["stage_passed"]:
                continue
            physical.setdefault(skill, []).append(row)
    stages = {}
    for skill in gate.STAGES[1:]:
        group = physical[skill]
        assert len(group) >= 2
        pairs, names = group[0]["pairs"], group[0]["names"]
        assert all(r["pairs"] == pairs and r["names"] == names for r in group)
        max_closing = np.max([r["closing"] for r in group], axis=0)
        max_pad = np.max([r["pad"] for r in group], axis=0)
        stages[skill] = dict(
            references=[r["features"] for r in group],
            pairs=pairs,
            # Account for unobserved near-neighbours and finite exposure/encoder resolution;
            # validate transfer of the entire forecast on separately drawn initial conditions.
            pair_closing_m=(1.25 * max_closing + 0.00075).tolist(),
            body_pad_xyz_m={
                n: (1.25 * p + 0.00075).tolist() for n, p in zip(names, max_pad, strict=True)
            },
            delays=group[0]["samples"],
        )
    return dict(
        schema="g1.development.continuous-handoff.v1",
        qualified=False,
        stages=stages,
        fits=receipts,
        gate_sha256=sha(Path(gate.__file__)),
    )


def validate(root, profile, cases):
    results = []
    assert profile["gate_sha256"] == sha(Path(gate.__file__))
    for case in cases:
        for skill, row in observations(root, case):
            assert case + "/" + skill not in profile["fits"]
            stage = profile["stages"][skill]
            obs = row["features"]
            refs = [s["features"] for s in stage["references"] if s["open"] is obs["open"]]
            near = bool(
                refs
                and gate.nearby_rows(
                    obs["features"],
                    np.zeros(len(obs["features"])),
                    refs,
                    np.repeat(gate.SCALES, gate.GROUPS),
                    gate.GROUPS,
                )
            )
            active = np.array([not gate.authorized_pair(skill, *p) for p in row["pairs"]])
            remaining = row["initial"] - np.asarray(stage["pair_closing_m"])
            gap_reserve = np.asarray(stage["pair_closing_m"]) - row["closing"]
            pad_reserve = (
                np.asarray([stage["body_pad_xyz_m"][n] for n in row["names"]]) - row["pad"]
            )
            # A refused out-of-domain entry does not count as positive coverage.
            results.append(
                dict(
                    case=case,
                    skill=skill,
                    in_domain=near,
                    continued=bool(near and min(remaining[active]) > 0),
                    envelope_pair_reserve_m=float(gap_reserve[active].min()),
                    envelope_vertex_reserve_m=float(pad_reserve.min()),
                    actual_contact=row["contact"],
                    actual_min_gap_m=float(min(row["minimum"][active])),
                    scheduled_stop_instants=row["samples"],
                    raw_catalog_sha256=row["raw_catalog_sha256"],
                    stage_passed=row["stage_passed"],
                )
            )
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["fit", "validate"])
    p.add_argument("root", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("case", nargs="+")
    p.add_argument("--profile", type=Path)
    a = p.parse_args()
    result = fit(a.root, a.case) if a.mode == "fit" else validate(a.root, read(a.profile), a.case)
    write_once(a.output, result)
    print(a.mode, a.case, sha(a.output))


if __name__ == "__main__":
    main()
