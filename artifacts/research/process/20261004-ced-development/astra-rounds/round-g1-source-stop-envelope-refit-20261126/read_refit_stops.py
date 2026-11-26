"""Fit source-world growth on sealed training stops or challenge it independently."""

import argparse
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from precheck_expansion import (
    HERE,
    PANDA,
    REPO,
    ROOTS,
    decode,
    evaluate,
    input_path,
    require,
    source,
)
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_payload import (
    AXES,
    SPEED_CLASSES,
    PayloadClearance,
    object_matrix,
    positive_support,
    snapshot,
)
from scripts.graduation.perception_io import pinned, read, sha, write

OUT = ROOTS["output"]
ACQUISITION = read(HERE / "stop-acquisition-registration.json")
REG = read(HERE / "fit-analysis-registration.json")
ALLOWED = {
    ("left_finger_geom", "object_geom"),
    ("object_geom", "right_finger_geom"),
    ("object_geom", "table"),
}
BILATERAL = ALLOWED - {("object_geom", "table")}
OLD_T01 = REPO / "experiments/results/g1-t01-lift55-native-qualification-20261126/stop-readback-01"


def arr(path, expected):
    require(sha(path) == expected, f"changed state file {path.name}")
    with np.load(path, allow_pickle=False) as f:
        return {k: f[k] for k in f.files}


def integer_key(n):
    return str(int(n))


def acquire_package(case, inventory):
    role = ACQUISITION["roles"][case]
    base = OUT / role / case
    if role == "fit":
        seal = pinned(base / "seal.json", REG["training_acquisition_seal_sha256"][case])
    else:
        seal = read(base / "seal.json")
    require(
        seal["case"] == case
        and seal["role"] == role
        and seal["registration_sha256"] == sha(HERE / "stop-acquisition-registration.json")
        and seal["source_sha256"] == REG["acquisition_source_sha256"]
        and seal["inventory_sha256"] == ACQUISITION["window_inventory_sha256"]
        and sorted(map(int, seal["new_stops"])) == inventory["new_stop_triggers_needed"]
        and seal["stop_steps"] == 240 * len(seal["new_stops"])
        and seal["normal_steps"] == ACQUISITION["normal_end"][case]
        and seal["steps"] == seal["normal_steps"] + seal["stop_steps"]
        and seal["exposures"] == 0
        and seal["resets"] == 1,
        "acquisition lineage or exact CPU budget differs",
    )
    normal = arr(base / "normal.npz", seal["normal_sha256"])
    contacts = pinned(base / "contacts.json", seal["normal_contacts_sha256"])
    if case == "grid04":
        inherited = read(source("midRaw/reader-1.json"))["all_file_sha256"]
    elif case == "t01":
        inherited = pinned(
            OLD_T01 / "result.json",
            "9bdc00b088f825a73750a8897aff19081ddf9205afbc72365d0c9f1fc7913732",
        )["branches"]
    else:
        inherited = {}
    return base, seal, normal, contacts, inherited


def branch(case, tick, target, base, seal, inherited):
    key = integer_key(tick)
    if key in seal["new_stops"]:
        item = seal["new_stops"][key]
        path = base / "stops" / f"stop-{key}.npz"
        state = arr(path, item["state_sha256"])
        contacts = pinned(path.with_suffix(".json"), item["contacts_sha256"])
        return state["q"], state["dq"], contacts
    expected = target["reusable_stop_state_bytes_sha256"][key]
    if case == "grid04":
        member = f"stops/stop-{key}.npz"
        require(inherited[member] == expected, "wrong original grid04 stop digest")
        path = ROOTS["midRaw"] / member
        state = arr(path, expected)
        contacts = pinned(path.with_suffix(".json"), inherited[f"stops/stop-{key}.json"])
        return state["q"], state["dq"], contacts
    require(case == "t01", "unregistered reuse in the challenge")
    member = f"{key}-after_integration.npz"
    require(inherited[member] == expected, "wrong t01 replay branch")
    state = arr(OLD_T01 / member, expected)
    contacts = [
        [n for n, c in zip(state["pair_names"].tolist(), counts, strict=True) for _ in range(c)]
        for counts in state["contact_counts"]
    ]
    return state["q"], state["qvel"], contacts


