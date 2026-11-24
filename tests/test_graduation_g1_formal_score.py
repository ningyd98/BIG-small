import json
import sys
from importlib import import_module
from pathlib import Path
from types import ModuleType

import pytest
from scripts.graduation import g1_dual_batch_score as dual
from scripts.graduation.perception_io import read, sha, write


def scorer():
    return import_module("scripts.graduation.g1_formal_score")


def test_formal_scene_rejects_crossed_truth_even_with_matching_episode():
    scene = "g1-formal-paired-20261124/f01-original"
    row = {"id": "f01-original", "visual_id": scene, "scene_id": scene}
    receipt = {"physical_reset": {"scenario": scene, "episode_id": "e"}}
    index = {"scene": scene, "episode": "e"}
    truth = {"scene": scene, "episode": "e"}
    scorer().check_scene("g1-formal-paired-20261124", row, receipt, index, truth)
    for wrong in ("S01_NORMAL_STATIC", "g1-formal-paired-20261124/f02-original"):
        with pytest.raises(ValueError, match="scene"):
            scorer().check_scene(
                "g1-formal-paired-20261124", row, receipt, index, {**truth, "scene": wrong}
            )


def test_shared_score_checks_explicit_scene_before_joining_measurements(tmp_path):
    scene = "g1-formal-paired-20261124/f01-dual"
    case = dict(
        id="f01-dual",
        group="f01",
        arm="dual",
        seed=1,
        reset_fixture_center_m=[0, 0, 0],
        yaw_rad=0,
        slot=1,
        asset_sha256="asset",
        allocation_sha256="allocation",
    )
    for name, value in {
        "pixel-index": {"allocation_sha256": "allocation", "episode": "e", "scene": "other"},
        "offline-truth": {"allocation_sha256": "allocation", "episode": "e"},
        "online-audit": [],
        "run": {},
    }.items():
        write(tmp_path / f"{name}.json", value)
    seal = {
        key: sha(tmp_path / f"{name}.json")
        for key, name in (
            ("index_sha256", "pixel-index"),
            ("truth_sha256", "offline-truth"),
            ("audit_sha256", "online-audit"),
            ("run_sha256", "run"),
        )
    }
    write(tmp_path / "acquisition-seal.json", seal)
    write(
        tmp_path / "receipt.json",
        {
            "allocation_sha256": "allocation",
            "physical_reset": {"episode_id": "e"},
            "capture_sha256": sha(tmp_path / "acquisition-seal.json"),
        },
    )
    observed = {"acquired": True, "receipt_sha256": sha(tmp_path / "receipt.json")}
    with pytest.raises(ValueError, match="foreign real run"):
        dual.score_case(case, {}, observed, tmp_path, tmp_path, tmp_path, {}, expected_scene=scene)


