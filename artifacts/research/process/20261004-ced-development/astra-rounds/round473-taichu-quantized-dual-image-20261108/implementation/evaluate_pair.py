"""Score retained actual responses with the existing strict planner and geometry."""

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
        generation_parameters={"do_sample": False, "max_new_tokens": 512, "num_beams": 1},
        timeout_s=180, coordinate_system="normalized_1000", grasp_profile="mujoco_upright_box_v2")
    planner = RGBDPlannerAdapter(base_url=snapshot.endpoint, model=snapshot.model,
                                 provider=snapshot.provider, model_snapshot=snapshot)
    request = InitialPlanningRequest(request_id="round473-fp8-fixed-s01",
        user_instruction="把图中的红色方块放到绿色方形目标区域。", observation=observation,
        scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)))
    run_path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "steps/model-run-b-result.json"
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "dual-image-results.json"
    run = json.loads(run_path.read_text())
    results = []
    for index in range(1, 5):
        attempt = next((row for row in run["actual_requests"] if row["index"] == index), None)
        if attempt is None:
            results.append({"index": index, "status": "NOT_COMPLETED", "quality_pass": False,
                            "not_run": index > run.get("requests_started", 0)})
            continue
        raw_directory = Path(attempt["raw_directory"])
        text = (raw_directory / "raw-response.txt").read_text()
        result = {**attempt, "strict_json": False, "grounded": False,
                  "target_hit": False, "destination_hit": False}
        try:
            decision = VisualDecision.model_validate_json(text, strict=True)
            result["strict_json"] = True
            result["decision"] = decision.model_dump(mode="json")
        except Exception as error:
            result["schema_error"] = str(error)
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
    summary = {"source_run_result": str(run_path), "planned_requests": 4, "requests_started": run.get("requests_started", 0),
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
