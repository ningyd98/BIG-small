"""Pinned official Qwen3-VL 8B Q8_0 download/import using the existing direct transport."""

from __future__ import annotations

import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from range_download import download as parallel_download

from cloud_edge_robot_arm.datasets.external.network import create_direct_transport

HERE = Path(__file__).parent
ROOT = HERE.parents[3]
REPO = "Qwen/Qwen3-VL-8B-Instruct-GGUF"
MODEL = "qwen3-vl-research:8b-instruct-q8_0"
POLICY = {
    "mode": "direct",
    "interface": "enp7s0",
    "dns_servers": ["223.5.5.5", "223.6.6.6"],
    "allowed_hosts": ["modelscope.cn", "cdn-lfs-cn-1.modelscope.cn"],
}


def main():
    HERE.mkdir(parents=True, exist_ok=True)
    metadata_path = HERE / "qwen8-source-metadata.json"
    with httpx.Client(
        transport=create_direct_transport(POLICY), trust_env=False, timeout=60
    ) as client:
        response = client.get(
            f"https://modelscope.cn/api/v1/models/{REPO}/repo/files",
            params={"Revision": "master", "Recursive": "true"},
        )
        response.raise_for_status()
        metadata = response.json()
    if not metadata_path.exists():
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    else:
        metadata = json.loads(metadata_path.read_text())
    names = {"Qwen3VL-8B-Instruct-Q8_0.gguf", "mmproj-Qwen3VL-8B-Instruct-F16.gguf"}
    rows = [row for row in metadata["Data"]["Files"] if row["Path"] in names]
    if len(rows) != 2 or len({row["Revision"] for row in rows}) != 1:
        raise ValueError("official weight/projector metadata missing or versions differ")
    source = ROOT / "artifacts/research/process/20261003-t3-vl-candidate/download.py"
    spec = importlib.util.spec_from_file_location("existing_direct_downloader", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CACHE = ROOT / "datasets/model-cache/qwen3-vl-8b-instruct-q8_0"
    module.REPO = REPO
    module.REVISION = rows[0]["Revision"]
    module.POLICY = POLICY
    module.FILES = [
        {"name": row["Path"], "size": row["Size"], "sha256": row["Sha256"]} for row in rows
    ]
    module.CACHE.mkdir(parents=True, exist_ok=True)
    records = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                parallel_download,
                item,
                cache=module.CACHE,
                repo=REPO,
                revision=module.REVISION,
                policy=POLICY,
            )
            for item in module.FILES
        ]
        for future in as_completed(futures):
            records.append(future.result())
            (HERE / "qwen8-downloads.json").write_text(
                json.dumps(
                    {
                        "repo": REPO,
                        "revision": module.REVISION,
                        "network_policy": POLICY,
                        "files": records,
                    },
                    indent=2,
                )
                + "\n"
            )
    with httpx.Client(base_url="http://127.0.0.1:11434", trust_env=False, timeout=600) as client:
        tags = client.get("/api/tags").json()["models"]
        if MODEL in {row["name"] for row in tags}:
            raise FileExistsError("refusing to replace an existing registered model")
        files = {}
        for item in records:
            path = Path(item["path"])
            sha = "sha256:" + item["sha256"]
            response = client.head("/api/blobs/" + sha)
            if response.status_code == 404:
                with path.open("rb") as stream:
                    response = client.post(
                        "/api/blobs/" + sha,
                        content=stream,
                        headers={"Content-Length": str(item["size"])},
                    )
                response.raise_for_status()
            else:
                response.raise_for_status()
            files[path.name] = sha
            print("IMPORTED_BLOB", path.name, flush=True)
        request = {
            "model": MODEL,
            "files": files,
            "stream": False,
            "parameters": {"temperature": 1.0, "top_p": 0.95, "top_k": 20, "presence_penalty": 1.5},
        }
        (HERE / "qwen8-create-request.json").write_text(json.dumps(request, indent=2) + "\n")
        response = client.post("/api/create", json=request)
        (HERE / "qwen8-create-response.json").write_text(response.text + "\n")
        response.raise_for_status()
        if response.json().get("status") != "success":
            raise RuntimeError("local model registration failed")
        entry = next(
            row for row in client.get("/api/tags").json()["models"] if row["name"] == MODEL
        )
        show = client.post("/api/show", json={"model": MODEL}).json()
        (HERE / "qwen8-entry.json").write_text(json.dumps(entry, indent=2) + "\n")
        (HERE / "qwen8-show.json").write_text(json.dumps(show, indent=2) + "\n")
        if "vision" not in show.get("capabilities", []):
            raise RuntimeError("imported candidate does not advertise vision")
        candidate = {
            "provider": "ollama",
            "model": MODEL,
            "endpoint": "http://127.0.0.1:11434",
            "weight_digest": entry["digest"],
            "quantization": "Q8_0",
            "image_size": [320, 240],
            "coordinate_system": "normalized_1000",
            "grasp_profile": "mujoco_upright_box_v1",
            "timeout_s": 180,
            "generation_parameters": {
                "temperature": 0,
                "num_ctx": 8192,
                "num_predict": 512,
                "think": False,
            },
            "probe": {
                "scenario_id": "S01_NORMAL_STATIC",
                "seed": 0,
                "instruction": "把图中的红色方块放到绿色方形目标区域。",
                "warm_runs": 3,
            },
        }
        (HERE / "qwen8-normalized.json").write_text(
            json.dumps(candidate, indent=2, ensure_ascii=False) + "\n"
        )
        print("REGISTERED", MODEL, entry["digest"], show.get("capabilities"), flush=True)


if __name__ == "__main__":
    main()
