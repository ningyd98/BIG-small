"""One registered workpiece, observed RGB-D changes and current measured robot kinematics."""

import json
import time
from pathlib import Path

import numpy as np
from scripts.graduation.g1_complete_cv_angle import grasp_readiness
from scripts.graduation.g1_complete_cv_calibrate import BAND, CAMERA_FIELDS, axial, digest
from scripts.graduation.g1_complete_cv_geometry import Box, Model, box_gaps, visible_box
from scripts.graduation.g1_complete_cv_motion import MotionGeometry, upper_support

from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def depth_changes(current, reference, band):
    present, known = current > 0, reference > 0
    return (
        present & (~known | (current < reference - 2 * band)),
        known & (~present | (current > reference + 2 * band)),
    )


def robot_raster_matches(current, predicted, empty, band):
    return (
        (predicted > 0)
        & (predicted < 10)
        & ((empty == 0) | (predicted < empty - 2 * band))
        & (abs(current - predicted) <= band)
    )


def camera_encoder_pose(model, data):
    """Recover the robot joint configuration in the exact kinematic buffer used by the camera.

    MuJoCo's RK4 position buffer and final visual body transforms can differ
    after a physics tick. Each hinge below uses only measured orientations of
    its named parent and child arm links. Each slide uses its named hand and
    finger. No free body, object, contact or segmentation buffer is accessed.
    """
    arm_names = ["panda_link0", *(f"panda_link{i}" for i in range(1, 7)), "panda_hand"]
    arm = [np.array(data.body(n).xmat).reshape(3, 3) for n in arm_names]
    q = []
    for i, (parent, child) in enumerate(zip(arm[:-1], arm[1:], strict=True), 1):
        r = parent.T @ child
        vector = np.array([r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1]])
        sine = float(vector @ np.asarray(model.joint(f"joint{i}").axis).ravel()) / 2
        q.append(float(np.arctan2(sine, (np.trace(r) - 1) / 2)))
    fingers = []
    hand = data.body("panda_hand").xpos
    for side in ("left", "right"):
        name = side + "_finger"
        local = arm[-1].T @ (data.body(name).xpos - hand) - model.body(name).pos
        fingers.append(float(local @ model.joint(f"finger_{side}_joint").axis.ravel()))
    return dict(
        camera_joint_positions_rad=q,
        camera_finger_positions_m=fingers,
        camera_encoder_sim_time_s=float(data.time),
    )


class RobotDepthReference:
    """A robot-only forward projection of encoders, with the registered rasterizer.

    The private model/data never advance physics, have no input for the true
    workpiece pose, and never request or return segmentation labels.
    """

    def __init__(self, asset, width, height):
        import mujoco

        self.mj = mujoco
        self.model = mujoco.MjModel.from_xml_path(str(asset))
        self.data = mujoco.MjData(self.model)
        self.data.qpos[self.model.joint("object_free").qposadr[0]] = 4.0
        self.renderer = mujoco.Renderer(self.model, width=width, height=height)
        self.renderer.enable_depth_rendering()

    def project(self, joints, fingers):
        self.data.qpos[:7] = joints
        self.data.qpos[7:9] = fingers
        self.mj.mj_forward(self.model, self.data)
        self.renderer.update_scene(self.data, camera="rgbd")
        return self.renderer.render()

    def close(self):
        self.renderer.close()


