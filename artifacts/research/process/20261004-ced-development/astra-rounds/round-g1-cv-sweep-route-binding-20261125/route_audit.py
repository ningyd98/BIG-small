"""Compare the locked candidate generations only after both independent readings agree."""

import base64
import gzip
import json
from collections import Counter
from pathlib import Path

from route_batch import PARENT, PLAN, ROUND, encode, read, sha
from route_independent import envelope_verification, native_check, original_lp, verify_force
from route_physical_audit import command_limits, contact_readback
from sweep_geometry import parse_tool


def decoded(x):
    return json.loads(gzip.decompress(base64.b64decode(x)))


def main():
    package = read(ROUND / "route-candidates.public.json")
    new = decoded(package["data_base64"])
    history = read(PARENT / "sweep-candidates.public.json")
    blind = read(PARENT / "sweep-prospective.public.json")
    prior = decoded(history["gzip_base64"]) + decoded(blind["full_predictions"]["data_base64"])
    imports = read(PARENT / "plan.json")["planning_frames"]
    root = Path(
        "assets/robots/franka_panda/scene_g1_development_dual_id7_y130_id8_x130_low_bracket_v3.xml"
    )
    X = [Path(x["assembly_xml"]) for x in imports] + [root, root]
    summary = []
    envelopes = {}
    old_count = 0
    new_count = 0
    oldf = oldm = newf = newm = 0.0
    for i, (old, fr, path) in enumerate(zip(prior, new, X, strict=True)):
        assert fr["frame_id"] == old["frame_id"] and fr["checksum"] == old["checksum"]
        tool = parse_tool(path)
        flag = package["readback_first"][i]["key"]
        moves = Counter()
        geom = Counter()
        statics = Counter()
        compensated = []
        center = []
        part_counts = Counter()
        unobserved = Counter()
        all_free = 0
        for a, b in zip(old["candidates"], fr["candidates"], strict=True):
            assert a["candidate_id"] == b["candidate_id"]
            moves[a["full_physical_clearance"] + " -> " + b["full_physical_clearance"]] += 1
            geom[a["geometric_status"] + " -> " + b["geometric_status"]] += 1
            statics[a["load_support"]["status"] + " -> " + b["load_support"]["status"]] += 1
            for p in {e[1] for e in b["hits"]}:
                part_counts[p] += 1
            if b["tangent_mm"] == 0:
                center.append(
                    dict(
                        direction=b["direction"],
                        full=b["full_physical_clearance"],
                        geom=b["geometric_status"],
                        hits=b["hits"],
                    )
                )
            if b["geometric_status"] == "CLEAR":
                compensated.append(b)
                for part in {e["part"] for e in b["phase_evidence"] if e["ray"] != "FREE"}:
                    unobserved[part] += 1
                all_free += b["clearance"] == "CLEAR"
            if a["load_support"]["status"] == "nominal_static_equilibrium":
                f, m = original_lp(old, a, tool)
                old_count += 1
                oldf = max(oldf, f)
                oldm = max(oldm, m)
            if b["load_support"]["status"] == "WITNESS":
                f, m = verify_force(b["load_support"], tool)
                new_count += 1
                newf = max(newf, f)
                newm = max(newm, m)
        if flag in ("A", "B"):
            envelopes[flag] = envelope_verification(fr, tool)

        def rank(b):
            return (
                -b["registered_min_sep_bound_mm"],
                -min(b["patch"]["contact_area_each_mm2"]),
                abs(b["tangent_mm"]),
            )

        best = min(compensated, key=rank) if compensated else None
        fixed = [r for r in fr["candidates"] if r["original_orientation"]]
        summary.append(
            dict(
                key=flag,
                frame_id=fr["frame_id"],
                checksum=fr["checksum"],
                frame_sha256=package["readback_first"][i]["frame_sha256"],
                geometry_transitions=dict(geom),
                dispatch_geometry_transitions=dict(moves),
                wrench_transitions=dict(statics),
                counts=fr["counts"],
                nominal=fr["nominal_counts"],
                optical=fr["observed_sweep_counts"],
                zero_offset=center,
                candidates_with_registered_part_contact=dict(part_counts),
                nominal_clear_with_unobserved_part=dict(unobserved),
                geometry_eligible_with_all_required_rays_clear=all_free,
                prospective_selected=fr["selected"],
                fixed_wrist_count=len(fixed),
                fixed_finite_face=sum(r["patch"]["face_supported"] for r in fixed),
                hypothetical_alignment=fixed[0]["passive_alignment"],
                nominal_best={
                    k: best[k]
                    for k in (
                        "candidate_id",
                        "orientation_wxyz",
                        "target_high_m",
                        "target_low_m",
                        "registered_min_sep_bound_mm",
                        "known_components_inflated_sep_bound_mm",
                        "volume_bounds",
                        "full_reasons",
                        "patch",
                        "load_support",
                    )
                }
                if best
                else None,
                high_direct_group_summary={
                    k: {
                        kk: v.get(kk)
                        for kk in (
                            "status",
                            "members",
                            "segments",
                            "max_vertex_motion_mm",
                            "within_segment_pad_mm",
                            "minimum_union_gap_mm",
                            "actual_midpoint_hits",
                            "max_family_center_displacement_mm",
                            "first_unconfirmed_ray_box",
                        )
                    }
                    for k, v in fr["initial_routes"].items()
                },
            )
        )
    result = dict(
        schema="g1.direct-route.independent-readback.v2",
        plan_sha256=PLAN,
        first_generation_seal_sha256=sha(PARENT / "sweep-seal.public.json"),
        candidate_seal_sha256=sha(ROUND / "route-candidates.public.json"),
        source_sha256={
            s: sha(ROUND / s)
            for s in ("route_audit.py", "route_independent.py", "route_physical_audit.py")
        },
        native_targets=native_check(new),
        old_verified_lp=dict(
            count=old_count, max_force_residual_n=oldf, max_moment_residual_nm=oldm
        ),
        new_analytic_witnesses=dict(
            count=new_count, max_force_residual_n=newf, max_moment_residual_nm=newm
        ),
        containment=envelopes,
        physically_observed=contact_readback(),
        command_bounds=command_limits(root),
        candidate_frames=summary,
        formal_runs=0,
        new_physical_steps=0,
    )
    with (ROUND / "route-audit.public.json").open("xb") as f:
        f.write(encode(result))
    print(
        sha(ROUND / "route-audit.public.json"),
        result["native_targets"],
        result["old_verified_lp"],
        result["new_analytic_witnesses"],
    )


if __name__ == "__main__":
    main()