def test_packet_manifest_rejects_changed_bytes_and_unlisted_originals(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    a = frames / "0000.json"
    a.write_bytes(b"rgbd-0")
    index = {
        "frames": [
            {"file": "frames/0000.json", "file_sha256": sha(a), "frame_id": "a", "physics_step": 0}
        ]
    }
    scorer().check_frame_files(tmp_path, index)
    (frames / "0001.json").touch()
    with pytest.raises(ValueError, match="frame"):
        scorer().check_frame_files(tmp_path, index)
    (frames / "0001.json").unlink()
    a.write_bytes(b"rgbd-edited")
    with pytest.raises(ValueError, match="frame"):
        scorer().check_frame_files(tmp_path, index)


def test_every_registered_slot_including_missing_and_interrupted_stays_in_rates():
    states = [
        ("f01", "original", "SCORED", False),
        ("f01", "dual", "SCORED", True),
        ("f02", "original", "SCORED", False),
        ("f02", "dual", "CORRUPT", None),
        ("f03", "original", "SCORED", False),
        ("f03", "dual", "INTERRUPTED", None),
        ("f04", "original", "SCORED", False),
        ("f04", "dual", "NOT_RUN", None),
    ]
    rows = [
        {
            "group": g,
            "arm": arm,
            "evidence_status": status,
            "acquired": status == "SCORED",
            **{
                k: val
                for k in (
                    "online_success",
                    "physical_success",
                    "both_windows_qualified",
                    "joint_success",
                )
            },
        }
        for g, arm, status, val in states
    ]
    report = scorer().allocated_outcomes(rows)
    rates = report["metrics"]["joint_success"]
    assert rates["by_arm"]["original"]["known_failures"] == 4
    assert rates["by_arm"]["dual"]["allocated"] == 4
    assert rates["by_arm"]["dual"]["allocation_rate_bounds"] == [0.25, 1.0]
    assert rates["by_arm"]["dual"]["wilson95"] is None
    assert rates["paired"]["outcomes"]["f04"]["dual"] is None
    assert report["evidence_status_by_arm"]["dual"] == {
        "SCORED": 1,
        "CORRUPT": 1,
        "INTERRUPTED": 1,
        "NOT_RUN": 1,
    }


def test_claim_must_match_issued_slot_and_its_private_mirror(tmp_path):
    plan = {"release": "example"}
    row = {
        "id": "f01-dual",
        "slot": 1,
        "visual_id": "example/f01-dual",
        "allocation_sha256": "slot-sha",
    }
    claim_path = tmp_path / "claims/f01-dual.json"
    mirror = tmp_path / "trials/f01-dual/claim.json"
    for p in (claim_path, mirror):
        p.parent.mkdir(parents=True)
    value = dict(
        schema="g1.formal-paired.claim.v1",
        release="example",
        id="f01-dual",
        slot=1,
        assignment="example/f01-dual",
        attempt=1,
        protocol_sha256="plan-sha",
        allocation_sha256="slot-sha",
        batch_sha256="batch-sha",
        output_root=str(tmp_path),
        claimed_at="2026-11-24T14:00:00+00:00",
    )
    for p in (claim_path, mirror):
        write(p, value)
    recorded = {"claim_sha256": sha(claim_path)}
    assert scorer().check_claim(tmp_path, plan, row, recorded, "plan-sha", "batch-sha")
    changed = {**value, "assignment": "example/f01-original"}
    for p in (claim_path, mirror):
        p.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="claim"):
        scorer().check_claim(
            tmp_path, plan, row, {"claim_sha256": sha(claim_path)}, "plan-sha", "batch-sha"
        )
    mirror.write_text("{}")
    with pytest.raises(ValueError):
        scorer().check_claim(
            tmp_path, plan, row, {"claim_sha256": sha(claim_path)}, "plan-sha", "batch-sha"
        )


def test_overlapping_lease_intervals_cannot_count_as_independent_resets(tmp_path):
    formal = scorer()
    slots = []
    for ident, start, end in (("one", 1, 4), ("two", 3, 5), ("three", 6, 7)):
        slots.append(
            formal.Slot(
                {"id": ident},
                {
                    "physical_reset": {"episode_id": "episode-" + ident},
                    "receipt_sha256": "receipt-" + ident,
                    "worker": {
                        "job_id": "job-" + ident,
                        "lease_id": "lease-" + ident,
                        "acquired_at": f"2026-11-24T14:00:0{start}+00:00",
                        "released_at": f"2026-11-24T14:00:0{end}+00:00",
                    },
                },
                tmp_path / ident,
            )
        )
    formal.mark_shared_identities(slots)
    assert [s.status for s in slots] == ["CORRUPT", "CORRUPT", "SCORED"]


