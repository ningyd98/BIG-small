"""下载完整 VINS bag，复用直连传输/续传/账本，不伪装成 Hub 仓库。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from cloud_edge_robot_arm.datasets.external.transfer import (
    _atomic_json,
    _directory,
    _failure_code,
    _hash_download,
    _http_download,
    _partial_paths,
    _reusable,
    _safe_target,
    _transfer_lock,
    _TransferState,
)

HERE = Path(__file__).resolve().parent
ROOT = Path.home() / "datasets/BIGsmall"
FILE = {
    "path": "Handheld/Normal.bag",
    "size": 505031296,
    "url": "https://robotics.shanghaitech.edu.cn/seafile/d/0ea45d1878914077ade5/files/?dl=1&p=%2FNormal.bag",
}
PLAN = {
    "dataset_id": "vins_rgbd_small",
    "source": "public_https",
    "repo_id": "STAR-Center/VINS-RGBD",
    "revision": "Normal-bag-505031296-20261003",
    "revision_note": (
        "Unversioned university source; local snapshot identity only, "
        "no upstream immutable commit or SHA claim."
    ),
    "data_root": str(ROOT),
    "budget_bytes": 250 * 1024**3,
    "dataset_budget_bytes": 5 * 1024**3,
    "minimum_free_bytes": 50 * 1024**3,
    "files": [FILE],
    "network": {
        "mode": "direct",
        "interface": "enp7s0",
        "dns_servers": ["223.5.5.5", "223.6.6.6"],
        "allowed_hosts": ["robotics.shanghaitech.edu.cn"],
    },
}


def main() -> None:
    _atomic_json(HERE / "vins-plan.json", PLAN)
    with _transfer_lock(PLAN):
        state = _TransferState(PLAN)
        target = _directory(PLAN) / FILE["path"]
        _safe_target(target, ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        if _reusable(PLAN, FILE, state.ledger):
            result = {
                "status": "COMPLETE",
                "reused": True,
                "local_path": str(target),
                "sha256": _hash_download(state, target),
                "verification": "LOCAL_SHA256_RECORDED",
            }
            _atomic_json(HERE / "vins-download.json", result)
            print(json.dumps(result), flush=True)
            return
        if shutil.disk_usage(ROOT).free < PLAN["minimum_free_bytes"] + FILE["size"]:
            raise RuntimeError("BLOCKED_STORAGE: preserve 50 GiB reserve")
        state.ledger["download_status"] = "DOWNLOADING"
        state.save()
        try:
            for attempt in range(1, 4):
                partial, sidecar = _partial_paths(target)
                offset = partial.stat().st_size if partial.exists() else 0
                state.reserve(FILE, max(0, FILE["size"] - offset))
                state.update(FILE, state="DOWNLOADING", attempt=attempt, local_path=str(target))
                try:
                    _http_download(state, FILE, target)
                    digest = _hash_download(state, target)
                    state.update(
                        FILE,
                        state="VERIFIED",
                        sha256=digest,
                        verification="LOCAL_SHA256_RECORDED",
                        transport="public_https_direct_http_range",
                        network_mode="direct",
                        interface="enp7s0",
                    )
                    partial.unlink(missing_ok=True)
                    sidecar.unlink(missing_ok=True)
                    state.ledger["download_status"] = "COMPLETE"
                    state.save()
                    result = {
                        "status": "COMPLETE",
                        "local_path": str(target),
                        "size": target.stat().st_size,
                        "sha256": digest,
                        "verification": "LOCAL_SHA256_RECORDED",
                        "upstream_sha256_available": False,
                        "network": PLAN["network"],
                        "source": "public_https",
                        "source_url": FILE["url"],
                        "network_bytes": state.ledger["network_bytes"] - state.start_bytes,
                    }
                    _atomic_json(HERE / "vins-download.json", result)
                    print(json.dumps(result), flush=True)
                    return
                except Exception as exc:
                    code = _failure_code(exc)
                    state.update(FILE, state="FAILED", error=code)
                    if attempt == 3 or code.startswith(
                        ("BLOCKED_", "SIZE:", "TLS:", "PATH:", "CANCELLED:")
                    ):
                        state.ledger["download_status"] = "FAILED"
                        state.save()
                        raise RuntimeError(code) from None
                    state.cancelled.wait(min(2**attempt, 8))
                finally:
                    state.reservations.clear()
        except BaseException:
            if state.ledger.get("download_status") != "FAILED":
                state.cancel()
            raise


if __name__ == "__main__":
    main()
