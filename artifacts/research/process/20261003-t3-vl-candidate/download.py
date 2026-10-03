"""Fetch pinned Qwen3-VL 4B GGUF files over the physical mainland connection.

Run from the repository root with ``.venv-data/bin/python``. The large files are
stored under the repository's ignored ``datasets/`` directory.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

from cloud_edge_robot_arm.datasets.external.network import create_direct_transport

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[4]
CACHE = ROOT / "datasets" / "model-cache" / "qwen3-vl-4b-instruct"
REPO = "Qwen/Qwen3-VL-4B-Instruct-GGUF"
REVISION = "625828cbd3489786522366e19e22b6f12278e41a"
POLICY = {
    "mode": "direct",
    "interface": "enp7s0",
    "dns_servers": ["223.5.5.5", "223.6.6.6"],
    "allowed_hosts": ["modelscope.cn", "cdn-lfs-cn-1.modelscope.cn"],
}
FILES = [
    {
        "name": "Qwen3VL-4B-Instruct-Q4_K_M.gguf",
        "size": 2497281664,
        "sha256": "66358cb18bb6b3b1b6675aa412c7a88ef01d228f481184d13668e5201c730a0a",
    },
    {
        "name": "mmproj-Qwen3VL-4B-Instruct-F16.gguf",
        "size": 836180256,
        "sha256": "256f3a43bd4205ffef48d6b92715e1e70b5b0e9aef06522584967513a9985331",
    },
]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_url(name: str) -> str:
    return f"https://modelscope.cn/models/{REPO}/resolve/{REVISION}/{name}"


def download(item: dict[str, object]) -> dict[str, object]:
    name = str(item["name"])
    expected_size = int(item["size"])
    expected_sha256 = str(item["sha256"])
    destination = CACHE / name
    partial = CACHE / (name + ".part")
    url = source_url(name)

    with httpx.Client(
        transport=create_direct_transport(POLICY), trust_env=False,
        timeout=60, follow_redirects=False,
    ) as client:
        response = client.head(url, headers={"Accept-Encoding": "identity"})
        response.raise_for_status()
        linked = response.headers.get("x-linked-etag", "").strip('"')
        if linked != expected_sha256:
            raise RuntimeError(f"pinned source SHA differs for {name}: {linked}")

    if destination.exists():
        if destination.stat().st_size != expected_size or digest(destination) != expected_sha256:
            raise RuntimeError(f"existing file failed integrity checks: {destination}")
        return {**item, "source": url, "path": str(destination), "verified": True}

    for attempt in range(1, 5):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset == expected_size:
            break
        if offset > expected_size:
            raise RuntimeError(f"partial file exceeds pinned size: {partial}")
        if shutil.disk_usage(CACHE).free < expected_size - offset + 50 * 1024**3:
            raise RuntimeError("less than 50 GiB free disk reserve")
        try:
            with httpx.Client(
                transport=create_direct_transport(POLICY), trust_env=False,
                timeout=60, follow_redirects=True,
            ) as client:
                headers = {
                    "Accept-Encoding": "identity",
                    "Range": f"bytes={offset}-",
                }
                with client.stream("GET", url, headers=headers) as response:
                    response.raise_for_status()
                    if response.status_code == 206:
                        expected_range = f"bytes {offset}-{expected_size - 1}/{expected_size}"
                        if response.headers.get("content-range") != expected_range:
                            raise RuntimeError("unexpected resumed content range")
                    elif response.status_code != 200 or offset:
                        raise RuntimeError("server did not honor resumed download")
                    if int(response.headers.get("content-length", -1)) != expected_size - offset:
                        raise RuntimeError("response size differs from pinned ModelScope size")
                    print(
                        json.dumps({"file": name, "start": offset, "host": response.url.host}),
                        flush=True,
                    )
                    last = time.monotonic()
                    with partial.open("ab") as output:
                        for chunk in response.iter_bytes(1024 * 1024):
                            if offset + len(chunk) > expected_size:
                                raise RuntimeError("response exceeded pinned size")
                            output.write(chunk)
                            offset += len(chunk)
                            if time.monotonic() - last >= 15:
                                progress = {"file": name, "bytes": offset, "total": expected_size}
                                print(json.dumps(progress), flush=True)
                                last = time.monotonic()
            if offset != expected_size:
                raise RuntimeError("incomplete download")
            break
        except (httpx.HTTPError, OSError) as error:
            print(
                json.dumps({"file": name, "attempt": attempt,
                            "error": type(error).__name__}),
                flush=True,
            )
            if attempt == 4:
                raise

    actual = digest(partial)
    if actual != expected_sha256:
        raise RuntimeError(f"SHA256 mismatch for {name}: {actual}")
    partial.rename(destination)
    print(json.dumps({"file": name, "verified_sha256": actual}), flush=True)
    return {**item, "source": url, "path": str(destination), "verified": True}


if __name__ == "__main__":
    CACHE.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(download, item) for item in FILES]):
            records.append(future.result())
            (HERE / "downloads.json").write_text(
                json.dumps({"repo": REPO, "revision": REVISION,
                            "network_policy": POLICY, "files": records}, indent=2) + "\n",
                encoding="utf-8",
            )
