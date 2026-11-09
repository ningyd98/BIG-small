"""Download a frozen official ModelScope snapshot using the existing range verifier."""

import hashlib
import importlib.util
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from cloud_edge_robot_arm.datasets.external.network import create_direct_transport

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[5]
CACHE = ROOT / "datasets/model-cache/ordered-small-vlm-20261109"
POLICY = {"mode": "direct", "interface": "enp7s0", "dns_servers": ["223.5.5.5", "223.6.6.6"],
          "allowed_hosts": ["modelscope.cn", "cdn-lfs-cn-1.modelscope.cn"]}
spec = importlib.util.spec_from_file_location("r505_pinned_ranges", ROOT / "artifacts/research/process/20261004-t7-larger-vlm-candidates/range_download.py")
ranges = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ranges)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    key, repo, candidate = sys.argv[1:]
    metadata = HERE / "diagnostic" / f"{key}-modelscope-metadata.raw.json"
    data = json.loads(metadata.read_text())
    rows = [row for row in data["Data"]["Files"] if row["Type"] == "blob"]
    destination = CACHE / "models" / repo.split("/")[-1]
    destination.mkdir(parents=True, exist_ok=True)
    folder = HERE / "candidates" / candidate
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"repo": repo, "source_metadata_sha256": digest(metadata), "files": rows,
                "bytes": sum(row["Size"] for row in rows), "policy": POLICY,
                "sdk_and_assets_local_only": True, "max_total_download_workers": 4}
    frozen = folder / "asset-manifest.json"
    if frozen.exists():
        if json.loads(frozen.read_text()) != manifest:
            raise ValueError("asset manifest drift")
    else:
        frozen.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    records = []
    started = time.monotonic()

    def save(row, record):
        records.append({**record, "revision": row["Revision"]})
        report = {"status": "DOWNLOADING", "repo": repo, "verified": records, "elapsed_s": time.monotonic() - started}
        (folder / "download-progress.local.json").write_text(json.dumps(report, indent=2) + "\n")
        print("ASSET_VERIFIED", row["Path"], row["Size"], flush=True)

    for row in rows:
        path = destination / row["Path"]
        if not path.is_relative_to(destination):
            raise ValueError("path escaped model cache")
        path.parent.mkdir(parents=True, exist_ok=True)
    for row in [row for row in rows if row["Size"] < 100_000_000]:
        item = {"name": row["Path"], "size": row["Size"], "sha256": row["Sha256"]}
        path = destination / row["Path"]
        url = f"https://modelscope.cn/models/{repo}/resolve/{row['Revision']}/{row['Path']}"
        if not path.exists():
            with httpx.Client(transport=create_direct_transport(POLICY), trust_env=False,
                              timeout=httpx.Timeout(120, connect=20), follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
            if len(response.content) != item["size"] or hashlib.sha256(response.content).hexdigest() != item["sha256"]:
                raise ValueError("small source size or hash mismatch: " + row["Path"])
            path.write_bytes(response.content)
        if path.stat().st_size != item["size"] or digest(path) != item["sha256"]:
            raise ValueError("existing source size or hash mismatch: " + row["Path"])
        save(row, {**item, "path": str(path), "verified": True})
    large = [row for row in rows if row["Size"] >= 100_000_000]
    # At most four physical requests, preserving each original shard's exact bytes.
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(large)))) as pool:
        futures = {pool.submit(ranges.download,
            {"name": row["Path"], "size": row["Size"], "sha256": row["Sha256"]},
            cache=destination, repo=repo, revision=row["Revision"], policy=POLICY, workers=1): row for row in large}
        for future in as_completed(futures):
            row = futures[future]
            save(row, future.result())
    result = {"status": "PASS", "repo": repo, "files": records, "elapsed_s": time.monotonic() - started,
              "cache": str(destination), "source_metadata_sha256": digest(metadata), "full_remote_reproduction": False}
    with (folder / "download-result.json").open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("MODEL_ASSETS_PASS", repo, len(records), flush=True)


if __name__ == "__main__":
    main()
