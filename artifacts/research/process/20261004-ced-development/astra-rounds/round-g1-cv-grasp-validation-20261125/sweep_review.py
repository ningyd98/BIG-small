"""Review the sealed first-generation candidates against the native direction and high target."""

import base64
import gzip
import json
from collections import Counter
from pathlib import Path

import numpy as np
from binding import check_direction
from sweep_history import ROUND, digest, encoded

from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD


def audit(first, seconde):
    h = json.loads(gzip.decompress(base64.b64decode(first["gzip_base64"])))
    p = json.loads(gzip.decompress(base64.b64decode(seconde["full_predictions"]["data_base64"])))
    comparisons = []
    analyses = []
    for kind, rows in (("historical", h), ("prospective_blind", p)):
        for i, fr in enumerate(rows):
            labeled = [e for e in fr["candidates"] if e["geometric_status"] == "CLEAR"]
            nominal_by_dir = Counter(e["direction"] for e in labeled)
            fixed = [e for e in fr["candidates"] if e["original_orientation"]]
            freepix = [e for e in labeled if e["ray_counts"].get("free", 0)]
            constrained = [e for e in labeled if e["clearance"] == "CLEAR"]
            analyses.append(
                dict(
                    source=kind,
                    frame_id=fr["frame_id"],
                    nominal_registered_by_axis=dict(nominal_by_dir),
                    fixed_count=len(fixed),
                    fixed_registered_clear=sum(e["geometric_status"] == "CLEAR" for e in fixed),
                    fixed_finite_face=sum(e["patch"]["face_supported"] for e in fixed),
                    fixed_aperture_ok=sum(e["patch"]["aperture_ok"] for e in fixed),
                    min_fixed_face_normal_difference_deg=min(
                        e["patch"]["face_alignment_error_deg"] for e in fixed
                    ),
                    nominal_candidates_with_positive_local_FREE=len(freepix),
                    nominal_candidates_all_rays_clear=len(constrained),
                    nominal_candidates_with_mixed_or_hidden_or_invalid=sum(
                        any(
                            e["ray_counts"].get(s, 0) > 0
                            for s in ("mixed", "behind", "invalid", "footprint_boundary", "outside")
                        )
                        for e in labeled
                    ),
                    nominal_wrench_balanced=sum(
                        e["load_support"]["status"] == "nominal_static_equilibrium" for e in labeled
                    ),
                )
            )
            if kind != "prospective_blind":
                continue
            fixed0 = next(e for e in fixed if e["tangent_mm"] == 0)
            q = fixed0["orientation_wxyz"]
            try:
                check_direction(q)
                fixed_decision = "eligible_orientation"
            except ValueError as exc:
                fixed_decision = str(exc)
            check_direction(list(_DOWNWARD))
            high = np.array(fr["high_tcp_m"])
            start = np.array(fr["measured_robot"]["tcp_m"])

            def ranking(e):
                return (
                    -e["registered_min_sep_bound_mm"],
                    -min(e["patch"]["contact_area_each_mm2"]),
                    abs(e["tangent_mm"]),
                )

            best = min(labeled, key=ranking)
            delta = np.array(best["world_offset_m"])
            full_delta = (
                np.array(fr["marker"]["rotation_object_to_world"]).reshape(3, 3)
                @ best["offset_object_m"]
            )
            # Native component holds MOVE_ABOVE's registered z. Its XY changes with selected grasp.
            native_hi = high.copy()
            native_hi[:2] += full_delta[:2]
            center_half = 0.5 * (start + high)
            native_half = 0.5 * (start + native_hi)
            comparisons.append(
                dict(
                    blind_slot=("A", "B")[i],
                    frame_id=fr["frame_id"],
                    source_initial=fr["measured_robot"]["reason"],
                    nominal_candidate=best["candidate_id"],
                    start_m=start.tolist(),
                    central_initial_high_m=high.tolist(),
                    candidate_planar_high_m=(high + delta).tolist(),
                    candidate_full_rotation_shift_m=full_delta.tolist(),
                    nominal_binding_high_m=native_hi.tolist(),
                    midpoint_shared_m=center_half.tolist(),
                    midpoint_direct_m=native_half.tolist(),
                    endpoint_distance_mm=float(1000 * np.linalg.norm(native_hi - high)),
                    same_fraction_midpoint_distance_mm=float(
                        1000 * np.linalg.norm(native_half - center_half)
                    ),
                    effect_of_full_object_rotation_minus_nominal_xyz_mm=(
                        1000 * (full_delta - delta)
                    ).tolist(),
                    fixed_source_q=q,
                    strict_native_q=list(_DOWNWARD),
                    native_fixed_source_decision=fixed_decision,
                    native_exact_constant_control="accepted",
                    angular_wxyz_equal_to_roundoff=bool(
                        np.allclose(q, _DOWNWARD, atol=3e-16, rtol=0)
                    ),
                    actual_dispatch=False,
                )
            )
    return dict(
        first_plan_sha256="596158c29f9d43573a92c2be22a5b9db55e5d8b21f08cc8382e65e3d8b7ffb1a",
        review_only=True,
        sealed_sources_sha256={
            nm: digest((ROUND / nm).read_bytes())
            for nm in (
                "sweep-seal.public.json",
                "sweep-candidates.public.json",
                "sweep-prospective.public.json",
                "binding.py",
            )
        },
        centered_vs_tangent_high=comparisons,
        all_frames=analyses,
        recorded_limits=dict(
            incremental_feedback_correction_mm=10,
            absolute_target_correction_mm=50,
            arrival_tcp_mm=5,
            arrival_angle_deg=5,
            capture_ik_deadline_ms=100,
            reach_or_hold_error_converted_to_uniform_tracking_tube=None,
            same_step_emergency_command_braking_distance_mm=None,
            tracked_position_crosscheck_as_uniform_pose_bound=None,
        ),
        conclusion=(
            "See per-frame fixed-axis finite-face counts and observed unknown volumes. "
            "The initial measured-to-central-high calculation was shared by direction. "
            "Offset-specific measured-to-high motion needs independent coverage."
        ),
    )


if __name__ == "__main__":
    result = audit(
        json.loads((ROUND / "sweep-candidates.public.json").read_bytes()),
        json.loads((ROUND / "sweep-prospective.public.json").read_bytes()),
    )
    result["audit_source_sha256"] = digest(Path(__file__).read_bytes())
    with (ROUND / "sweep-review.public.json").open("xb") as f:
        f.write(encoded(result))
