#!/usr/bin/env python3
"""Phase 4 云端规划和契约修复演示或实验入口，用固定参数运行受控流程并输出可追溯结果。

Phase 4 acceptance: API smoke test.

Verifies:
- FastAPI health endpoint
- Capabilities endpoint
- TaskContract schema endpoint"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline


def request(app: Any, method: str, path: str) -> dict[str, Any]:
    return asyncio.run(_asgi_request(app, method, path))


async def _asgi_request(app: Any, method: str, path: str) -> dict[str, Any]:
    sent = False
    status_code = 0
    response_body = bytearray()

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        nonlocal status_code
        if message["type"] == "http.response.start":
            status_code = int(message["status"])
        elif message["type"] == "http.response.body":
            response_body.extend(message.get("body", b""))

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": b"",
            "headers": [],
            "client": ("verify", 50000),
            "server": ("testserver", 80),
            "root_path": "",
            "state": {},
        },
        receive,
        send,
    )
    text = response_body.decode("utf-8")
    return {"status_code": status_code, "json": json.loads(text) if text else None}


def main() -> None:
    pipeline = PlanningPipeline(planner=MockPlannerAdapter())
    app = create_app(pipeline)

    errors: list[str] = []

    # Health
    resp = request(app, "GET", "/health")
    if resp["status_code"] != 200:
        errors.append(f"GET /health returned {resp['status_code']}")
    data = resp["json"]
    if data.get("status") != "ok":
        errors.append(f"/health status={data.get('status')}")
    print(f"  GET /health -> {resp['status_code']} {data['status']}")

    # Capabilities
    resp = request(app, "GET", "/api/v1/planning/capabilities")
    if resp["status_code"] != 200:
        errors.append(f"GET /capabilities returned {resp['status_code']}")
    data = resp["json"]
    if "supported_skills" not in data:
        errors.append("GET /capabilities missing supported_skills")
    print(f"  GET /api/v1/planning/capabilities -> {resp['status_code']}")

    # Task contract schema
    resp = request(app, "GET", "/api/v1/planning/schemas/task-contract")
    if resp["status_code"] != 200:
        errors.append(f"GET /schemas/task-contract returned {resp['status_code']}")
    data = resp["json"]
    if "task_contract_schema" not in data:
        errors.append("GET /schemas/task-contract missing task_contract_schema")
    print(f"  GET /api/v1/planning/schemas/task-contract -> {resp['status_code']}")

    if errors:
        print(f"\nFAIL: {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print("\nPASS: API smoke test passed")
    print("success=true")


if __name__ == "__main__":
    main()
