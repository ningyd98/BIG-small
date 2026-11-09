"""Freeze R501 v1 bytes into opaque, oracle-free R505 model inputs."""

import hashlib
import json
import re
from pathlib import Path

from score_native import assert_public_inputs

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[5]
CACHE = ROOT / "datasets/model-cache/ordered-small-vlm-20261109"
SOURCE = HERE.parent / "round501-taichu-captured-multiscene-20261108/diagnostic/source-inventory.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(row):
    path = ROOT / row["path"]
    if path.stat().st_size != row["bytes"] or sha(path) != row["sha256"]:
        raise ValueError("frozen input drift: " + row["path"])


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def freeze_inputs(source_inventory=SOURCE, out=HERE / "diagnostic"):
    plan = json.loads((HERE / "plan.json").read_text())
    for row in plan["inputs"]:
        verify(row)
    source = json.loads(source_inventory.read_text())
    expected = [f"positive-{i:02}" for i in range(1, 13)] + [f"negative_absent-{i:02}" for i in range(1, 5)]
    if source["case_order"] != expected or [row["case_id"] for row in source["cases"]] != expected:
        raise ValueError("wrong v1 case order or a different dataset")
    for row in source["common_inputs"]:
        verify(row)
    public = {"schema": "r505-public-v1", "cases": []}
    oracle = {"schema": "r505-oracle-v1", "source_inventory_sha256": sha(source_inventory), "cases": []}
    pairs = {"schema": "r505-public-dual-v1", "cases": []}
    verified = len(source["common_inputs"])
    for index, case in enumerate(source["cases"], 1):
        for row in case["files"]:
            verify(row)
            verified += 1
        files = {Path(row["path"]).name: row for row in case["files"]}
        opaque = f"case-{index:04}"
        directory = CACHE / "inputs" / opaque
        directory.mkdir(parents=True, exist_ok=True)
        for name in ("rgb.png", "depth.png"):
            data = (ROOT / files[name]["path"]).read_bytes()
            dest = directory / name
            if dest.exists():
                if dest.read_bytes() != data:
                    raise ValueError("opaque input copy differs")
            else:
                dest.write_bytes(data)
        match = re.fullmatch(r"Pick up the (.+?) and place it in the (.+?)\.", case["instruction"])
        if not match:
            raise ValueError("instruction cannot be mechanically split")
        public["cases"].append({"index": index, "id": opaque, "rgb_path": str((directory / "rgb.png").relative_to(ROOT)),
            "rgb_sha256": files["rgb.png"]["sha256"], "rgb_bytes": files["rgb.png"]["bytes"],
            "instruction": case["instruction"], "target_phrase": match[1], "destination_phrase": match[2]})
        pairs["cases"].append({"id": opaque, "rgb_path": str((directory / "rgb.png").relative_to(ROOT)),
            "depth_path": str((directory / "depth.png").relative_to(ROOT)), "rgb_sha256": files["rgb.png"]["sha256"],
            "depth_sha256": files["depth.png"]["sha256"]})
        observation = json.loads((ROOT / files["observation.json"]["path"]).read_text())
        oracle["cases"].append({"id": opaque, "original_case_id": case["case_id"], "kind": case["kind"],
            "files": files, "width": observation["width"], "height": observation["height"],
            "instance_labels": observation["instance_labels"], "grasp_profile_source": "mujoco_upright_box_v1"})
    assert_public_inputs(public)
    write_new(out / "model-inputs.json", public)
    write_new(out / "model-inputs-dual.json", pairs)
    write_new(out / "oracle-inputs.json", oracle)
    write_new(out / "inputs-freeze-report.json", {"status": "PASS", "cases": 16, "positive": 12, "absent": 4,
        "recursive_source_files_verified": verified, "original_bytes_unchanged": True, "opaque_rgb_and_depth_copies": 32,
        "model_inputs_sha256": sha(out / "model-inputs.json"), "oracle_inputs_sha256": sha(out / "oracle-inputs.json"),
        "source_inventory_sha256": sha(source_inventory), "formal_acceptance": "NOT_PERFORMED"})
    print("INPUT_FREEZE_PASS", verified, "original sources; 16 v1 cases")


if __name__ == "__main__":
    freeze_inputs()
