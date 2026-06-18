"""模型 profile repository 协议。"""

from __future__ import annotations

from typing import Protocol

from cloud_edge_robot_arm.model_control.downloads import ModelDownloadJob
from cloud_edge_robot_arm.model_control.models import ModelProviderProfile


class PlannerProfileRepository(Protocol):
    """只保存非敏感 profile 数据和 active profile id。"""

    def create_profile(self, profile: ModelProviderProfile) -> ModelProviderProfile:
        """创建非敏感模型 profile 记录。"""
        ...

    def update_profile(self, profile: ModelProviderProfile) -> ModelProviderProfile:
        """更新 profile 元数据并保持 secret 不入库。"""
        ...

    def get_profile(self, profile_id: str) -> ModelProviderProfile:
        """按 profile id 读取单条非敏感配置。"""
        ...

    def list_profiles(self) -> list[ModelProviderProfile]:
        """列出全部非敏感 profile。"""
        ...

    def delete_profile(self, profile_id: str) -> None:
        """删除非 active profile 记录。"""
        ...

    def get_active_profile_id(self) -> str:
        """读取当前 active planner profile id。"""
        ...

    def set_active_profile_id(self, profile_id: str) -> None:
        """原子切换 active planner profile。"""
        ...

    def save_download_job(self, job: ModelDownloadJob) -> ModelDownloadJob:
        """保存 Ollama 下载任务进度快照。"""
        ...

    def get_download_job(self, download_id: str) -> ModelDownloadJob:
        """按 download id 读取下载任务。"""
        ...

    def list_download_jobs(self) -> list[ModelDownloadJob]:
        """按时间倒序列出下载任务。"""
        ...
