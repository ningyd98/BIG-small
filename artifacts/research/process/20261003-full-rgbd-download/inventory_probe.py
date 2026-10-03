"""小体积来源核查：物理直连、重定向门禁、实际字节计入既有全局账本。"""

from __future__ import annotations

import fcntl
import hashlib
import json
import socket
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from cloud_edge_robot_arm.datasets.external.network import create_direct_transport
from cloud_edge_robot_arm.datasets.external.transfer import _atomic_json

ROOT = Path.home() / "datasets/BIGsmall"
HERE = Path(__file__).resolve().parent
PROBES = ROOT / "source-probes/full-rgbd-20261003"
POLICY = {
    "mode": "direct",
    "interface": "enp7s0",
    "dns_servers": ["223.5.5.5", "223.6.6.6"],
    "allowed_hosts": [
        "modelscope.cn",
        "cdn-lfs-cn-1.modelscope.cn",
        "jbox.sjtu.edu.cn",
        "robotics.shanghaitech.edu.cn",
    ],
    "host_addresses": {"cdn-lfs-cn-1.modelscope.cn": ["119.249.48.19", "119.249.48.20"]},
}
PROBES.mkdir(parents=True, exist_ok=True)
requests = json.loads(Path(sys.argv[1]).read_text())
limit = sum(item.get("limit", 262144) for item in requests)
assert limit <= 8 * 1024**2
lock = threading.Lock()
ledger_path = ROOT / "manifests/download-ledger.json"
with ledger_path.with_name(".download-ledger.lock").open("a+") as ledger_lock:
    fcntl.flock(ledger_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    ledger = json.loads(ledger_path.read_text())
    assert ledger["network_bytes"] + limit <= 250 * 1024**3

    def count(amount):
        with lock:
            ledger["network_bytes"] += amount
            totals = ledger["dataset_network_bytes"]
            totals["rgbd_small_metadata"] = totals.get("rgbd_small_metadata", 0) + amount
            _atomic_json(ledger_path, ledger)

    def probe(item):
        record = {
            "id": item["id"],
            "url": item["url"],
            "interface": "enp7s0",
            "trust_env": False,
            "tls_verification": True,
            "requests": [],
        }
        url = item["url"]
        cap = item.get("limit", 262144)
        payload = bytearray()
        try:
            with httpx.Client(
                transport=create_direct_transport(POLICY),
                trust_env=False,
                follow_redirects=False,
                timeout=12,
            ) as client:
                for _ in range(5):
                    with client.stream(
                        item.get("method", "GET"),
                        url,
                        headers={"Accept-Encoding": "identity", "Range": f"bytes=0-{cap - 1}"},
                    ) as response:
                        network = response.extensions.get("network_stream")
                        sock = network.get_extra_info("socket") if network else None
                        step = {
                            "host": urlsplit(url).hostname,
                            "status": response.status_code,
                            "server_addr": network.get_extra_info("server_addr")
                            if network
                            else None,
                            "bound_interface": sock.getsockopt(
                                socket.SOL_SOCKET, socket.SO_BINDTODEVICE, 256
                            )
                            .rstrip(b"\0")
                            .decode()
                            if sock
                            else None,
                            "content_type": response.headers.get("content-type"),
                            "content_length": response.headers.get("content-length"),
                            "content_range": response.headers.get("content-range"),
                        }
                        record["requests"].append(step)
                        if response.is_redirect:
                            location = str(response.url.join(response.headers["location"]))
                            step["redirect_host"] = urlsplit(location).hostname
                            url = location
                            continue
                        for chunk in response.iter_raw(chunk_size=4096):
                            count(len(chunk))
                            payload.extend(chunk)
                            if len(payload) >= cap:
                                break
                        step["received_body_bytes"] = len(payload)
                        step["bounded_partial"] = response.status_code == 206 or len(payload) >= cap
                        target = PROBES / (item["id"] + ".body")
                        target.write_bytes(payload)
                        record["body_path"] = str(target)
                        record["body_sha256"] = hashlib.sha256(payload).hexdigest()
                        record["status"] = "RESPONSE"
                        if (
                            len(payload) < cap
                            and step["content_type"]
                            and "json" in step["content_type"]
                        ):
                            try:
                                value = json.loads(payload)
                                _atomic_json(HERE / (item["id"] + ".json"), value)
                            except (ValueError, TypeError):
                                pass
                        break
                else:
                    record["status"] = "TOO_MANY_REDIRECTS"
        except (RuntimeError, OSError, ValueError, KeyError, httpx.HTTPError) as exc:
            record["status"] = "BLOCKED_OR_UNAVAILABLE"
            record["error"] = str(exc)
        return record

    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(probe, requests))
    result = {
        "snapshot_utc": datetime.now(UTC).isoformat(),
        "policy": POLICY,
        "probe_only_no_full_dataset_download": True,
        "probes": records,
        "global_network_bytes_after": ledger["network_bytes"],
        "research_network_bytes": ledger["dataset_network_bytes"].get("rgbd_small_metadata", 0),
    }
    _atomic_json(HERE / (Path(sys.argv[1]).stem + "-results.json"), result)
    print(
        json.dumps(
            [
                {
                    "id": p["id"],
                    "status": p["status"],
                    "http": [x["status"] for x in p["requests"]],
                    "peer": [x["server_addr"] for x in p["requests"]],
                    "bytes": sum(x.get("received_body_bytes", 0) for x in p["requests"]),
                    "error": p.get("error"),
                }
                for p in records
            ],
            ensure_ascii=False,
        )
    )
