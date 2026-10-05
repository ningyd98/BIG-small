"""仅使用 synthetic_fixture 检查版本、预算和可恢复传输。"""

from __future__ import annotations

import hashlib
import importlib
import json
import threading
import time
from pathlib import Path

import httpx
import pytest


def transfer():
    try:
        return importlib.import_module("cloud_edge_robot_arm.datasets.external.transfer")
    except ModuleNotFoundError:
        pytest.fail("固定版本的外部 RGB-D 传输尚未实现")


def make_plan(tmp_path, **changes):
    plan = {
        "dataset_id": "robomind",
        "source": "huggingface",
        "repo_id": "synthetic_fixture/rgbd",
        "revision": "a" * 40,
        "files": [{"path": "trajectory.h5", "size": 6}],
        "data_root": str(tmp_path),
        "budget_bytes": 100,
        "dataset_budget_bytes": 100,
        "minimum_free_bytes": 10,
        "extraction_estimated_bytes": 0,
        "sample_provenance": "synthetic_fixture",
    }
    return {**plan, **changes}


def fake_hf(monkeypatch, body=b"rgbd01", *, fail_first=False):
    import huggingface_hub

    calls = []

    def download(repo_id, filename, **kwargs):
        calls.append(kwargs)
        assert repo_id == "synthetic_fixture/rgbd"
        assert kwargs["revision"] == "a" * 40
        assert kwargs["repo_type"] == "dataset"
        assert "local_dir" in kwargs and "cache_dir" not in kwargs
        if fail_first and len(calls) == 1:
            raise httpx.ReadTimeout("Authorization: SECRET_TOKEN")
        path = Path(kwargs["local_dir"]) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return str(path)

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    return calls


def test_plan_blocks_download_budget_before_network(tmp_path, monkeypatch):
    mod = transfer()
    calls = fake_hf(monkeypatch)
    plan = make_plan(tmp_path, budget_bytes=5)
    assert mod.plan_budget(plan, free_bytes=100)["status"] == "BLOCKED_BUDGET"
    with pytest.raises(RuntimeError, match="BLOCKED_BUDGET"):
        mod.download_plan(plan)
    assert calls == []


def test_unknown_archive_expansion_is_marked_estimated_and_gated(tmp_path):
    mod = transfer()
    plan = make_plan(
        tmp_path,
        files=[{"path": "scenes.7z.001", "size": 6}],
        extraction_estimated_bytes=None,
    )
    result = mod.plan_budget(plan, free_bytes=33)
    assert result["extraction_estimated_bytes"] == 18
    assert result["estimation"] == "ESTIMATED"
    assert result["status"] == "BLOCKED_STORAGE"
    assert result["network_bytes"] == 6


@pytest.mark.parametrize("revision", ["main", "latest", "abcdef0", "../escape"])
def test_hf_requires_full_commit_sha(tmp_path, revision):
    with pytest.raises(ValueError, match="revision"):
        transfer().plan_budget(make_plan(tmp_path, revision=revision), free_bytes=100)


@pytest.mark.parametrize("path", ["../outside", "/absolute", "C:/escape", "x\\y", ".cache/x"])
def test_plan_rejects_unsafe_download_paths(tmp_path, path):
    with pytest.raises(ValueError, match="path"):
        transfer().plan_budget(
            make_plan(tmp_path, files=[{"path": path, "size": 6}]), free_bytes=100
        )


def test_hash_file_streams_and_matches_known_digest(tmp_path):
    path = tmp_path / "synthetic_fixture"
    path.write_bytes(b"abc")
    assert transfer().hash_file(path) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_hf_retries_then_reuses_only_version_and_hash_bound_file(tmp_path, monkeypatch):
    mod = transfer()
    calls = fake_hf(monkeypatch, fail_first=True)
    plan = make_plan(tmp_path)
    first = mod.download_plan(plan, retries=2)
    assert first["status"] == "COMPLETE"
    assert len(calls) == 2
    assert first["files"][0]["verification"] == "LOCAL_SHA256_RECORDED"
    assert mod.plan_budget(plan, free_bytes=100)["network_bytes"] == 0
    mod.download_plan(plan)
    assert len(calls) == 2
    Path(first["files"][0]["local_path"]).write_bytes(b"broken")
    assert mod.plan_budget(plan, free_bytes=100)["network_bytes"] == 6
    changed = make_plan(tmp_path, revision="b" * 40)
    assert mod.plan_budget(changed, free_bytes=100)["reusable"] == []


