"""Pinned Google mirror download and loopback import; never loads the model."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(HERE.parent / "source-snapshot/src"))
import httpx
from cloud_edge_robot_arm.datasets.external.network import create_direct_transport

POLICY = {"mode": "direct", "interface": "enp7s0", "dns_servers": ["223.5.5.5", "223.6.6.6"], "allowed_hosts": ["modelscope.cn", "cdn-lfs-cn-1.modelscope.cn"]}
REPO = "google/gemma-4-12B-it-qat-q4_0-gguf"
NAME = "gemma4-research:12b-it-qat"

def main():
    metadata = json.loads((HERE / "gemma-ms-metadata.json").read_text())
    rows = [r for r in metadata["Data"]["Files"] if r["Path"].endswith(".gguf")]
    assert len(rows) == 2 and len({r["Revision"] for r in rows}) == 1
    cache = HERE / "gemma-model"
    cache.mkdir(exist_ok=True)
    spec = importlib.util.spec_from_file_location("prior_range_download", ROOT / "artifacts/research/process/20261004-t7-larger-vlm-candidates/range_download.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    items = [{"name": r["Path"], "size": r["Size"], "sha256": r["Sha256"]} for r in rows]
    revision = rows[0]["Revision"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(module.download, item, cache=cache, repo=REPO, revision=revision, policy=POLICY) for item in items]
        records = [f.result() for f in futures]
    (HERE / "gemma-downloads.json").write_text(json.dumps({"repo": REPO, "revision": revision, "files": records, "network_policy": POLICY}, indent=2) + "\n")
    with httpx.Client(base_url="http://127.0.0.1:11434", trust_env=False, timeout=600) as client:
        tags = client.get("/api/tags").json()["models"]
        if NAME in {r["name"] for r in tags}:
            raise FileExistsError("refusing to replace existing research model")
        files = {}
        for item in records:
            digest = "sha256:" + item["sha256"]
            response = client.head("/api/blobs/" + digest)
            if response.status_code == 404:
                with Path(item["path"]).open("rb") as stream:
                    response = client.post("/api/blobs/" + digest, content=stream, headers={"Content-Length": str(item["size"])})
            response.raise_for_status()
            files[item["name"]] = digest
        request = {"model": NAME, "files": files, "stream": False, "parameters": {"temperature": 0, "num_ctx": 8192, "num_predict": 512}}
        (HERE / "gemma-create-request.json").write_text(json.dumps(request, indent=2) + "\n")
        response = client.post("/api/create", json=request)
        (HERE / "gemma-create-response.json").write_text(response.text + "\n")
        response.raise_for_status()
        assert response.json().get("status") == "success"
        entry = next(r for r in client.get("/api/tags").json()["models"] if r["name"] == NAME)
        show = client.post("/api/show", json={"model": NAME}).json()
        (HERE / "gemma-entry.json").write_text(json.dumps(entry, indent=2) + "\n")
        (HERE / "gemma-show.json").write_text(json.dumps(show, indent=2) + "\n")
        assert "vision" in show.get("capabilities", [])
        config = {"provider": "ollama", "model": NAME, "endpoint": "http://127.0.0.1:11434", "weight_digest": entry["digest"], "quantization": show["details"]["quantization_level"], "image_size": [320, 240], "coordinate_system": "normalized_1000", "grasp_profile": "mujoco_upright_box_v1", "timeout_s": 180, "generation_parameters": {"temperature": 0, "num_ctx": 8192, "num_predict": 512, "think": False}}
        (HERE / "gemma-normalized.json").write_text(json.dumps(config, indent=2) + "\n")
        print("REGISTERED", NAME, entry["digest"], show["capabilities"], flush=True)

if __name__ == "__main__":
    main()
