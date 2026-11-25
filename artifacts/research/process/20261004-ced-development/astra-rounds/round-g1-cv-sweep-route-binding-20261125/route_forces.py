"""Independent finite-patch static wrench witnesses, in object axes and SI units."""

import numpy as np


def stability(tool, center, tcp, yaw, angle, patch):
    if not patch["face_supported"] or not patch["aperture_ok"]:
        return dict(status="NO_FINITE_PATCH")
    normal = np.array([np.cos(angle), np.sin(angle), 0.0])
    tangent = np.array([normal[1], -normal[0], 0.0])
    up = np.array([0.0, 0.0, 1.0])
    half = tool["target"].h
    hn = float(abs(normal) @ half)
    ht = float(abs(tangent) @ half)
    com = np.array(tool["com"])
    mg = tool["mass"] * 9.81
    mu = min([tool["registered_object_friction"], *tool["finger_slide_friction"]])
    capacity = np.multiply(tool["actuator_kp"], patch["contact_joint_positions_m"])
    limits = []
    heights = []
    for hand, _, _ in tool["fingers"]:
        c = patch["tcp_tangent_offset_m"] + hand.c[2]
        limits.append([max(-ht, c - hand.h[2]), min(ht, c + hand.h[2])])
        z = tcp[2] - center[2] - hand.c[0]
        heights.append([max(-half[2], z - hand.h[0]), min(half[2], z + hand.h[0])])
    a = max(v[0] for v in limits)
    b = min(v[1] for v in limits)
    za = max(z[0] for z in heights)
    zb = min(z[1] for z in heights)
    base = dict(
        weight_n=mg,
        mu=mu,
        nominal_static_normal_capacity_n=capacity.tolist(),
        vertical_coulomb_capacity_upper_n=float(mu * sum(capacity)),
        face_tangent_intervals_m=limits,
        face_vertical_intervals_m=heights,
        physical_bilateral_contact=False,
    )
    if base["vertical_coulomb_capacity_upper_n"] + 1e-10 < mg:
        return base | dict(
            status="PROVEN_INFEASIBLE_WEIGHT",
            proof="sum of tangential force capacity is smaller than weight",
        )
    if b <= a or za > zb or mu <= 0:
        return base | dict(status="UNKNOWN", reason="no constructive common support interval")
    # Split the upward force between faces, then interpolate its line of action at
    # the projected centre of mass. Extrapolation legitimately requires a pair of
    # opposing vertical forces on the same face. Friction capacity checks each one.
    f = tangent @ com
    fn = normal @ com
    factors = np.array([(hn + fn) / (2 * hn), (hn - fn) / (2 * hn)])
    each = mg * factors[:, None] * np.array([(b - f) / (b - a), (f - a) / (b - a)])[None, :]
    N = np.max(np.abs(each), axis=0) / mu
    loads = np.repeat(sum(N), 2)
    if np.any(loads > capacity + 1e-9):
        return base | dict(
            status="UNKNOWN",
            reason="constructed normals exceed a cap",
            normal_each_n=loads.tolist(),
        )
    vertices = []
    forces = []
    moments = []
    margin = np.inf
    z = np.clip(com[2], za, zb)
    for side, sign in enumerate((1, -1)):
        for j, t in enumerate((a, b)):
            X = sign * hn * normal + t * tangent + z * up
            force = -sign * N[j] * normal + up * each[side, j]
            inward = -sign * float(force @ normal)
            slip = float(np.linalg.norm(force + sign * inward * normal))
            margin = min(margin, mu * inward - slip)
            assert inward >= -1e-10 and slip <= mu * inward + 1e-10
            assert (
                abs(X @ normal - sign * hn) < 1e-9
                and limits[side][0] - 1e-9 <= X @ tangent <= limits[side][1] + 1e-9
                and heights[side][0] - 1e-9 <= X[2] <= heights[side][1] + 1e-9
            )
            vertices.append(
                dict(
                    side=side,
                    point_object_m=X.tolist(),
                    force_n=force.tolist(),
                    normal_n=inward,
                    tangential_n=slip,
                )
            )
            forces.append(force)
            moments.append(np.cross(X - com, force))
    res = np.sum(forces, axis=0) - mg * up
    mom = np.sum(moments, axis=0)
    assert np.max(abs(res)) < 1e-8 and np.max(abs(mom)) < 1e-8
    return base | dict(
        status="WITNESS",
        normal_each_n=loads.tolist(),
        face_contacts=vertices,
        force_residual_n=res.tolist(),
        moment_about_com_residual_nm=mom.tolist(),
        min_coulomb_margin_n=float(margin),
        capacity_margin_n=(capacity - loads).tolist(),
    )
