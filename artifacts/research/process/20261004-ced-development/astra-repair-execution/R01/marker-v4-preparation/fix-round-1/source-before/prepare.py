"""Source-bound visual candidate and immutable original-frame selection. CPU only."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
DEV = ROOT / "artifacts/research/process/20261004-ced-development"
OLD = ROOT / "assets/robots/franka_panda/scene_pose_marker_outboard_v3.xml"
V3_SHA = "ddc34b13d8df403f3fdeeab94be75ca988541f2eac0a3e534704f68200c39a23"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def vector(node, name):
    return [float(x) for x in node.attrib[name].split()]


def marker_geoms(tree, version):
    prefix = f"pose_marker_outboard_{version}_"
    body = tree.find("./worldbody/body[@name='object']")
    if body is None:
        raise ValueError("candidate object missing")
    entries = [g for g in body.findall("geom") if g.get("name", "").startswith(prefix)]
    result = {g.attrib["name"][len(prefix) :]: g for g in entries}
    if len(entries) != 37 or set(result) != {
        "quiet",
        *(f"r{r}c{c}" for r in range(6) for c in range(6)),
    }:
        raise ValueError("candidate complete 37-geom pattern required")
    return result


def nonmarker_tree(tree):
    def node(n):
        return (
            n.tag,
            tuple(sorted(n.attrib.items())),
            tuple(node(c) for c in n if not c.get("name", "").startswith("pose_marker_outboard_")),
        )

    return node(tree)


def build_v4(original):
    if digest(original) != V3_SHA:
        raise ValueError("frozen v3 bytes required")
    tree = ET.fromstring(original)
    for suffix, geom in marker_geoms(tree, "v3").items():
        if any(geom.get(k) != "0" for k in ("mass", "density", "contype", "conaffinity")):
            raise ValueError("candidate must remain visual only")
        x, y, z = vector(geom, "pos")
        sx, sy, sz = vector(geom, "size")
        geom.set("name", "pose_marker_outboard_v4_" + suffix)
        geom.set("pos", f"{0.16 + (x - 0.1) * 5 / 3:.10f} {y * 5 / 3:.10f} {z:.10f}")
        geom.set("size", f"{sx * 5 / 3:.10f} {sy * 5 / 3:.10f} {sz:.10f}")
    tree.insert(
        0,
        ET.Comment(
            "EXCLUDED DEVELOPMENT OUTBOARD V4 CANDIDATE: ID7 75mm/X160mm visual attachment; "
            "same object physics/camera/controller; no physical mount "
            "or native/calibration admission"
        ),
    )
    ET.indent(tree, space="  ")
    return ET.tostring(tree, encoding="utf-8") + b"\n"


def validate_candidate(original, candidate):
    if candidate != build_v4(original):
        raise ValueError("candidate must equal complete source-bound visual transformation")


def select_steps(markers, boundaries, adjacent_healthy):
    if [r["physics_step"] for r in markers] != list(range(len(markers))):
        raise ValueError("complete ordered original marker denominator required")
    if any(r["decode_status"] not in {"OBSERVED", "UNKNOWN"} for r in markers):
        raise ValueError("complete original decoder status required")
    failure = [r["physics_step"] for r in markers if r["decode_status"] == "UNKNOWN"]
    controls = sorted(set(boundaries) | set(adjacent_healthy))
    if len(controls) > 12 or any(
        type(n) is not int or not 0 <= n < len(markers) or markers[n]["decode_status"] != "OBSERVED"
        for n in controls
    ):
        raise ValueError("at most twelve genuine healthy controls required")
    return {
        "failure_steps": failure,
        "healthy_control_steps": controls,
        "selected_steps": sorted(set(failure) | set(controls)),
    }


def preview_readiness(selected, states, episode):
    missing = []
    for step in selected:
        if step not in states:
            missing.append(step)
            continue
        s = states[step]
        c = s["camera_state"]
        if (
            s["episode_id"] != episode
            or s["physics_step"] != step
            or s["sim_time_s"] != c["sim_time_s"]
        ):
            raise ValueError("original pose identity mismatch")
        for field, count in (("qpos", 37), ("qvel", 33), ("act", 0), ("ctrl", 9)):
            values = c[field]
            if len(values) != count or any(
                type(x) not in {float, int} or not math.isfinite(x) for x in values
            ):
                raise ValueError("original full state shape/value mismatch")
    return {
        "status": "UNAVAILABLE_MISSING_ORIGINAL_FULL_QPOS"
        if missing
        else "SOURCE_POSES_PRESENT_NOT_EXECUTED",
        "missing_pose_steps": missing,
        "present_pose_steps": [n for n in selected if n not in missing],
        "actual_model_constructions": 0,
        "actual_render_calls": 0,
        "render_pass_budget_available": 0 if missing else len(selected) * 4,
    }


def write_new(path, data):
    with path.open("x") as f:
        json.dump(data, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def pin(path):
    data = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "sha256": digest(data), "bytes": len(data)}


def prepare_original_selection():
    actual = DEV / "t7b-continuous-visibility-v3/fix-round-1/attempt-1"
    offline = HERE.parent / "offline"
    marker_path = offline / "offline-markers.jsonl"
    markers = [json.loads(line) for line in marker_path.read_text().splitlines()]
    journal_path = actual / "nominal-journal.jsonl.gz"
    states, physical_steps = {}, []
    with gzip.open(journal_path, "rt") as stream:
        for line in stream:
            row = json.loads(line)
            s = row.get("source", {})
            if s.get("kind") == "CAPTURE" and s.get("phase") == "BEGIN":
                if s["physics_step"] in states:
                    raise ValueError("ambiguous full capture state")
                states[s["physics_step"]] = {
                    k: s[k] for k in ("episode_id", "physics_step", "sim_time_s")
                }
                states[s["physics_step"]]["camera_state"] = s["parameters"]["camera_state"]
            if s.get("kind") == "PHYSICS" and s.get("phase") == "END":
                physical_steps.append(s["physics_step"])
    if physical_steps != list(range(1, 4807)) or len(markers) != 4807:
        raise ValueError("original complete horizon changed")
    selected = select_steps(markers, sorted(states), [628])
    if len(selected["failure_steps"]) != 189 or len(selected["selected_steps"]) != 201:
        raise ValueError("original fixed selection changed")
    episode = markers[0]["episode_id"]
    frames = []
    for step in selected["selected_steps"]:
        row = markers[step]
        path = actual / f"whole-step/frames/{step:07d}.json.gz"
        zipped = path.read_bytes()
        raw = json.loads(gzip.decompress(zipped))
        if (
            row["episode_id"] != episode
            or raw["episode_id"] != episode
            or raw["observation_id"] != row["observation_id"]
            or raw["checksum_sha256"] != row["checksum"]
            or raw["sim_time_s"] != row["sim_time_s"]
        ):
            raise ValueError("selected original identity mismatch")
        for member, key in (
            ("rgb.png", "rgb_png_base64"),
            ("depth.f32", "depth_float32_base64"),
            ("valid_mask.u8", "valid_mask_base64"),
        ):
            data = base64.b64decode(raw[key], validate=True)
            if (
                digest(data) != row["raw_member_sha256"][member]
                or len(data) != row["raw_member_bytes"][member]
            ):
                raise ValueError("selected original member mismatch")
        frames.append(
            {
                **pin(path),
                "physics_step": step,
                "episode_id": episode,
                "sim_time_s": row["sim_time_s"],
                "observation_id": row["observation_id"],
                "checksum": row["checksum"],
                "original_decode_status": row["decode_status"],
                "original_decode_reason": row["marker"]["reason"],
                "raw_member_sha256": row["raw_member_sha256"],
            }
        )
    refs = [
        marker_path,
        offline / "offline-verification.json",
        actual / "teacher-evidence.json",
        journal_path,
        actual / "summary.json",
        actual / "execution-header.json",
        actual.parent / "execution-source-hashes.json",
        actual.parent / "execution-archive-index.json",
        OLD,
    ]
    manifest = {
        "protocol": "research.marker-v4-sparse-selection.v1",
        "scope": "EXCLUDED_SAME_DEVELOPMENT_COMPONENT",
        "independent_calibration_group": False,
        "original_episode_id": episode,
        "original_total_frames": 4807,
        **selected,
        "selected_count": len(frames),
        "selection_rule": (
            "ALL_189_UNKNOWN_PLUS_ALL_11_ORIGINAL_FULL_QPOS_BOUNDARIES_"
            "PLUS_PRE_FIRST_UNKNOWN_628"
        ),
        "input_pins": [pin(p) for p in refs],
        "original_frames": frames,
        "original_fixed_pose_preview": preview_readiness(
            selected["selected_steps"], states, episode
        ),
        "candidate_tag_size_m": 0.075,
        "candidate_local_center_m": [0.16, 0, 0.03505],
        "native_admission": "NOT_PROMOTED",
        "continuous_visibility": "NOT_ESTABLISHED",
    }
    write_new(HERE / "selection-manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    candidate = HERE / "scene_pose_marker_outboard_v4.xml"
    with candidate.open("xb") as f:
        f.write(build_v4(OLD.read_bytes()))
    result = prepare_original_selection()
    print(
        json.dumps(
            {
                "status": "PREPARED_SOFTWARE_ONLY",
                "selected_count": result["selected_count"],
                "original_fixed_pose_preview": result["original_fixed_pose_preview"]["status"],
                "actual_calls": 0,
            }
        )
    )
