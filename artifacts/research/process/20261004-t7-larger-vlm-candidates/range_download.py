"""Resume pinned files with bounded parallel byte ranges on the physical interface."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from cloud_edge_robot_arm.datasets.external.network import create_direct_transport


def download(item, *, cache, repo, revision, policy, workers=8):
    destination = cache / item["name"]
    partial = cache / (item["name"] + ".part")
    size, expected = item["size"], item["sha256"]
    url = f"https://modelscope.cn/models/{repo}/resolve/{revision}/{item['name']}"

    def file_digest(path):
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    if destination.exists():
        if destination.stat().st_size != size or file_digest(destination) != expected:
            raise ValueError("existing destination failed pinned integrity")
        return {**item, "path": str(destination), "source": url, "verified": True}
    with httpx.Client(
        transport=create_direct_transport(policy),
        trust_env=False,
        timeout=60,
        follow_redirects=False,
    ) as client:
        response = client.head(url)
        response.raise_for_status()
        if response.headers.get("x-linked-etag", "").strip('"') != expected:
            raise ValueError("pinned HEAD digest differs")
    offset = partial.stat().st_size if partial.exists() else 0
    if not 0 <= offset <= size:
        raise ValueError("partial prefix exceeds expected size")
    if shutil.disk_usage(cache).free < 2 * (size - offset) + 50 * 1024**3:
        raise RuntimeError("insufficient disk reserve for parallel segments and merge")
    chunk_size = 128 * 1024**2
    ranges = [
        (start, min(start + chunk_size, size) - 1) for start in range(offset, size, chunk_size)
    ]

    def segment(bounds):
        start, end = bounds
        path = cache / f"{item['name']}.range-{start}-{end}"
        done = path.stat().st_size if path.exists() else 0
        if done > end - start + 1:
            raise ValueError("segment exceeds expected range")
        for attempt in range(4):
            if done == end - start + 1:
                return path
            try:
                with httpx.Client(
                    transport=create_direct_transport(policy),
                    trust_env=False,
                    timeout=60,
                    follow_redirects=True,
                ) as client:
                    with client.stream(
                        "GET",
                        url,
                        headers={
                            "Range": f"bytes={start + done}-{end}",
                            "Accept-Encoding": "identity",
                        },
                    ) as response:
                        response.raise_for_status()
                        wanted = f"bytes {start + done}-{end}/{size}"
                        if (
                            response.status_code != 206
                            or response.headers.get("content-range") != wanted
                        ):
                            raise ValueError("server did not return the exact pinned byte range")
                        if (
                            int(response.headers.get("content-length", -1))
                            != end - start + 1 - done
                        ):
                            raise ValueError("segment Content-Length differs")
                        with path.open("ab") as stream:
                            for chunk in response.iter_bytes(1024**2):
                                if done + len(chunk) > end - start + 1:
                                    raise ValueError("segment exceeded expected length")
                                stream.write(chunk)
                                done += len(chunk)
                if done != end - start + 1:
                    raise OSError("short segment")
                return path
            except (httpx.HTTPError, OSError):
                done = path.stat().st_size if path.exists() else 0
                if attempt == 3:
                    raise

    start_time, completed, paths = time.monotonic(), offset, {}
    last = start_time
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(segment, bounds): bounds for bounds in ranges}
        for future in as_completed(futures):
            bounds = futures[future]
            paths[bounds[0]] = future.result()
            completed += bounds[1] - bounds[0] + 1
            if time.monotonic() - last >= 15:
                print(
                    json.dumps(
                        {
                            "file": item["name"],
                            "completed_bytes": completed,
                            "total": size,
                            "workers": workers,
                            "elapsed_s": round(time.monotonic() - start_time, 1),
                        }
                    ),
                    flush=True,
                )
                last = time.monotonic()
    # A separate merge preserves the original prefix if interrupted.
    merged = cache / (item["name"] + ".merged")
    with merged.open("wb") as output:
        if offset:
            with partial.open("rb") as prefix:
                shutil.copyfileobj(prefix, output, 4 * 1024**2)
        for first in sorted(paths):
            with paths[first].open("rb") as piece:
                shutil.copyfileobj(piece, output, 4 * 1024**2)
    if merged.stat().st_size != size or file_digest(merged) != expected:
        raise ValueError("assembled file failed pinned size/SHA256")
    merged.rename(destination)
    # Delete only this task's confirmed redundant prefixes/segments after full SHA verification.
    if partial.exists():
        partial.unlink()
    for path in paths.values():
        path.unlink()
    print("VERIFIED", item["name"], expected, flush=True)
    return {
        **item,
        "path": str(destination),
        "source": url,
        "verified": True,
        "parallel_ranges": workers,
    }
