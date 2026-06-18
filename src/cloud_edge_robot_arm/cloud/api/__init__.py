"""云端 API 包。

这里集中暴露 FastAPI 入口、Dashboard API 和仿真工作台 API。API 层只做鉴权、
请求校验和服务编排，不直接控制真实机械臂。
"""

from __future__ import annotations
