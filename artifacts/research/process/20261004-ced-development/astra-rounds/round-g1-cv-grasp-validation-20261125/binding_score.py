"""Blind rigid-pose and issued-target checks for G1 development; physics scoring stays native."""
import hashlib
import json

import numpy as np


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _require(ok, msg):
    if not ok:
        raise ValueError(msg)


def _close(left, right, what):
    _require(np.allclose(left, right, rtol=0, atol=1e-10), what)


def _rot(frame):
    _require(frame["usable"], "blind selected marker missing")
    return np.reshape(frame["per_id"][str(frame["selected_id"])]["rotation_object_to_world"], (3, 3))


def offset_delta(spec, reference, current):
    return (_rot(current) - _rot(reference)) @ np.asarray(spec["offset_object_m"])


def verify_issues(audit, frames):
    issues = {}
    scope = None
    for a in audit:
        if a.get("schema_version") != "native.registered.grounding.v2":
            continue
        ticket = a["development_grasp_binding"]
        selection = ticket["selection"]
        p = a["binding"]["prepared"]
        current = frames[a["observation_id"]]
        table = a["development_grasp_screen"]
        spec = selection["spec"]
        candidates = [r for r in table["rows"] if r["candidate_id"] == spec["candidate_id"]]
        _require(len(candidates) == 1 and _hash(table) == ticket["screen_sha256"]
                 and all(candidates[0][k] == v for k, v in spec.items())
                 and candidates[0]["clearance"] == "CLEAR"
                 and candidates[0]["proof_sha256"] == ticket["proof_sha256"]
                 and all(table[k] == v for k, v in ticket["frame"].items()),
                 "blind read found a substituted frame or screen entry")
        _require(p["development_grasp_binding_sha256"] == _hash(ticket)
                 and _hash(selection) == ticket["selection_sha256"]
                 and selection["original_sha256"] == a["original_plan_sha256"] == p["original_plan_hash"]
                 and selection["owner"] == a["identity"] == p["current_identity"]
                 and p["observation_id"] == ticket["frame"]["frame_id"] == current["frame_id"]
                 and p["observation_checksum_sha256"] == ticket["frame"]["checksum_sha256"] == current["checksum_sha256"]
                 and ticket["step_id"] == a["step_id"] and a["grounded_step"] == p["grounded_step"],
                 "independent read found a changed selection, frame or native issue")
        _require(scope in (None, ticket["selection_sha256"]), "offset changed during one attempt")
        scope = ticket["selection_sha256"]
        step = a["grounded_step"]
        _require(step == next(s for s in a["executed_contract"]["steps"] if s["step_id"] == step["step_id"]),
                 "execution contract replaced the signed step")
        skill = step["skill"]
        _require(skill not in issues, "one stage was signed twice")
        issues[skill] = (selection["spec"], a["binding_sha256"], scope)
        base = np.array(current["tcp_m"])
        central = current["per_id"][str(current["selected_id"])]["center_m"]
        _close(a["inputs"]["object_center_world_m"], central, "blind central object estimate differs")
        _close(a["inputs"]["grasp_tcp_world_m"], base, "blind central TCP differs")
        offset = _rot(current) @ selection["spec"]["offset_object_m"]
        target = base + offset
        policy = a["policy"]
        if skill in {"MOVE_ABOVE", "MOVE_TO_REGION"}:
            target[2] = max(policy["minimum_height_m"], target[2] + policy["clearance_m"])
        if skill in {"MOVE_TO_REGION", "PLACE"}:
            dest = np.array(a["inputs"]["destination_world_m"])
            target[:2] = dest[:2] + offset[:2]
            if skill == "PLACE":
                target[2] += dest[2] - a["inputs"]["nominal_support_height_m"]
        if skill in {"LIFT", "RETREAT"}:
            sensed = a["online"]["robot_state"]["tcp_pose"]
            target = np.array([sensed[k] for k in "xyz"])
            target[2] = max(target[2] + policy["clearance_m"], policy["minimum_height_m"])
        params = step["parameters"]
        if skill in {"GRASP", "RELEASE"}:
            _require("target_pose" not in params, "gripper stage unexpectedly moved TCP")
        else:
            _close([params["target_pose"][k] for k in "xyz"], target, "signed offset target disagrees with blind pixels")
        for action in audit:
            if action.get("phase") == "PRE" and "shield" in action and action["step_id"] == step["step_id"]:
                _require(action["frame_id"] == current["frame_id"] and action["target_pose"] == params.get("target_pose"),
                         "Shield consumed a different target")
    return issues


def verify_sample(issues, skill, sample, current):
    spec, issued_hash, selection_hash = issues[skill]
    measurement = sample["development_grasp_binding"]
    _require(measurement["selection_sha256"] == selection_hash and measurement["issued_sha256"] == issued_hash,
             "servo feedback follows a different issue")
    _close(measurement["central_grasp_m"], current["tcp_m"], "servo central TCP differs from raw marker")
    _close(measurement["selected_grasp_m"], np.array(current["tcp_m"]) + _rot(current) @ spec["offset_object_m"],
           "servo selected TCP differs from blind rigid readback")
