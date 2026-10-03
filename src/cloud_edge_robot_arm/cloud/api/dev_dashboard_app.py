"""本地开发 Dashboard API 入口。

默认以真实 RGB-D 相机观测调用视觉模型；模型缺失时明确阻塞规划。
该入口用于仿真，不连接真实机械臂控制器。
"""

from __future__ import annotations

from cloud_edge_robot_arm.cloud.api.app import create_app
app = create_app()
