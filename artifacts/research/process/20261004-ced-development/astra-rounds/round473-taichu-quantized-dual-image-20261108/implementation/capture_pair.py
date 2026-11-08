"""Capture one real registered S01 frame; instances remain offline-only."""

import base64
import hashlib
import json
from pathlib import Path

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession, save_captured_frame
from cloud_edge_robot_arm.vision.messages import build_visual_messages
from cloud_edge_robot_arm.vision.planner import VisualDecision

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[5]
CACHE = ROOT / "datasets/model-cache/zdtaichu5-9b-fp8-round473"


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def main():
    directory = CACHE / "actual/capture"
    directory.mkdir(parents=True, exist_ok=False)
    config = SimulatorConfig(camera_width=320, camera_height=240, render_rgb=True,
                             render_depth=True, domain_randomization=False, seed=0)
    with MuJoCoCaptureSession(config) as session:
        frame = session.capture_with_instances()
        save_captured_frame(frame, directory)
    if len(set(frame.pass_state_hashes)) != 1 or frame.pass_state_hashes[0] != frame.physics_state_hash:
        raise ValueError("capture is not synchronized")
    save(directory / "full-observation.json", frame.observation.model_dump(mode="json"))
    schema = VisualDecision.model_json_schema()
    messages = build_visual_messages(
        "把图中的红色方块放到绿色方形目标区域。", frame.observation,
        image_size=(320, 240), coordinate_system="normalized_1000", decision_schema=schema)
    save(directory / "ollama-format-messages.json", messages)
    images = []
    for index, encoded in enumerate(messages[1]["images"]):
        raw = base64.b64decode(encoded, validate=True)
        path = directory / f"model-image-{index+1}.png"
        with path.open("xb") as stream:
            stream.write(raw)
        images.append({"index": index + 1, "kind": ["RGB", "aligned_depth_visualization"][index],
                       "path": str(path), "bytes": len(raw),
                       "sha256": hashlib.sha256(raw).hexdigest(), "width": 320, "height": 240})
    if len(images) != 2 or images[0]["sha256"] == images[1]["sha256"]:
        raise ValueError("two distinct images required")
    # The official processor receives two content parts, never a mosaic.
    native = [{"role": "system", "content": messages[0]["content"]},
              {"role": "user", "content": [
                  *[{"type": "image", "image": image["path"]} for image in images],
                  {"type": "text", "text": messages[1]["content"]}]}]
    save(directory / "native-messages.json", native)
    prompt_text = {"system": messages[0]["content"], "user": messages[1]["content"]}
    result = {"status": "PASS", "scenario": "S01_NORMAL_STATIC", "seed": 0,
              "capture_source": frame.observation.source, "evidence": frame.observation.evidence(),
              "physics_state_hash": frame.physics_state_hash,
              "pass_state_hashes": list(frame.pass_state_hashes), "synchronized": True,
              "coordinate_system": "normalized_1000", "image_count": 2, "images": images,
              "depth_range_m": frame.observation.depth_range(), "prompt": prompt_text,
              "schema": schema, "messages_path": str(directory / "native-messages.json"),
              "oracle_in_prompt": False, "held_out": False,
              "raw_directory": str(directory), "real_hardware_dispatch": False}
    save(HERE / "dual-image-protocol.json", result)
    print(json.dumps({"status": "PASS", "images": images,
                      "synchronized": True}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
