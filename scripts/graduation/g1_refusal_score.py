"""Test static complementarity from source identity, blind measurements and frozen assignments."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from scripts.graduation import g1_mount_geometry as geo
from scripts.graduation import g1_refusal_capture as source
from scripts.graduation import proposal_camera as cam
from scripts.graduation.g1_mount_screen_score import Evidence, pose_errors
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

SIDES = ("X", "Y")
BUCKETS = ("both", "X_only", "Y_only", "neither", "unverified")


def check_normal_pair(pair, name, time_role, episode, step, seed, state_sha):
    geo.require(set(pair) == set(SIDES), "pair incomplete")
    for side, row in pair.items():
        expected = dict(
            case=name,
            time_role=time_role,
            mount_side=side,
            condition="normal",
            source_episode=episode,
            step=step,
            seed=seed,
            source_state_sha256=state_sha,
        )
        geo.require(
            all(row[k] == v for k, v in expected.items()),
            "misjoined time, identity, condition or seed",
        )
    geo.require(
        pair["X"]["state_sha256"] == pair["Y"]["state_sha256"],
        "different physical state at paired mount images",
    )


def bucket(row):
    if not row["verified"]:
        return "unverified"
    return {
        (True, True): "both",
        (True, False): "X_only",
        (False, True): "Y_only",
        (False, False): "neither",
    }[row["X"], row["Y"]]


def coverage(rows):
    counted = Counter(map(bucket, rows))
    return dict(
        allocated=len(rows),
        **{b: counted[b] for b in BUCKETS},
        X_usable=counted["X_only"] + counted["both"],
        Y_usable=counted["Y_only"] + counted["both"],
        union_usable=len(rows) - counted["unverified"] - counted["neither"],
    )


def decision(rows):
    geo.require(
        len(rows) == 16
        and len({(r["case"], r["time_role"]) for r in rows}) == 16
        and Counter((r["time_role"], r["source_side"]) for r in rows)
        == {(t, s): 4 for t in source.TIMES for s in SIDES},
        "expected 16 distinct 8x2 source poses covering both source sides",
    )
    all_rows = coverage(rows)
    triggered = bool(all_rows["X_only"] and all_rows["Y_only"])
    absent_directions = sum(all_rows[b] == 0 for b in ("X_only", "Y_only"))
    unresolved = not triggered and all_rows["unverified"] >= absent_directions
    return dict(
        triggered=triggered,
        outcome="bidirectional_complementarity"
        if triggered
        else ("unresolved" if unresolved else "bidirectional_complementarity_absent"),
        all=all_rows,
        by_time_role={t: coverage([r for r in rows if r["time_role"] == t]) for t in source.TIMES},
        by_source_side_and_time={
            s: {
                t: coverage([r for r in rows if r["time_role"] == t and r["source_side"] == s])
                for t in source.TIMES
            }
            for s in SIDES
        },
    )


def identity(row, decision_):
    return dict(
        key=row["key"],
        frame_id=row["frame_id"],
        checksum=row["checksum"],
        sha256=decision_["frame_sha256"],
        step=row["step"],
        sim_time_s=row["sim_time_s"],
        episode=row["episode"],
        scene=row["scene"],
        source_state_sha256=row["source_state_sha256"],
    )


def brief(row, dec, side):
    e = dec["by_mount"][side]
    sub = e["estimates"]["SUBPIX"]
    fit = dec["depth_fit"]
    detected = dec["detection"]
    return dict(
        **identity(row, dec),
        usable=e["usable"],
        ids=sub["ids"],
        status=sub["status"],
        reason=sub["reason"],
        direct_ids=detected["direct_ids"],
        recovered_ids=detected["recovered_ids"],
        rejected_candidates=len(detected["rejected_quads_px"]),
        marker_center_optical_depth_m=sub["marker_center_optical_depth_m"],
        marker_rotation_row_major=e["marker_rotation_row_major"],
        ordered_corners_px=fit["ordered_corners_px"],
        four_sides_px=fit["four_sides_px"],
        five_depth_patches=fit["five_patches"],
        plane=fit["plane"],
        measured_edge_lengths_m=fit["measured_edge_lengths_m"],
        marker_center_world_m=sub["marker_center_world_m"],
        object_center_world_m=sub["object_center_world_m"],
        object_top_world_m=sub["object_top_center_world_m"],
        grasp_world_m=e["grasp_world_m"],
        grasp_reason=e["grasp_reason"],
    )


def open_evidence(plan_file, raw):
    plan = pinned(plan_file, source.PLAN_SHA)
    seal = read(raw / "decision-seal.json")
    src = pinned(raw / "source-seal.json", seal["source_seal_sha256"])
    geo.require(
        raw.resolve() == (ROOT / plan["new_private"] / "cross-verified").resolve()
        and src["plan_sha256"] == source.PLAN_SHA
        and src["audit_plan_sha256"] == source.AUDIT_SHA
        and seal["capture_sha256"] == src["capture_sha256"],
        "foreign source capture",
    )
    camera = pinned(raw / "camera-commands.json", src["camera_commands_sha256"])
    for row in camera["mounts"].values():
        geo.require(
            row["verified"] == source.audit_camera_commands(row["boundaries"], row["records"])
            and row["initial"] == row["boundaries"][0]["before"],
            "camera audit differs",
        )
    orig = pinned(raw / "originals.json", src["originals_sha256"])
    ev = Evidence(raw, source.PLAN_SHA)
    gs = {source.SIDES[m["id"]]: geo.descriptor(m)[0] for m in plan["single_mounts"]}
    return plan, orig, ev, gs


def measure_pairs(plan_file, raw):
    plan, originals, ev, gs = open_evidence(plan_file, raw)
    rows, source_exposures = [], []
    for spec, pre in zip(plan["source_cases"], originals["cases"], strict=True):
        name, side = spec["case"], spec["source_side"]
        geo.require(pre["case"] == name and pre["source_side"] == side, "swapped historical case")
        actual = {}
        by_role = {}
        for t, hist in source.HISTORICAL.items():
            f, r, d = ev.get(f"{name}/source/{t}", gs[side])
            e = d["by_mount"][side]
            pack = spec["original_feedback"][hist]
            geo.require(
                r["condition"] == "actual"
                and r["source_episode"] == r["episode"] == spec["episode"]
                and r["step"] == pack["physics_step"]
                and r["source_state_sha256"] == pack["source_state_canonical_sha256"]
                and r["original_sha256"] == pack["packet_sha256"]
                and r["frame_id"] == pack["frame_id"]
                and e["estimates"]["SUBPIX"] == r["original_subpix"]
                and e["grasp_world_m"] == r["original_grasp"]
                and [p["median_optical_depth_m"] for p in e["subpix_depth_samples"]]
                == r["original_depth_m"]
                and e["usable"] == pack["grasp_usable"],
                "historical packet, five depths or pixel verdict changed",
            )
            actual[t] = (f, r, d)
            by_role[t] = {
                **brief(r, d, side),
                "original_file_sha256": r["original_sha256"],
                "captured_at": r["captured_at"],
                "original_label": r["original_label"],
            }
        source_exposures.append(dict(**pre, packets=by_role))
        for k, t in enumerate(source.TIMES):
            f0, r0, d0 = actual[t]
            joined = {s: ev.get(f"{name}/{t}/{s}/normal", gs[s]) for s in SIDES}
            meta = {s: v[1] for s, v in joined.items()}
            check_normal_pair(
                meta,
                name,
                t,
                spec["episode"],
                r0["step"],
                spec["paired_noise_seeds"][k],
                r0["source_state_sha256"],
            )
            f, r, d = joined[side]
            a0 = d0["by_mount"][side]
            a = d["by_mount"][side]
            diag = {**r["residuals"], **cam.compare(f0, f)}
            geo.require(set(diag) == set(cam.CHECK_LIMITS), "missing reconstruction check")
            statuses_match = (
                all(
                    a["estimates"]["SUBPIX"][x] == a0["estimates"]["SUBPIX"][x]
                    for x in ("status", "reason", "ids")
                )
                and a["usable"] == a0["usable"]
            )
            verified = statuses_match and all(diag[n] <= lim for n, lim in cam.CHECK_LIMITS.items())
            frames = {}
            for s, (_, sr, sd) in joined.items():
                geo.require(
                    sr["asset_sha256"] == gs[s]["pose_marker"]["marked_asset_sha256"]
                    and all(v <= cam.CHECK_LIMITS[n] for n, v in sr["residuals"].items()),
                    "wrong reconstructed side or kinematics",
                )
                frames[s] = {
                    **brief(sr, sd, s),
                    "state_sha256": sr["state_sha256"],
                    "seed": sr["seed"],
                    "asset_sha256": sr["asset_sha256"],
                    "pose_errors_m_and_rad": pose_errors(sd["by_mount"][s], sr["geometry"], gs[s]),
                }
            row = dict(
                case=name,
                time_role=t,
                source_side=side,
                source_episode=spec["episode"],
                step=r0["step"],
                source_feedback_original_sha256=r0["original_sha256"],
                source_state_sha256=r0["source_state_sha256"],
                source_side_reconstruction=diag,
                status_reason_ids_and_usable_match=statuses_match,
                verified=verified,
                X=frames["X"]["usable"],
                Y=frames["Y"]["usable"],
                normal_frames=frames,
            )
            row["bucket"] = bucket(row)
            rows.append(row)
    tables = decision(rows)
    refused = [r for r in rows if r["time_role"] == "refused"]
    rescue = {}
    for side, other in [("X", "Y"), ("Y", "X")]:
        subset = [r for r in refused if r["source_side"] == side]
        rescue[side] = dict(
            allocated=len(subset),
            verified_source_side_missing=sum(r["verified"] and not r[side] for r in subset),
            recovered_by_other_side=sum(r["verified"] and not r[side] and r[other] for r in subset),
            cases=[r["case"] for r in subset if r["verified"] and not r[side] and r[other]],
        )
    pub = plan_file.parent
    pairs_file = pub / "refusal-pairs.public.json"
    write(
        pairs_file,
        dict(
            schema="g1.first-refusal.paired-static.v1",
            plan_sha256=source.PLAN_SHA,
            capture_seal_sha256=ev.seal["capture_sha256"],
            decisions_sha256=ev.seal["decisions_sha256"],
            checks_upper_limits=cam.CHECK_LIMITS,
            actual_episodes=source_exposures,
            normal_pairs=rows,
            by_time_role=tables["by_time_role"],
            refused_recovery_by_source_side=rescue,
        ),
    )
    witnesses = {}
    for label in ("X_only", "Y_only"):
        match = next((r for r in rows if r["bucket"] == label), None)
        if match:
            witnesses[label] = {
                k: match[k]
                for k in (
                    "case",
                    "time_role",
                    "source_side",
                    "source_episode",
                    "step",
                    "source_state_sha256",
                )
            }
            witnesses[label]["normal_frames"] = {
                s: {
                    k: match["normal_frames"][s][k]
                    for k in ("frame_id", "checksum", "sha256", "usable", "key")
                }
                for s in SIDES
            }
            witnesses[label]["pair_sha256"] = source.digest_state(match)
    write(
        pub / "refusal-decision.public.json",
        dict(
            schema="g1.first-refusal.complementarity.v1",
            plan_sha256=source.PLAN_SHA,
            camera_audit_plan_sha256=source.AUDIT_SHA,
            capture_seal_sha256=ev.seal["capture_sha256"],
            blind_decisions_sha256=ev.seal["decisions_sha256"],
            paired_readings_sha256=sha(pairs_file),
            complementary=tables["triggered"],
            witnesses=witnesses,
            refused_recovery_by_source_side=rescue,
            **tables,
        ),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("plan", type=Path)
    p.add_argument("raw", type=Path)
    args = p.parse_args()
    measure_pairs(args.plan.resolve(), args.raw.resolve())


if __name__ == "__main__":
    main()
