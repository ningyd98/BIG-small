"""固定来源、版本和摘要的传输；预算计算与网络操作保持分离。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

GiB = 1024**3
_DEFAULT_BUDGET = 250 * GiB
_DEFAULT_RESERVE = 50 * GiB
_HASH = re.compile(r"[0-9a-fA-F]{64}\Z")
_COMMIT = re.compile(r"[0-9a-fA-F]{40}\Z")


def hash_file(path: str | Path) -> str:
    """逐块记录本地 SHA256，不把本地摘要误称为官方验证。"""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_path(value: Any) -> str:
    path = PurePosixPath(str(value))
    if (
        not isinstance(value, str)
        or not value
        or path.is_absolute()
        or "\\" in value
        or "\x00" in value
        or ":" in value
        or any(part in ("..", ".cache") for part in path.parts)
        or path.as_posix() in (".", "")
        or path.as_posix() != value
    ):
        raise ValueError("unsafe file path")
    return path.as_posix()


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return int(value)


def _validate(plan: dict[str, Any]) -> dict[str, Any]:
    data = dict(plan)
    dataset = _relative_path(data.get("dataset_id", ""))
    if "/" in dataset:
        raise ValueError("dataset_id must be a single safe path component")
    source, revision = data.get("source"), data.get("revision")
    if source not in ("huggingface", "modelscope"):
        raise ValueError("source must be huggingface or modelscope")
    if (
        not isinstance(revision, str)
        or revision in (".", "..")
        or not re.fullmatch(r"[A-Za-z0-9._-]+", revision)
    ):
        raise ValueError("unsafe revision")
    if source == "huggingface" and not _COMMIT.fullmatch(revision):
        raise ValueError("HF revision must be a full 40-character commit SHA")
    if source == "modelscope" and not _COMMIT.fullmatch(revision):
        if not data.get("revision_verified"):
            raise ValueError("ModelScope revision must have verified immutable identity")
        if not all(file.get("sha256") for file in data.get("files", [])):
            raise ValueError("non-commit revision requires verified file sha256 identities")
    repo = data.get("repo_id")
    if not isinstance(repo, str) or not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        raise ValueError("invalid repo_id")
    files = data.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("plan requires a nonempty exact files list")
    paths = set()
    for file in files:
        path = _relative_path(file.get("path"))
        if path in paths:
            raise ValueError("duplicate file path")
        paths.add(path)
        _integer(file.get("size"), "size")
        digest = file.get("sha256")
        if digest is not None and not _HASH.fullmatch(str(digest)):
            raise ValueError("invalid sha256")
        if source == "modelscope":
            parsed = urlsplit(str(file.get("url", "")))
            if parsed.scheme != "https" or not parsed.netloc or parsed.username:
                raise ValueError("ModelScope file url requires credential-free HTTPS")
            if revision not in str(file.get("url")) and not digest:
                raise ValueError("file url must pin revision or have verified sha256 identity")
    data["data_root"] = str(Path(data.get("data_root", "")).expanduser().absolute())
    if not plan.get("data_root"):
        raise ValueError("data_root is required")
    data["budget_bytes"] = _integer(data.get("budget_bytes", _DEFAULT_BUDGET), "budget_bytes")
    default_dataset = 10 * GiB if dataset.lower() == "robomind" else data["budget_bytes"]
    data["dataset_budget_bytes"] = _integer(
        data.get("dataset_budget_bytes", default_dataset), "dataset_budget_bytes"
    )
    data["minimum_free_bytes"] = _integer(
        data.get("minimum_free_bytes", _DEFAULT_RESERVE), "minimum_free_bytes"
    )
    return data


def _directory(plan: dict[str, Any]) -> Path:
    return (
        Path(plan["data_root"])
        / "downloads"
        / str(plan["dataset_id"])
        / str(plan["source"])
        / str(plan["revision"])
    )


def _ledger_path(plan: dict[str, Any]) -> Path:
    return Path(plan["data_root"]) / "manifests" / "download-ledger.json"


def _identity(plan: dict[str, Any], file: dict[str, Any]) -> str:
    value = [plan[key] for key in ("dataset_id", "source", "repo_id", "revision")]
    return hashlib.sha256(json.dumps([*value, file["path"]]).encode()).hexdigest()


def _read_ledger(plan: dict[str, Any]) -> dict[str, Any]:
    path = _ledger_path(plan)
    if path.is_symlink():
        raise ValueError("unsafe ledger path")
    if not path.exists():
        return {"format_version": 1, "network_bytes": 0, "dataset_network_bytes": {}, "files": {}}
    try:
        ledger = json.loads(path.read_text())
        _integer(ledger["network_bytes"], "network_bytes")
        for size in ledger["dataset_network_bytes"].values():
            _integer(size, "dataset_network_bytes")
        if not isinstance(ledger["files"], dict):
            raise ValueError("files")
        return dict(ledger)
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("invalid download ledger; preserve it for inspection") from exc


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if path.is_symlink() or temporary.is_symlink():
        raise ValueError("unsafe atomic manifest path")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _free_bytes(path: Path) -> int:
    while not path.exists():
        path = path.parent
    return int(shutil.disk_usage(path).free)


def _safe_target(path: Path, root: Path) -> None:
    for candidate in [path, *path.parents]:
        if candidate.is_symlink():
            raise ValueError("unsafe symlink in download path")
        if candidate == root:
            return


def _reusable(plan: dict[str, Any], file: dict[str, Any], ledger: dict[str, Any]) -> bool:
    entry = ledger["files"].get(_identity(plan, file), {})
    path = _directory(plan) / file["path"]
    _safe_target(path, Path(plan["data_root"]))
    return bool(
        entry.get("state") == "VERIFIED"
        and path.is_file()
        and entry.get("size") == file["size"]
        and path.stat().st_size == file["size"]
        and entry.get("sha256") == hash_file(path)
        and (not file.get("sha256") or entry["sha256"] == file["sha256"].lower())
    )


def _is_archive(path: str) -> bool:
    return bool(re.search(r"\.(?:7z|tar(?:\.gz)?|tgz|zip)(?:\.(?:part)?[a-z0-9]+)?$", path))


def _network_reason(plan: dict[str, Any]) -> str | None:
    """未验证大陆镜像时关闭入口，不退回系统隧道或上游文件站。"""
    policy = plan.get("network")
    if policy is None:
        # 旧SDK路径仅供明确的synthetic_fixture仓库及被mock的离线单元测试。
        if plan.get("sample_provenance") == "synthetic_fixture" and str(
            plan.get("repo_id", "")
        ).startswith("synthetic_fixture/"):
            return None
        return "Real downloads require an explicit physical-interface direct policy"
    if not isinstance(policy, dict) or policy.get("mode") != "direct":
        return "Only explicitly configured physical-interface direct downloads are allowed"
    if policy.get("blocked_reason"):
        return str(policy["blocked_reason"])
    if not policy.get("allowed_hosts"):
        return "No verified mainland download hosts configured"
    if plan["source"] == "huggingface":
        endpoint = urlsplit(str(policy.get("hf_endpoint") or ""))
        if (
            endpoint.scheme != "https"
            or endpoint.hostname not in policy["allowed_hosts"]
            or endpoint.username
            or endpoint.port not in (None, 443)
            or endpoint.path not in ("", "/")
            or endpoint.query
            or endpoint.fragment
        ):
            return "No verified credential-free HTTPS mirror endpoint configured"
        if not all(file.get("sha256") for file in plan["files"]):
            return "Mirror downloads require pinned upstream SHA256 for every file"
    return None


def plan_budget(plan: dict[str, Any], free_bytes: int | None = None) -> dict[str, Any]:
    """先检查版本账本、网络上限和保守存储门禁；此函数不下载。"""
    data = _validate(plan)
    ledger = _read_ledger(data)
    reusable: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for file in data["files"]:
        (reusable if _reusable(data, file, ledger) else pending).append(dict(file))
    network = 0
    for file in pending:
        target = _directory(data) / file["path"]
        partial, sidecar = _partial_paths(target)
        offset = 0
        if partial.exists() and sidecar.exists():
            _safe_target(partial, Path(data["data_root"]))
            _safe_target(sidecar, Path(data["data_root"]))
            if json.loads(sidecar.read_text()) != _partial_identity(data, file):
                raise ValueError("partial revision mismatch")
            offset = partial.stat().st_size
            if offset > file["size"]:
                raise ValueError("partial SIZE mismatch")
        file["remaining_network_bytes"] = file["size"] - offset
        network += file["remaining_network_bytes"]
    expansion = data.get("extraction_estimated_bytes")
    estimation = data.get("estimation", "LISTING" if expansion is not None else "ESTIMATED")
    if estimation not in ("LISTING", "ESTIMATED"):
        raise ValueError("estimation must be LISTING or ESTIMATED")
    if expansion is None:
        expansion = 3 * sum(file["size"] for file in data["files"] if _is_archive(file["path"]))
    expansion = _integer(expansion, "extraction_estimated_bytes")
    available = _free_bytes(Path(data["data_root"])) if free_bytes is None else free_bytes
    needed = network + expansion + data["minimum_free_bytes"]
    prior_total = ledger["network_bytes"]
    prior_dataset = ledger["dataset_network_bytes"].get(data["dataset_id"], 0)
    status = "READY"
    if prior_total + network > data["budget_bytes"]:
        status = "BLOCKED_BUDGET"
    elif prior_dataset + network > data["dataset_budget_bytes"]:
        status = "BLOCKED_BUDGET"
    elif available < needed:
        status = "BLOCKED_STORAGE"
    network_reason = _network_reason(data)
    if status == "READY" and network_reason:
        status = "BLOCKED_NETWORK"
    return {
        "status": status,
        "network_reason": network_reason,
        "pending": pending,
        "reusable": reusable,
        "network_bytes": network,
        "known_network_bytes": network,
        "previous_network_bytes": prior_total,
        "extraction_estimated_bytes": expansion,
        "estimation": estimation,
        "storage_required_bytes": needed,
        "free_bytes": available,
        "remaining_free_bytes": available - network - expansion,
        "minimum_free_bytes": data["minimum_free_bytes"],
        "archive_dependency_groups": data.get("archive_dependency_groups", []),
        "download_directory": str(_directory(data)),
    }


class _TransferState:
    """锁内持久化实际下载量，失败与重传也消耗预算。"""

    def __init__(self, plan: dict[str, Any]) -> None:
        self.plan = plan
        self.ledger = _read_ledger(plan)
        self.lock = threading.RLock()
        self.start_bytes = self.ledger["network_bytes"]
        self.reservations: dict[str, int] = {}
        self.cancelled = threading.Event()

    def check_cancelled(self) -> None:
        if self.cancelled.is_set():
            raise RuntimeError("CANCELLED: transfer interrupted; partial files retained")

    def cancel(self) -> None:
        self.cancelled.set()
        with self.lock:
            self.ledger["download_status"] = "INTERRUPTED"
            self.save()

    def save(self) -> None:
        _atomic_json(_ledger_path(self.plan), self.ledger)

    def reserve(self, file: dict[str, Any], amount: int) -> None:
        with self.lock:
            totals = self.ledger["dataset_network_bytes"]
            reserved = sum(self.reservations.values())
            if (
                self.ledger["network_bytes"] + reserved + amount > self.plan["budget_bytes"]
                or totals.get(self.plan["dataset_id"], 0) + reserved + amount
                > self.plan["dataset_budget_bytes"]
            ):
                raise RuntimeError("BLOCKED_BUDGET: retry network allowance exhausted")
            key = _identity(self.plan, file)
            self.reservations[key] = self.reservations.get(key, 0) + amount

    def record(self, file: dict[str, Any], amount: int) -> None:
        with self.lock:
            key = _identity(self.plan, file)
            self.reservations[key] = max(0, self.reservations.get(key, 0) - amount)
            self.ledger["network_bytes"] += amount
            totals = self.ledger["dataset_network_bytes"]
            key = self.plan["dataset_id"]
            totals[key] = totals.get(key, 0) + amount
            self.save()
            if (
                self.ledger["network_bytes"] > self.plan["budget_bytes"]
                or totals[key] > self.plan["dataset_budget_bytes"]
            ):
                raise RuntimeError("BLOCKED_BUDGET: actual transfer bytes exhausted allowance")

    def ensure_storage(self, incoming: int = 0) -> None:
        if _free_bytes(Path(self.plan["data_root"])) < self.plan["minimum_free_bytes"] + incoming:
            raise RuntimeError("BLOCKED_STORAGE: ongoing disk reserve reached")

    def update(self, file: dict[str, Any], **values: Any) -> None:
        with self.lock:
            key = _identity(self.plan, file)
            entry = self.ledger["files"].setdefault(
                key,
                {
                    "dataset_id": self.plan["dataset_id"],
                    "source": self.plan["source"],
                    "repo_id": self.plan["repo_id"],
                    "revision": self.plan["revision"],
                    "path": file["path"],
                    "size": file["size"],
                },
            )
            entry.update(values)
            self.save()


def _partial_paths(target: Path) -> tuple[Path, Path]:
    return target.with_name(target.name + ".part"), target.with_name(target.name + ".part.json")


def _partial_identity(plan: dict[str, Any], file: dict[str, Any]) -> dict[str, Any]:
    return {"identity": _identity(plan, file), "size": file["size"], "sha256": file.get("sha256")}


def _prepare_partial(plan: dict[str, Any], file: dict[str, Any], target: Path) -> Path:
    partial, sidecar = _partial_paths(target)
    for path in (partial, sidecar):
        _safe_target(path, Path(plan["data_root"]))
    binding = _partial_identity(plan, file)
    if partial.exists():
        if not sidecar.exists() or json.loads(sidecar.read_text()) != binding:
            raise ValueError("partial revision mismatch; preserve file for inspection")
        if partial.stat().st_size > file["size"]:
            raise ValueError("partial immutable SIZE mismatch")
    _atomic_json(sidecar, binding)
    return partial


def _http_download(state: _TransferState, file: dict[str, Any], target: Path) -> None:
    import httpx

    plan = state.plan
    state.check_cancelled()
    partial = _prepare_partial(plan, file, target)
    offset = partial.stat().st_size if partial.exists() else 0
    if offset == file["size"] and partial.exists():
        partial.replace(target)
        return
    headers = {"Accept-Encoding": "identity"}
    url = str(file.get("url", ""))
    policy = plan.get("network")
    if plan["source"] == "huggingface":
        from huggingface_hub import get_token, hf_hub_url

        url = hf_hub_url(
            plan["repo_id"],
            file["path"],
            repo_type="dataset",
            revision=plan["revision"],
            endpoint=policy["hf_endpoint"] if policy else None,
        )
        # 官方HF凭证不发给第三方镜像；公开数据镜像无需凭证。
        token = get_token() if urlsplit(url).hostname == "huggingface.co" else None
        if token:
            headers["Authorization"] = "Bearer " + token
    if offset:
        headers["Range"] = f"bytes={offset}-"

    def secure_request(request: httpx.Request) -> None:
        state.check_cancelled()
        if request.url.scheme != "https":
            raise RuntimeError("TLS: redirect to unencrypted transport rejected")
        if policy:
            from cloud_edge_robot_arm.datasets.external.network import require_allowed_host

            require_allowed_host(str(request.url), policy)
        if request.url.host != urlsplit(str(url)).hostname:
            request.headers.pop("Authorization", None)

    options: dict[str, Any] = {}
    if policy:
        from cloud_edge_robot_arm.datasets.external.network import create_direct_transport

        options = {"transport": create_direct_transport(policy), "trust_env": False}
    with httpx.Client(
        timeout=httpx.Timeout(15, connect=15),
        follow_redirects=True,
        event_hooks={"request": [secure_request]},
        **options,
    ) as client:
        with client.stream("GET", url, headers=headers) as response:
            state.check_cancelled()
            response.raise_for_status()
            if response.headers.get("content-encoding", "identity") != "identity":
                raise RuntimeError("ENCODING: unexpected transformed file response")
            if response.status_code == 206:
                wanted = f"bytes {offset}-{file['size'] - 1}/{file['size']}"
                if response.headers.get("content-range") != wanted:
                    raise RuntimeError("SIZE: immutable Content-Range mismatch")
                mode = "ab"
            elif response.status_code == 200:
                if offset:
                    state.reserve(file, offset)
                offset, mode = 0, "wb"
            else:
                raise RuntimeError("NETWORK: unexpected HTTP status")
            state.ensure_storage()
            with partial.open(mode) as stream:
                for chunk in response.iter_bytes():
                    state.record(file, len(chunk))
                    state.check_cancelled()
                    state.ensure_storage(len(chunk))
                    if stream.tell() + len(chunk) > file["size"]:
                        raise RuntimeError("SIZE: response exceeded immutable file size")
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
    state.check_cancelled()
    if partial.stat().st_size != file["size"]:
        raise RuntimeError("SIZE: incomplete response")
    partial.replace(target)


def _hf_download(state: _TransferState, file: dict[str, Any], target: Path) -> None:
    from huggingface_hub import hf_hub_download
    from huggingface_hub.utils import tqdm

    plan = state.plan
    state.check_cancelled()
    partial = _prepare_partial(plan, file, target)
    if partial.exists():
        _http_download(state, file, target)
        return
    counted = 0

    class BudgetProgress(tqdm):
        """SDK 进度中保留临时文件硬链接，避免复制大型缓存。"""

        def update(self, n: float = 1) -> bool | None:
            nonlocal counted
            if n > 0:
                if not partial.exists():
                    metadata = _directory(plan) / ".cache" / "huggingface" / "download"
                    folder = metadata / PurePosixPath(file["path"]).parent
                    candidates = list(folder.glob(target.name + ".*.incomplete"))
                    if len(candidates) == 1 and not candidates[0].is_symlink():
                        os.link(candidates[0], partial)
                state.record(file, int(n))
                counted += int(n)
                state.ensure_storage()
            state.check_cancelled()
            result = super().update(n)
            return bool(result) if result is not None else None

    output = hf_hub_download(
        repo_id=plan["repo_id"],
        filename=file["path"],
        repo_type="dataset",
        revision=plan["revision"],
        local_dir=_directory(plan),
        etag_timeout=15,
        tqdm_class=BudgetProgress,
        force_download=target.exists(),
    )
    if Path(output) != target:
        raise RuntimeError("PATH: SDK output left fixed local directory")
    if counted == 0 and target.exists():
        state.record(file, target.stat().st_size)
    state.ensure_storage()
    state.check_cancelled()


def _failure_code(exc: Exception) -> str:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (401, 403):
        return f"BLOCKED_AUTH: source returned HTTP {status}; authorized access required"
    if isinstance(exc, RuntimeError) and re.match(
        r"(?:BLOCKED_STORAGE|BLOCKED_BUDGET|BLOCKED_AUTH|BLOCKED_NETWORK|SHA256|SIZE|PATH|ENCODING|NETWORK|TLS|CANCELLED):",
        str(exc),
    ):
        return str(exc)
    # 不传播原异常中的 URL、HTTP 头、查询字符串或凭证。
    return "NETWORK: " + type(exc).__name__


def _hash_download(state: _TransferState, path: Path) -> str:
    """取消下载后的摘要验证也必须逐块响应中断。"""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            state.check_cancelled()
            chunk = stream.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def _download_one(state: _TransferState, file: dict[str, Any], retries: int) -> dict[str, Any]:
    target = _directory(state.plan) / file["path"]
    _safe_target(target, Path(state.plan["data_root"]))
    target.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, retries + 1):
        state.check_cancelled()
        partial, sidecar = _partial_paths(target)
        offset = partial.stat().st_size if partial.exists() else 0
        reserved = file["size"] - offset
        state.reserve(file, reserved)
        state.update(file, state="DOWNLOADING", attempt=attempt, local_path=str(target))
        try:
            state.ensure_storage()
            if state.plan["source"] == "huggingface":
                if (
                    file["size"] >= 64 * 1024**2
                    or state.plan.get("transport") == "hf_sdk_metadata_http_range"
                    or state.plan.get("network")
                ):
                    transport = (
                        "hf_mirror_direct_http_range"
                        if state.plan.get("network")
                        else "hf_sdk_metadata_http_range"
                    )
                    _http_download(state, file, target)
                else:
                    transport = "hf_sdk"
                    _hf_download(state, file, target)
            else:
                transport = "modelscope_http_range"
                _http_download(state, file, target)
            if target.stat().st_size != file["size"]:
                raise RuntimeError("SIZE: immutable downloaded size mismatch")
            digest = _hash_download(state, target)
            if file.get("sha256") and digest != file["sha256"].lower():
                raise RuntimeError("SHA256: upstream digest mismatch")
            verification = (
                "UPSTREAM_SHA256_VERIFIED" if file.get("sha256") else "LOCAL_SHA256_RECORDED"
            )
            state.update(
                file,
                state="VERIFIED",
                sha256=digest,
                verification=verification,
                transport=transport,
                endpoint=(state.plan.get("network") or {}).get("hf_endpoint"),
                network_mode=(state.plan.get("network") or {}).get("mode", "system"),
                interface=(state.plan.get("network") or {}).get("interface"),
            )
            partial.unlink(missing_ok=True)
            sidecar.unlink(missing_ok=True)
            return {
                **file,
                "local_path": str(target),
                "sha256": digest,
                "verification": verification,
                "transport": transport,
            }
        except Exception as exc:
            code = _failure_code(exc)
            entry_state = "CANCELLED" if code.startswith("CANCELLED:") else "FAILED"
            state.update(file, state=entry_state, error=code)
            if attempt == retries or code.startswith(
                ("BLOCKED_", "SHA256:", "SIZE:", "PATH:", "CANCELLED:")
            ):
                raise RuntimeError(code) from None
            if state.cancelled.wait(min(2 ** (attempt - 1), 8)):
                state.update(file, state="CANCELLED", error="CANCELLED: retry interrupted")
                state.check_cancelled()
        finally:
            with state.lock:
                state.reservations.pop(_identity(state.plan, file), None)
    raise RuntimeError("NETWORK: retries exhausted")


def _download_plan_locked(
    plan: dict[str, Any],
    max_workers: int,
    retries: int,
) -> dict[str, Any]:
    if max_workers < 1 or retries < 1:
        raise ValueError("max_workers and retries must be positive")
    data = _validate(plan)
    budget = plan_budget(data)
    if budget["status"] != "READY":
        raise RuntimeError(budget["status"] + ": plan gate rejected transfer")
    state = _TransferState(data)
    state.ledger["download_status"] = "DOWNLOADING"
    state.save()
    results = []
    for file in budget["reusable"]:
        entry = state.ledger["files"][_identity(data, file)]
        results.append(
            {
                **file,
                "local_path": str(_directory(data) / file["path"]),
                "sha256": entry["sha256"],
                "verification": entry["verification"],
                "reused": True,
            }
        )
    failures = []
    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures = []
    try:
        futures = [
            executor.submit(_download_one, state, file, retries) for file in budget["pending"]
        ]
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                failures.append(_failure_code(exc))
    except BaseException:
        # 必须先发出取消信号，再等线程退出；不能先进入 context manager 的等待。
        state.cancel()
        for future in futures:
            future.cancel()
        raise
    finally:
        executor.shutdown(wait=True, cancel_futures=state.cancelled.is_set())
    if failures:
        state.ledger["download_status"] = (
            "BLOCKED_AUTH"
            if any(code.startswith("BLOCKED_AUTH:") for code in failures)
            else "FAILED"
        )
        state.save()
        raise RuntimeError(failures[0]) from None
    state.ledger["download_status"] = "COMPLETE"
    state.save()
    results.sort(key=lambda file: file["path"])
    return {
        "status": "COMPLETE",
        "files": results,
        "network_bytes": state.ledger["network_bytes"] - state.start_bytes,
        "total_network_bytes": state.ledger["network_bytes"],
        "ledger_path": str(_ledger_path(data)),
        "download_directory": str(_directory(data)),
    }


@contextmanager
def _transfer_lock(plan: dict[str, Any]) -> Iterator[None]:
    """阻止不同进程同时改写同一数据根的全局预算账本。"""
    import fcntl

    path = _ledger_path(plan).with_name(".download-ledger.lock")
    _safe_target(path, Path(plan["data_root"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "BUSY: another download process owns this data_root ledger"
            ) from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def download_plan(plan: dict[str, Any], max_workers: int = 4, retries: int = 3) -> dict[str, Any]:
    """执行已锁定清单；保留续传状态，所有重传量纳入同一账本。"""
    data = _validate(plan)
    with _transfer_lock(data):
        return _download_plan_locked(data, max_workers, retries)