def test_known_upstream_digest_failure_never_becomes_reusable(tmp_path, monkeypatch):
    mod = transfer()
    fake_hf(monkeypatch)
    plan = make_plan(tmp_path, files=[{"path": "trajectory.h5", "size": 6, "sha256": "0" * 64}])
    with pytest.raises(RuntimeError, match="SHA256"):
        mod.download_plan(plan, retries=1)
    assert mod.plan_budget(plan, free_bytes=100)["reusable"] == []


def test_immutable_size_is_checked_after_download(tmp_path, monkeypatch):
    mod = transfer()
    fake_hf(monkeypatch, b"wrong size")
    with pytest.raises(RuntimeError, match="SIZE"):
        mod.download_plan(make_plan(tmp_path), retries=1)


def test_failed_download_has_finite_retries_and_sanitized_error(tmp_path, monkeypatch):
    import huggingface_hub

    mod = transfer()
    calls = []

    def failing(**kwargs):
        calls.append(kwargs)
        raise httpx.ReadError("https://user:SECRET_TOKEN@host/?token=SECRET_TOKEN")

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", failing)
    with pytest.raises(RuntimeError) as exc:
        mod.download_plan(make_plan(tmp_path), retries=2)
    assert len(calls) == 2
    assert "SECRET_TOKEN" not in str(exc.value)
    ledger = (tmp_path / "manifests" / "download-ledger.json").read_text()
    assert "SECRET_TOKEN" not in ledger


class InterruptedBody(httpx.SyncByteStream):
    def __iter__(self):
        yield b"rgb"
        raise httpx.ReadError("synthetic_fixture interruption")


def test_modelscope_partial_resume_survives_interruption_and_binds_revision(tmp_path, monkeypatch):
    mod = transfer()
    requests = []

    def serve(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, stream=InterruptedBody())
        assert request.headers["range"] == "bytes=3-"
        return httpx.Response(206, content=b"d01", headers={"content-range": "bytes 3-5/6"})

    original_client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: original_client(transport=httpx.MockTransport(serve), **kw)
    )
    plan = make_plan(
        tmp_path,
        source="modelscope",
        files=[
            {
                "path": "trajectory.h5",
                "size": 6,
                "sha256": hashlib.sha256(b"rgbd01").hexdigest(),
                "url": "https://modelscope.cn/synthetic_fixture?Revision=" + "a" * 40,
            }
        ],
    )
    with pytest.raises(RuntimeError):
        mod.download_plan(plan, retries=1)
    result = mod.download_plan(plan, retries=1)
    assert result["status"] == "COMPLETE"
    assert result["files"][0]["verification"] == "UPSTREAM_SHA256_VERIFIED"
    assert Path(result["files"][0]["local_path"]).read_bytes() == b"rgbd01"
    assert len(requests) == 2


def test_modelscope_ignoring_range_restarts_without_appending(tmp_path, monkeypatch):
    mod = transfer()
    requests = []

    def serve(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, stream=InterruptedBody())
        return httpx.Response(200, content=b"rgbd01")

    original_client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: original_client(transport=httpx.MockTransport(serve), **kw)
    )
    plan = make_plan(
        tmp_path,
        source="modelscope",
        files=[
            {
                "path": "trajectory.h5",
                "size": 6,
                "url": "https://modelscope.cn/synthetic_fixture?Revision=" + "a" * 40,
            }
        ],
    )
    result = mod.download_plan(plan, retries=2)
    assert Path(result["files"][0]["local_path"]).read_bytes() == b"rgbd01"
    ledger = json.loads((tmp_path / "manifests" / "download-ledger.json").read_text())
    assert ledger["network_bytes"] == 9


def test_actual_retry_network_bytes_cannot_exceed_total_budget(tmp_path, monkeypatch):
    mod = transfer()
    original_client = httpx.Client

    def serve(_request):
        return httpx.Response(200, stream=InterruptedBody())

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: original_client(transport=httpx.MockTransport(serve), **kw)
    )
    plan = make_plan(
        tmp_path,
        source="modelscope",
        budget_bytes=6,
        files=[
            {
                "path": "trajectory.h5",
                "size": 6,
                "url": "https://modelscope.cn/synthetic_fixture?Revision=" + "a" * 40,
            }
        ],
    )
    with pytest.raises(RuntimeError):
        mod.download_plan(plan, retries=3)
    ledger = json.loads((tmp_path / "manifests" / "download-ledger.json").read_text())
    assert ledger["network_bytes"] <= 6


