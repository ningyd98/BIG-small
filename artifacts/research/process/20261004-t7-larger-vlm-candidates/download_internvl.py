"""Download hash-pinned official InternVL weights and code through enp7s0."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from range_download import download

from cloud_edge_robot_arm.datasets.external.network import create_direct_transport

HERE = Path(__file__).parent
CACHE = HERE.parents[3] / "datasets/model-cache/internvl2_5-8b"
REPO = "OpenGVLab/InternVL2_5-8B"
POLICY = {
    "mode": "direct",
    "interface": "enp7s0",
    "dns_servers": ["223.5.5.5", "223.6.6.6"],
    "allowed_hosts": ["modelscope.cn", "cdn-lfs-cn-1.modelscope.cn"],
}


def fetch(row):
    item = {"name": row["Path"], "size": row["Size"], "sha256": row["Sha256"]}
    if row["Size"] > 100 * 1024**2:
        return download(
            item, cache=CACHE, repo=REPO, revision=row["Revision"], policy=POLICY, workers=4
        )
    path = CACHE / row["Path"]
    url = f"https://modelscope.cn/models/{REPO}/resolve/{row['Revision']}/{row['Path']}"
    if not path.exists():
        with httpx.Client(
            transport=create_direct_transport(POLICY),
            trust_env=False,
            timeout=60,
            follow_redirects=True,
        ) as client:
            response = client.get(url)
            response.raise_for_status()
        raw = response.content
        if len(raw) != row["Size"] or hashlib.sha256(raw).hexdigest() != row["Sha256"]:
            raise ValueError("small source file failed pinned integrity")
        path.write_bytes(raw)
    if (
        path.stat().st_size != row["Size"]
        or hashlib.sha256(path.read_bytes()).hexdigest() != row["Sha256"]
    ):
        raise ValueError("existing source file failed pinned integrity")
    return {**item, "path": str(path), "source": url, "verified": True}


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    data = json.loads((HERE / "internvl8-metadata.json").read_text())
    rows = [
        r
        for r in data["Data"]["Files"]
        if "/" not in r["Path"]
        and r["Size"] > 0
        and r["Path"].endswith((".py", ".json", ".model", ".safetensors"))
    ]
    # Source file names, revisions and hashes are frozen before downloads or execution.
    protocol = {"repo": REPO, "files": rows, "network_policy": POLICY, "cache": str(CACHE)}
    manifest = HERE / "internvl8-download-protocol.json"
    if not manifest.exists():
        manifest.write_text(json.dumps(protocol, indent=2) + "\n")
    if json.loads(manifest.read_text()) != protocol:
        raise ValueError("source protocol drift")
    records = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(fetch, row) for row in rows]):
            records.append(future.result())
            (HERE / "internvl8-downloads.json").write_text(
                json.dumps({"repo": REPO, "network_policy": POLICY, "files": records}, indent=2)
                + "\n"
            )
            print("FILE_DONE", records[-1]["name"], flush=True)
    print("COMPLETE", len(records), sum(r["size"] for r in records), flush=True)


if __name__ == "__main__":
    main()
