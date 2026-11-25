"""Observable applicability and optical uncertainty for an unloaded, tabletop swept volume."""

import numpy as np

FREE_PHASES = ("MOVE_ABOVE", "APPROACH")
# Fixed development locality around the same measured configuration. Direction,
# speed, position, command phase and opening must all match one common sample.
TOLERANCE = np.array(
    [0.10] * 7 + [0.10] * 7 + [0.003] * 2 + [0.030] * 2 + [0.025] * 3 + [0.035] * 3
)


def state_rows(g, q, f, dq, df, center):
    _, _, tcp, _ = g.poses(q, f)
    _, _, next_tcp, _ = g.poses(q + dq / 240, f + df / 240)
    return np.concatenate((q, dq, f, df, tcp - center, 240 * (next_tcp - tcp)), axis=1)


def locate(probe, archive):
    compatible = np.flatnonzero((abs(archive - probe) <= TOLERANCE).all(axis=1))
    if not len(compatible):
        return None
    v = probe[-3:]
    rate = np.linalg.norm(v)
    candidates = archive[compatible, -3:]
    speeds = np.linalg.norm(candidates, axis=1)
    if rate <= 0.0025:
        accepted = speeds <= 0.0025
    else:
        accepted = (speeds > 0.0025) & ((candidates @ v) >= np.cos(np.radians(18)) * rate * speeds)
    return int(compatible[np.argmax(accepted)]) if accepted.any() else None


def descending(v, increments=0.0):
    v = np.asarray(v)
    extras = np.broadcast_to(increments, (3,))
    vertical = -v[..., 2] - extras[2]
    lateral = abs(v[..., 1]) + extras[1]
    return (vertical > 0.010) & (lateral <= 0.030) & (lateral <= 0.25 * vertical)


def optically_supported(marker, geometry, angle, model, axes, fingers):
    if not angle or min(fingers) < 0.035:
        return None
    ids = marker["usable_ids"]
    yaw = np.radians(angle["yaw_deg"])
    uncertainty = np.radians(angle["uncertainty_deg"])
    co, si = np.cos(yaw), np.sin(yaw)
    rot = np.array([[co, -si, 0], [si, co, 0], [0, 0, 1.0]])
    origins = []
    offsets = []
    for i in ids:
        side = str(i)
        origin = np.asarray(marker["by_id"][side]["marker_center_world_m"])
        meta = geometry["development_dual"]["markers"][side]
        shift = np.asarray(meta["object_T_marker"]).reshape(4, 4)[:3, 3]
        origins.append(origin)
        offsets.append(shift)
    if not origins:
        return None
    anchor = np.mean(offsets, axis=0)
    center = np.mean(origins, axis=0) - rot @ anchor
    height = model.table.c[2] + model.table.h[2] + model.object[0].h[2]
    if abs(center[2] - height) > 0.004:
        return None
    # The single object's registered base is on its support throughout these
    # precontact stages. The observed printed plane must corroborate that state.
    # Each original code centre has an independently measured 0.75-mm axis error.
    dirs = axes @ rot
    pads = []
    for box in model.object:
        corners = box.corners() - anchor
        x, y = corners[:, 0], corners[:, 1]
        horizontal = x[:, None] * dirs[:, 0] + y[:, None] * dirs[:, 1]
        tangent = -y[:, None] * dirs[:, 0] + x[:, None] * dirs[:, 1]
        # Bound the exact in-plane rotation of every physical box corner over
        # the independently supported yaw interval about the observed code.
        angular = (
            abs(horizontal) * (1 - np.cos(uncertainty)) + abs(tangent) * np.sin(uncertainty)
        ).max(0)
        support = 0.00075 * abs(dirs).sum(1) + angular
        if (
            angle["method"] == "one_id_and_opposite_plate_edges"
            and max(abs(box.corners()[:, 0])) <= 0.13
        ):
            # The measured transverse centres of BOTH registered plates bracket
            # these vertices. A point on the baseline is their convex combination.
            # A transverse offset contributes an additional cosine error.
            # The directly decoded endpoint has the certified colour/depth
            # registration error. The independently observed opposite centred
            # plate has signed training errors [-.548,+.472] mm (estimate−true).
            # Keep their convex weights for the specific registered solid.
            direct_y = 0.00075 * (abs(co) + abs(si))
            other_y = np.where(axes[:, 1] >= 0, 0.000935, 0.000841)
            opposite_weight = abs(box.corners()[:, 0] - anchor[0]) / 0.260
            corner_y = (direct_y + opposite_weight[:, None] * (other_y - direct_y)).max(0)
            corner_y += abs(box.corners()[:, 1]).max() * (
                abs(si) * np.sin(uncertainty) + 1 - np.cos(uncertainty)
            )
            world_x = np.array([co, -si])
            xerr = (
                0.00075 * abs(world_x).sum()
                + (
                    abs(x * world_x[0] + y * world_x[1]) * (1 - np.cos(uncertainty))
                    + abs(-y * world_x[0] + x * world_x[1]) * np.sin(uncertainty)
                ).max()
            )
            support = np.minimum(
                support,
                abs(axes[:, 0]) * xerr + abs(axes[:, 1]) * corner_y + abs(axes[:, 2]) * 0.00075,
            )
        pads.append(support)
    return center, rot, np.array(pads)