def _xyz(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    if isinstance(value, dict):
        value = [value[k] for k in "xyz"]
    v = np.array(value, dtype=float)
    if v.shape != (3,) or not np.isfinite(v).all():
        raise ValueError("invalid xyz")
    return v


def _capsule(points, eye, ends, radius, tolerance):
    delta = ends[1] - ends[0]
    length = delta @ delta
    t = np.clip((points - ends[0]) @ delta / length, 0, 1) if length > 0 else 0.0
    origin = ends[0] + np.asarray(t)[..., None] * delta
    normals = points - origin
    # At a silhouette a finite pixel cone and optical error can straddle the tangent.
    facing = (normals * (eye - points)).sum(axis=1)
    return (abs(np.linalg.norm(normals, axis=1) - radius) <= tolerance) & (
        facing >= -tolerance * np.linalg.norm(eye - points, axis=1)
    )


def _covers(points, camera, depth, floor_contact):
    """Every pixel cone in the projected bounding rectangle has a calibrated far return."""
    tf = np.asarray(camera["camera_to_world"]).reshape(4, 4)
    local = (points - tf[:3, 3]) @ tf[:3, :3]
    if local[:, 2].min() <= 0:
        return False
    fx, fy, cx, cy = camera["intrinsics"]
    uv = local[:, :2] / local[:, 2, None] * [fx, fy] + [cx, cy]
    lo, hi = np.floor(uv.min(axis=0) - 0.5).astype(int), np.ceil(uv.max(axis=0) + 0.5).astype(int)
    if (lo < 0).any() or (hi >= depth.shape[::-1]).any():
        return False
    roi = depth[lo[1] : hi[1] + 1, lo[0] : hi[0] + 1]
    # Resting workpiece can meet its named static support. The signed nominal
    # floor/structure distances are checked separately for each moving part.
    return bool(roi.size and roi.min() + floor_contact >= local[:, 2].max())


class LocalClearance:
    def __init__(
        self, geometry, asset_path, calibration_dir, *, calibration_sha256, isolated_scene
    ):
        base = Path(calibration_dir)
        manifest = base / "manifest.json"
        if type(isolated_scene) is not bool or not isolated_scene:
            raise ValueError("certified exclusive development workspace required")
        if digest(manifest) != calibration_sha256:
            raise ValueError("unbound calibration manifest")
        reg = json.loads(manifest.read_bytes())
        asset_hash = digest(asset_path)
        if (
            reg["schema"] != "g1.controlled-workspace.calibration.v1"
            or reg["asset_sha256"] != geometry["pose_marker"]["marked_asset_sha256"]
            or reg["asset_sha256"] != asset_hash
            or reg["primary_camera"] != geometry["camera"]
            or reg["optical_band_m"] != BAND
        ):
            raise ValueError("incorrect asset or camera registration")
        self.model = Model(asset_path)
        self.motion = MotionGeometry(self.model)
        profile_path = Path(__file__).with_name("g1_complete_cv_motion_profile.json")
        profile = json.loads(profile_path.read_bytes())
        if (
            digest(profile_path)
            != "d0538758052dcaab43af8cea64c1defe43396eae1fa12d15c8a33ddc84a7c1f8"
            or profile["asset_sha256"] != asset_hash
            or profile["parts"] != self.motion.names
        ):
            raise ValueError("unbound trajectory and stop calibration")
        self.motion_profiles = profile["phases"]
        support_path = Path(__file__).with_name("g1_complete_cv_support_profile.json")
        support = json.loads(support_path.read_bytes())
        if (
            digest(support_path)
            != "1202b3a1bafe024dd99b1d4d5b0869c608fbf73713ece3597482c942ef63eae6"
            or support["parts"] != profile["parts"]
            or support["sources"] != profile["sources"]
            or support["asset_sha256"] != asset_hash
        ):
            raise ValueError("unbound directional motion calibration")
        self.axes = np.asarray(support["axes"])
        self.opposite = np.argmin(self.axes @ self.axes.T, axis=1)
        self.down = int(np.argmin(self.axes[:, 2]))
        self.support_phases = {
            stage: (
                1.25 * (np.asarray(values["normal"]) + np.asarray(values["stop"]))
                + 0.0005 * abs(self.axes).sum(axis=1)
            )
            for stage, values in support["phases"].items()
        }
        self.asset_path = Path(asset_path)
        self.robot_raster = None
        self.geometry, self.asset_sha, self.calibration_sha = (
            geometry,
            asset_hash,
            calibration_sha256,
        )
        self.maps = {}
        for label in ("table", "panel-primary", "panel-start"):
            row = reg["maps"][label]
            path = base / row["depth_file"]
            if path.parent.resolve() != base.resolve() or digest(path) != row["depth_sha256"]:
                raise ValueError("unbound calibrated depth map")
            depth = np.load(path, allow_pickle=False)
            camera = row["camera"]
            if depth.shape != (camera["height"], camera["width"]):
                raise ValueError("invalid calibrated map shape")
            self.maps[label] = (camera, depth)
        camera, self.reference = self.maps["table"]
        tf = np.asarray(camera["camera_to_world"]).reshape(4, 4)
        self.eye = tf[:3, 3]
        fx, fy, cx, cy = camera["intrinsics"]
        v, u = np.indices(self.reference.shape)
        self.rays = (
            np.stack(((u - cx) / fx, (v - cy) / fy, np.ones_like(v)), axis=-1) @ tf[:3, :3].T
        )
        self.pixel_extent = np.hypot(0.5 / fx, 0.5 / fy)
        self.episode = None
        self.seen = set()

    def short_motion(self, q, f, dq, df, center, rot, skill, robot, allow_table_contact):
        row = self.motion_profiles[skill]
        speed = float(abs(dq).max())
        # A future brake may start at any of the following eight physical ticks.
        # Use the enclosing measured speed class, including observed acceleration.
        reachable_speed = speed + float(row["speed_increment"])
        bins = row["brakes"]
        choices = [
            v
            for v in sorted(map(float, bins))
            if reachable_speed <= v and bins[str(v)]["stop_branches"] >= 3
        ]
        selected = bins[str(choices[0])] if choices else row
        profile = dict(
            normal=np.array(row["normal"]) * 1.25 + 0.00025,
            stop=np.array(selected["stop"]) * 1.25 + 0.00025,
        )
        evidence = dict(
            physics_ticks=8,
            brake_ticks=240,
            training_windows=row["normal_windows"],
            stop_branches=selected["stop_branches"],
            max_initial_joint_speed_rad_s=speed,
            brake_speed_class=choices[0] if choices else None,
        )
        if speed > max(row["peak_joint_speed"]) + float(row["speed_increment"]) + 0.002:
            return evidence | dict(reason="measured_speed_outside_motion_calibration")
        boxes, vertices = self.motion.envelopes(
            q, f, dq, df, center, rot, skill, profile, with_vertices=True
        )
        supports = {}

        def upper(i):
            if i not in supports:
                supports[i] = upper_support(
                    vertices[:, i], self.axes, self.support_phases[skill][i]
                )
            return supports[i]

        refinements = []
        start = self.motion.load_start
        load = boxes[start:]
        cs = np.array([b.c for b in load])
        hs = np.array([b.h for b in load])
        minimum = float("inf")
        pair = None
        floor = self.model.table.c[2] + self.model.table.h[2]
        for i, b in enumerate(boxes):
            gap = float(b.c[2] - abs(b.r[2]) @ b.h - floor)
            if b.name == "object_geom" and allow_table_contact:
                gap = float("inf")
            elif gap <= 0:
                gap = max(gap, float(-upper(i)[self.down] - floor))
            if gap < minimum:
                minimum, pair = gap, [b.name, "table"]
            if i >= start:
                continue
            if (
                skill in ("GRASP", "LIFT", "MOVE_TO_REGION", "PLACE", "RELEASE")
                and i >= self.motion.hand_start
            ):
                # Independent world boxes would count shared payload and wrist translation
                # twice. The measured relative-vertex excursions use workpiece coordinates.
                j = i - self.motion.hand_start
                source = robot[j]
                pad = (
                    np.array(row["relative_normal"][j]) + selected["relative_stop"][j]
                ) * 1.25 + 0.0005
                b = Box(b.name, source.c, source.h + abs(source.r.T @ rot) @ pad, source.r)
                gaps = box_gaps(b, center + self.model.obj_c @ rot.T, self.model.obj_h, rot)
                if j:
                    gaps[0] = float("inf")
            else:
                gaps = box_gaps(b, cs, hs, rot)
                for k in np.flatnonzero(gaps <= 0):
                    # Each axis tests the complete sampled forecast and both
                    # signed uncertainties. A single positive axis suffices.
                    separation = -upper(start + k)[self.opposite] - upper(i)
                    axis = int(np.argmax(separation))
                    improved = float(separation[axis])
                    refinements.append(
                        dict(
                            pair=[b.name, load[k].name],
                            gap_box_m=float(gaps[k]),
                            gap_support_m=improved,
                            axis_world=self.axes[axis].tolist(),
                        )
                    )
                    gaps[k] = max(gaps[k], improved)
            k = int(np.argmin(gaps))
            if gaps[k] < minimum:
                minimum, pair = float(gaps[k]), [b.name, load[k].name]
        evidence.update(minimum_gap_m=minimum, limiting_pair=pair, signed_support=refinements)
        if minimum <= 0:
            return evidence | dict(reason="eight_tick_and_stop_envelope_meets_solid")
        views = {}
        for b in boxes:
            corners = b.corners()
            if b.name == "object_geom" and allow_table_contact:
                # This is the single pre-authorized contact on the named support.
                # The object's observed pose and all hardware solids remain checked.
                corners[:, 2] = np.maximum(corners[:, 2], floor)
            view = next(
                (
                    k
                    for k in ("panel-primary", "panel-start")
                    if _covers(corners, *self.maps[k], 2 * BAND if b.name == "object_geom" else 0.0)
                ),
                None,
            )
            views[b.name] = view
        return evidence | dict(
            reason=None if all(views.values()) else "short_motion_outside_calibrated_views",
            views=views,
        )

    def close(self):
        if self.robot_raster is not None:
            self.robot_raster.close()
            self.robot_raster = None

    def changed_surfaces(self, frame, workpiece, robot, tcp, links, joints, fingers):
        depth = axial(frame)
        near, lost = depth_changes(depth, self.reference, BAND)
        ys, xs = near.nonzero()
        points = self.eye + self.rays[ys, xs] * depth[ys, xs, None]
        # The visible-pixel cone is propagated into the surface attribution
        # in metres. It grants no occupancy exemption away from the actual face.
        ray_tol = BAND + self.pixel_extent * float(depth[ys, xs].max(initial=0))
        objects = np.zeros(len(points), dtype=bool)
        arm = np.zeros_like(objects)
        for b in workpiece:
            # Current marker localization and current depth each carry an optical band.
            objects |= visible_box(points, self.eye, b, ray_tol + BAND)
        for b in robot:
            arm |= visible_box(points, self.eye, b, ray_tol)
        for _, ends, radius in links:
            arm |= _capsule(points, self.eye, ends, radius, ray_tol)
        arm |= _capsule(points, self.eye, np.array([tcp, tcp]), self.model.site_radius, ray_tol)
        base = self.model.base
        radial = np.linalg.norm(points[:, :2] - base[:2], axis=1)
        radius, half = self.model.base_size
        top = (abs(points[:, 2] - base[2] - half) <= ray_tol) & (radial <= radius + ray_tol)
        sides = (
            (abs(radial - radius) <= ray_tol)
            & (abs(points[:, 2] - base[2]) <= half + ray_tol)
            & (
                ((points[:, :2] - base[:2]) * (self.eye[:2] - points[:, :2])).sum(axis=1)
                >= -ray_tol * np.linalg.norm(self.eye[:2] - points[:, :2], axis=1)
            )
        )
        arm |= top | sides
        unknown = ~(objects | arm)
        explained_raster = 0
        if unknown.any():
            if self.robot_raster is None:
                self.robot_raster = RobotDepthReference(self.asset_path, frame.width, frame.height)
            pred = self.robot_raster.project(joints, fingers)
            ii = np.flatnonzero(unknown)
            y, x = ys[ii], xs[ii]
            explained = robot_raster_matches(depth[y, x], pred[y, x], self.reference[y, x], BAND)
            arm[ii[explained]] = True
            unknown[ii[explained]] = False
            explained_raster = int(explained.sum())
        return dict(
            nearer_returns=int(near.sum()),
            arm_surface_pixels=int(arm.sum()),
            robot_raster_surface_pixels=explained_raster,
            workpiece_surface_pixels=int(objects.sum()),
            unknown_pixels=int(unknown.sum()),
            unmatched_pixels_uv=np.column_stack((xs[unknown], ys[unknown]))[:12].tolist(),
            unmatched_world_m=points[unknown][:12].round(5).tolist(),
            lost_or_farther_static=int(lost.sum()),
            static_covered=int((self.reference > 0).sum()),
            measured_surface_tolerance_m=ray_tol,
            missing_uv=np.column_stack(lost.nonzero())[:8, ::-1].tolist(),
        )

    def check(
        self,
        frame,
        marker,
        robot_measurement,
        skill,
        target_xyz,
        orientation_wxyz,
        *,
        phase="FEEDBACK",
    ):
        started = time.perf_counter_ns()
        result = dict(
            schema="g1.local-current-rgbd.v1",
            skill=skill,
            phase=phase,
            calibration_sha256=self.calibration_sha,
            selected_object_delta_m=[0.0, 0.0, 0.0],
        )

        def finish(status, reason):
            return dict(
                result,
                status=status,
                reason=reason,
                check_ms=(time.perf_counter_ns() - started) / 1e6,
            )

        if type(frame) is not RGBDObservation:
            return finish("UNKNOWN", "unbound_frame_type")
        result.update(frame_id=frame.frame_id, checksum_sha256=frame.checksum_sha256)
        if frame.model_dump(mode="json", include=set(CAMERA_FIELDS)) != self.geometry["camera"]:
            return finish("UNKNOWN", "camera_registration_mismatch")
        if not frame.scene_id or not frame.episode_id:
            return finish("UNKNOWN", "missing_native_scene")
        identity = (frame.scene_id, frame.episode_id)
        if self.episode not in (None, identity) or frame.frame_id in self.seen:
            return finish("UNKNOWN", "changed_episode_or_repeated_frame")
        self.episode = identity
        self.seen.add(frame.frame_id)
        if (
            marker.get("usable") is not True
            or marker.get("frame_id") != frame.frame_id
            or marker.get("checksum") != frame.checksum_sha256
            or marker.get("asset_sha256") != self.asset_sha
            or marker.get("registration_id") != self.geometry["registration_id"]
        ):
            return finish("UNKNOWN", "current_registered_marker_required")
        m = robot_measurement
        if (
            m.get("frame_id") != frame.frame_id
            or m.get("checksum_sha256") != frame.checksum_sha256
            or m.get("sim_time_s") != frame.sim_time_s
        ):
            return finish("UNKNOWN", "synchronized_measured_robot_required")
        if tuple(orientation_wxyz) != _DOWNWARD:
            return finish("UNKNOWN", "unqualified_wrist")
        if skill not in (
            "MOVE_ABOVE",
            "APPROACH",
            "GRASP",
            "LIFT",
            "MOVE_TO_REGION",
            "PLACE",
            "RELEASE",
            "RETREAT",
        ):
            return finish("UNKNOWN", "unregistered_skill")
        q = np.array(m.get("joint_positions_rad"), dtype=float)
        fingers = np.array(m.get("finger_positions_m"), dtype=float)
        if (
            q.shape != (7,)
            or fingers.shape != (2,)
            or not np.isfinite(q).all()
            or not np.isfinite(fingers).all()
            or max(abs(fingers - 0.020)) > 0.024
        ):
            return finish("UNKNOWN", "invalid_measured_joints")
        center = _xyz(marker["object_center_world_m"])
        rot = np.asarray(marker["rotation_object_to_world"], dtype=float).reshape(3, 3)
        if (
            not np.isfinite(rot).all()
            or not np.allclose(rot.T @ rot, np.eye(3), atol=1e-5)
            or np.linalg.det(rot) < 0.999
            or rot[2, 2] < 0.98
        ):
            return finish("UNKNOWN", "invalid_measured_workpiece_rotation")
        tcp, r, links = self.model.forward(q)
        if "tcp_position_m" in m and np.linalg.norm(_xyz(m["tcp_position_m"]) - tcp) > 0.001:
            return finish("UNKNOWN", "registered_fk_disagrees")
        robot = self.model.hand_at(tcp, r, fingers)
        obj = [b.placed(center, rot) for b in self.model.object]
        exposed_q = q
        exposed_f = fingers
        if "camera_joint_positions_rad" in m:
            exposed_q = np.asarray(m["camera_joint_positions_rad"], dtype=float)
            exposed_f = np.asarray(m["camera_finger_positions_m"], dtype=float)
            if (
                m.get("camera_encoder_sim_time_s") != frame.sim_time_s
                or exposed_q.shape != (7,)
                or exposed_f.shape != (2,)
                or not np.isfinite(exposed_q).all()
                or not np.isfinite(exposed_f).all()
                or abs(exposed_q - q).max() > 0.01
                or abs(exposed_f - fingers).max() > 0.002
            ):
                return finish("UNKNOWN", "camera_encoder_and_current_robot_differ")
        result["camera_current_encoder_difference"] = dict(
            joint_rad=float(abs(exposed_q - q).max()),
            finger_m=float(abs(exposed_f - fingers).max()),
        )
        measured = self.changed_surfaces(frame, obj, robot, tcp, links, exposed_q, exposed_f)
        result["depth"] = measured
        if measured["unknown_pixels"]:
            return finish("BLOCKED", "unregistered_near_surface")
        if measured["lost_or_farther_static"]:
            return finish("UNKNOWN", "lost_static_depth_support")
        floor = self.model.table.c[2] + self.model.table.h[2]
        present = self.model.hand_gaps(
            robot,
            center,
            rot,
            fingers_may_touch=skill
            in ("GRASP", "LIFT", "MOVE_TO_REGION", "PLACE", "RELEASE", "RETREAT"),
        )
        result["measured_hand_gap"] = present
        result["hand_above_floor_m"] = min(float(b.c[2] - abs(b.r[2]) @ b.h - floor) for b in robot)
        if present["gap_m"] <= 0 or result["hand_above_floor_m"] <= 0:
            return finish("BLOCKED", "measured_hand_intersects_registered_solid")
        for name, ends, radius in links:
            if ends[:, 2].min() - radius <= floor:
                return finish("BLOCKED", "measured_arm_intersects_registered_table")
            # Enclose the complete measured capsule in its own oriented segment box.
            axis = (ends[1] - ends[0]) / np.linalg.norm(ends[1] - ends[0])
            ref = np.array([0.0, 1.0, 0.0]) if abs(axis[1]) < 0.8 else np.array([1.0, 0.0, 0.0])
            perp = np.cross(axis, ref)
            perp /= np.linalg.norm(perp)
            basis = np.column_stack((axis, perp, np.cross(axis, perp)))
            b = Box(
                name,
                ends.mean(axis=0),
                np.array([np.linalg.norm(ends[1] - ends[0]) / 2 + radius, radius, radius]),
                basis,
            )
            if self.model.hand_gaps([b], center, rot)["gap_m"] <= 0:
                return finish("UNKNOWN", "measured_arm_envelope_meets_registered_workpiece")
        # The same actual camera observed these empty volumes in the separate
        # registration. The second view observes the start hand outside the main FOV.
        covers = {}
        for b in [*robot, *obj]:
            corners = b.corners()
            tolerance = 2 * BAND if b in obj else 0.0
            view = next(
                (
                    k
                    for k in ("panel-primary", "panel-start")
                    if _covers(corners, *self.maps[k], tolerance)
                ),
                None,
            )
            covers[b.name] = view
        result["known_volume_views"] = covers
        if any(v is None for v in covers.values()):
            return finish("UNKNOWN", "outside_calibrated_free_volume")
        if target_xyz is not None:
            target = _xyz(target_xyz)
            result["commanded_target_xyz_m"] = target.tolist()
            if not (
                0.08 <= target[0] <= 0.72
                and -0.53 <= target[1] <= 0.41
                and floor <= target[2] <= 0.68
            ):
                return finish("UNKNOWN", "target_outside_calibrated_workcell")
        if skill in ("MOVE_ABOVE", "APPROACH", "GRASP"):
            low = _xyz(marker["grasp_world_m"])
            route = self.model.approach(center, rot, low, 0.039)
            result["center_approach"] = route
            if route["gap_m"] <= 0:
                return finish("BLOCKED", "registered_center_descent_or_close_intersects")
            angle, patch, reason = grasp_readiness(
                frame, marker, self.geometry, center, rot, tcp, r, fingers, closure=skill == "GRASP"
            )
            if angle is not None:
                result["grasp_angle"] = angle
            if patch is not None:
                result["grasp_patch"] = patch
            if reason:
                return finish("UNKNOWN", reason)
        dq = np.asarray(m.get("joint_velocities_rad_s"), dtype=float)
        df = np.asarray(m.get("finger_velocities_m_s"), dtype=float)
        if (
            dq.shape != (7,)
            or df.shape != (2,)
            or not np.isfinite(dq).all()
            or not np.isfinite(df).all()
        ):
            return finish("UNKNOWN", "synchronized_joint_and_finger_speeds_required")
        dest = self.model.region
        in_region = bool((abs(center[:2] - dest.c[:2]) <= dest.h[:2]).all())
        allow_ground = skill in ("MOVE_ABOVE", "APPROACH", "GRASP", "LIFT") or (
            skill in ("PLACE", "RELEASE", "RETREAT") and in_region
        )
        motion = self.short_motion(q, fingers, dq, df, center, rot, skill, robot, allow_ground)
        result["short_motion"] = motion
        if motion["reason"]:
            return finish("UNKNOWN", motion["reason"])
        return finish("CLEAR", "controlled_scene_current_surfaces_and_registered_clearance")