def test_ongoing_disk_reserve_blocks_http_body_write(tmp_path, monkeypatch):
    mod = transfer()
    original_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: original_client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"rgbd01")), **kw
        ),
    )
    free_values = iter([100, 100, 100, 9])
    monkeypatch.setattr(mod, "_free_bytes", lambda _path: next(free_values, 9))
    plan = make_plan(
        tmp_path,
        source="modelscope",
        files=[
            {
                "path": "trajectory.h5",
                "size": 6,
                "url": "https://modelscope.cn/synthetic_fixture?Revision=" + "a" * 40,
            }
        ],
    )
    with pytest.raises(RuntimeError, match="BLOCKED_STORAGE"):
        mod.download_plan(plan, retries=1)


def test_hf_persistent_transport_pins_revision_and_records_actual_bytes(tmp_path, monkeypatch):
    mod = transfer()
    original_client = httpx.Client
    requests = []

    def serve(request):
        requests.append(request)
        assert "/resolve/" + "a" * 40 + "/trajectory.h5" in str(request.url)
        return httpx.Response(200, content=b"rgbd01")

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: original_client(transport=httpx.MockTransport(serve), **kw)
    )
    plan = make_plan(tmp_path, transport="hf_sdk_metadata_http_range")
    result = mod.download_plan(plan, retries=1)
    assert result["files"][0]["transport"] == "hf_sdk_metadata_http_range"
    assert result["network_bytes"] == 6
    assert len(requests) == 1


def test_resume_budget_counts_remaining_partial_bytes_not_full_file(tmp_path, monkeypatch):
    mod = transfer()
    original_client = httpx.Client
    requests = []

    def serve(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, stream=InterruptedBody())
        return httpx.Response(206, content=b"d01", headers={"content-range": "bytes 3-5/6"})

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: original_client(transport=httpx.MockTransport(serve), **kw)
    )
    plan = make_plan(
        tmp_path,
        source="modelscope",
        budget_bytes=6,
        files=[
            {
                "path": "trajectory.h5",
                "size": 6,
                "url": "https://modelscope.cn/synthetic_fixture?Revision=" + "a" * 40,
            }
        ],
    )
    with pytest.raises(RuntimeError):
        mod.download_plan(plan, retries=1)
    assert mod.plan_budget(plan, free_bytes=100)["network_bytes"] == 3
    assert mod.download_plan(plan, retries=1)["total_network_bytes"] == 6


def test_caller_supplied_estimate_does_not_claim_archive_listing(tmp_path):
    result = transfer().plan_budget(
        make_plan(tmp_path, estimation="ESTIMATED", extraction_estimated_bytes=18), free_bytes=100
    )
    assert result["estimation"] == "ESTIMATED"


def test_modelscope_verified_revision_cannot_escape_download_directory(tmp_path):
    with pytest.raises(ValueError, match="revision"):
        transfer().plan_budget(
            make_plan(
                tmp_path,
                source="modelscope",
                revision="..",
                revision_verified=True,
                files=[
                    {
                        "path": "a.h5",
                        "size": 6,
                        "sha256": "0" * 64,
                        "url": "https://modelscope.cn/synthetic_fixture",
                    }
                ],
            ),
            free_bytes=100,
        )


def test_hf_persistent_auth_is_removed_before_cross_domain_redirect(tmp_path, monkeypatch):
    import huggingface_hub

    mod = transfer()
    original_client = httpx.Client
    observed = []
    monkeypatch.setattr(huggingface_hub, "get_token", lambda: "SECRET_TOKEN")

    def serve(request):
        observed.append((request.url.host, request.headers.get("authorization")))
        if request.url.host == "huggingface.co":
            return httpx.Response(302, headers={"location": "https://cdn.example.test/file"})
        return httpx.Response(200, content=b"rgbd01")

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: original_client(transport=httpx.MockTransport(serve), **kw)
    )
    mod.download_plan(make_plan(tmp_path, transport="hf_sdk_metadata_http_range"), retries=1)
    assert observed == [("huggingface.co", "Bearer SECRET_TOKEN"), ("cdn.example.test", None)]


