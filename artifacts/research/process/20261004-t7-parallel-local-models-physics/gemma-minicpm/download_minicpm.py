"""Download native BF16 files with per-file immutable revision and SHA pins."""
from __future__ import annotations
import importlib.util
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(HERE.parent / "source-snapshot/src"))
import httpx
from cloud_edge_robot_arm.datasets.external.network import create_direct_transport
POLICY = {"mode": "direct", "interface": "enp7s0", "dns_servers": ["223.5.5.5", "223.6.6.6"], "allowed_hosts": ["modelscope.cn", "cdn-lfs-cn-1.modelscope.cn"]}
REPO = "OpenBMB/MiniCPM-V-4.6"

def small_file(row, cache):
    path = cache / row["Path"]
    url = f"https://modelscope.cn/models/{REPO}/resolve/{row['Revision']}/{row['Path']}"
    if path.exists():
        payload = path.read_bytes()
    else:
        with httpx.Client(transport=create_direct_transport(POLICY), trust_env=False, timeout=60, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.content
    if len(payload) != row["Size"] or hashlib.sha256(payload).hexdigest() != row["Sha256"]:
        raise ValueError("pinned small-file size/SHA differs")
    if not path.exists():
        path.write_bytes(payload)
    return {"name": row["Path"], "size": row["Size"], "sha256": row["Sha256"], "path": str(path), "source": url, "verified": True}

def main():
    metadata = json.loads((HERE / "minicpm-source-metadata.json").read_text())
    rows = [r for r in metadata["Data"]["Files"] if r["Type"] == "blob"]
    if "--small-only" in sys.argv:
        rows = [r for r in rows if r["Size"] < 1024**2]
    cache = HERE / "minicpm-model"
    cache.mkdir(exist_ok=True)
    spec = importlib.util.spec_from_file_location("prior_range_download", ROOT / "artifacts/research/process/20261004-t7-larger-vlm-candidates/range_download.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {}
        for r in rows:
            if r["Size"] < 1024**2:
                future = pool.submit(small_file, r, cache)
            else:
                future = pool.submit(module.download, {"name": r["Path"], "size": r["Size"], "sha256": r["Sha256"]}, cache=cache, repo=REPO, revision=r["Revision"], policy=POLICY, workers=6)
            futures[future] = r
        for f in as_completed(futures):
            r = futures[f]
            records.append({**f.result(), "revision": r["Revision"]})
            manifest = "minicpm-small-downloads.json" if "--small-only" in sys.argv else "minicpm-downloads.json"
            (HERE / manifest).write_text(json.dumps({"repo": REPO, "files": records, "network_policy": POLICY}, indent=2) + "\n")
    print("NATIVE_BF16_DOWNLOADED", len(records), flush=True)

if __name__ == "__main__":
    main()
