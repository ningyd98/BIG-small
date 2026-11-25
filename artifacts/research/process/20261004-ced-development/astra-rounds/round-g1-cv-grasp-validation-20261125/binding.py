"""Finite, current-frame grasp binding for the isolated G1 development worker."""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from contextlib import closing, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.mujoco.motion_controller import MotionTarget
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD
from cloud_edge_robot_arm.vision.servo import OpenCVServoFeedback

PLAN = "596158c29f9d43573a92c2be22a5b9db55e5d8b21f08cc8382e65e3d8b7ffb1a"
SPEC = ("candidate_id", "direction", "tangent_mm", "offset_object_m", "orientation_wxyz")
_resolution = ContextVar("g1_development_resolution", default=None)
_screen = ContextVar("g1_development_current_screen", default=None)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def require(truth, reason):
    if not truth:
        raise ValueError(reason)


def frame_identity(obs):
    return {"frame_id": obs.frame_id, "checksum_sha256": obs.checksum_sha256}


def check_direction(q):
    require(isinstance(q, (list, tuple)) and tuple(q) == _DOWNWARD, "fixed tool direction required")


def select_row(table, frame, candidate_id):
    require(all(table.get(k) == frame[k] for k in ("frame_id", "checksum_sha256")), "foreign screen frame")
    rows = [r for r in table["rows"] if r["candidate_id"] == candidate_id]
    require(len(rows) == 1, "uniquely registered candidate required")
    row = rows[0]
    require(row["clearance"] == "CLEAR", "current CLEAR candidate required")
    require(re.fullmatch(r"[a-f0-9]{64}", row.get("proof_sha256", "")), "sweep proof digest required")
    require(all(row.get(k, frame[k]) == frame[k] for k in frame), "candidate frame mismatch")
    require(row["direction"] in {"object_X", "object_Y", "existing_tool_closure_axis"}, "unregistered direction")
    check_direction(row["orientation_wxyz"])
    delta = np.asarray(row["offset_object_m"], dtype=float)
    d = row["tangent_mm"]
    require(type(d) in (int, float) and math.isfinite(d) and delta.shape == (3,)
            and np.isfinite(delta).all() and abs(delta[2]) < 1e-12
            and abs(np.linalg.norm(delta) * 1000 - abs(d)) < 1e-6, "unregistered object offset")
    on_grid = abs(d) <= 49 and float(d).is_integer()
    require(on_grid or (row.get("projected_overlap_boundary") is True and abs(d) <= 35 * math.sqrt(2) + 14 + 1e-6),
            "offset outside finite matrix")
    return json.loads(canonical(row))


def require_fixed_face(row, rotation):
    axis = row["direction"]
    if axis != "existing_tool_closure_axis":
        rot = np.asarray(rotation).reshape(3, 3)
        normal = rot[:2, 0 if axis == "object_X" else 1]
        require(np.linalg.norm(normal) > 0 and abs(normal[0]) <= 1e-7 * np.linalg.norm(normal),
                "object face direction requires unsupported wrist yaw")


def selected_tcp(central, rotation, offset):
    return np.asarray(central) + np.asarray(rotation).reshape(3, 3) @ np.asarray(offset)


def claim(path, key, record):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS selection (scope TEXT PRIMARY KEY, record TEXT NOT NULL)")
        enc = canonical(record)
        db.execute("INSERT OR IGNORE INTO selection VALUES (?,?)", (key, enc))
        (persisted,) = db.execute("SELECT record FROM selection WHERE scope=?", (key,)).fetchone()
        require(persisted == enc, "attempt selection or step already bound")


def recall(path, key):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        found = db.execute("SELECT record FROM selection WHERE scope=?", (key,)).fetchone()
    require(found, "no registered attempt selection")
    return json.loads(found[0])