def test_concurrent_process_cannot_overwrite_shared_budget_ledger(tmp_path, monkeypatch):
    import fcntl

    mod = transfer()
    fake_hf(monkeypatch)
    directory = tmp_path / "manifests"
    directory.mkdir()
    with (directory / ".download-ledger.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="BUSY"):
            mod.download_plan(make_plan(tmp_path))


def test_https_download_refuses_redirect_to_plain_http(tmp_path, monkeypatch):
    mod = transfer()
    original_client = httpx.Client

    def serve(request):
        if request.url.host == "huggingface.co":
            return httpx.Response(302, headers={"location": "http://cdn.example.test/file"})
        return httpx.Response(200, content=b"rgbd01")

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: original_client(transport=httpx.MockTransport(serve), **kw)
    )
    with pytest.raises(RuntimeError, match="TLS"):
        mod.download_plan(make_plan(tmp_path, transport="hf_sdk_metadata_http_range"), retries=1)


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize("transport", ["hf_sdk", "hf_sdk_metadata_http_range"])
def test_unauthorized_download_is_blocked_auth_without_retry(
    tmp_path, monkeypatch, status, transport
):
    import huggingface_hub

    mod = transfer()
    requests = []
    original_client = httpx.Client

    def serve(request):
        requests.append(request)
        return httpx.Response(status, request=request)

    def failing_sdk(**_kwargs):
        request = httpx.Request("GET", "https://huggingface.co/?token=SECRET_TOKEN")
        serve(request).raise_for_status()

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", failing_sdk)
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: original_client(transport=httpx.MockTransport(serve), **kw)
    )
    with pytest.raises(RuntimeError, match="BLOCKED_AUTH") as exc:
        mod.download_plan(make_plan(tmp_path, transport=transport), retries=3)
    assert len(requests) == 1
    assert "SECRET_TOKEN" not in str(exc.value)
    ledger_text = (tmp_path / "manifests/download-ledger.json").read_text()
    assert "BLOCKED_AUTH" in ledger_text and "SECRET_TOKEN" not in ledger_text


def test_keyboard_interrupt_cancels_active_http_and_queued_files_preserving_partial(
    tmp_path,
    monkeypatch,
):
    mod = transfer()
    started = threading.Event()
    requests = []
    original_client = httpx.Client

    class SlowBody(httpx.SyncByteStream):
        def __iter__(self):
            yield b"r"
            started.set()
            for _ in range(20):
                time.sleep(0.005)
                yield b"x"

    def serve(request):
        requests.append(request)
        return httpx.Response(200, stream=SlowBody())

    def interrupted_iterator(_futures):
        assert started.wait(2)
        raise KeyboardInterrupt

    monkeypatch.setattr(mod, "as_completed", interrupted_iterator)
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: original_client(transport=httpx.MockTransport(serve), **kw)
    )
    plan = make_plan(
        tmp_path,
        transport="hf_sdk_metadata_http_range",
        files=[{"path": "trajectory.h5", "size": 21}, {"path": "queued.h5", "size": 21}],
    )
    with pytest.raises(KeyboardInterrupt):
        mod.download_plan(plan, max_workers=1)
    partials = list(tmp_path.rglob("trajectory.h5.part"))
    assert len(partials) == 1 and partials[0].read_bytes() == b"r"
    assert len(requests) == 1
    ledger = json.loads((tmp_path / "manifests/download-ledger.json").read_text())
    assert any(entry["state"] == "CANCELLED" for entry in ledger["files"].values())


def test_keyboard_interrupt_stops_sdk_progress_without_losing_partial(tmp_path, monkeypatch):
    import huggingface_hub

    mod = transfer()
    started = threading.Event()

    def slow_sdk(filename, **kwargs):
        directory = Path(kwargs["local_dir"])
        temporary = directory / ".cache/huggingface/download" / (filename + ".fixture.incomplete")
        temporary.parent.mkdir(parents=True)
        progress = kwargs["tqdm_class"](total=21, disable=True)
        try:
            with temporary.open("wb") as stream:
                stream.write(b"r")
                stream.flush()
                progress.update(1)
                started.set()
                for _ in range(20):
                    time.sleep(0.005)
                    stream.write(b"x")
                    stream.flush()
                    progress.update(1)
            target = directory / filename
            temporary.replace(target)
            return str(target)
        finally:
            temporary.unlink(missing_ok=True)
            progress.close()

    def interrupted_iterator(_futures):
        assert started.wait(2)
        raise KeyboardInterrupt

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", slow_sdk)
    monkeypatch.setattr(mod, "as_completed", interrupted_iterator)
    with pytest.raises(KeyboardInterrupt):
        mod.download_plan(make_plan(tmp_path, files=[{"path": "trajectory.h5", "size": 21}]))
    partials = list(tmp_path.rglob("trajectory.h5.part"))
    assert len(partials) == 1 and 0 < partials[0].stat().st_size < 21
    ledger = json.loads((tmp_path / "manifests/download-ledger.json").read_text())
    assert next(iter(ledger["files"].values()))["state"] == "CANCELLED"