def test_blind_decoder_requires_the_frozen_assignment_scene_and_reads_actual_markers(
    tmp_path, monkeypatch
):
    from scripts.graduation import g1_dual_asset as asset
    from scripts.graduation import g1_dual_observer as original
    from scripts.graduation import g1_dual_pixel_readback as reader
    from scripts.graduation import g1_formal_runtime as build

    from tests.test_graduation_g1_dual_observer import software_frame

    # Load the production derivation of the observer in this isolated software fixture.
    # Historical deployments retain their original observer and their default scene.
    name = "scripts/graduation/g1_dual_observer.py"
    expected = "nonstudy-scope/fixture-dual"
    original_path = Path(original.__file__)
    module = ModuleType(original.__name__)
    module.__file__ = str(original_path)
    module.__package__ = original.__package__
    derived = build.adapt_source(name, original_path.read_bytes())
    exec(compile(derived, str(original_path), "exec"), module.__dict__)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    template = software_frame([(7, 160, 80), (8, 200, 120)])
    packet = type(template).model_validate(
        template.model_dump() | {"scene_id": expected, "checksum_sha256": ""}
    )
    token = "a" * 64
    root = tmp_path / token
    root.mkdir()
    original_file = root / "0000.json"
    write(original_file, packet.model_dump(mode="json"))
    frame = dict(
        file="0000.json",
        file_sha256=sha(original_file),
        checksum_sha256=packet.checksum_sha256,
        frame_id=packet.frame_id,
        physics_step=0,
    )
    bundle = dict(
        episode=packet.episode_id,
        scene=expected,
        mode="dual",
        geometry=asset.geometry_descriptor(),
        frames=[frame],
    )
    for index, binding in enumerate(
        (
            {},
            {"registered_scene": "nonstudy-scope/another"},
            {"registered_scene": "S01_NORMAL_STATIC"},
        )
    ):
        document = tmp_path / f"invalid-{index}.json"
        write(document, {token: {**bundle, **binding}})
        with pytest.raises(ValueError, match="scene"):
            reader.read_images(document, sha(document), tmp_path / f"reject-{index}")
    document = tmp_path / "registered.json"
    write(document, {token: {**bundle, "registered_scene": expected}})
    for side in ("one", "two"):
        reader.read_images(document, sha(document), tmp_path / side)
    (row,) = read(tmp_path / "one" / (token + ".json"))
    assert row["usable"] and row["usable_ids"] == [7, 8] and row["selected_id"] == 7
    assert sha(tmp_path / "one/seal.json") == sha(tmp_path / "two/seal.json")
    crossed = type(packet).model_validate(
        packet.model_dump() | {"scene_id": "foreign", "checksum_sha256": ""}
    )
    original_file.write_text(crossed.model_dump_json())
    wrong_packet = tmp_path / "crossed-index.json"
    write(
        wrong_packet,
        {
            token: {
                **bundle,
                "registered_scene": expected,
                "frames": [
                    {
                        **frame,
                        "file_sha256": sha(original_file),
                        "checksum_sha256": crossed.checksum_sha256,
                    }
                ],
            }
        },
    )
    with pytest.raises(ValueError, match="frame/source"):
        reader.read_images(wrong_packet, sha(wrong_packet), tmp_path / "crossed")


def test_formal_pack_seals_scene_from_checked_allocation_and_refuses_crossed_capture(tmp_path):
    scene = "fixture/arm-b"
    raw = tmp_path / "raw"
    (raw / "frames").mkdir(parents=True)
    packet = raw / "frames/0000.json"
    packet.write_bytes(b"non-study pixels")
    frame = {
        "file": "frames/0000.json",
        "file_sha256": sha(packet),
        "checksum_sha256": "image",
        "physics_step": 0,
        "frame_id": "0",
    }
    index = raw / "pixel-index.json"
    write(
        index,
        {
            "scene": scene,
            "episode": "fixture-episode",
            "frames": [frame],
            "allocation_sha256": "slot",
        },
    )
    token = sha(index)
    write(raw / "acquisition-seal.json", {"index_sha256": token})
    row = {"allocation_sha256": "slot", "arm": "dual", "scene_id": scene}
    allocation = {"geometry": {}, "case": {"scene_id": scene}}
    observed = {
        "acquired": True,
        "physical_reset": {"scenario": scene, "episode_id": "fixture-episode"},
    }
    cases = [(row, allocation, observed, raw)]
    packed = dual.package(cases, tmp_path / "ok", registered_scene=True)
    assert read(packed)[token]["registered_scene"] == scene
    swapped = [(row, {**allocation, "case": {"scene_id": "fixture/arm-a"}}, observed, raw)]
    with pytest.raises(ValueError, match="scene"):
        dual.package(swapped, tmp_path / "bad", registered_scene=True)
