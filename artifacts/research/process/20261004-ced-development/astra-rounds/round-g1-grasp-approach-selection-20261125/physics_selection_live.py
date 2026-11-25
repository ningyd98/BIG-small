"""Real optical APPROACH/GRASP/LIFT on an independently recorded MOVE_ABOVE return."""

import argparse
import fcntl
import gzip
import time
from pathlib import Path

import cv2
import mujoco
import numpy as np
from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.research.native_collection_grounding import bootstrap_collection_tracker
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.simulation.mujoco.motion_controller import MotionTarget
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.simulation.mujoco.visual_servo import VisualServoSession
from cloud_edge_robot_arm.vision.observations import RGBDObservation, observation_from_sensor_frame
from cloud_edge_robot_arm.vision.servo import OpenCVServoFeedback
from scripts.graduation.g1_formal_runtime import bind_scene
from scripts.graduation.g1_visibility_vision import measure_frame

import physics_selection_study as s


def capture(root, case, cid, role):
    dest = root / s.RAW
    out = dest/"live-servo"/case/cid
    out.mkdir(parents=True, exist_ok=False)
    frozen = s.HERE/"physics_selection_freeze.public.json"
    if not frozen.is_file():
        raise ValueError("no frozen finite candidate rule")
    geom = s.geometry(root)
    eng = s.native_engine(root)
    cfg = next(c for c in eng.DESIGN["candidates"] if c["id"] == cid)
    b, recipe = eng.setup(root, case)
    robot = MuJoCoSkillRobot(b)
    sensor = eng.native.Sensors(b)
    data = mujoco.MjData(b._model)
    camera = MuJoCoRGBDCamera(mujoco, b._model, width=320, height=240)
    prefix = dest/"prefix"/case
    scene = "approach-candidate-" + case
    rng = np.random.default_rng(recipe["seed"] + 9931)
    timeline, frames, actions = [], [], []
    phase = "PREFIX"

    def observe(step=None):
        row, _ = sensor.snap(b)
        tp = b.get_tcp_pose()
        timeline.append({"step": b.total_physics_steps, "stage": phase,
                         "q": row["q"], "dq": row["qvel"], "ctrl": row["ctrl"],
                         "np_tcp": [tp.x, tp.y, tp.z], "cube": row["centers"][10],
                         "cube_bottom": row["cube_bottom_m"], "forces": row["force_N"],
                         "contacts": row["contacts"]})

    def camera_read(reason):
        data.qpos[:] = b._data.qpos
        data.qvel[:] = b._data.qvel
        data.ctrl[:] = b._data.ctrl
        data.time = b.get_sim_time()
        mujoco.mj_forward(b._model, data)
        tick = time.monotonic_ns()
        f = observation_from_sensor_frame(camera.capture(data, rng=rng, noise_std_m=.001,
            scene_id=scene, episode_id=scene), source="mujoco_camera", png_compress_level=1)
        row = {"stage": phase, "kind": reason, "step": b.total_physics_steps,
               "capture_ms": (time.monotonic_ns()-tick)/1e6, "frame_id": f.frame_id,
               "checksum": f.checksum_sha256}
        frames.append((f,row))
        return f,row

    def execute(skill,current,provider,target,fn):
        def sample(prior):
            nonlocal phase
            f,row = camera_read("native_feedback")
            effective = provider.update(f)
            row["target_m"] = [effective.x,effective.y,effective.z]
            return MotionTarget(effective, prior.orientation_wxyz)
        path = None
        if skill == "LIFT":
            path = VerticalClearancePath(task_id=scene,step_id="original-LIFT",skill="LIFT",
                start_m=(current.x,current.y,current.z), target_m=(target.x,target.y,target.z),minimum_height_m=.08)
        session = VisualServoSession(sample, vertical_clearance=path)
        start = b.total_physics_steps
        with robot.visual_servo(session), b.observe_physics_steps(observe):
            result = fn()
        actions.append({"skill":skill,"start":start,"end":b.total_physics_steps,"success":result.success,
                        "error":result.error_code,"details":result.details,"feedback_count":len(session.records),
                        "max_sample_and_ik_ms":max((1000*r["sample_and_ik_s"] for r in session.records if r.get("sample_and_ik_s") is not None),default=None)})
        return result

    try:
        with bind_scene(scene):
            q = np.load(prefix/"return.npz")
            eng.io.restore(b,(q["packed"],q["command_q"],bool(q["command_open"]),int(q["step"])))
            b._command_records=s.read(prefix/"commands.json")
            np.testing.assert_array_equal(q["q"],b._data.qpos)
            bootstrap = RGBDObservation.model_validate_json(gzip.decompress((prefix/"bootstrap.json.gz").read_bytes()))
            reference = RGBDObservation.model_validate_json(gzip.decompress((prefix/"approach-reference.json.gz").read_bytes()))
            tracker, ev = bootstrap_collection_tracker(bootstrap,geom)
            m = measure_frame(reference,geom)
            aim = s.object_target(m["object_center_world_m"],m["rotation_object_to_world"],cfg)
            target = Pose(x=aim[0],y=aim[1],z=aim[2])
            provider = OpenCVServoFeedback(reference,tracker,ev,skill="APPROACH",initial_target=target,
                                         marker_family_id=geom["marker_family"],verify_mujoco_calibration=True)
            phase="APPROACH"
            observe()
            approach=execute(phase,None,provider,target,lambda: robot.approach("object",resolved_target=target,tcp_velocity=.15,acceleration=.5,timeout_ms=8000))
            lift_origin = None
            if approach.success:
                phase="GRASP"
                current_f, current_row=camera_read("closure_reference")
                near=measure_frame(current_f,geom)
                angle=patch=reason=None
                if near["usable"]:
                    from scripts.graduation.g1_complete_cv_angle import grasp_readiness
                    hand=data.site("tcp")
                    angle,patch,reason=grasp_readiness(current_f,near,geom,near["object_center_world_m"],
                        np.asarray(near["rotation_object_to_world"]).reshape(3,3),hand.xpos,hand.xmat.reshape(3,3),data.qpos[7:9],closure=True)
                else:
                    reason=near["reason"]
                current_row["original_closure_certificate"]=dict(reason=reason,angle=angle,patch=patch)
                start=b.total_physics_steps
                with b.observe_physics_steps(observe):
                    gr=robot.grasp("object",timeout_ms=1000)
                actions.append({"skill":phase,"start":start,"end":b.total_physics_steps,"success":gr.success,"error":gr.error_code})
                if gr.success:
                    phase="LIFT"
                    current=robot.get_state().tcp_pose
                    lift_origin=[current.x,current.y]
                    target=Pose(x=current.x,y=current.y,z=max(.16,current.z+.10))
                    ref,_=camera_read("lift_reference")
                    provider=OpenCVServoFeedback(ref,tracker,ev,skill="LIFT",initial_target=target,
                        marker_family_id=geom["marker_family"],verify_mujoco_calibration=True)
                    execute(phase,current,provider,target,lambda: robot.lift(target.z-current.z,resolved_target=target,tcp_velocity=.15,acceleration=.5,timeout_ms=8000))
            series=eng.io.stack(timeline)
            np.savez_compressed(out/"physical.npz",**series)
            index=[]
            for j,(frame,info) in enumerate(frames):
                file=out/f"image-{j:04d}.json.gz"
                file.write_bytes(gzip.compress(frame.model_dump_json().encode(),3,mtime=0))
                index.append({**info,"file":file.name,"sha256":s.sha(file)})
            ls=np.flatnonzero(series["stage"]=="LIFT")
            peak=float(np.max(np.linalg.norm(series["np_tcp"][ls,:2]-lift_origin,axis=1))) if len(ls) else None
            last=ls[-120:]
            held=bool(len(last)==120 and np.all(series["contacts"][last,:2]>0) and np.all(series["cube_bottom"][last]-series["cube_bottom"][0]>=.05))
            s.write(out/"result.json",{"case":case,"candidate":cid,"role":role,"freeze_sha256":s.sha(frozen),
                   "native_prefix_sha256":s.sha(prefix/"return.npz"),"actual_observed_target_m":aim.tolist(),"actions":actions,
                   "lateral_peak_m":peak,"bilateral_50mm_120_steps":held,
                   "forbidden_steps":int(np.count_nonzero(series["contacts"][:,3])),"frames":index,
                   "series_sha256":s.sha(out/"physical.npz"),"source_sha256":s.sha(Path(__file__))})
    finally:
        camera.close()
        b.shutdown()


if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--root",required=True,type=Path)
    a.add_argument("--case",required=True)
    a.add_argument("--candidate",action="append",required=True)
    a.add_argument("--role",required=True)
    args=a.parse_args()
    root=args.root.resolve()
    cv2.setNumThreads(1)
    with (root/s.LOCK).open("rb") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        for candidate in dict.fromkeys(args.candidate):
            capture(root,args.case,candidate,args.role)