def contact_failure(pairs):
    contacts = set(map(tuple, pairs))
    return not BILATERAL <= contacts <= ALLOWED


def motion_bounds(motion, q, dq, world_anchor, relative_anchor, directions):
    w, v, r, rv = snapshot(motion, q, dq, q[:, 9:12], object_matrix(q))
    world = positive_support(w, v, world_anchor, AXES)
    relative = positive_support(r, rv, relative_anchor, directions)
    scaled = v / 720
    delta = w - world_anchor
    nodes = np.concatenate((delta, delta[:-1] + scaled[:-1], delta[1:] - scaled[1:]))
    project = nodes @ AXES.T
    nearly = np.maximum(0, project.max(axis=(0, 2)))
    require(np.array_equal(world, nearly), "world support witness projection diverges")
    flat = project.transpose(1, 3, 0, 2).reshape(len(motion.names), len(AXES), -1)
    winner = flat.argmax(axis=-1)
    return world, relative, winner, len(w), w.shape[2]


def frame_sources(case):
    if case == "t01":
        decision_rows = read(source("t01/local-clearance.json"))["rows"]
        raw = pinned(
            source("t01/pixel-index.json"),
            read(source("t01/acquisition-seal.json"))["index_sha256"],
        )
        frames = {x["frame_id"]: x for x in raw["frames"]}
        return {
            row["physics_step"]: (
                row["robot"],
                row["evidence"],
                frames[row["frame_id"]],
                raw["episode"],
                raw["scene"],
            )
            for row in decision_rows
            if row["phase"] == "FEEDBACK" and row["skill"] == "LIFT"
        }
    decisions = read(source(f"{case}/clearance-gate.json"))["checks"]
    index = read(source(f"{case}/rgbd-index.json"))
    frames = {x["robot"]["frame_id"]: x for x in index["rows"]}
    return {
        row["step"]: (
            frames[row["frame_id"]]["robot"],
            row["current"],
            frames[row["frame_id"]],
            index["episode_id"],
            index["scene_id"],
        )
        for row in decisions
        if row["phase"] == "FEEDBACK" and row["skill"] == "LIFT"
    }


def gate_source(case, tick, raw, calibration):
    robot, evidence, item, episode, scene = raw
    path = input_path(f"{case}/{item['file']}")
    require(sha(path) == item["file_sha256"], "changed original exposure bytes")
    f = decode(path)
    camera = calibration["primary_camera"]
    require(
        f.model_dump(mode="json", include=set(camera)) == camera
        and f.episode_id == episode
        and f.scene_id == scene
        and f.frame_id == robot["frame_id"] == evidence["frame_id"]
        and f.checksum_sha256 == robot["checksum_sha256"] == evidence["checksum_sha256"]
        and f.sim_time_s == robot["sim_time_s"] == robot["camera_encoder_sim_time_s"]
        and robot["physics_step"] == tick
        and evidence["status"] == "CLEAR"
        and robot["handoff"]["current_step"] == tick
        and evidence["depth"]["unknown_pixels"] == 0,
        "wrong source exposure, original authorization or simultaneous encoders",
    )
    return robot, evidence


