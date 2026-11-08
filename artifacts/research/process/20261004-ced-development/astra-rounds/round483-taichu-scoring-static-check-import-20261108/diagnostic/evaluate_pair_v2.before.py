"""Score retained actual responses with the existing strict planner and geometry."""

import ast
import hashlib
import json
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
sys.path.insert(0, str(ROOT))
from scripts.probe_rgbd_model import _original_decision_pixel, _pixel_hit


def main():
    if len(sys.argv) != 3:
        raise ValueError("explicit successful R481 run and unique v2 output paths required")
    if Path(sys.argv[2]).exists():
        raise FileExistsError(sys.argv[2])
    protocol = json.loads((HERE / "dual-image-protocol.json").read_text())
    capture = Path(protocol["raw_directory"])
    observation = RGBDObservation.model_validate_json((capture / "full-observation.json").read_text())
    offline = json.loads((capture / "observation.json").read_text())
    frame = CapturedFrame(
        observation=observation,
        instance_ids=tuple(row[0] for row in struct.iter_unpack("<i", (capture / "instance_geom_ids.i32").read_bytes())),
        instance_labels={int(key): value for key, value in offline["instance_labels"].items()},
        physics_state_hash=offline["physics_state_hash"], pass_state_hashes=tuple(offline["pass_state_hashes"]))
    messages = json.loads((capture / "ollama-format-messages.json").read_text())
    snapshot = ModelConfigSnapshot(provider="openai_compatible", model="zdtaichu5.0-9b-fp8",
        endpoint="http://127.0.0.1:18050/v1", weight_digest="c2b70d4aeaa499e4bc4a267332b0338cdfca685de448338ea5014fc3eaf0a07a",
        quantization="FP8_DYNAMIC", image_size=(320, 240),
        generation_parameters={"num_predict": 512},
        timeout_s=180, coordinate_system="normalized_1000", grasp_profile="mujoco_upright_box_v2")
    planner = RGBDPlannerAdapter(base_url=snapshot.endpoint, model=snapshot.model,
                                 provider=snapshot.provider, model_snapshot=snapshot)
    request = InitialPlanningRequest(request_id="round473-fp8-fixed-s01",
        user_instruction="把图中的红色方块放到绿色方形目标区域。", observation=observation,
        scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)))
    run_path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "steps/model-run-b-result.json"
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "dual-image-results.json"
    run = json.loads(run_path.read_text())
    if run["status"] != "FOUR_REQUESTS_COMPLETED" or len(run["actual_requests"]) != 4:
        raise ValueError("successful R481 four-request evidence required")
    runner = HERE / "implementation/run_fp8_pair_r481.py"
    generate_calls = [node for node in ast.walk(ast.parse(runner.read_text()))
                      if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                      and node.func.attr == "generate"]
    if len(generate_calls) != 1:
        raise ValueError("ambiguous effective generation source")
    overrides = {item.arg: ast.literal_eval(item.value) for item in generate_calls[0].keywords
                 if item.arg is not None}
    generation_config_path = Path(run["actual_requests"][0]["raw_directory"]).parent / "generation-config.json"
    effective_metadata = {
        "snapshot_scope": "OFFLINE_SCORING_ONLY",
        "snapshot_generation_parameters_are_not_effective_hf_config": True,
        "offline_snapshot": snapshot.evidence(),
        "offline_snapshot_projection": {"num_predict": "only HF max_new_tokens=512 token cap"},
        "provider_endpoint_role": "offline identity and coordinate adapter; no service or request",
        "actual_runner_path": str(runner),
        "actual_runner_sha256": hashlib.sha256(runner.read_bytes()).hexdigest(),
        "actual_run_result_sha256": hashlib.sha256(run_path.read_bytes()).hexdigest(),
        "generation_config_path": str(generation_config_path),
        "generation_config_sha256": hashlib.sha256(generation_config_path.read_bytes()).hexdigest(),
        "generation_config": json.loads(generation_config_path.read_text()),
        "explicit_generate_overrides": overrides,
        "effective_config_rule": "explicit overrides replace generation_config; remaining values inherited",
        "torch_manual_seed": 0,
        "scored_decode": "raw-response.txt; skip_special_tokens=True",
        "preserved_decode": "raw-response-with-special-tokens.txt; skip_special_tokens=False",
        "network_calls": 0, "model_loads": 0, "generation_calls": 0,
    }
    metadata_path = output_path.with_name("hf-execution-parameters-v2.json")
    with metadata_path.open("x") as stream:
        json.dump(effective_metadata, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    results = []
    for index in range(1, 5):
        attempt = next((row for row in run["actual_requests"] if row["index"] == index), None)
        if attempt is None:
            results.append({"index": index, "status": "NOT_COMPLETED", "quality_pass": False,
                            "not_run": index > run.get("requests_started", 0)})
            continue
        raw_directory = Path(attempt["raw_directory"])
        text = (raw_directory / "raw-response.txt").read_text()
        actual_sha256 = hashlib.sha256((raw_directory / "raw-response.txt").read_bytes()).hexdigest()
        if actual_sha256 != attempt["raw_response_sha256"]:
            raise ValueError("immutable response SHA drift")
        if len(json.loads((raw_directory / "output-token-ids.json").read_text())) != attempt["output_tokens"]:
            raise ValueError("immutable output token count drift")
        result = {**attempt, "strict_json": False, "grounded": False,
                  "target_hit": False, "destination_hit": False}
        try:
            decision = VisualDecision.model_validate_json(text, strict=True)
            result["strict_json"] = True
            result["output_status"] = "STRICT_JSON_PARSED"
            result["decision"] = decision.model_dump(mode="json")
        except Exception as error:
            result["schema_error"] = str(error)
            result["output_status"] = "MODEL_OUTPUT_INVALID_JSON"
            result["localization_assessment"] = "NO_VALID_COORDINATES; false hits are not measured pixel misses"
        response = {"choices": [{"message": {"content": text}}]}
        draft = planner._ground_response(request, response, int(attempt["end_to_end_s"] * 1000),
                                         observation, messages, (320, 240), "normalized_1000",
                                         "mujoco_upright_box_v2")
        result["parse_error"] = draft.parse_error
        result["observed_scene_present"] = draft.observed_scene is not None
        result["grounded"] = draft.parse_error is None and draft.parsed_json is not None
        result["grounding_evidence"] = draft.observation_evidence
        decision_data = result.get("decision", {})
        for kind, label in [("target", "object_geom"), ("destination", "target_region_geom")]:
            pixel = _original_decision_pixel(planner, frame, draft.observation_evidence, decision_data, kind)
            hit, details = _pixel_hit(frame, pixel, label)
            result[kind + "_hit"] = hit
            result[kind + "_offline_check"] = details
        result["quality_pass"] = all(result[key] for key in
            ["strict_json", "grounded", "observed_scene_present", "target_hit", "destination_hit"])
        results.append(result)
    summary = {"scoring_scope": "OFFLINE_SCORING_ONLY",
               "hf_execution_parameters_path": str(metadata_path),
               "network_calls": 0, "model_loads": 0, "generation_calls": 0,
               "source_run_result": str(run_path), "planned_requests": 4, "requests_started": run.get("requests_started", 0),
               "inference_calls_started": run.get("inference_calls_started", 0),
               "completed_requests": len(run["actual_requests"]),
               "strict_json_passes": sum(bool(row.get("strict_json")) for row in results),
               "target_hits": sum(bool(row.get("target_hit")) for row in results),
               "destination_hits": sum(bool(row.get("destination_hit")) for row in results),
               "quality_passes": sum(bool(row["quality_pass"]) for row in results),
               "fixed_s01_quality_pass": all(row["quality_pass"] for row in results),
               "independent_scenes": 1, "repeated_static_frame": True,
               "depth_causal_use": "NOT_TESTED", "formal_acceptance": "NOT_PERFORMED",
               "real_hardware_dispatch": False, "results": results}
    with output_path.open("x") as stream:
        json.dump(summary, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps({key: value for key, value in summary.items() if key != "results"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
