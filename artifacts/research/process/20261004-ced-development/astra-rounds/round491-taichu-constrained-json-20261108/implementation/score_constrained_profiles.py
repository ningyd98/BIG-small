"""Strict, unchanged project scoring for the real R486 response files."""

import ast
import hashlib
import json
import statistics
import struct
import sys
from datetime import UTC, datetime
from pathlib import Path

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
from cloud_edge_robot_arm.vision.capture import CapturedFrame
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter, VisualDecision

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[5]
BASELINE = HERE.parent / "round473-taichu-quantized-dual-image-20261108"
sys.path.insert(0, str(ROOT))
from scripts.probe_rgbd_model import _original_decision_pixel, _pixel_hit


def read(path):
    return json.loads(Path(path).read_text())


def main():
    if len(sys.argv) != 3:
        raise ValueError("explicit run result and unique score output required")
    run_path, output_path = map(Path, sys.argv[1:])
    if output_path.exists():
        raise FileExistsError(output_path)
    run = read(run_path)
    protocol = read(BASELINE / "dual-image-protocol.json")
    capture = Path(protocol["raw_directory"])
    observation = RGBDObservation.model_validate_json((capture / "full-observation.json").read_text())
    offline = read(capture / "observation.json")
    frame = CapturedFrame(observation=observation,
        instance_ids=tuple(row[0] for row in struct.iter_unpack("<i", (capture / "instance_geom_ids.i32").read_bytes())),
        instance_labels={int(key): value for key, value in offline["instance_labels"].items()},
        physics_state_hash=offline["physics_state_hash"], pass_state_hashes=tuple(offline["pass_state_hashes"]))
    messages = read(capture / "ollama-format-messages.json")
    snapshot = ModelConfigSnapshot(provider="openai_compatible", model="zdtaichu5.0-9b-fp8",
        endpoint="http://127.0.0.1:18050/v1", weight_digest="c2b70d4aeaa499e4bc4a267332b0338cdfca685de448338ea5014fc3eaf0a07a",
        quantization="FP8_DYNAMIC", image_size=(320, 240), generation_parameters={"num_predict": 512},
        timeout_s=180, coordinate_system="normalized_1000", grasp_profile="mujoco_upright_box_v2")
    planner = RGBDPlannerAdapter(base_url=snapshot.endpoint, model=snapshot.model,
                                provider=snapshot.provider, model_snapshot=snapshot)
    request = InitialPlanningRequest(request_id="round491-fixed-s01", observation=observation,
        user_instruction="把图中的红色方块放到绿色方形目标区域。",
        scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)))
    runner = HERE / "implementation/run_constrained_profiles_r495.py"
    calls = [node for node in ast.walk(ast.parse(runner.read_text())) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == "generate"]
    if len(calls) != 1:
        raise ValueError("ambiguous generation call")
    overrides = {item.arg: ast.literal_eval(item.value) for item in calls[0].keywords if item.arg is not None}
    results = []
    for attempt in run["actual_requests"]:
        raw = Path(attempt["raw_directory"])
        response_bytes = (raw / "raw-response.txt").read_bytes()
        if hashlib.sha256(response_bytes).hexdigest() != attempt["raw_response_sha256"]:
            raise ValueError("raw response bytes changed")
        if len(read(raw / "output-token-ids.json")) != attempt["output_tokens"]:
            raise ValueError("output token count changed")
        text = response_bytes.decode()
        result = {**attempt, "strict_json": False, "json_syntax": False, "grounded": False,
                  "target_hit": False, "destination_hit": False}
        try:
            json.loads(text);result['json_syntax']=True
        except (ValueError,TypeError):pass
        try:
            decision = VisualDecision.model_validate_json(text, strict=True)
            result.update(strict_json=True, decision=decision.model_dump(mode="json"))
        except Exception as error:
            result.update(output_status="MODEL_OUTPUT_INVALID_JSON", schema_error=str(error),
                          localization_assessment="UNSCORABLE_NO_VALID_COORDINATES")
        draft = planner._ground_response(request, {"choices": [{"message": {"content": text}}]},
            int(attempt["end_to_end_s"] * 1000), observation, messages, (320, 240),
            "normalized_1000", "mujoco_upright_box_v2")
        result.update(parse_error=draft.parse_error, observed_scene_present=draft.observed_scene is not None,
                      grounded=draft.parse_error is None and draft.parsed_json is not None,
                      grounding_evidence=draft.observation_evidence)
        for kind, label in [("target", "object_geom"), ("destination", "target_region_geom")]:
            pixel = _original_decision_pixel(planner, frame, draft.observation_evidence,
                                             result.get("decision", {}), kind)
            hit, details = _pixel_hit(frame, pixel, label)
            result[kind + "_hit"] = hit
            result[kind + "_offline_check"] = details
        result["quality_pass"] = all(result[key] for key in
            ["strict_json", "grounded", "observed_scene_present", "target_hit", "destination_hit"])
        results.append(result)
    groups = {}
    for mode in ["FREE", "JSON"]:
        rows = [row for row in results if row["mode"] == mode]
        warm = [row for row in rows if row["mode_warm_sample"]]
        groups[mode] = {"completed": len(rows), "planned": 4,
            "json_syntax":sum(row["json_syntax"] for row in rows),
            "strict_json": sum(row["strict_json"] for row in rows),
            "median_constraint_callback_s":statistics.median(row["constraint_callback_s"] for row in rows) if rows else None,
            "target_hits": sum(row["target_hit"] for row in rows),
            "destination_hits": sum(row["destination_hit"] for row in rows),
            "quality_passes": sum(row["quality_pass"] for row in rows),
            "all_four_quality_pass": len(rows) == 4 and all(row["quality_pass"] for row in rows),
            "output_tokens": [row["output_tokens"] for row in rows],
            "generation_s": [row["generation_s"] for row in rows],
            "first_for_mode_s": rows[0]["end_to_end_s"] if rows else None,
            "warm_end_to_end_s": [row["end_to_end_s"] for row in warm],
            "warm_median_end_to_end_s": statistics.median(row["end_to_end_s"] for row in warm) if warm else None,
            "warm_median_generation_s": statistics.median(row["generation_s"] for row in warm) if warm else None,
            "token_cap_hits": sum(row["reached_token_cap"] for row in rows)}
    generation_path = Path(run["actual_requests"][0]["raw_directory"]).parent / "generation-config.json" if results else None
    summary = {"profile": run["profile"], "run_status": run["status"], "groups": groups,
        "actual_generation_calls": run["inference_calls_started"], "source_run": str(run_path),
        "source_run_sha256": hashlib.sha256(run_path.read_bytes()).hexdigest(),
        "hf_execution_parameters": {"generation_config": read(generation_path) if generation_path else None,
            "explicit_overrides": overrides, "runner_sha256": hashlib.sha256(runner.read_bytes()).hexdigest(),
            "rule": "explicit overrides replace generation_config; JSON alone adds a per-request prefix callback"},
        "snapshot_scope": "OFFLINE_SCORING_ONLY", "offline_snapshot": snapshot.evidence(),
        "snapshot_generation_parameters_are_not_effective_hf_config": True,
        "network_calls": 0, "model_loads": 0, "generation_calls": 0,
        "independent_scenes": 1, "repeated_static_frame": True,
        "depth_causal_use": "NOT_TESTED", "formal_acceptance": "NOT_PERFORMED", "results": results}
    with output_path.open("x") as stream:
        json.dump(summary, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"profile": summary["profile"], "groups": groups}, ensure_ascii=False))


if __name__ == "__main__":
    main()
