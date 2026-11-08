"""Freeze, verify and install the resolved B wheels into a new nested venv."""

import hashlib
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx

from cloud_edge_robot_arm.datasets.external.network import create_direct_transport

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[5]
CACHE = ROOT / "datasets/model-cache/zdtaichu5-9b-fp8-round473"
ENV = ROOT / ".venv-taichu-round473/runtime-b"
WHEELS = CACHE / "wheelhouse-b"
POLICY = {"mode": "direct", "interface": "enp7s0",
          "dns_servers": ["223.5.5.5", "223.6.6.6"],
          "allowed_hosts": ["pypi.org", "files.pythonhosted.org", "pypi.tuna.tsinghua.edu.cn"]}


def save(name, value):
    with (HERE / name).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(row):
    destination = WHEELS / row["filename"]
    earlier = CACHE / "wheelhouse-b-discovery" / row["filename"]
    if earlier.exists() and earlier.stat().st_size == row["size"] and digest(earlier) == row["sha256"]:
        shutil.copyfile(earlier, destination)
        return {**row, "verified": True, "path": str(destination)}
    part = destination.with_name(destination.name + ".part")
    transfer_url = row["transfer_url"]
    for attempt in range(3):
        offset = part.stat().st_size if part.exists() else 0
        if offset == row["size"]:
            break
        if offset > row["size"]:
            raise ValueError("oversized partial wheel")
        headers = {"Accept-Encoding": "identity"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            with httpx.Client(transport=create_direct_transport(POLICY), trust_env=False,
                              timeout=60, follow_redirects=True) as client:
                with client.stream("GET", transfer_url, headers=headers) as response:
                    if response.status_code == 404 and transfer_url != row["url"] and not offset:
                        print("MIRROR_NOT_SYNCED", row["name"], flush=True)
                        transfer_url = row["url"]
                        continue
                    response.raise_for_status()
                    if offset and (response.status_code != 206 or response.headers.get("content-range")
                                   != f"bytes {offset}-{row['size']-1}/{row['size']}"):
                        raise ValueError("wheel resume was not honored exactly")
                    if int(response.headers.get("content-length", -1)) != row["size"] - offset:
                        raise ValueError("wheel response size differs")
                    last = time.monotonic()
                    with part.open("ab") as stream:
                        for chunk in response.iter_bytes(1024**2):
                            if offset + len(chunk) > row["size"]:
                                raise ValueError("wheel exceeded frozen size")
                            stream.write(chunk)
                            offset += len(chunk)
                            if time.monotonic() - last > 20:
                                print("WHEEL_PROGRESS", row["name"], offset, row["size"], flush=True)
                                last = time.monotonic()
            if offset != row["size"]:
                raise OSError("short wheel response")
            break
        except (httpx.HTTPError, OSError):
            if attempt == 2:
                raise
    if part.stat().st_size != row["size"] or digest(part) != row["sha256"]:
        raise ValueError("wheel SHA256 differs")
    part.rename(destination)
    print("WHEEL_VERIFIED", row["name"], row["version"], flush=True)
    return {**row, "verified": True, "path": str(destination), "actual_transfer_url": transfer_url}


def main():
    report = json.loads((HERE / "steps/runtime-b-resolver.json").read_text())
    manifest = []
    WHEELS.mkdir(exist_ok=False)
    for resolved in report["install"]:
        name = resolved["metadata"]["name"]
        version = resolved["metadata"]["version"]
        url = resolved["download_info"]["url"]
        filename = unquote(Path(urlsplit(url).path).name)
        expected = resolved["download_info"]["archive_info"]["hashes"]["sha256"]
        if not filename.endswith(".whl") or urlsplit(url).hostname != "files.pythonhosted.org":
            raise ValueError("non-wheel or unexpected dependency host")
        with httpx.Client(transport=create_direct_transport(POLICY), trust_env=False, timeout=60) as client:
            response = client.get(f"https://pypi.org/pypi/{name}/{version}/json")
            response.raise_for_status()
        raw = response.content
        with (HERE / f"diagnostic/b-dependency-{name}-{version}.json").open("xb") as stream:
            stream.write(raw)
        candidates = [item for item in response.json()["urls"] if item["filename"] == filename]
        if len(candidates) != 1 or candidates[0]["digests"]["sha256"] != expected:
            raise ValueError("resolver and upstream metadata disagree")
        manifest.append({"name": name, "version": version, "filename": filename,
                         "url": url, "size": candidates[0]["size"], "sha256": expected,
                         "transfer_url": "https://pypi.tuna.tsinghua.edu.cn" + urlsplit(url).path,
                         "metadata_sha256": hashlib.sha256(raw).hexdigest()})
    total = sum(row["size"] for row in manifest)
    if total > 12 * 1024**3 or shutil.disk_usage(CACHE).free < total * 2 + 50 * 1024**3:
        raise ValueError("dependency or disk budget exceeded")
    save("wheel-manifest-b.json", {"total_bytes": total, "files": manifest, "policy": POLICY,
         "mirror_provenance": "diagnostic/tuna-mirror-discovery.json"})
    print("FROZEN_B_WHEELS", len(manifest), total, flush=True)
    records = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(download, row) for row in manifest]):
            records.append(future.result())
    save("steps/runtime-b-wheel-verification.json", {"files": records, "verified": True})
    subprocess.run([sys.executable, "-m", "venv", str(ENV)], check=True)
    argv = [str(ENV / "bin/python"), "-m", "pip", "install", "--no-index", "--no-deps",
            "--disable-pip-version-check", "--report", str(HERE / "steps/pip-install-b.json"),
            *[str(WHEELS / row["filename"]) for row in manifest]]
    save("runtime-decision-b.json", {"route": "B", "venv": str(ENV),
         "torch": "2.10.0", "transformers": "5.22.2", "compressed_tensors": "0.20.1",
         "use_optimized_inference": True, "dequantize": False, "device": "cuda:0 only",
         "kernel": "Transformers CompressedTensorsFP8Linear; CUDA SM89 supported by source gate",
         "install_argv": argv, "base_borrowed": False})
    result = subprocess.run(argv, capture_output=True)
    (HERE / "steps/pip-install-b.stdout").write_bytes(result.stdout)
    (HERE / "steps/pip-install-b.stderr").write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError("offline B wheel installation failed")
    checks = {}
    for name, arguments in [("check", ["-m", "pip", "check"]), ("freeze", ["-m", "pip", "freeze", "--all"])]:
        result = subprocess.run([str(ENV / "bin/python"), *arguments], capture_output=True)
        (HERE / f"steps/pip-{name}-b.stdout").write_bytes(result.stdout)
        (HERE / f"steps/pip-{name}-b.stderr").write_bytes(result.stderr)
        checks[name] = result.returncode
    save("steps/step-02-runtime-b-install.json", {"status": "PASS" if not any(checks.values())
         else "DEPENDENCY_INCOMPATIBLE", "checks": checks, "wheel_bytes": total})
    print("B_INSTALLED", checks, flush=True)


if __name__ == "__main__":
    main()