@dataclass(frozen=True)
class BoundAttempt:
    ledger: Path
    scope: str
    selection_sha256: str

    @classmethod
    def select(cls, original, lease, frame, table, candidate_id, *, ledger):
        from cloud_edge_robot_arm.vision.worker_owner import WorkerLeaseObservation

        require(type(lease) is WorkerLeaseObservation, "SQLite worker lease required")
        identity = original.identity
        actual = lease.identity(episode_id=frame.episode_id, task_id=identity.task_id,
                                plan_id=identity.plan_id, robot_id=identity.robot_id)
        require(identity == actual and lease.observed_at <= datetime.now(UTC) < lease.expires_at,
                "foreign or expired binding owner")
        require(original.registered_at <= frame.captured_at <= datetime.now(UTC)
                and (datetime.now(UTC) - frame.captured_at).total_seconds() <= 5,
                "selection frame is stale or foreign")
        require(original.source_hashes.get("scripts/graduation/binding.py")
                == hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "binding generation mismatch")
        packet = frame_identity(frame)
        row = select_row(table, packet, candidate_id)
        scope = digest({"identity": identity.to_payload(), "plan_version": original.contract.plan_version,
                        "command_seq": original.contract.command_seq})
        record = dict(owner=identity.to_payload(), original_sha256=original.digest(),
                      plan_sha256=PLAN, first_frame=packet, first_screen_sha256=digest(table),
                      scene_id=frame.scene_id, calibration=frame.calibration_version,
                      scope=scope, spec={k: row[k] for k in SPEC})
        claim(ledger, scope, record)
        return cls(Path(ledger), scope, digest(record))

    def record(self):
        record = recall(self.ledger, self.scope)
        require(digest(record) == self.selection_sha256, "changed attempt selection")
        return record

    def issue_step(self, original, *, index, observation, state, tracker, lease_source, table, evidence_sink=None):
        from cloud_edge_robot_arm.research.native_collection_grounding import registered_collection_step_v2

        record = self.record()
        packet = frame_identity(observation)
        require(record["original_sha256"] == original.digest() and record["owner"] == original.identity.to_payload()
                and observation.episode_id == original.identity.episode_id and observation.scene_id == record["scene_id"]
                and observation.calibration_version == record["calibration"], "foreign attempt or frame")
        row = select_row(table, packet, record["spec"]["candidate_id"])
        require({k: row[k] for k in SPEC} == record["spec"], "running direction or selected offset changed")
        first = self.scope + ":first-issue"
        with closing(sqlite3.connect(self.ledger)) as db:
            any_issue = db.execute("SELECT record FROM selection WHERE scope=?", (first,)).fetchone()
        if not any_issue:
            require(record["first_frame"] == packet and record["first_screen_sha256"] == digest(table),
                    "selected frame replaced before first issue")
        ticket = dict(selection=record, selection_sha256=self.selection_sha256, frame=packet,
                      screen_sha256=digest(table), proof_sha256=row["proof_sha256"],
                      step_id=original.contract.steps[index].step_id)
        result = []
        token = _resolution.set(ticket)
        try:
            native = registered_collection_step_v2(original, index=index, observation=observation, state=state,
                       tracker=tracker, lease_source=lease_source, evidence_sink=result.append)
        finally:
            _resolution.reset(token)
        (audit,) = result
        require(audit["binding"]["prepared"]["development_grasp_binding_sha256"] == digest(ticket),
                "issuer did not sign current candidate")
        if not any_issue:
            claim(self.ledger, first, ticket["frame"])
        claim(self.ledger, self.scope + ":" + ticket["step_id"], ticket)
        if evidence_sink is not None:
            evidence_sink({**audit, "development_grasp_binding": ticket, "development_grasp_screen": table})
        return native

    def verify_issue(self, issued):
        item = issued.prepared.to_payload()
        ticket = recall(self.ledger, self.scope + ":" + issued.grounded_step.step_id)
        require(item["development_grasp_binding_sha256"] == digest(ticket)
                and ticket["selection_sha256"] == self.selection_sha256
                and ticket["selection"] == self.record(), "foreign issued target or attempt")
        return ticket


def resolve_registered_parameters(native, step, original, online, inputs, policy):
    ticket = _resolution.get()
    require(ticket is not None, "development selection required before native issue")
    p = inputs.to_payload()
    require(ticket["selection"]["original_sha256"] == original.digest()
            and ticket["step_id"] == step.step_id and p["observation_id"] == ticket["frame"]["frame_id"]
            and p["observation_checksum_sha256"] == ticket["frame"]["checksum_sha256"],
            "selection and native owner frame differ")
    row = ticket["selection"]["spec"]
    rot = np.reshape(p["rotation_object_to_world"], (3, 3))
    require_fixed_face(row, rot)
    if row["tangent_mm"] and ticket["frame"] == ticket["selection"]["first_frame"]:
        # The screening matrix uses upright Rz for XY and the original full rotation for the grasp height.
        yaw = math.atan2(rot[1, 0], rot[0, 0])
        signed_x = math.cos(yaw) * row["offset_object_m"][0] - math.sin(yaw) * row["offset_object_m"][1]
        require(abs(signed_x * 1000 - row["tangent_mm"]) < 1e-5, "registered tangent offset/direction mismatch")
    params = native(step, original, online, inputs, policy)
    shift = rot @ np.array(row["offset_object_m"])
    if any(shift) and step.skill.value in {"MOVE_ABOVE", "APPROACH", "MOVE_TO_REGION", "PLACE"}:
        grasp = selected_tcp(p["grasp_tcp_world_m"], rot, row["offset_object_m"])
        dest = np.array(p["destination_world_m"])
        dest[:2] += shift[:2]
        adapted = SimpleNamespace(grasp_tcp=dict(zip("xyz", grasp.tolist(), strict=True)),
                                  destination=dict(zip("xyz", dest.tolist(), strict=True)),
                                  support_height_m=inputs.support_height_m)
        params = native(step, original, online, adapted, policy)
    return params, digest(ticket)


