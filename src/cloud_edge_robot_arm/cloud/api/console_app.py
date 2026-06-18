"""可直接运行的 BIG-small Console FastAPI 入口。

该入口使用 Mock planner 初始化 API，并把已构建的 Dashboard 静态资源挂载到
``/console``。它不启动真实硬件服务，也不连接控制器。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline


def create_console_app(*, dashboard_dist: Path | None = None) -> FastAPI:
    """Create API app with optional Dashboard SPA mount under ``/console``."""

    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))
    dist = dashboard_dist or Path("dashboard/dist")
    mount_console(app, dist)
    return app


def mount_console(app: FastAPI, dashboard_dist: Path) -> None:
    """Mount Dashboard dist while keeping API and WebSocket routes untouched."""

    dist = dashboard_dist.resolve()
    assets = dist / "assets"
    if assets.exists():
        app.mount("/console/assets", StaticFiles(directory=assets), name="console-assets")

    @app.get("/console", include_in_schema=False)
    async def console_index() -> Response:
        return _index_response(dist)

    @app.get("/console/{path:path}", include_in_schema=False)
    async def console_spa(path: str, request: Request) -> Response:
        target = (dist / path).resolve()
        if dist in target.parents and target.is_file():
            return FileResponse(target)
        return _index_response(dist)


def _index_response(dist: Path) -> Response:
    index = dist / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse(
        "<h1>BIG-small Console build missing</h1>"
        "<p>Run <code>cd dashboard && npm run build</code> before using /console.</p>",
        status_code=503,
    )


app = create_console_app()
