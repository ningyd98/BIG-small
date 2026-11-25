"""Independent current-image rendering of the registered carried surfaces and measured arm."""

import base64
from xml.etree import ElementTree as ET

import cv2
import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import BAND, axial
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_handoff_optics import directional_error


def compare_face_patch(observed, reference, colors, expected_colors, interior):
    """Require the centre and its independently predicted neighbors on one continuous face."""
    if not (np.all(interior) and np.all(np.isfinite(observed)) and np.all(observed > 0)):
        return False
    # In particular never use a renderer's multisample edge as a solid surface.
    if np.ptp(reference) >= BAND or np.any(abs(observed - reference) >= BAND):
        return False
    error = abs(np.asarray(colors, float) - expected_colors)
    return bool(error.max() <= 6)


class CarriedSurface:
    def __init__(self, asset_path, width=320, height=240, *, additional_physical_fixture=None):
        import mujoco

        root = ET.parse(asset_path).getroot()
        obj = root.find("./worldbody/body[@name='object']")
        # The reference has no free object or live state. Only optical rigid transforms
        # may set the single kinematic drawing body. All original prints and edges remain.
        for child in list(obj):
            if child.tag == "freejoint" or child.tag == "joint" and child.get("type") == "free":
                obj.remove(child)
        obj.set("mocap", "true")
        if additional_physical_fixture is not None:
            root.find("worldbody").append(ET.fromstring(additional_physical_fixture))
        self.boxes = Model(asset_path).object
        self.mj = mujoco
        self.model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))
        self.data = mujoco.MjData(self.model)
        self.renderer = mujoco.Renderer(self.model, width=width, height=height)
        self.width = width
        self.height = height
        self.arm = np.array([self.model.joint("joint" + str(i)).qposadr[0] for i in range(1, 8)])
        self.finger = np.array(
            [self.model.joint("finger_" + side + "_joint").qposadr[0] for side in ("left", "right")]
        )
        self.object = self.model.body("object").mocapid[0]

    def project(self, center, rotation, joints, fingers):
        self.data.qpos[self.arm] = joints
        self.data.qpos[self.finger] = fingers
        self.data.mocap_pos[self.object] = center
        self.mj.mju_mat2Quat(self.data.mocap_quat[self.object], np.asarray(rotation).ravel())
        self.mj.mj_forward(self.model, self.data)
        self.renderer.update_scene(self.data, camera="rgbd")
        self.renderer.disable_depth_rendering()
        rgb = self.renderer.render().copy()
        self.renderer.enable_depth_rendering()
        depth = self.renderer.render().copy()
        return rgb, depth

    def close(self):
        self.renderer.close()

    def _first_interior_face(self, uv, frame, pose, z):
        tf = np.asarray(frame.camera_to_world).reshape(4, 4)
        fx, fy, cx, cy = frame.intrinsics
        offsets = np.array([(x, y) for y in (-1, 0, 1) for x in (-1, 0, 1)])
        pixels = np.asarray(uv) + offsets
        ray = (
            np.column_stack(((pixels[:, 0] - cx) / fx, (pixels[:, 1] - cy) / fy, np.ones(9)))
            @ tf[:3, :3].T
        )
        rotation = np.asarray(pose["rotation"])
        ray = ray @ rotation
        eye = (tf[:3, 3] - pose["center_m"]) @ rotation
        first = np.full(9, np.inf)
        names = np.full(9, -1)
        faces = np.full(9, -1)
        within = np.zeros(9, bool)
        for j, box in enumerate(self.boxes):
            with np.errstate(divide="ignore", invalid="ignore"):
                near = (box.c - box.h - eye) / ray
                far = (box.c + box.h - eye) / ray
            start = np.minimum(near, far)
            end = np.maximum(near, far)
            face = start.argmax(axis=1)
            entry = start.max(axis=1)
            hit = (end.min(axis=1) >= entry) & (entry > 0) & (entry < first)
            if not hit.any():
                continue
            local = eye + entry[:, None] * ray
            safe = np.ones(9, bool)
            for k in range(3):
                direction = rotation[:, k]
                signed_error = directional_error(pose, local, direction)
                safe &= (face == k) | (abs(local[:, k] - box.c[k]) + signed_error < box.h[k])
            first[hit] = entry[hit]
            names[hit] = j
            faces[hit] = face[hit]
            within[hit] = safe[hit]
        if (names < 0).any() or np.ptp(names) or np.ptp(faces):
            return np.zeros((3, 3), bool)
        axis = int(faces[4])
        # Very grazing rays and crossing first faces are intrinsically ambiguous.
        return (within & (abs(ray[:, axis]) > 0.45) & (abs(first - z.ravel()) < BAND)).reshape(3, 3)

    def explain(self, frame, pose, camera_joints, camera_fingers, uv):
        """Compare only unresolved rays to the current independent object and hand projection."""
        uv = np.asarray(uv)
        flags = np.zeros(len(uv), bool)
        evidence = dict(checked=len(uv), explained=0, reason="missing_current_optical_pose")
        if not len(uv):
            return flags, evidence
        if len(uv) > 32:
            evidence["reason"] = "excess_unresolved_returns"
            return flags, evidence
        if (
            not pose
            or pose.get("frame_id") != frame.frame_id
            or pose.get("checksum_sha256") != frame.checksum_sha256
        ):
            return flags, evidence
        if (
            (frame.width, frame.height) != (self.width, self.height)
            or uv.ndim != 2
            or uv.shape[1] != 2
            or not np.issubdtype(uv.dtype, np.integer)
        ):
            return flags, evidence
        joints = np.asarray(camera_joints)
        fingers = np.asarray(camera_fingers)
        if (
            joints.shape != (7,)
            or fingers.shape != (2,)
            or not np.isfinite(np.r_[joints, fingers]).all()
        ):
            return flags, evidence
        rgb, z = self.project(pose["center_m"], pose["rotation"], joints, fingers)
        depth = axial(frame)
        actual = cv2.imdecode(
            np.frombuffer(base64.b64decode(frame.rgb_png_base64), np.uint8), cv2.IMREAD_COLOR
        )
        if actual is None:
            return flags, evidence
        actual = actual[:, :, ::-1]
        for i, (u, v) in enumerate(uv):
            if 1 <= u < self.width - 1 and 1 <= v < self.height - 1:
                roi = np.s_[v - 1 : v + 2, u - 1 : u + 2]
                face = self._first_interior_face((u, v), frame, pose, z[roi])
                flags[i] = compare_face_patch(depth[roi], z[roi], actual[roi], rgb[roi], face)
        evidence.update(
            explained=int(flags.sum()), reason="same_visible_interior_face_and_current_rgbd"
        )
        return flags, evidence
