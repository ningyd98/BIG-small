"""Rigid score geometry, source-addressed mount generations and old case preservation."""

import copy
import json
from pathlib import Path

import numpy as np
import pytest
from scripts.graduation import g1_visibility_runtime as build
from scripts.graduation import g1_visibility_trials as trials


@pytest.mark.parametrize("radius_mm", [100, 115, 130])
@pytest.mark.parametrize("code", [7, 8])
def test_score_rigid_pose_is_rebuilt_from_an_independently_registered_attachment(radius_mm, code):
    from scripts.graduation.g1_visibility_mount_runtime import rigid_geometry

    t = np.eye(4)
    t[1 if code == 7 else 0, 3] = radius_mm / 1000
    t[2, 3] = 0.03505
    alpha = 0.27
    r = np.array([[np.cos(alpha), -np.sin(alpha), 0], [np.sin(alpha), np.cos(alpha), 0], [0, 0, 1]])
    obj = np.array([0.45, 0.017, 0.035])
    w = obj + r @ t[:3, 3]
    tool = np.eye(4)
    tool[2, 3] = 0.01
    g = {
        "development_dual": {"markers": {str(code): {"object_T_marker": t.ravel().tolist()}}},
        "object_half_extent_m": [0.035, 0.035, 0.035],
        "object_to_tcp": tool.ravel().tolist(),
    }
    center, top, tcp = rigid_geometry(w, r.ravel(), code, g)
    assert np.allclose(center, obj, rtol=0, atol=1e-15)
    assert np.allclose(top, obj + [0, 0, 0.035], rtol=0, atol=1e-15)
    assert np.allclose(tcp, obj + [0, 0, 0.01], rtol=0, atol=1e-15)


def test_prepare_cli_has_explicit_discrete_registration_without_environment_selection():
    assert trials.parser().parse_args(["prepare"]).radial_mm == 0
    for offset in (15, 30):
        assert (
            trials.parser().parse_args(["prepare", "--radial-mm", str(offset)]).radial_mm == offset
        )
    with pytest.raises(SystemExit):
        trials.parser().parse_args(["prepare", "--radial-mm", "20"])


def test_prior_source_tree_remains_the_only_mechanical_parent():
    from scripts.graduation import g1_visibility_mount_runtime as mount

    assert (
        mount.PARENT_GENERATION
        == "c3ca24cf1dc459651bd99dc85a997c36d39108c91d3cf7fb73d35e8071487261"
    )
    tree = Path(build.PRIVATE) / "builds" / mount.PARENT_GENERATION / "runtime-source"
    if not tree.exists():
        pytest.skip("immutable source tree unavailable")
    lock = json.loads((tree / "runtime-build.json").read_text())
    assert (
        mount.reader_bytes((tree / mount.READER).read_bytes()) != (tree / mount.READER).read_bytes()
    )
    assert lock["runtime_files_sha256"][mount.READER] == build.sha(tree / mount.READER)


def test_wrong_generation_geometry_is_rejected_before_unscored_data_can_be_joined():
    from scripts.graduation.g1_visibility_mount_runtime import verify_geometry

    source = Path("experiments/results/g1-formal-paired-20261124/trials/f01-dual/allocation.json")
    if not source.is_file():
        pytest.skip("private registered geometry unavailable")
    old = json.loads(source.read_text())["geometry"]
    spec = dict(
        offset_mm=15,
        family="new",
        registration_id="new-reg",
        asset_path="new.xml",
        asset_sha256="0" * 64,
        body_mass_kg=0.10102432,
        centers={"7": [0, 0.115, 0.03505], "8": [0.115, 0, 0.03505]},
    )
    with pytest.raises(ValueError):
        verify_geometry(old, copy.deepcopy(old), spec, {})


@pytest.fixture(scope="module")
def radial_calibration_evidence():
    from scripts.graduation.perception_io import pinned

    round_root = Path("artifacts/research/process/20261004-ced-development/astra-rounds")
    plan = pinned(
        round_root / "round-g1-radial-calibration-witness-20261125/plan.json",
        "5c8381df27ab735b68cb1a281a0139b42661a4116201649a5085b0a793df9f2d",
    )
    filename = next(name for name in plan["inputs_sha256"] if name.endswith("/result.json"))
    if not Path(filename).is_file():
        pytest.skip("sealed private RGB-D pair unavailable")
    return Path(filename).parent, pinned(Path(filename), plan["wrong_calibration_row_sha256"])


