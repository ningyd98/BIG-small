"""只读核验新 seed 的实际模型与物理证据；不执行模型或控制动作。"""

from __future__ import annotations

# ruff: noqa: E402 -- 显式固定本工作树源码后才导入核验依赖。
import base64
import hashlib
import io
import json
import math
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import run_batch
from PIL import Image

from cloud_edge_robot_arm.research.sol_molmo_scenarios import sample_component_scene
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    PhysicalSample,
    evaluate_evidence,
)


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(value):
    return json.loads(json.dumps(value))


def request_parts(request):
    message = next(m for m in request["messages"] if m["role"] == "user")
    if isinstance(message["content"], str):
        return json.loads(message["content"]), [
            base64.b64decode(x, validate=True) for x in message.get("images", [])
        ]
    text_parts = [p["text"] for p in message["content"] if p["type"] == "text"]
    assert len(text_parts) == 1
    images = []
    for part in message["content"]:
        if part["type"] == "image_url":
            url = part["image_url"]["url"]
            assert url.startswith("data:image/png;base64,")
            images.append(base64.b64decode(url.split(",", 1)[1], validate=True))
        else:
            assert part["type"] == "text"
    return json.loads(text_parts[0]), images


def verify_request(episode, request, entries, evidence):
    assert request["model"] == "gpt-6.1-sol"
    system = next(m["content"] for m in request["messages"] if m["role"] == "system")
    payload, images = request_parts(request)
    for forbidden in (
        "component_scene",
        "scene_application",
        "object_position_m",
        "object_yaw_rad",
        "requested_scene",
        "depth_float32_base64",
        "valid_mask_base64",
        "instance_labels",
    ):
        assert forbidden not in json.dumps(payload), forbidden
    if not images:
        assert "MuJoCo software component diagnostic only" in system
        assert set(payload) == {
            "execution_scope",
            "hardware_dispatch",
            "instruction",
            "geometry",
            "geometry_status",
        }
        assert payload["execution_scope"] == "MUJOCO_COMPONENT_DIAGNOSTIC"
        assert payload["hardware_dispatch"] is False
        assert (
            payload["geometry_status"] == "CALIBRATED_DEVELOPMENT_ESTIMATE_NOT_PHYSICAL_ACCEPTANCE"
        )
        return False, None
    assert "No hardware is dispatched" in system
    assert set(payload) == {
        "instruction",
        "target_phrase",
        "destination_phrase",
        "local_failure",
        "images",
    }
    assert 1 <= len(images) == len(payload["images"]) <= 2
    audit = next(
        e["cloud_vision_fallback"]
        for e in evidence
        if e.get("cloud_vision_fallback", {}).get("images") == payload["images"]
    )
    assert audit["hardware_dispatch"] is False
    assert audit["metric_geometry_source"] == "FRESH_LOCAL_ORIGINAL_DEPTH_ONLY"
    assert audit["coordinate_system"] == "normalized_1000_full_original_image"
    assert audit["local_failure"] == payload["local_failure"]
    assert audit["image_count"] == len(images)
    for raw, meta in zip(images, payload["images"], strict=True):
        assert hashlib.sha256(raw).hexdigest() == meta["sha256"]
        with Image.open(io.BytesIO(raw)) as picture:
            assert picture.size == (meta["width"], meta["height"])
    first = payload["images"][0]
    assert first["role"] == "FULL_ORIGINAL_RGB"
    assert any(e["path"].endswith("/rgb.png") and e["sha256"] == first["sha256"] for e in entries)
    matching = []
    for entry in entries:
        if entry["path"].endswith("observation.json"):
            frame = read(episode / entry["path"])
            if frame.get("observation_id") == audit["reference_observation_id"]:
                matching.append(frame)
    assert matching
    assert any(
        frame["checksum_sha256"] == audit["reference_checksum"]
        and frame["rgb_sha256"] == first["sha256"]
        for frame in matching
    )
    if len(images) == 2:
        crop = payload["images"][1]
        assert crop["role"] == "RGB_CROP_CONTEXT_ONLY"
        x0, y0, x1, y1 = crop["full_image_box_xyxy"]
        assert 0 <= x0 < x1 <= first["width"] and 0 <= y0 < y1 <= first["height"]
        assert x1 - x0 == crop["width"] <= 97 and y1 - y0 == crop["height"] <= 97
        with (
            Image.open(io.BytesIO(images[0])) as original,
            Image.open(io.BytesIO(images[1])) as part,
        ):
            assert original.crop((x0, y0, x1, y1)).tobytes() == part.tobytes()
    return True, audit


