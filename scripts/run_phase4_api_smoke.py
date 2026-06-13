#!/usr/bin/env python3
"""Phase 4 acceptance: API smoke test.

Verifies:
- FastAPI health endpoint
- Capabilities endpoint
- TaskContract schema endpoint
"""

from __future__ import annotations

import sys

from fastapi.testclient import TestClient

from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline


def main() -> None:
    pipeline = PlanningPipeline(planner=MockPlannerAdapter())
    app = create_app(pipeline)
    client = TestClient(app)

    errors: list[str] = []

    # Health
    resp = client.get("/health")
    if resp.status_code != 200:
        errors.append(f"GET /health returned {resp.status_code}")
    data = resp.json()
    if data.get("status") != "ok":
        errors.append(f"/health status={data.get('status')}")
    print(f"  GET /health -> {resp.status_code} {data['status']}")

    # Capabilities
    resp = client.get("/api/v1/planning/capabilities")
    if resp.status_code != 200:
        errors.append(f"GET /capabilities returned {resp.status_code}")
    data = resp.json()
    if "supported_skills" not in data:
        errors.append("GET /capabilities missing supported_skills")
    print(f"  GET /api/v1/planning/capabilities -> {resp.status_code}")

    # Task contract schema
    resp = client.get("/api/v1/planning/schemas/task-contract")
    if resp.status_code != 200:
        errors.append(f"GET /schemas/task-contract returned {resp.status_code}")
    data = resp.json()
    if "task_contract_schema" not in data:
        errors.append("GET /schemas/task-contract missing task_contract_schema")
    print(f"  GET /api/v1/planning/schemas/task-contract -> {resp.status_code}")

    if errors:
        print(f"\nFAIL: {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print("\nPASS: API smoke test passed")
    print("success=true")


if __name__ == "__main__":
    main()
