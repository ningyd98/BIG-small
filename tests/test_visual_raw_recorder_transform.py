"""Software camera fixtures verify actual recorded sensor corruption provenance."""

import pytest

from cloud_edge_robot_arm.research.raw_episode_v3 import _replay_transform
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from tests.test_visual_raw_recorder_v3 import recorder_fixture, software_sensor_camera


def transform_fixture(tmp_path, *, invalid_source=False, wrong_bytes=False, failure=False):
    recorder, backend, capture, executor, identity, original = recorder_fixture(tmp_path)
    software_sensor_camera(backend)
    seen = []

    def transform(observation):
        seen.append(observation)
        if failure:
            raise RuntimeError("software corruption failed")
        policy = {
            "schema_version": "rgbd.fixed-corruption.v1",
            "perturbation_seed": 17,
            "frame_count": len(seen),
            "noise_m": 0.005,
            "invalid_fraction": 0.1,
            "occlusion_fraction": 0.25,
        }
        source = "src/cloud_edge_robot_arm/vision/raw_recorder_v3.py"
        sources = {source: "0" * 64 if invalid_source else recorder.source_hashes[source]}
        derived = (
            observation
            if wrong_bytes
            else RGBDObservation.model_validate(
                _replay_transform(observation.model_dump(mode="json"), policy)
            )
        )
        return derived, policy, sources

    capture.transform_observation = transform
    return recorder, backend, capture, identity, original, seen


def test_sensor_corruption_is_applied_once_and_keeps_clean_source(tmp_path):
    recorder, backend, capture, identity, original, seen = transform_fixture(tmp_path)
    with capture, recorder:
        returned = recorder.capture()
        recorder.bind_source(identity, original)
        source, online = recorder.build_records().frames
        assert len(seen) == 1
        assert source.input_role == "SOURCE" and online.input_role == "ONLINE"
        assert online.source_acquisition_id == source.acquisition_id
        assert source.interval_id == online.interval_id
        assert source.camera_state_payload == online.camera_state_payload
        assert source.pass_state_hashes == online.pass_state_hashes
        assert RGBDObservation.model_validate(dict(source.observation_payload)) == seen[0]
        assert RGBDObservation.model_validate(dict(online.observation_payload)) == returned
        assert returned.checksum_sha256 != seen[0].checksum_sha256
        assert recorder.allocated_acquisition_ids == ("acquisition-1", "acquisition-2")
        assert recorder._last_online_id == online.acquisition_id
        assert backend.total_physics_steps == 0 and backend.command_records == []
    assert (
        len(
            [
                row
                for row in backend.operation_ledger
                if row["kind"] == "CAPTURE" and row["phase"] == "BEGIN"
            ]
        )
        == 1
    )


@pytest.mark.parametrize("option", ["invalid_source", "wrong_bytes", "failure"])
def test_corruption_failure_retains_derived_denominator_and_never_returns_clean(tmp_path, option):
    recorder, backend, capture, identity, original, seen = transform_fixture(
        tmp_path, **{option: True}
    )
    with capture, recorder:
        with pytest.raises((RuntimeError, ValueError)):
            recorder.capture()
        recorder.bind_source(identity, original)
        source, failed = recorder.build_records().frames
        assert source.input_role == "SOURCE" and source.observation_payload is not None
        assert failed.input_role == "ONLINE" and failed.observation_payload is None
        assert failed.source_acquisition_id is None
        assert recorder.allocated_acquisition_ids == ("acquisition-1", "acquisition-2")
        assert recorder._last_online_id is None
        assert len(seen) == 1 and backend.total_physics_steps == 0
