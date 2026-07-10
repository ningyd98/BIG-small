#!/usr/bin/env python
"""Apply the audited Phase 12.4 P0 remediation patch in a checked-out worktree."""

from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    replace_once(
        "src/cloud_edge_robot_arm/edge/runtime/task_executor.py",
        ").accept_payload(payload, now=self._validation_now(payload))",
        ").accept_payload(payload, now=self._clock.now())",
    )
    replace_once(
        "src/cloud_edge_robot_arm/edge/runtime/task_executor.py",
        '''    def _validation_now(self, payload: dict[str, Any]) -> datetime:\n        raw_timestamp = payload.get("timestamp")\n        if isinstance(raw_timestamp, datetime):\n            return raw_timestamp\n        if isinstance(raw_timestamp, str):\n            try:\n                parsed = datetime.fromisoformat(raw_timestamp)\n            except ValueError:\n                return datetime.now(UTC)\n            if parsed.tzinfo is None:\n                return parsed.replace(tzinfo=UTC)\n            return parsed\n        return datetime.now(UTC)\n''',
        "",
    )

    Path("src/cloud_edge_robot_arm/dashboard/security.py").write_text(
        '''"""Dashboard transport authentication and server-side role authorization."""\n\nfrom __future__ import annotations\n\nimport hashlib\nimport hmac\nimport os\nfrom collections.abc import Mapping\nfrom enum import StrEnum\n\nfrom fastapi import HTTPException, Request, WebSocket\n\nfrom cloud_edge_robot_arm.dashboard.models import UserRole\n\n\nclass DashboardAuthMode(StrEnum):\n    LOCAL_ONLY = "LOCAL_ONLY"\n    TOKEN = "TOKEN"\n\n\ndef enforce_dashboard_access(request: Request) -> None:\n    _authenticated_request_role(request)\n\n\ndef enforce_dashboard_websocket_access(websocket: WebSocket) -> None:\n    mode = DashboardAuthMode(os.environ.get("DASHBOARD_AUTH_MODE", "LOCAL_ONLY"))\n    if mode == DashboardAuthMode.LOCAL_ONLY:\n        _enforce_loopback(websocket.client.host if websocket.client else "")\n        return\n    _token_role(websocket.headers, websocket.cookies)\n\n\ndef enforce_dashboard_role(request: Request, allowed: set[UserRole]) -> UserRole:\n    role = _authenticated_request_role(request)\n    if role not in allowed:\n        raise HTTPException(status_code=403, detail="dashboard_role_forbidden")\n    return role\n\n\ndef _authenticated_request_role(request: Request) -> UserRole:\n    mode = DashboardAuthMode(os.environ.get("DASHBOARD_AUTH_MODE", "LOCAL_ONLY"))\n    if mode == DashboardAuthMode.LOCAL_ONLY:\n        _enforce_loopback(request.client.host if request.client else "")\n        # LOCAL_ONLY is an explicitly trusted developer mode. The role header is\n        # accepted only on loopback so existing local workflows remain usable.\n        return _request_role(request)\n    return _token_role(request.headers, request.cookies)\n\n\ndef _enforce_loopback(host: str) -> None:\n    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:\n        raise HTTPException(status_code=403, detail="dashboard_local_only")\n\n\ndef _token_role(headers: Mapping[str, str], cookies: Mapping[str, str]) -> UserRole:\n    provided = _provided_token(headers, cookies)\n    configured = _configured_tokens()\n    if not configured or not provided:\n        raise HTTPException(status_code=401, detail="dashboard_token_required")\n    matches = {role for token, role in configured if _token_matches(token, provided)}\n    if not matches:\n        raise HTTPException(status_code=403, detail="dashboard_token_invalid")\n    if len(matches) != 1:\n        raise HTTPException(status_code=403, detail="dashboard_token_role_ambiguous")\n    return next(iter(matches))\n\n\ndef _configured_tokens() -> list[tuple[str, UserRole]]:\n    configured: list[tuple[str, UserRole]] = []\n    dedicated = (\n        ("DASHBOARD_VIEWER_TOKEN", UserRole.VIEWER),\n        ("DASHBOARD_OPERATOR_TOKEN", UserRole.EXPERIMENT_OPERATOR),\n        ("DASHBOARD_REVIEWER_TOKEN", UserRole.SAFETY_REVIEWER),\n    )\n    for env_name, role in dedicated:\n        value = os.environ.get(env_name, "").strip()\n        if value:\n            configured.append((value, role))\n\n    legacy = os.environ.get("DASHBOARD_TOKEN", "").strip()\n    if legacy:\n        raw_role = os.environ.get("DASHBOARD_TOKEN_ROLE", UserRole.VIEWER.value)\n        try:\n            role = UserRole(raw_role)\n        except ValueError as exc:\n            raise HTTPException(status_code=500, detail="dashboard_token_role_invalid") from exc\n        configured.append((legacy, role))\n    return configured\n\n\ndef _request_role(request: Request) -> UserRole:\n    raw = request.headers.get("x-dashboard-role", UserRole.VIEWER.value)\n    try:\n        return UserRole(raw)\n    except ValueError as exc:\n        raise HTTPException(status_code=403, detail="dashboard_role_invalid") from exc\n\n\ndef _token_matches(expected: str, provided: str) -> bool:\n    return hmac.compare_digest(_hash(expected), _hash(provided))\n\n\ndef _hash(value: str) -> str:\n    return hashlib.sha256(value.encode("utf-8")).hexdigest()\n\n\ndef _provided_token(headers: Mapping[str, str], cookies: Mapping[str, str]) -> str:\n    authorization = headers.get("authorization", "")\n    if authorization.startswith("Bearer "):\n        return authorization.removeprefix("Bearer ").strip()\n    return cookies.get("dashboard_token", "").strip()\n''',
        encoding="utf-8",
    )

    replace_once(
        "src/cloud_edge_robot_arm/cloud/api/model_control.py",
        "from fastapi import APIRouter, HTTPException, Request, WebSocket, status",
        "from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, status",
    )
    replace_once(
        "src/cloud_edge_robot_arm/cloud/api/model_control.py",
        "from cloud_edge_robot_arm.model_control.downloads import ModelDownloadJob\n",
        "from cloud_edge_robot_arm.dashboard.models import UserRole\n"
        "from cloud_edge_robot_arm.dashboard.security import (\n"
        "    enforce_dashboard_access,\n"
        "    enforce_dashboard_role,\n"
        "    enforce_dashboard_websocket_access,\n"
        ")\n"
        "from cloud_edge_robot_arm.model_control.downloads import ModelDownloadJob\n",
    )
    replace_once(
        "src/cloud_edge_robot_arm/cloud/api/model_control.py",
        'router = APIRouter(prefix="/api/v1/model-control", tags=["model-control"])',
        '''def enforce_model_control_access(request: Request) -> None:\n    """Allow reads to authenticated viewers and require operator role for writes."""\n\n    if request.method in {"GET", "HEAD", "OPTIONS"}:\n        enforce_dashboard_access(request)\n        return\n    enforce_dashboard_role(request, {UserRole.EXPERIMENT_OPERATOR})\n\n\nrouter = APIRouter(\n    prefix="/api/v1/model-control",\n    tags=["model-control"],\n    dependencies=[Depends(enforce_model_control_access)],\n)''',
    )
    replace_once(
        "src/cloud_edge_robot_arm/cloud/api/model_control.py",
        '''async def model_control_stream(websocket: WebSocket, last_sequence: int = 0) -> None:\n    await websocket.accept()''',
        '''async def model_control_stream(websocket: WebSocket, last_sequence: int = 0) -> None:\n    enforce_dashboard_websocket_access(websocket)\n    await websocket.accept()''',
    )

    replace_once(
        ".github/workflows/ci.yml",
        '''      - name: Project CI profile\n        run: python scripts/verify_project.py --profile ci\n\n      - name: Phase 10 software-side checks''',
        '''      - name: Project CI profile\n        run: python scripts/verify_project.py --profile ci\n\n      - name: Upload project CI summary\n        if: always()\n        uses: actions/upload-artifact@v4\n        with:\n          name: project-ci-summary\n          path: artifacts/project_verification/ci_summary.json\n          if-no-files-found: ignore\n\n      - name: Phase 10 software-side checks''',
    )
    replace_once(
        ".github/workflows/ci.yml",
        '''      - name: Phase 12 smoke evaluation\n        run: |\n          python scripts/run_phase12_experiments.py --profile smoke --output artifacts/phase12\n          python scripts/analyze_phase12_results.py --profile smoke --output artifacts/phase12\n          python scripts/export_phase12_thesis_assets.py --profile smoke --output artifacts/phase12\n          python scripts/verify_phase12.py --smoke --output artifacts/phase12/verification --artifact-root artifacts/phase12\n\n      - name: Upload Phase 12 smoke artifacts\n        if: always()\n        uses: actions/upload-artifact@v4\n        with:\n          name: phase12-smoke-artifacts\n          path: artifacts/phase12\n          if-no-files-found: ignore''',
        '''      - name: Phase 12 smoke evaluation\n        run: |\n          output="artifacts/phase12_ci/${GITHUB_RUN_ID}-${GITHUB_SHA}"\n          rm -rf "$output"\n          python scripts/run_phase12_experiments.py --profile smoke --output "$output"\n          python scripts/analyze_phase12_results.py --profile smoke --output "$output"\n          python scripts/export_phase12_thesis_assets.py --profile smoke --output "$output"\n          python scripts/verify_phase12.py --smoke --output "$output/verification" --artifact-root "$output"\n\n      - name: Upload Phase 12 smoke artifacts\n        if: always()\n        uses: actions/upload-artifact@v4\n        with:\n          name: phase12-smoke-artifacts\n          path: artifacts/phase12_ci/${{ github.run_id }}-${{ github.sha }}\n          if-no-files-found: ignore''',
    )

    Path("tests/test_phase12_4_security_remediation.py").write_text(
        '''"""Phase 12.4 regression tests for trusted time and console authorization."""\n\nfrom __future__ import annotations\n\nfrom datetime import UTC, datetime, timedelta\n\nfrom fastapi import FastAPI, Request\nfrom fastapi.testclient import TestClient\n\nfrom cloud_edge_robot_arm.cloud.api.app import create_app\nfrom cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter\nfrom cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline\nfrom cloud_edge_robot_arm.cloud.supervision.core import FakeClock\nfrom cloud_edge_robot_arm.dashboard.models import UserRole\nfrom cloud_edge_robot_arm.dashboard.security import enforce_dashboard_role\nfrom cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor\nfrom cloud_edge_robot_arm.edge.safety.shield import SafetyShield\nfrom cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene\nfrom tests.phase2_helpers import contract\n\n\ndef test_contract_expiry_uses_edge_clock_not_message_timestamp() -> None:\n    issued = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)\n    payload = contract(task_id="trusted-clock-expiry").model_dump(mode="json")\n    payload["timestamp"] = issued.isoformat()\n    payload["issued_at"] = issued.isoformat()\n    payload["valid_until"] = (issued + timedelta(seconds=1)).isoformat()\n    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)\n    executor = TaskExecutor(\n        robot=robot,\n        shield=SafetyShield(),\n        clock=FakeClock(start=issued + timedelta(minutes=1)),\n    )\n\n    result = executor.submit_contract(payload)\n\n    assert result.success is False\n    assert result.error is not None\n    assert result.error.code == "CONTRACT_EXPIRED"\n    assert robot.history == []\n\n\ndef test_token_viewer_cannot_self_escalate_with_role_header(monkeypatch) -> None:\n    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "TOKEN")\n    monkeypatch.setenv("DASHBOARD_TOKEN", "viewer-secret")\n    monkeypatch.setenv("DASHBOARD_TOKEN_ROLE", UserRole.VIEWER.value)\n    app = FastAPI()\n\n    @app.post("/operator")\n    async def operator(request: Request) -> dict[str, str]:\n        role = enforce_dashboard_role(request, {UserRole.EXPERIMENT_OPERATOR})\n        return {"role": role.value}\n\n    response = TestClient(app).post(\n        "/operator",\n        headers={\n            "authorization": "Bearer viewer-secret",\n            "x-dashboard-role": UserRole.EXPERIMENT_OPERATOR.value,\n        },\n    )\n\n    assert response.status_code == 403\n    assert response.json()["detail"] == "dashboard_role_forbidden"\n\n\ndef test_model_control_http_routes_require_server_authorized_role(monkeypatch, tmp_path) -> None:\n    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "TOKEN")\n    monkeypatch.setenv("DASHBOARD_TOKEN", "viewer-secret")\n    monkeypatch.setenv("DASHBOARD_TOKEN_ROLE", UserRole.VIEWER.value)\n    monkeypatch.setenv("MODEL_CONTROL_DB", str(tmp_path / "model_control.db"))\n    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))\n    client = TestClient(app)\n    headers = {\n        "authorization": "Bearer viewer-secret",\n        "x-dashboard-role": UserRole.EXPERIMENT_OPERATOR.value,\n    }\n\n    read_response = client.get("/api/v1/model-control/capabilities", headers=headers)\n    write_response = client.post(\n        "/api/v1/model-control/profiles",\n        headers=headers,\n        json={\n            "display_name": "blocked escalation",\n            "provider_kind": "MOCK",\n            "model_name": "mock-planner",\n        },\n    )\n\n    assert read_response.status_code == 200\n    assert write_response.status_code == 403\n    assert write_response.json()["detail"] == "dashboard_role_forbidden"\n\n\ndef test_model_control_operator_token_can_write(monkeypatch, tmp_path) -> None:\n    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "TOKEN")\n    monkeypatch.delenv("DASHBOARD_TOKEN", raising=False)\n    monkeypatch.setenv("DASHBOARD_OPERATOR_TOKEN", "operator-secret")\n    monkeypatch.setenv("MODEL_CONTROL_DB", str(tmp_path / "model_control.db"))\n    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))\n\n    response = TestClient(app).post(\n        "/api/v1/model-control/profiles",\n        headers={"authorization": "Bearer operator-secret"},\n        json={\n            "display_name": "authorized operator",\n            "provider_kind": "MOCK",\n            "model_name": "mock-planner",\n        },\n    )\n\n    assert response.status_code == 201\n    assert response.json()["display_name"] == "authorized operator"\n''',
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