def rescore(episode, result):
    raw = read(episode / "component/physical-evidence.json")
    samples = []
    for row in raw:
        item = dict(row)
        for name in (
            "object_position_m",
            "object_half_extent_xy_m",
            "region_center_xy_m",
            "region_half_extent_xy_m",
        ):
            item[name] = tuple(item[name])
        for name in ("contact_pairs", "self_collision_checked_pairs"):
            item[name] = tuple(tuple(pair) for pair in item[name])
        samples.append(PhysicalSample(**item))
    assert samples and samples[0].physics_step == 120
    assert samples[-1].physics_step == result["physics_steps"]
    assert all(s.episode_id == result["episode_id"] for s in samples)
    scored = normalized(
        asdict(
            evaluate_evidence(
                samples, CompletionCriteria("object", "target_region"), evaluation_start_step=120
            )
        )
    )
    assert scored == result["outcome"]["independent_physical_outcome"]
    return scored


def main():
    """按固定分母核验实际结果，完整性与组件成功分别报告。"""
    run_batch.check()
    output = HERE / "raw-local/run-01"
    batch = read(output / "batch-result.json")
    protocol = read(HERE / "protocol.json")
    frozen = read(HERE / "source-freeze.json")
    assert batch["denominator"] == protocol["denominator"] == 15
    assert [r["seed"] for r in batch["episodes"]] == protocol["seeds"][: batch["completed"]]
    counts, reasons, tokens, models = Counter(), Counter(), Counter(), Counter()
    snapshots, rows, errors = set(), [], []
    for row in batch["episodes"]:
        episode = output / f"held-out-{row['seed']:06d}"
        record = {
            "seed": row["seed"],
            "component_success": False,
            "physical_success": False,
            "case_integrity": "NOT_VERIFIED",
        }
        try:
            result = read(episode / "result.json")
            assignment = read(episode / "scene-assignment.json")
            snapshot = read(episode / "source-hashes.json")
            snapshots.add(json.dumps(snapshot, sort_keys=True))
            assert snapshot["scope"] == "SELECTED_ENTRY_SOURCES"
            for name, expected in snapshot["files"].items():
                assert frozen["files"][name] == expected
            assert result["changed_source_paths"] == []
            assert result["execution_scope"] == "MUJOCO_COMPONENT_DIAGNOSTIC"
            assert result["success"] is False and result["hardware_dispatch"] is False
            assert (
                result["formal_research"] == "NOT_ACCEPTED"
                and result["qualified_groups_added"] == 0
            )
            assert result["continuous_visibility_proven"] is False
            assert result["cloud_vision_fallback"] is True
            assert result["seed"] == row["seed"] and not row["timed_out"]
            assert row["child_returncode"] in (0, 2, 3)
            assert 0 <= result["local_generations_completed"] <= result["local_generations"] <= 4
            assert result["model_loads"] == int((episode / "raw/molmo/loaded.json").is_file()) <= 1
            assert result["local_generations_completed"] == len(
                list((episode / "raw/molmo").glob("request-*/generation-completed.json"))
            )
            requested = (episode / "raw/cloud/request.json").is_file()
            assert result["cloud_requests"] == int(requested)
            assert 0 <= result["cloud_requests"] <= result["cloud_request_reservations"] <= 1
            expected_scene = sample_component_scene(row["seed"], "held-out")
            assert assignment["component_scene"] == expected_scene
            assert assignment["independent_random_scene"] is True
            assert assignment["camera_size"] == [320, 240]
            assert assignment["marker_family_id"] == protocol["marker_family"]
            assert assignment["budget"] == {
                "model_loads": 1,
                "local_generations": 4,
                "cloud_requests": 1,
                "repairs": 0,
                "retries": 0,
            }
            entries = read(episode / "evidence-manifest.json")["files"]
            for item in entries:
                p = (episode / item["path"]).resolve()
                assert p.is_relative_to(episode.resolve()) and p.is_file()
                assert p.stat().st_size == item["bytes"] and digest(p) == item["sha256"]
                counts["evidence_files"] += 1
                counts["evidence_bytes"] += item["bytes"]
            stages = [read(p) for p in sorted((episode / "planning").glob("planning-stage-*.json"))]
            evidence = [
                a["draft"]["observation_evidence"]
                for s in stages
                for a in s.get("attempts", [])
                if a.get("draft")
            ]
            image = False
            if requested:
                image, _ = verify_request(
                    episode, read(episode / "raw/cloud/request.json"), entries, evidence
                )
                response_path = episode / "raw/cloud/response.json"
                if response_path.is_file():
                    response = read(response_path)
                    models[str(response.get("model"))] += 1
                    for key, value in (response.get("usage") or {}).items():
                        if key in {"prompt_tokens", "completion_tokens", "total_tokens"}:
                            tokens[key] += value
                counts["image_requests" if image else "text_requests"] += 1
            application = read(episode / "component/scene-application.json")
            assert application["scope"] == "OFFLINE_INITIAL_PHYSICS_AUDIT_NOT_ONLINE_MODEL_INPUT"
            assert application["requested_scene"] == expected_scene
            assert all(
                abs(a - b) < 1e-10
                for a, b in zip(
                    application["object_position_m"],
                    expected_scene["object_position_m"],
                    strict=True,
                )
            )
            yaw = expected_scene["object_yaw_rad"]
            quaternion = [math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]
            assert all(
                abs(a - b) < 1e-10
                for a, b in zip(application["object_quaternion_wxyz"], quaternion, strict=True)
            )
            scored = rescore(episode, result)
            counts["physical_rescores"] += 1
            counts["safety_violations"] += int(scored["safety_violation"])
            success = result["component_success"] is True
            if success:
                assert result["physical_success"] is True and scored["success"] is True
                assert result["executed_actions"] == 8
            else:
                reasons[
                    str(
                        result.get("outcome", {}).get("terminal_reason") or result.get("error_type")
                    )
                ] += 1
            for key in (
                "model_loads",
                "local_generations",
                "local_generations_completed",
                "cloud_requests",
                "cloud_request_reservations",
                "executed_actions",
            ):
                counts[key] += result[key]
            counts["component_success"] += int(success)
            counts["marker_endpoints_observed"] += int(result["marker_endpoints_observed"])
            record.update(
                component_success=success,
                physical_success=result["physical_success"],
                case_integrity="PASS",
                intended_condition=expected_scene["condition"],
                terminal_reason=result.get("outcome", {}).get("terminal_reason"),
                image_fallback=image,
                executed_actions=result["executed_actions"],
                marker_before=result["marker_before"]["status"],
                marker_after=result["marker_after"]["status"],
            )
        except Exception as error:
            record["integrity_error"] = type(error).__name__ + ": " + str(error)
            errors.append({"seed": row["seed"], "error": record["integrity_error"]})
        rows.append(record)
    assert counts["cloud_request_reservations"] <= 15
    successes, n, z = counts["component_success"], 15, 1.959963984540054
    proportion = successes / n
    denominator = 1 + z * z / n
    center = (proportion + z * z / (2 * n)) / denominator
    half = z * math.sqrt(proportion * (1 - proportion) / n + z * z / (4 * n * n)) / denominator
    complete = batch["completed"] == 15
    integrity = complete and not errors and len(snapshots) == 1
    report = {
        "scope": "FRESH_SEED_ACTUAL_SOL_MOLMO_MUJOCO_COMPONENT_GENERALIZATION",
        "source_commit": protocol["source_commit"],
        "source_freeze_sha256": digest(HERE / "source-freeze.json"),
        "protocol_sha256": digest(HERE / "protocol.json"),
        "seeds": protocol["seeds"],
        "completed": batch["completed"],
        "denominator": 15,
        "not_run": 15 - batch["completed"],
        "integrity_status": "PASS" if integrity else "FAIL_OR_INCOMPLETE",
        "source_snapshot_variants": len(snapshots),
        "counts": dict(counts),
        "failure_reasons": dict(reasons),
        "component_success_rate": proportion if integrity else None,
        "wilson_95_ci": [max(0, center - half), min(1, center + half)] if integrity else None,
        "ci_scope": (
            "Self-calculated Wilson interval for the fixed 15-case component denominator; "
            "same asset and sampling family only. No cross-domain acceptance claim."
        ),
        "provider_response_models": dict(models),
        "tokens": dict(tokens),
        "errors": errors,
        "episodes": rows,
        "wall_s": batch["wall_s"],
        "hardware_dispatch": False,
        "formal_research": "NOT_ACCEPTED",
        "raw_delivery": "LOCAL_ONLY",
        "unseen_boundary": (
            "No matching prior-run seed in 12784 audited identity files under three roots. "
            "No global or training-data novelty claim."
        ),
        "qualification_limit": (
            "New seeds within the existing held-out pose sampler and single registered "
            "asset; no new asset, hardware, continuous visibility or formal research "
            "qualification. Do not pool with the diagnosed old held-out set."
        ),
    }
    with (HERE / "verification.json").open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "integrity_status",
                    "completed",
                    "counts",
                    "failure_reasons",
                    "wilson_95_ci",
                )
            },
            ensure_ascii=False,
        )
    )
    return 0 if integrity else 1


if __name__ == "__main__":
    raise SystemExit(main())
