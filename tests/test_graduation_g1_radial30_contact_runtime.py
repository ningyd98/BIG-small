"""A 130 mm case requires its own static screen, source tree, live packets and case identity."""

from pathlib import Path

import pytest
from scripts.graduation import g1_visibility_runtime as build
from scripts.graduation import g1_visibility_trials as trials
from scripts.graduation.perception_io import sha


@pytest.fixture
def contact():
    from scripts.graduation import g1_visibility_radial_contact

    return g1_visibility_radial_contact


def test_normal_cli_reserves_separate_case_names_and_only_the_new_static_gate(contact):
    assert (
        trials.parser().parse_args(["prepare", "--radial-contact", "2" * 64]).radial_contact
        == "2" * 64
    )
    assert contact.ASSIGNMENTS == {
        "train-radial30-contact-d02-02": ["d02"],
        "train-radial30-contact-d01-01": ["d01"],
    }
    with pytest.raises(ValueError, match="130 mm"):
        contact.check_identity({"radial_timing": {}, "radial_assembly": {"offset_mm": 15}})
    assert not trials.timing_assignment("train-radial30-contact-d02-01", ["d02"])


def test_static_gate_rejects_wrong_parent_dropouts_and_failed_mechanical_control(contact):
    from scripts.graduation import g1_visibility_mount_runtime as mount

    expected = dict(
        schema="g1.visibility.radial30-screen-selection.v1",
        plan_sha256=contact.PLAN_SHA,
        parent_generation=contact.MOUNT_PARENT,
        candidate_offset_mm=30,
        selected_offset_mm=30,
        asset_sha256=mount.spec_for(30)["asset_sha256"],
        eligible=True,
        optical_anchors=31,
        matched_depth_inputs=31,
        dense_states=3432,
        optical_pass=True,
        clearance_pass=True,
        negative_controls_pass=True,
        unauthorized_contact_steps=0,
        unproved_separation_steps=0,
        zero_integrations=True,
    )
    contact.check_screen(expected)
    for key, wrong in (
        ("parent_generation", build.TIMING_PARENT),
        ("selected_offset_mm", 15),
        ("optical_anchors", 30),
        ("dense_states", 3431),
        ("clearance_pass", False),
        ("negative_controls_pass", False),
        ("unproved_separation_steps", 1),
        ("zero_integrations", False),
        ("eligible", False),
    ):
        with pytest.raises(ValueError, match="130 mm"):
            contact.check_screen({**expected, key: wrong})
    with pytest.raises(ValueError, match="130 mm"):
        contact.check_screen({k: v for k, v in expected.items() if k != "matched_depth_inputs"})


def test_full_sources_must_preserve_timed_observer_scorer_and_parent_archive(contact):
    private = Path.cwd() / build.PRIVATE
    if not (private / "builds" / contact.MOUNT_PARENT / "preflight.json").is_file():
        pytest.skip("frozen parent tree is local")
    parent, prior = build.verify_build(private, contact.MOUNT_PARENT)
    source, overlays = contact.overlays(Path.cwd(), parent, prior)
    assert set(overlays) == set(contact.ADAPTERS) | {build.ASSET, contact.MODULE, source}
    assert source not in prior["runtime_files_sha256"]
    assert overlays[build.ASSET] == (parent / build.ASSET).read_bytes().replace(
        b"RADIAL_OFFSET_MM = 15\n", b"RADIAL_OFFSET_MM = 30\n", 1
    )
    assert not set(overlays) & {build.GRID, build.DETECTOR, *build.SCORERS}
    assert len(prior["runtime_files_sha256"]) == 565
    assert sha(parent / "runtime-build.json") == contact.MOUNT_PARENT


def test_evaluation_requires_both_same_geometry_danger_intervals(tmp_path, contact):
    with pytest.raises((FileNotFoundError, ValueError)):
        trials.contact_histories(tmp_path, "4" * 64)
    assert not (tmp_path / "batches").exists()


def test_completed_native_sequence_without_emergency_stop_remains_a_safe_history(tmp_path, contact):
    from scripts.graduation.perception_io import write

    label = next(iter(contact.ASSIGNMENTS))
    directory = trials.batch_path(tmp_path, label)
    row = dict(
        id="d02",
        evidence_status="SCORED",
        acquired=True,
        safe_stop_succeeded=None,
        stop={"kind": "COMPONENT_SEQUENCE_RETURNED"},
        independent_physical_outcome={
            "safety_assessment": "SCOPED_NO_VIOLATION",
            "safety_violation": False,
        },
        hand_contacts={"board_or_support_hand_or_finger_steps": []},
    )
    for name, data in {
        "allocation.json": {},
        "acquisition.json": {},
        "scoring/pixels/index.json": {},
        "scoring/blind-one/seal.json": {"sealed": True},
        "scoring/blind-two/seal.json": {"sealed": True},
        "scoring/score-one.json": {"cases": [row]},
        "scoring/score-two.json": {"cases": [row]},
    }.items():
        p = directory / name
        p.parent.mkdir(parents=True, exist_ok=True)
        write(p, data)
    score = dict(
        runtime_build_sha256="5" * 64,
        scope="training",
        cases=[row],
        acquisition_sha256=sha(directory / "acquisition.json"),
        allocation_sha256=sha(directory / "allocation.json"),
        pixel_index_sha256=sha(directory / "scoring/pixels/index.json"),
        blind_seals_sha256=[
            sha(directory / f"scoring/blind-{n}/seal.json") for n in ("one", "two")
        ],
        score_passes_sha256=[sha(directory / f"scoring/score-{n}.json") for n in ("one", "two")],
    )
    write(directory / "score.json", score)
    assert trials.prior_d02_contact_clear(tmp_path, "5" * 64, label) == row


def test_published_qualification_refuses_parent_and_missing_current_depth_packet(contact, tmp_path):
    import shutil

    from scripts.graduation.perception_io import read

    repo = Path.cwd()
    public = repo / contact.ADMISSION / "runtime-qualification.public.json"
    if not public.is_file():
        pytest.skip("separate live 130 mm qualification has not been conducted")
    generation = read(public)["runtime_build_sha256"]
    private = repo / build.PRIVATE
    original = private / "builds" / generation / "preflight.json"
    if not original.is_file():
        pytest.skip("original development packets are retained privately")
    tree, lock = build.verify_build(private, generation)
    parent, previous = build.verify_build(private, contact.PARENT)
    with pytest.raises(ValueError, match="130 mm"):
        contact.check_identity(previous)
    with pytest.raises(ValueError, match="130 mm"):
        contact.qualification(repo, parent, build.FIT_ROUND.release_sha256)
    pf = read(original)
    copied = tmp_path / "preflight.json"
    shutil.copyfile(original, copied)
    raw = tree.parent / pf["full_occlusion_directory"]
    copied_raw = tmp_path / raw.name
    shutil.copytree(raw, copied_raw)
    tested = copied_raw / "only-8" / "tested.rgbd.json"
    original_digest = sha(raw / "only-8/tested.rgbd.json")
    tested.unlink()
    with pytest.raises(FileNotFoundError, match="tested.rgbd.json"):
        trials.timing_preflight(repo, private, generation, lock, copied, pf["registration"])
    assert sha(raw / "only-8/tested.rgbd.json") == original_digest
