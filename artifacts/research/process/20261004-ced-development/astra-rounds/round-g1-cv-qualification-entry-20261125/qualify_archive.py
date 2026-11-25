"""Reconstruct original pixels at an independently recorded read time in a cold reader only."""
from datetime import UTC, datetime, timedelta

import numpy as np


def utc(text):
    try:
        value = datetime.fromisoformat(text)
    except (ValueError, TypeError) as exc:
        raise ValueError("missing or invalid original read time") from exc
    if value.utcoffset() != timedelta(0):
        raise ValueError("original read time must be UTC")
    return value


def checked_time(packet, event, role, lease_id, deadline):
    if any(event.get(k) != v for k, v in packet.items()) or event.get("role") != role or event.get("lease_id") != lease_id:
        raise ValueError("archived frame, role or lease crosslink differs")
    capture = utc(packet["captured_at"])
    start, end, stamp = (utc(event[k]) for k in ("call_start_utc", "call_end_utc", "evaluated_at"))
    if not capture <= start <= stamp <= end < deadline or (stamp - capture).total_seconds() >= 5:
        raise ValueError("recorded read is outside operation, source freshness or lease window")
    return stamp


def frame_key(frame):
    return dict(frame_id=frame.frame_id, checksum_sha256=frame.checksum_sha256, captured_at=frame.captured_at.isoformat())


def archived_color(frame, geometry, role_event, lease, deadline):
    from cloud_edge_robot_arm.research.native_archived_tracker import _ArchivedTargetTracker
    from cloud_edge_robot_arm.research.native_collection_grounding import collection_bootstrap_evidence

    evaluated = checked_time(frame_key(frame), role_event, "color.initial", lease, utc(deadline))
    evidence = collection_bootstrap_evidence(frame, geometry)
    return _ArchivedTargetTracker(frame, evidence, evaluated_at=evaluated)


