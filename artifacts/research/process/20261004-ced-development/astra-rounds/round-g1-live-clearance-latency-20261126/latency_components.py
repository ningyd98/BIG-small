"""Scoped primitives for measuring the original G1 clearance path."""

from hashlib import sha256
from pathlib import Path
from threading import get_ident
from time import perf_counter_ns

import mujoco
import numpy as np
from scripts.graduation.g1_complete_cv_clearance import RobotDepthReference

INTEGRATION_FIELD = "mujoco_integration_sha256"


def integration_sha256(backend, mj=mujoco):
    """Take the original little-endian integration digest without reading history."""
    model, data = backend._model, backend._data
    signature = mj.mjtState.mjSTATE_INTEGRATION
    state = np.empty(mj.mj_stateSize(model, signature), dtype="<f8")
    mj.mj_getState(model, data, state, signature)
    return sha256(state.tobytes()).hexdigest()


class BorrowedReference:
    def __init__(self, owner):
        self.owner = owner

    def project(self, joints, fingers):
        return self.owner.project(joints, fingers)

    def close(self):
        pass


class EpisodeRobotReference:
    """Own a renderer, never a projected image or an optical decision."""

    def __init__(self, factory=RobotDepthReference):
        self.factory = factory
        self.thread = get_ident()
        self.reference = None
        self.key = None
        self.closed = False
        self.active = False
        self.startup_ms = None
        self.close_ms = None
        self.projections = 0

    def attach(self, certificate):
        self._verify_thread()
        identity = certificate.optical_identity
        camera = certificate.geometry["camera"]
        if (
            identity is None
            or certificate.robot_raster is not None
            or certificate.asset_sha != identity.asset_sha256
            or certificate.calibration_sha != identity.calibration_sha256
            or camera["calibration_version"] != identity.calibration_version
            or (camera["width"], camera["height"]) != (identity.width, identity.height)
            or tuple(camera["intrinsics"]) != identity.intrinsics
            or tuple(camera["camera_to_world"]) != identity.camera_to_world
        ):
            raise ValueError("unverified reference renderer binding")
        key = (identity, Path(certificate.asset_path).resolve())
        if self.reference is None:
            started = perf_counter_ns()
            self.reference = self.factory(key[1], identity.width, identity.height)
            self.startup_ms = (perf_counter_ns() - started) / 1e6
            self.key = key
        elif key != self.key:
            raise ValueError("reference renderer cannot cross registered episodes")
        certificate.robot_raster = BorrowedReference(self)

    def _verify_thread(self):
        if self.closed or self.thread != get_ident():
            raise ValueError("reference renderer left its original episode thread")

    def project(self, joints, fingers):
        self._verify_thread()
        if self.reference is None or self.active:
            raise ValueError("reference renderer must have one serial caller")
        self.active = True
        try:
            result = self.reference.project(joints, fingers)
            self.projections += 1
            return result
        finally:
            self.active = False

    def close(self):
        self._verify_thread()
        if self.active:
            raise ValueError("reference renderer still rendering")
        started = perf_counter_ns()
        self.closed = True
        try:
            if self.reference is not None:
                self.reference.close()
        finally:
            self.close_ms = (perf_counter_ns() - started) / 1e6