def test_original_and_both_historical_native_calibration_refusals(radial_calibration_evidence):
    from scripts.graduation import g1_dual_probe as probe
    from scripts.graduation import g1_visibility_mount_runtime as mount
    from scripts.graduation.perception_io import pinned

    directory, row = radial_calibration_evidence
    assert not probe.expected_refusal(
        "wrong-calibration", row["measurement"], row["servo_refusal"], row["target_refusal"]
    )
    assert mount.wrong_calibration_witness(directory, row)
    history = pinned(
        Path("artifacts/research/process/20261004-ced-development/astra-rounds")
        / "round-g1-first-refusal-dual-marker-20261124/zero-step-probes.public.json",
        "e8d1cbee3e655bfb8eb2daa54ed4236fa738e312ef9e2ce7b7cbc91773931c55",
    )
    archived = [r for r in history["results"] if r["kind"] == "wrong-calibration"]
    assert {r["pose"] for r in archived} == {"preregistered-0", "preregistered-1"}
    for r in archived:
        assert r["control_demonstrated"] and r["physics_steps"] == r["commands"] == 0
        assert probe.expected_refusal(
            "wrong-calibration",
            {"reason": r["measured_reason"]},
            r["servo_error"],
            r["target_error"],
        )
        # Apply the two observed native errors to the sealed radial input as a software control.
        assert mount.wrong_calibration_witness(
            directory,
            {**row, "servo_refusal": r["servo_error"], "target_refusal": r["target_error"]},
        )


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("measurement", "reason", "registered_scene_mismatch"),
        ("measurement", "reason", "known_marker_not_observed"),
        ("measurement", "reason", "ambiguous_marker_identity"),
        ("measurement", "usable", True),
        ("measurement", "frame_id", "another_frame"),
        ("measurement", "observation_id", "another_observation"),
        ("measurement", "checksum", "0" * 64),
        (
            "row",
            "target_refusal",
            "registered collection geometry unavailable: observation_not_fresh",
        ),
        ("row", "target_refusal", "development dual registration and runtime sources differ"),
        ("row", "target_refusal", "initial registered geometry unavailable: unknown_calibration"),
        ("row", "target_refusal", None),
        ("row", "servo_refusal", "servo calibration mismatched because of another camera"),
        ("row", "servo_refusal", None),
        ("row", "source_sha256", "0" * 64),
        ("row", "tested_sha256", "0" * 64),
        ("row", "id", "another_frame"),
        ("row", "checksum", "0" * 64),
        ("row", "target_emitted", True),
        ("row", "servo_accepted", 1),
        ("row", "commands", 1),
        ("row", "source_step", 1),
        ("row", "physics_steps", 1),
    ],
)
def test_other_failures_cannot_witness_radial_calibration(
    radial_calibration_evidence, section, field, value
):
    from scripts.graduation import g1_visibility_mount_runtime as mount

    directory, original = radial_calibration_evidence
    altered = copy.deepcopy(original)
    (altered if section == "row" else altered[section])[field] = value
    assert not mount.wrong_calibration_witness(directory, altered)


@pytest.mark.parametrize(
    "mutation", ["swapped", "other_scene", "other_calibration", "bad_checksum"]
)
def test_radial_calibration_requires_matching_valid_native_packets(
    tmp_path, radial_calibration_evidence, mutation
):
    from scripts.graduation import g1_visibility_mount_runtime as mount
    from scripts.graduation.perception_io import read, sha, write

    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    directory, original = radial_calibration_evidence
    source = read(directory / "source.rgbd.json")
    tested = read(directory / "tested.rgbd.json")
    if mutation == "swapped":
        source, tested = tested, source
    elif mutation == "bad_checksum":
        tested["checksum_sha256"] = "f" * 64
    else:
        key = "scene_id" if mutation == "other_scene" else "calibration_version"
        tested = RGBDObservation.model_validate(
            {**tested, key: "another", "checksum_sha256": ""}
        ).model_dump(mode="json")
    write(tmp_path / "source.rgbd.json", source)
    write(tmp_path / "tested.rgbd.json", tested)
    row = copy.deepcopy(original)
    row.update(
        source_sha256=sha(tmp_path / "source.rgbd.json"),
        tested_sha256=sha(tmp_path / "tested.rgbd.json"),
        checksum=tested["checksum_sha256"],
        id=tested["frame_id"],
    )
    row["measurement"].update(
        checksum=tested["checksum_sha256"],
        observation_id=tested["observation_id"],
        frame_id=tested["frame_id"],
    )
    assert not mount.wrong_calibration_witness(tmp_path, row)
