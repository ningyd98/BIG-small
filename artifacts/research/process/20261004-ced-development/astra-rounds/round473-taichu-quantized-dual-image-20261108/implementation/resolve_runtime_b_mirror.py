"""R475: pin every wheel against PyPI before pip can read its body."""

import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pip._vendor.urllib3.connection as urllib_connection
import pip._vendor.urllib3.util.connection as util_connection
from packaging.utils import parse_wheel_filename
from pip._internal.cli.main import main
from pip._internal.network import download as pip_download

from cloud_edge_robot_arm.datasets.external.network import (
    DirectNetworkBackend, create_direct_transport, validate_network_policy,
)

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[5]
R475 = HERE.parent / "round475-taichu-dependency-mirror-20261108"
CACHE = ROOT / "datasets/model-cache/zdtaichu5-9b-fp8-round473/wheelhouse-b-discovery"
PINS = R475 / "discovery-pins"
BODIES = R475 / "body-receipts"
POLICY = validate_network_policy({"mode": "direct", "interface": "enp7s0",
    "dns_servers": ["223.5.5.5", "223.6.6.6"],
    "allowed_hosts": ["pypi.org", "files.pythonhosted.org",
                      "pypi.tuna.tsinghua.edu.cn", "mirrors.tuna.tsinghua.edu.cn"]})
BACKEND = DirectNetworkBackend(POLICY)
ORIGINAL_DOWNLOAD = pip_download.Downloader.__call__


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def bound_connection(address, timeout=None, source_address=None, socket_options=None):
    return BACKEND.connect_tcp(address[0], address[1], timeout=60).get_extra_info("socket")


def gated_wheel(link):
    filename = link.filename
    name, version, _, tags = parse_wheel_filename(filename)
    if urlsplit(link.url).hostname not in POLICY["allowed_hosts"]:
        raise ValueError("wheel host outside exact allowlist")
    pin_path = PINS / (filename + ".json")
    if pin_path.exists():
        pin = json.loads(pin_path.read_text())
    else:
        metadata_path = R475 / "diagnostic" / f"upstream-{name}-{version}.json"
        if metadata_path.exists():
            raw = metadata_path.read_bytes()
        else:
            with httpx.Client(transport=create_direct_transport(POLICY), trust_env=False, timeout=60) as client:
                response = client.get(f"https://pypi.org/pypi/{name}/{version}/json")
                response.raise_for_status()
            raw = response.content
            with metadata_path.open("xb") as stream:
                stream.write(raw)
        matches = [row for row in json.loads(raw)["urls"] if row["filename"] == filename]
        if len(matches) != 1:
            raise ValueError("wheel not uniquely present in official PyPI metadata")
        source = matches[0]
        expected = source["digests"]["sha256"]
        if link.hash_name == "sha256" and link.hash != expected:
            raise ValueError("mirror link hash differs from upstream")
        pin = {"name": str(name), "version": str(version), "filename": filename,
               "size": source["size"], "sha256": expected,
               "canonical_upstream_url": source["url"], "transfer_url": link.url_without_fragment,
               "upstream_metadata_sha256": hashlib.sha256(raw).hexdigest(),
               "pin_utc": datetime.now(UTC).isoformat(), "pin_monotonic_ns": time.monotonic_ns(),
               "wheel_tags": sorted(str(tag) for tag in tags)}
        save(pin_path, pin)
    destination = CACHE / filename
    receipt_path = BODIES / (filename + ".json")
    if destination.exists():
        if destination.stat().st_size != pin["size"] or digest(destination) != pin["sha256"]:
            raise ValueError("existing cached wheel differs from frozen upstream")
        if not receipt_path.exists():
            save(receipt_path, {"cache_reused": True, "current_body_downloaded": False,
                 "verified_sha256": pin["sha256"], "pin_utc": pin["pin_utc"]})
        return str(destination), "application/octet-stream"
    if sum(json.loads(p.read_text())["size"] for p in PINS.glob("*.json")) > 12 * 1024**3:
        raise ValueError("12 GiB dependency budget exceeded")
    partial = destination.with_name(destination.name + ".part")
    start_ns = time.monotonic_ns()
    start_utc = datetime.now(UTC).isoformat()
    received = 0
    with httpx.Client(transport=create_direct_transport(POLICY), trust_env=False,
                      timeout=60, follow_redirects=True) as client:
        with client.stream("GET", pin["transfer_url"], headers={"Accept-Encoding": "identity"}) as response:
            response.raise_for_status()
            if int(response.headers.get("content-length", -1)) != pin["size"]:
                raise ValueError("mirror wheel length differs from upstream")
            last = time.monotonic()
            with partial.open("xb") as stream:
                for chunk in response.iter_bytes(1024**2):
                    received += len(chunk)
                    if received > pin["size"]:
                        raise ValueError("mirror wheel exceeds upstream size")
                    stream.write(chunk)
                    if time.monotonic() - last > 15:
                        print("PINNED_WHEEL_PROGRESS", name, received, pin["size"], flush=True)
                        last = time.monotonic()
    actual = digest(partial)
    if received != pin["size"] or actual != pin["sha256"]:
        raise ValueError("mirror body SHA256 differs from upstream")
    partial.rename(destination)
    save(receipt_path, {"cache_reused": False, "body_start_utc": start_utc,
         "body_start_monotonic_ns": start_ns, "body_end_utc": datetime.now(UTC).isoformat(),
         "pin_before_body": pin["pin_monotonic_ns"] < start_ns,
         "bytes": received, "verified_sha256": actual})
    print("PINNED_WHEEL_VERIFIED", name, version, received, flush=True)
    return str(destination), "application/octet-stream"


def download(self, link, location):
    if link.filename.endswith(".whl"):
        return gated_wheel(link)
    if link.filename.endswith(".metadata"):
        return ORIGINAL_DOWNLOAD(self, link, location)
    raise ValueError("sdist and non-wheel bodies are prohibited")


def batch(self, links, location):
    for link in links:
        yield link, download(self, link, location)


if __name__ == "__main__":
    PINS.mkdir(exist_ok=False)
    BODIES.mkdir(exist_ok=False)
    save(R475 / "dependency-policy.json", POLICY)
    for key in list(os.environ):
        if key.lower() in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}:
            os.environ.pop(key)
    util_connection.create_connection = bound_connection
    urllib_connection.connection.create_connection = bound_connection
    pip_download.Downloader.__call__ = download
    pip_download.BatchDownloader.__call__ = batch
    argv = ["install", "--dry-run", "--ignore-installed", "--only-binary=:all:",
            "--disable-pip-version-check", "--no-input", "--no-cache-dir", "--progress-bar", "off",
            "--index-url", "https://pypi.tuna.tsinghua.edu.cn/simple", "--report",
            str(HERE / "steps/runtime-b-mirror-resolver.json"),
            "torch==2.10.0", "torchvision==0.25.0", "transformers==5.22.2",
            "compressed-tensors==0.20.1", "accelerate==1.3.0", "timm==1.0.14",
            "pydantic==2.13.5", "loguru==0.7.3", "psutil==7.2.2", "einops==0.8.0"]
    save(R475 / "resolver-argv.json", argv)
    raise SystemExit(main(argv))