def source_windows(case, target, motion, directions):
    base, seal, normal, contact_rows, inherited = acquire_package(case, target)
    source_frames = frame_sources(case)
    q, dq = normal["q"], normal["dq"]
    need = {row["tick"] for row in target["enrolled_windows"]}
    triggers = {}
    file_cache = {}
    windows = []
    for row in target["enrolled_windows"]:
        start = row["tick"]
        require(
            row["verified_old_command_delay_indices"] == list(range(9)),
            "incomplete normal source window",
        )
        dc = contact_rows[start : start + 9]
        q0, dq0 = q[start][None], dq[start][None]
        anc, _, rel, _ = snapshot(motion, q0, dq0, q0[:, 9:12], object_matrix(q0))
        old_rel = source_frames[start][1]["short_motion"]["speed_class"]
        old_world = source_frames[start][1]["short_motion"]["registered_source_speed_class"]
        require(
            old_world == row["original_selected_class"] and len(dc) == 9,
            "source speed class changed",
        )
        speed = float(abs(dq[start, :7]).max())
        allowed_classes = ["all", *(str(k) for k in SPEED_CLASSES if speed <= k)]
        require(
            old_world in allowed_classes,
            "recorded source speed class does not contain native speed",
        )
        window_world = np.zeros((len(motion.names), 6))
        window_relative = np.zeros((motion.load_start, len(directions)))
        provenance = {}
        violations = []
        if any(contact_failure(c) for c in dc):
            violations.append("original normal window contact is outside named source contract")
        for delay in range(9):
            tick = start + delay
            if tick not in file_cache:
                stop_q, stop_dq, contacts = branch(case, tick, target, base, seal, inherited)
                incoming_contacts = Counter(map(tuple, contact_rows[tick]))
                archived_contacts = Counter(map(tuple, contacts[0]))
                reusable_grid_stop = case == "grid04" and str(tick) not in seal["new_stops"]
                compatible_contacts = (
                    archived_contacts.keys() == incoming_contacts.keys()
                    if reusable_grid_stop
                    else archived_contacts == incoming_contacts
                )
                require(
                    stop_q.shape == (241, 16)
                    and stop_dq.shape == (241, 15)
                    and np.isfinite(stop_q).all()
                    and np.isfinite(stop_dq).all()
                    and np.array_equal(stop_q[0], q[tick])
                    and np.array_equal(stop_dq[0], dq[tick])
                    and len(contacts) == 241
                    and compatible_contacts,
                    f"stop origin/cache/geometry differs at {case} {tick}",
                )
                file_cache[tick] = (stop_q, stop_dq, contacts)
            stop_q, stop_dq, contacts = file_cache[tick]
            fault = next((n for n, p in enumerate(contacts) if contact_failure(p)), None)
            if fault is not None:
                violations.append(
                    {"trigger": tick, "stop_offset": fault, "contacts": contacts[fault]}
                )
            pos = np.concatenate((q[start:tick], stop_q))
            rate = np.concatenate((dq[start:tick], stop_dq))
            world, relative, indices, length, corners = motion_bounds(
                motion, pos, rate, anc[0], rel[0], directions
            )
            for j, k in np.argwhere((world >= window_world) & (world > 0)):
                node, corner = divmod(int(indices[j, k]), corners)
                if node < length:
                    step, kind = node, "endpoint"
                elif node < 2 * length - 1:
                    step, kind = node - length, "outgoing_control"
                else:
                    step, kind = node - (2 * length - 1) + 1, "incoming_control"
                key = (motion.names[j], k)
                detail = {
                    "trigger": tick,
                    "delay": delay,
                    "offset_from_trigger": step - delay,
                    "node": kind,
                    "corner": corner,
                }
                if world[j, k] > window_world[j, k]:
                    provenance[key] = [detail]
                else:
                    provenance[key].append(detail)
            window_world = np.maximum(window_world, world)
            window_relative = np.maximum(window_relative, relative)
            triggers[tick] = True
        windows.append(
            {
                "tick": start,
                "speed": speed,
                "classes": allowed_classes,
                "selected_source": old_world,
                "selected_relative": old_rel,
                "world": window_world,
                "relative": window_relative,
                "provenance": provenance,
                "contact_violations": violations,
            }
        )
    require(
        len(triggers) == target["distinct_triggers"] and len(need) == len(windows),
        "window or trigger coverage differs",
    )
    return windows, source_frames, sha(base / "seal.json")


def profiles():
    source_profile = read(
        source("runtime/scripts/graduation/g1_complete_cv_source_motion_profile.json")
    )
    motion_profile = read(source("runtime/scripts/graduation/g1_complete_cv_payload_profile.json"))
    return source_profile, motion_profile