class BoundServoFeedback(OpenCVServoFeedback):
    """The native marker/colour identity test keeps checking the central TCP."""

    def __init__(self, attempt, issued, reference, tracker, evidence, *, marker_family_id):
        from scripts.graduation import g1_dual_asset as asset

        self.ticket = attempt.verify_issue(issued)
        self.geometry = asset.geometry_descriptor()
        self.delta = self.ticket["selection"]["spec"]["offset_object_m"]
        self.receipt_sha256 = issued.digest()
        step = issued.grounded_step
        require(reference.episode_id == self.ticket["selection"]["owner"]["episode_id"]
                and reference.scene_id == self.ticket["selection"]["scene_id"]
                and reference.calibration_version == self.ticket["selection"]["calibration"]
                and reference.frame_id != self.ticket["frame"]["frame_id"]
                and reference.captured_at >= datetime.fromisoformat(issued.prepared.to_payload()["created_at"]),
                "foreign or old servo reference")
        super().__init__(reference, tracker, evidence, skill=step.skill.value,
                         initial_target=Pose.model_validate(step.parameters["target_pose"]),
                         marker_family_id=marker_family_id, verify_mujoco_calibration=True)
        self.reference_selected = self._reference_grasp.tolist()

    def _measure_target(self, observation):
        central, source = super()._measure_target(observation)
        estimate = self._observed_marker
        require(self._marker_bound and estimate.observation_id == observation.observation_id
                and estimate.observation_checksum_sha256 == observation.checksum_sha256,
                "servo selection lacks current registered marker")
        code = self._development_dual_measurement["selected_id"]
        attachment = np.array(self.geometry["development_dual"]["markers"][str(code)]["object_T_marker"]).reshape(4, 4)
        rot = np.array(estimate.rotation_marker_to_world).reshape(3, 3) @ attachment[:3, :3].T
        point = selected_tcp(central, rot, self.delta)
        self.current_selection = dict(central_grasp_m=central.tolist(), selected_grasp_m=point.tolist(),
                                      selection_sha256=self.ticket["selection_sha256"], issued_sha256=self.receipt_sha256)
        return point, source

    def update(self, observation, *, require_retreat_region=False):
        pose = super().update(observation, require_retreat_region=require_retreat_region)
        self.records[-1]["development_grasp_binding"] = dict(self.current_selection)
        return pose

    def motion_target(self, previous, measured):
        check_direction(previous.orientation_wxyz)
        require(self.records and self.records[-1]["target_pose"] == measured.model_dump(),
                "motion target differs from the accepted servo sample")
        return MotionTarget(measured, previous.orientation_wxyz)


@contextmanager
def screen_episode(screen):
    """screen(frame, state, step_index, frozen_spec_or_none) returns (table, selected_id)."""
    token = _screen.set(screen)
    try:
        yield
    finally:
        _screen.reset(token)


def issue_for_episode(episode, *, index, observation, state, tracker, lease_source, evidence_sink):
    screen = _screen.get()
    require(callable(screen), "current candidate screen required")
    attempt = getattr(episode, "grasp_attempt", None)
    table, candidate_id = screen(observation, state, index, attempt.record()["spec"] if attempt else None)
    if attempt is None:
        attempt = BoundAttempt.select(episode.original, lease_source, observation, table, candidate_id,
                                      ledger=episode.raw / "grasp-binding.sqlite")
        episode.grasp_attempt = attempt
    require(candidate_id == attempt.record()["spec"]["candidate_id"], "attempt candidate changed")
    return attempt.issue_step(episode.original, index=index, observation=observation, state=state, tracker=tracker,
                              lease_source=lease_source, table=table, evidence_sink=evidence_sink)
