"""A slow evidence scan must not prevent users from saving model profiles."""

from __future__ import annotations

import asyncio
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from cloud_edge_robot_arm.cloud.api.dashboard import router as dashboard_router
from cloud_edge_robot_arm.cloud.api.model_control import router as model_router
from cloud_edge_robot_arm.dashboard.evidence_index import EvidenceIndex
from cloud_edge_robot_arm.dashboard.service import DashboardService


@pytest.mark.parametrize(
    "endpoint",
    [
        "summary",
        "runtime",
        "evidence",
        "evidence-errors",
        "evidence/{id}",
        "evidence/{id}/download",
        "evidence/{id}/compare/{id}",
    ],
)
def test_profile_save_completes_while_evidence_scan_is_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "LOCAL_ONLY")
    monkeypatch.setenv("MODEL_CONTROL_DB", str(tmp_path / "models.db"))
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "example.json").write_text("{}")
    app = FastAPI()
    app.include_router(dashboard_router)
    app.include_router(model_router)
    service = DashboardService(artifact_root=root)
    app.state.dashboard_service = service
    started, release = threading.Event(), threading.Event()
    original = service.evidence_index._record_for

    def blocked_record(*args, **kwargs):
        started.set()
        release.wait(3)
        return original(*args, **kwargs)

    monkeypatch.setattr(service.evidence_index, "_record_for", blocked_record)
    evidence_id = hashlib.sha256(b"example.json").hexdigest()[:16]

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            watchdog = threading.Timer(2, release.set)
            watchdog.start()
            scan = asyncio.create_task(
                client.get("/api/v1/dashboard/" + endpoint.format(id=evidence_id))
            )
            try:
                assert await asyncio.to_thread(started.wait, 3)
                saved = await client.post(
                    "/api/v1/model-control/profiles",
                    json={
                        "display_name": "isolated-save-test",
                        "provider_kind": "RULE_BASED",
                        "model_name": "rule-based",
                    },
                )
                listed = await client.get("/api/v1/model-control/profiles")
                completed_during_scan = not release.is_set()
            finally:
                release.set()
                watchdog.cancel()
                scan_response = await scan
            assert scan_response.status_code == 200
            assert saved.status_code == 201
            assert listed.json()[0]["profile_id"] == saved.json()["profile_id"]
            assert completed_during_scan, "profile save/list waited for the evidence scan"

    asyncio.run(exercise())


def test_concurrent_refreshes_share_scan_and_next_refresh_sees_new_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "first.json").write_text("{}")
    index = EvidenceIndex(tmp_path)
    original = index._record_for
    entered, release = threading.Event(), threading.Event()
    calls = []

    def blocked_record(*args, **kwargs):
        calls.append(args[0].name)
        entered.set()
        release.wait(3)
        return original(*args, **kwargs)

    monkeypatch.setattr(index, "_record_for", blocked_record)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(index.refresh)
        assert entered.wait(2)
        second = pool.submit(index.refresh)
        timer = threading.Timer(0.2, release.set)
        timer.start()
        try:
            left, right = first.result(timeout=3), second.result(timeout=3)
        finally:
            release.set()
            timer.cancel()
    assert calls == ["first.json"], "concurrent refresh repeated the full scan"
    assert [r.relative_path for r in left] == [r.relative_path for r in right] == ["first.json"]
    (tmp_path / "second.json").write_text("{}")
    assert {r.relative_path for r in index.refresh()} == {"first.json", "second.json"}


def test_inflight_scan_preserves_completed_error_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "broken.json").write_text("{")
    index = EvidenceIndex(tmp_path)
    index.refresh()
    previous_errors = list(index.errors)
    entered, release = threading.Event(), threading.Event()
    original = index._record_for

    def blocked_record(*args, **kwargs):
        entered.set()
        release.wait(3)
        return original(*args, **kwargs)

    monkeypatch.setattr(index, "_record_for", blocked_record)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(index.refresh)
        try:
            assert entered.wait(2)
            assert index.errors == previous_errors
        finally:
            release.set()
            pending.result(timeout=3)