def fit_profiles(old, collections, motion, data_hashes):
    rows = {}
    result = dict(old, sources=dict(old["sources"], **data_hashes))
    for key, old_class in old["classes"].items():
        best = np.asarray(old_class["world"]).copy()
        sources = set(old_class["sources"])
        count = old_class["windows"]
        evidence = {}
        for case, windows in collections.items():
            for win in windows:
                if key not in win["classes"]:
                    continue
                count += 1
                sources.add(case)
                measured = win["world"]
                for i, j in np.argwhere((measured >= best) & (measured > old_class["world"])):
                    record = {
                        "case": case,
                        "window": win["tick"],
                        "support_m": float(measured[i, j]),
                        "maximizers": win["provenance"][motion.names[i], j],
                    }
                    axis = f"{motion.names[i]}:{j}"
                    if measured[i, j] > best[i, j]:
                        evidence[axis] = [record]
                    else:
                        evidence[axis].append(record)
                best = np.maximum(best, measured)
        old_a = np.asarray(old_class["world"])
        grown = np.maximum(old_a, np.where(best > old_a, np.ceil(best * 1e8) / 1e8, old_a))
        require((grown >= old_a).all(), "a conservative refit shrank old authority")
        rows[key] = {
            "world": grown.tolist(),
            "windows": count,
            "sources": sorted(sources),
            "fit_support_witnesses": evidence,
        }
    rows_without_witnesses = {
        k: {j: x for j, x in v.items() if j != "fit_support_witnesses"} for k, v in rows.items()
    }
    previous = None
    for label in [*(str(s) for s in SPEED_CLASSES), "all"]:
        if label in rows:
            current = np.asarray(rows[label]["world"])
            require(
                previous is None or (current >= previous).all(), "source speed class nesting broken"
            )
            previous = current
    return dict(result, classes=rows_without_witnesses), {
        k: v["fit_support_witnesses"] for k, v in rows.items()
    }


def case_checks(case, enrolled, frames, old, new, cal, views):
    detail = []
    minimum_original = float("inf")
    minimum_new = float("inf")
    for row in enrolled:
        tick = row["tick"]
        robot, e = gate_source(case, tick, frames[tick], cal)
        src = row["selected_source"]
        rel = new.data["LIFT"]["classes"][row["selected_relative"]]["relative"]
        original = old.source_classes[src][0] - row["world"]
        candidate = new.source_classes[src][0] - row["world"]
        ri = rel - row["relative"]
        base = evaluate(old, robot, e, views, src, 0, 0, None)
        tested = evaluate(new, robot, e, views, src, 0, 0, None)
        exact = e["short_motion"]
        require(
            base["predicate"]["reason"] == exact["reason"]
            and base["predicate"]["reference"] == exact["reference"]
            and base["predicate"]["limiting_pair"] == exact["limiting_pair"]
            and abs(base["predicate"]["minimum_gap_m"] - exact["minimum_gap_m"]) <= 1e-12,
            f"frozen clearance admission did not re-read at {case} {tick}",
        )
        minimum_original = min(minimum_original, float(original.min()))
        minimum_new = min(minimum_new, float(candidate.min()))
        j, k = np.unravel_index(candidate.argmin(), candidate.shape)
        detail.append(
            {
                "tick": tick,
                "source_class": src,
                "arm_speed_rad_s": row["speed"],
                "world_original_min_m": float(original.min()),
                "world_refit_min_m": float(candidate.min()),
                "refit_worst_world_part": new.motion.names[j],
                "refit_worst_world_axis": AXES[k].tolist(),
                "relative_original_min_m": float(ri.min()),
                "stop_contact_violations": row["contact_violations"],
                "old_spatial_min_m": base["predicate"]["minimum_gap_m"],
                "new_spatial_min_m": tested["predicate"].get("minimum_gap_m"),
                "new_volume_min_m": tested["minimum_best_view_m"],
                "new_spatial_reason": tested["predicate"]["reason"],
            }
        )

    def qualified(x):
        return (
            x["world_refit_min_m"] >= 0
            and x["relative_original_min_m"] >= 0
            and not x["stop_contact_violations"]
            and x["new_spatial_reason"] is None
        )

    return {
        "frames": detail,
        "checks_passing": sum(qualified(x) for x in detail),
        "checks": len(detail),
        "old_world_min_m": minimum_original,
        "refit_world_min_m": minimum_new,
    }


def load_optics():
    from precheck_expansion import VIEWS

    c = read(source("calibration/manifest.json"))
    views = {}
    for k in VIEWS:
        row = c["maps"][k]
        path = input_path("calibration/" + row["depth_file"])
        require(sha(path) == row["depth_sha256"], "changed coverage map")
        views[k] = row["camera"], np.load(path, allow_pickle=False)
    return c, views