def read_case(folder, expected):
    from scripts.graduation import binding_score, g1_dual_asset as asset, g1_dual_batch_score as scoring, g1_dual_pixel_readback as reader
    from scripts.graduation import g1_visibility_trials as trials
    from scripts.graduation.g1_formal_runtime import bind_scene
    from cloud_edge_robot_arm.contracts import RobotState
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.servo_region import measure_servo_region
    from scripts.graduation.proposal_scoring import PhysicsStepObservation, sample_physical_observation, evaluate_evidence, CRITERIA
    from qualify_native import checked

    alloc = checked(folder / "allocation.json", expected["allocation.json"])
    run = checked(folder / "run.json", expected["run.json"])
    audit = checked(folder / "audit.json", expected["audit.json"])
    index = checked(folder / "frames.json", expected["frames.json"])
    owner = checked(folder / "owner.json", expected["owner.json"])
    for name in ("grasp-binding.sqlite","development-worker.db"):
        import hashlib
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != expected[name]:
            raise ValueError("changed sealed owner database")
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect((folder / "development-worker.db").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)) as db:
        job, = db.execute("select job_id,run_id,status from simulation_jobs")
        lease, = db.execute("select lease_id,worker_id,released_at from simulation_job_leases")
    issue, = [a for a in audit if a.get("schema_version") == "native.registered.grounding.v2"]
    if not (job[0] == issue["identity"]["job_id"] == owner["job_id"] and lease[0] == issue["lease_source"]["lease_id"]
            and lease[1] == issue["identity"]["worker_id"] and lease[2] and job[2] == owner["final_job_status"]):
        raise ValueError("SQLite owner differs from native issue")
    with closing(sqlite3.connect((folder / "grasp-binding.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)) as db:
        import json
        persisted = {k: json.loads(v) for k,v in db.execute("select scope,record from selection")}
    ticket = issue["development_grasp_binding"]
    if persisted[ticket["selection"]["scope"]] != ticket["selection"] or persisted[ticket["selection"]["scope"]+":"+ticket["step_id"]] != ticket:
        raise ValueError("SQLite selection differs from native issue")
    frames, raw = {}, {}
    cap_events = {e["frame_id"]: e for e in run["operations"] if e["kind"]=="CAPTURE" and e["phase"]=="END" and "frame_id" in e}
    with bind_scene(alloc["case"]["scene_id"]):
        for spec in index:
            f=RGBDObservation.model_validate(checked(folder/spec["file"], spec["file_sha256"]))
            if f.frame_id!=spec["frame_id"] or f.checksum_sha256!=spec["checksum_sha256"] or cap_events[f.frame_id]["captured_at"]!=f.captured_at.isoformat():
                raise ValueError("sealed packet or native acquisition crosslink differs")
            raw[f.frame_id]=f
            frames[f.frame_id]=dict(**reader.dual_read(f,alloc["geometry"]), **frame_key(f), sim_time_s=f.sim_time_s, label=spec["role"])
        issued=raw[issue["observation_id"]]
        deadline=utc(issue["binding"]["prepared"]["valid_until"])
        lease_id=issue["lease_source"]["lease_id"]
        for stage,field in (("registered.preview","tracker_evaluated_at"),("registered.issue","binding_now")):
            t=checked_time(frame_key(issued),run["read_times"][stage],stage,lease_id,deadline)
            if t!=utc(issue[field]):
                raise ValueError("original issuer and archived evaluation time differ")
        color=archived_color(issued, alloc["geometry"], run["color_init_event"], lease_id,deadline.isoformat())
        facts_stamp=checked_time(frame_key(issued),run["read_times"]["color.facts"],"color.facts",lease_id,deadline)
        facts=color.facts_at(issued, RobotState.model_validate(run["measured_state"]), evaluated_at=facts_stamp)
        region,why=measure_servo_region(issued,color)
        if facts != run["facts_readback"] or region is None or why:
            raise ValueError("archived original tracker facts or measured region differ")
        issue_count=len(binding_score.verify_issues(audit,frames))
        reader_check=scoring.online_targets(run,audit,frames,alloc["geometry"],raw.__getitem__)
        sample=run.get("component_sample")
        component_residual=None
        if sample:
            initial=issue["grounded_step"]["parameters"]["target_pose"]
            ref=frames[sample["reference"]]
            cur=frames[sample["sample"]["observation_id"]]
            expected_pose=np.array([initial[k] for k in "xyz"])+np.subtract(cur["tcp_m"],ref["tcp_m"])+binding_score.offset_delta(ticket["selection"]["spec"],ref,cur)
            actual=np.asarray([sample["sample"]["target_pose"][k] for k in "xyz"])
            np.testing.assert_allclose(actual,expected_pose,rtol=0,atol=1e-10)
            binding_score.verify_sample(binding_score.verify_issues(audit,frames),"MOVE_ABOVE",sample["sample"],cur)
            component_residual=float(np.linalg.norm(actual-expected_pose)*1000)
    import xml.etree.ElementTree as ET
    xml = ET.parse(folder.parent / "runtime-source" / alloc["geometry"]["asset_path"])
    supports={g.get("name") for g in xml.find(".//body[@name='object']").findall("geom") if g.get("name")!="object_geom" and (int(g.get("contype",1)) or int(g.get("conaffinity",1)))}
    contacts=scoring.contact_counts([run["physical_sample"]], supports)
    outcomes=evaluate_evidence([sample_physical_observation(PhysicsStepObservation(**run["physical_sample"]),CRITERIA)],CRITERIA)
    return dict(offset_mm=run["offset_mm"], lease_id=lease_id, actual_issue_count=issue_count, actual_pre=run["admission"],
            source_times=run["read_times"], component_sample=sample, score_checks=reader_check,
            center_recipe=run["central_recipe"], selected=issue["grounded_step"]["parameters"]["target_pose"],
            selection_sha256=ticket["selection_sha256"], component_residual_mm=component_residual, source_frames=len(raw),
            cold_original_tracker_facts_equal=True, archived_region_center=region["center"],
            negative_controls=run["controls"], physical_steps=run["physics_steps"], motion_commands=len(run["commands"]),
            native_capture_events=len(cap_events), controller_callbacks=0, dispatched=0,
            physics_snapshot=dict(success=outcomes.success,bilateral_steps=contacts["bilateral_cube_steps"]),
            training_success=trials.training_success({"contacts":contacts, "dispatched":0, "verified_posts":0}),
            ready_for_motion=False, clock_contexts=run["clock_contexts"], action_clock=run["action_clock"], seals=expected)