def test_mainland_source_block_prevents_network_without_discarding_partials(tmp_path, monkeypatch):
    mod = transfer()
    calls = fake_hf(monkeypatch)
    plan = make_plan(
        tmp_path,
        files=[
            {"path": "trajectory.h5", "size": 6, "sha256": hashlib.sha256(b"rgbd01").hexdigest()}
        ],
        network={
            "mode": "direct",
            "interface": "enp7s0",
            "dns_servers": ["223.5.5.5"],
            "allowed_hosts": [],
            "blocked_reason": "No verified mainland file mirror",
        },
    )
    report = mod.plan_budget(plan, free_bytes=100)
    assert report["status"] == "BLOCKED_NETWORK"
    assert report["network_reason"] == "No verified mainland file mirror"
    with pytest.raises(RuntimeError, match="BLOCKED_NETWORK"):
        mod.download_plan(plan, retries=1)
    assert not calls


def test_real_plan_without_direct_policy_cannot_fall_back_to_sdk(tmp_path, monkeypatch):
    mod = transfer()
    calls = fake_hf(monkeypatch)
    plan = make_plan(tmp_path, sample_provenance=None)
    assert mod.plan_budget(plan, free_bytes=100)["status"] == "BLOCKED_NETWORK"
    with pytest.raises(RuntimeError, match="BLOCKED_NETWORK"):
        mod.download_plan(plan, retries=1)
    assert not calls


def test_direct_mirror_range_keeps_identity_and_never_sends_hf_token(tmp_path, monkeypatch):
    import huggingface_hub

    from cloud_edge_robot_arm.datasets.external import network

    mod = transfer()
    original_client = httpx.Client
    observed, options = [], []

    def serve(request):
        observed.append(request)
        return httpx.Response(200, content=b"rgbd01")

    monkeypatch.setattr(network, "create_direct_transport", lambda _: httpx.MockTransport(serve))
    monkeypatch.setattr(huggingface_hub, "get_token", lambda: "SECRET_TOKEN")
    monkeypatch.setattr(
        huggingface_hub, "hf_hub_download", lambda **_: pytest.fail("SDK bypasses direct policy")
    )

    def client(**kwargs):
        options.append(kwargs.copy())
        return original_client(**kwargs)

    monkeypatch.setattr(httpx, "Client", client)
    plan = make_plan(
        tmp_path,
        files=[
            {"path": "trajectory.h5", "size": 6, "sha256": hashlib.sha256(b"rgbd01").hexdigest()}
        ],
        network={
            "mode": "direct",
            "interface": "enp7s0",
            "dns_servers": ["223.5.5.5"],
            "allowed_hosts": ["mirror.example.cn"],
            "hf_endpoint": "https://mirror.example.cn",
        },
    )
    result = mod.download_plan(plan, retries=1)
    assert observed[0].url.host == "mirror.example.cn"
    assert "/resolve/" + "a" * 40 + "/trajectory.h5" in str(observed[0].url)
    assert "authorization" not in observed[0].headers
    assert options[0]["trust_env"] is False
    assert result["files"][0]["transport"] == "hf_mirror_direct_http_range"
    ledger = json.loads((tmp_path / "manifests/download-ledger.json").read_text())
    entry = next(iter(ledger["files"].values()))
    assert entry["source"] == "huggingface"
    assert entry["revision"] == "a" * 40
    assert entry["endpoint"] == "https://mirror.example.cn"


def test_direct_mirror_refuses_overseas_redirect_before_contact(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.datasets.external import network

    mod = transfer()
    observed = []

    def serve(request):
        observed.append(request.url.host)
        return httpx.Response(302, headers={"location": "https://cas-bridge.xethub.hf.co/file"})

    monkeypatch.setattr(network, "create_direct_transport", lambda _: httpx.MockTransport(serve))
    plan = make_plan(
        tmp_path,
        files=[
            {"path": "trajectory.h5", "size": 6, "sha256": hashlib.sha256(b"rgbd01").hexdigest()}
        ],
        network={
            "mode": "direct",
            "interface": "enp7s0",
            "dns_servers": ["223.5.5.5"],
            "allowed_hosts": ["mirror.example.cn"],
            "hf_endpoint": "https://mirror.example.cn",
        },
    )
    with pytest.raises(RuntimeError, match="BLOCKED_NETWORK"):
        mod.download_plan(plan, retries=1)
    assert observed == ["mirror.example.cn"]
    ledger = json.loads((tmp_path / "manifests/download-ledger.json").read_text())
    assert ledger["network_bytes"] == 0
