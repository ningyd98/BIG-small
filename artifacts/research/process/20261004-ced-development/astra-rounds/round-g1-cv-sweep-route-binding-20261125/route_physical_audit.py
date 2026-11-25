"""Read the two archived first contacts and bound commanded joint setpoint motion."""

import sys
from pathlib import Path
from xml.etree import ElementTree

import mujoco
import numpy as np
from route_geometry import PARENT
from sweep_geometry import Box, clearance, parse_tool, values

sys.path.insert(0, str(PARENT.parent / "round-g1-dual-support-contact-diagnosis-20261125"))
import contact_geometry as old


def contact_readback():
    result = {}
    for mount, stop in ((15, 1221), (30, 1228)):
        case = old.screen.checked_case(old.TRIALS[mount])
        p = old.exact_asset(mount)

        def prohibited(st):
            return [
                pair
                for pair in st["contact_pairs"]
                if any("finger_geom" in n or n == "hand" for n in pair)
                and any(n.startswith("g1_dual_id") for n in pair)
            ]

        hits = [(i, prohibited(s)) for i, s in enumerate(case["states"]) if prohibited(s)]
        assert hits[0][0] == stop
        m = mujoco.MjModel.from_xml_path(str(p))
        d = mujoco.MjData(m)
        t1 = case["states"][stop - 1]
        t2 = case["states"][stop]
        pair = hits[0][1][0]
        evidence = []
        for step, s in ((stop - 1, t1), (stop, t2)):
            residual = old.screen.restore(m, d, s)
            ends = []
            for name in pair:
                geo = m.geom(name)
                w = d.geom(name)
                ends.append(Box(name, w.xpos.copy(), geo.size.copy(), w.xmat.reshape(3, 3).copy()))
            signed = clearance(*ends)
            native = [
                float(c.dist * 1000)
                for c in d.contact
                if {c.geom1, c.geom2} == {m.geom(pair[0]).id, m.geom(pair[1]).id}
            ]
            evidence.append(
                dict(
                    step=step,
                    physics_seconds=step / 240,
                    registered_pair=pair,
                    signed_sat_mm=1000 * signed,
                    physics_contact_dist_mm=native,
                    source_contact_names=prohibited(s),
                    FK_TCP_mm=1000 * residual["tcp_residual_m"],
                )
            )
        assert evidence[0]["signed_sat_mm"] > 0 and evidence[1]["signed_sat_mm"] < 0
        result[str(mount)] = dict(
            dense_saved_steps=len(case["states"]),
            first_archived_stop=stop,
            bracket=evidence,
            dt_s=1 / 240,
            measured_extra_physics_steps_after_stop=0,
            physical_braking_distance_upper_bound_m=None,
        )
    return result


def command_limits(xml: Path):
    tool = parse_tool(xml)
    world = ElementTree.parse(xml).find(".//body[@name='panda_link0']")
    origins = []
    b = world
    while b is not None:
        if b.find("joint") is not None:
            origins.append(values(b, "pos", "0 0 0"))
        if b.get("name") == "panda_hand":
            break
        b = b.find("body")
    lengths = np.array([np.linalg.norm(o) for o in origins])
    tip = values(b.find("site[@name='tcp']"), "pos", "0 0 0")
    parts = {}
    # The moment arm is an upper bound over all robot configurations by the triangle inequality.
    for box, sg, rng in [(tool["palm"], 0, [0.0, 0.0]), *tool["fingers"]]:
        c = box.c.copy() + tip
        c[1] += sg * rng[1]
        end = float(np.linalg.norm(np.abs(c) + box.h))
        arms = np.array([lengths[j + 1 :].sum() + end for j in range(7)])
        dt = 5 / 240
        parts[box.name] = dict(
            downstream_radius_upper_m=arms.tolist(),
            command_speed_bound_m_s=float(1.5 * sum(arms)),
            command_one_5_step_interval_mm=float(1000 * 1.5 * dt * sum(arms)),
            command_first_5_step_interval_from_measured_rest_mm=float(
                1000 * 4.0 * dt**2 * sum(arms)
            ),
            command_100ms_path_bound_any_initial_speed_mm=float(1000 * 1.5 * 0.1 * sum(arms)),
        )
    return dict(
        physics_step_s=1 / 240,
        control_interval_s=5 / 240,
        velocity_limit_rad_s=1.5,
        acceleration_limit_rad_s2=4.0,
        per_part=parts,
        physical_tracking_and_stop_bound_mm=None,
        applicability=(
            "Consecutive commanded joint setpoints. The packets do not bound "
            "deviations from setpoints or post-stop motion under compliant actuators."
        ),
    )
