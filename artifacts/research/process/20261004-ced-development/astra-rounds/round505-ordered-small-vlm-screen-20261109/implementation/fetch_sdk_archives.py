"""Fetch pinned official SDK archive bytes over the project physical route."""
import hashlib
import json
import sys
from pathlib import Path
import httpx
from cloud_edge_robot_arm.datasets.external.network import create_direct_transport
ROOT = Path.cwd()
BASE = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109"
sdk = ROOT / "datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e"
policy = {"mode": "direct", "interface": "enp7s0", "dns_servers": ["223.5.5.5", "223.6.6.6"], "allowed_hosts": ["raw.githubusercontent.com"]}
rows = [("third_party/manifest.json", None), ("third_party/transformers.tar.gz", "3b9d4b20efc92041d3d270be1b875a760f7ed2651ba01be59286d1e0ad6d4f25")]
records = []
for path, expected in rows:
    url = "https://raw.githubusercontent.com/groundingpi/GroundingPI/98641f0b8ed94a091f1457e0e624c49c0ebf3876/" + path
    record = {"url": url, "policy": policy}
    try:
        with httpx.Client(transport=create_direct_transport(policy), trust_env=False, follow_redirects=False, timeout=httpx.Timeout(120, connect=20)) as client:
            response = client.get(url)
            record["status_code"] = response.status_code
            response.raise_for_status()
        value = response.content
        checksum = hashlib.sha256(value).hexdigest()
        if expected:
            assert checksum == expected
        destination = sdk / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(value)
        record.update(status="PASS", bytes=len(value), sha256=checksum, local_path=str(destination))
    except Exception as error:
        record.update(status="DOWNLOAD_DEFERRED", error_type=type(error).__name__, error=str(error))
    records.append(record)
    print(record["status"], path, flush=True)
with (BASE / "diagnostic/grounding-sdk-physical-download.json").open("x") as stream:
    json.dump(records, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
