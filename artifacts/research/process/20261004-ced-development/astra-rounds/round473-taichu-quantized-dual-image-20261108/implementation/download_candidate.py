"""Fetch the frozen official FP8 candidate through the existing bound transport."""

import hashlib
import json
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

from cloud_edge_robot_arm.datasets.external.network import create_direct_transport

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[5]
CACHE = ROOT / "datasets/model-cache/zdtaichu5-9b-fp8-round473"
REPO = "TaichuAI/ZDTaichu5.0-9B-FP8"
POLICY = {
    "mode": "direct",
    "interface": "enp7s0",
    "dns_servers": ["223.5.5.5", "223.6.6.6"],
    "allowed_hosts": ["modelscope.cn", "cdn-lfs-cn-1.modelscope.cn"],
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(name, value):
    with (HERE / name).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def sources():
    raw = HERE / "diagnostic/modelscope-FP8-metadata.raw.json"
    data = json.loads(raw.read_text())
    if data.get("Success") is not True:
        raise ValueError("metadata does not establish a successful official listing")
    rows = []
    for row in data["Data"]["Files"]:
        name = row["Path"]
        if "/" in name or row["Size"] <= 0 or name.startswith("."):
            continue
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", name):
            raise ValueError("unsafe manifest path")
        if not re.fullmatch(r"[a-f0-9]{64}", row["Sha256"]):
            raise ValueError("missing expected SHA256")
        if not re.fullmatch(r"[a-f0-9]{40}", row["Revision"]):
            raise ValueError("missing immutable revision")
        rows.append({"name": name, "size": row["Size"], "sha256": row["Sha256"],
                     "revision": row["Revision"], "repo": REPO})
    small = [r for r in rows if not r["name"].endswith(".safetensors")]
    weights = [r for r in rows if r["name"].endswith(".safetensors")]
    if len({r["name"] for r in rows}) != len(rows) or len(weights) != 1:
        raise ValueError("manifest duplicates or unexpected weight layout")
    if sum(r["size"] for r in small) > 100 * 1024**2:
        raise ValueError("small-source budget exceeded")
    if sum(r["size"] for r in weights) > 16 * 1024**3:
        raise ValueError("weight budget exceeded")
    CACHE.mkdir(parents=True, exist_ok=False)
    save("metadata-freeze.json", {"repo": REPO, "metadata_path": str(raw),
         "metadata_sha256": digest(raw), "policy": POLICY,
         "created_at": datetime.now(UTC).isoformat()})
    save("source-manifest.json", {"repo": REPO, "files": small})
    save("weight-manifest.json", {"repo": REPO, "files": weights, "cache": str(CACHE)})
    results = []
    for row in small:
        dst = CACHE / row["name"]
        earlier = HERE / "diagnostic/official-fp8-files" / row["name"]
        url = f"https://modelscope.cn/models/{REPO}/resolve/{row['revision']}/{row['name']}"
        if earlier.exists() and digest(earlier) == row["sha256"]:
            shutil.copyfile(earlier, dst)
        else:
            with httpx.Client(transport=create_direct_transport(POLICY), trust_env=False,
                              timeout=60, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
            with dst.open("xb") as stream:
                stream.write(response.content)
        if dst.stat().st_size != row["size"] or digest(dst) != row["sha256"]:
            raise ValueError(f"source integrity failure: {row['name']}")
        results.append({**row, "path": str(dst), "url": url, "verified": True})
        print("SOURCE_VERIFIED", row["name"], flush=True)
    save("steps/step-01-sources.json", {"status": "PASS", "files": results})


def weights():
    tools = ROOT / "artifacts/research/process/20261004-t7-larger-vlm-candidates"
    sys.path.insert(0, str(tools))
    from range_download import download

    manifest = json.loads((HERE / "weight-manifest.json").read_text())
    results = []
    for row in manifest["files"]:
        results.append(download(row, cache=CACHE, repo=REPO,
                                revision=row["revision"], policy=POLICY, workers=4))
    save("steps/step-03-weights.json", {"status": "PASS", "files": results})


if __name__ == "__main__":
    {"sources": sources, "weights": weights}[sys.argv[1]]()