def common(names):
    inv = pinned(OUT / "inventory-1.json", ACQUISITION["window_inventory_sha256"])["inventory"]
    source_profile, payload_profile = profiles()
    motion = MotionGeometry(Model(source("runtime/" + PANDA)))
    old = PayloadClearance(motion, payload_profile, source_profile)
    windows, frames, hashes = {}, {}, {}
    for case in names:
        windows[case], frames[case], hashes[case] = source_windows(
            case, inv[case], motion, old.axes
        )
    return motion, old, windows, frames, hashes, source_profile, payload_profile


def stop_challenge_access(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = str(args[0])
        if "/challenge/" in path or "g1-lift-grid-02/" in path:
            raise PermissionError("fitter cannot open grid02 data")


def fitting(reader):
    sys.addaudithook(stop_challenge_access)
    motion, old, windows, frames, hashes, source_profile, payload_profile = common(
        ("grid04", "t01")
    )
    profile, witness = fit_profiles(source_profile, windows, motion, hashes)
    new = PayloadClearance(motion, payload_profile, profile)
    cal, views = load_optics()
    result = {c: case_checks(c, win, frames[c], old, new, cal, views) for c, win in windows.items()}
    write(
        OUT / "fit" / f"{reader}.json",
        {
            "profile": profile,
            "fit_witnesses": witness,
            "checks": result,
            "readback_source_sha256": sha(Path(__file__)),
            "fit_analysis_registration_sha256": sha(HERE / "fit-analysis-registration.json"),
            "training_seal_sha256": hashes,
            "inventory_sha256": ACQUISITION["window_inventory_sha256"],
            "ready_for_challenge": all(x["checks"] == x["checks_passing"] for x in result.values()),
            "challenge_rows_opened": 0,
            "new_exposures": 0,
            "full_live_gate_rerun": False,
        },
    )


def freeze():
    place = OUT / "fit"
    a = place / "reader-1.json"
    b = place / "reader-2.json"
    require(sha(a) == sha(b), "fitting readers differ")
    report = read(a)
    require(
        report["readback_source_sha256"] == sha(Path(__file__)),
        "fitting source changed before seal",
    )
    profile = place / "candidate-profile.json"
    write(profile, report["profile"])
    write(
        place / "fit-seal.json",
        {
            "profile_sha256": sha(profile),
            "independent_reader_sha256": sha(a),
            "readback_source_sha256": sha(Path(__file__)),
            "inventory_sha256": report["inventory_sha256"],
            "ready_for_challenge": report["ready_for_challenge"],
            "training": report["training_seal_sha256"],
        },
    )


def challenge(reader):
    place = OUT / "fit"
    seal = read(place / "fit-seal.json")
    require(
        seal["ready_for_challenge"]
        and seal["readback_source_sha256"] == sha(Path(__file__))
        and sha(place / "reader-1.json")
        == seal["independent_reader_sha256"]
        == sha(place / "reader-2.json"),
        "fitting profile and both readers must be sealed before challenge",
    )
    profile = pinned(place / "candidate-profile.json", seal["profile_sha256"])
    motion, old, windows, frames, hashes, _, payload_profile = common(("grid02",))
    new = PayloadClearance(motion, payload_profile, profile)
    cal, views = load_optics()
    report = case_checks("grid02", windows["grid02"], frames["grid02"], old, new, cal, views)
    write(
        OUT / "challenge" / f"{reader}.json",
        {
            "profile_sha256": seal["profile_sha256"],
            "challenge_seal_sha256": hashes["grid02"],
            "checks": report,
            "passed": report["checks"] == report["checks_passing"],
            "challenge_eligible_classes": sorted({x["source_class"] for x in report["frames"]}),
            "readback_source_sha256": sha(Path(__file__)),
            "new_exposures": 0,
            "full_live_gate_rerun": False,
        },
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("stage", choices=("fit", "freeze", "challenge"))
    cli.add_argument("--reader", choices=("reader-1", "reader-2"))
    args = cli.parse_args()
    if args.stage == "freeze":
        freeze()
    else:
        require(args.reader is not None, "specify a separate reader")
        if args.stage == "fit":
            fitting(args.reader)
        else:
            challenge(args.reader)
