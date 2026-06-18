"""模型控制中心 SQLite repository。"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from cloud_edge_robot_arm.model_control.downloads import ModelDownloadJob
from cloud_edge_robot_arm.model_control.models import (
    ModelProviderProfile,
    PlannerProviderKind,
    SecretStoreKind,
)

SCHEMA_VERSION = 1


class SQLiteModelProfileRepository:
    """只存非敏感 profile 字段，不保存明文 API key。"""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create_profile(self, profile: ModelProviderProfile) -> ModelProviderProfile:
        """创建一条模型 provider profile，只持久化脱敏后的配置。"""

        self._initialize()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO model_provider_profiles (
                    profile_id, payload_json, config_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    profile.profile_id,
                    _profile_payload(profile),
                    profile.config_version,
                    profile.created_at.isoformat(),
                    profile.updated_at.isoformat(),
                ),
            )
        return self.get_profile(profile.profile_id)

    def update_profile(self, profile: ModelProviderProfile) -> ModelProviderProfile:
        """更新模型 provider profile，并保持 API key 不进入 SQLite。"""

        self._initialize()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE model_provider_profiles
                SET payload_json = ?, config_version = ?, updated_at = ?
                WHERE profile_id = ?
                """,
                (
                    _profile_payload(profile),
                    profile.config_version,
                    profile.updated_at.isoformat(),
                    profile.profile_id,
                ),
            )
        return self.get_profile(profile.profile_id)

    def get_profile(self, profile_id: str) -> ModelProviderProfile:
        """按 profile id 读取模型配置，不返回任何明文 secret。"""

        self._initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM model_provider_profiles WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()
        if row is None:
            raise KeyError(profile_id)
        return ModelProviderProfile.model_validate(json.loads(str(row["payload_json"])))

    def list_profiles(self) -> list[ModelProviderProfile]:
        """列出所有模型配置，结果仍保持脱敏。"""

        self._initialize()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM model_provider_profiles ORDER BY created_at ASC"
            ).fetchall()
        return [
            ModelProviderProfile.model_validate(json.loads(str(row["payload_json"])))
            for row in rows
        ]

    def delete_profile(self, profile_id: str) -> None:
        """删除指定 profile 的非敏感配置记录。"""

        self._initialize()
        with self._connect() as conn:
            conn.execute("DELETE FROM model_provider_profiles WHERE profile_id = ?", (profile_id,))

    def get_active_profile_id(self) -> str:
        """读取当前 active planner profile id。"""

        self._initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM model_runtime_state WHERE key = 'active_profile_id'"
            ).fetchone()
        return str(row["value"]) if row else ""

    def set_active_profile_id(self, profile_id: str) -> None:
        """原子写入当前 active planner profile id。"""

        self._initialize()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO model_runtime_state(key, value, updated_at)
                VALUES ('active_profile_id', ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (profile_id, datetime.now(UTC).isoformat()),
            )

    def save_download_job(self, job: ModelDownloadJob) -> ModelDownloadJob:
        """保存 Ollama 下载任务快照，供断线后继续查询进度。"""

        self._initialize()
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO model_download_jobs(
                    download_id, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(download_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    job.download_id,
                    json.dumps(job.model_dump(mode="json"), sort_keys=True),
                    job.created_at.isoformat(),
                    now,
                ),
            )
        return self.get_download_job(job.download_id)

    def get_download_job(self, download_id: str) -> ModelDownloadJob:
        """按下载 id 读取模型下载任务。"""

        self._initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM model_download_jobs WHERE download_id = ?",
                (download_id,),
            ).fetchone()
        if row is None:
            raise KeyError(download_id)
        return ModelDownloadJob.model_validate(json.loads(str(row["payload_json"])))

    def list_download_jobs(self) -> list[ModelDownloadJob]:
        """按创建时间倒序列出模型下载任务。"""

        self._initialize()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM model_download_jobs ORDER BY created_at DESC"
            ).fetchall()
        return [
            ModelDownloadJob.model_validate(json.loads(str(row["payload_json"]))) for row in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS model_provider_profiles (
                    profile_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    config_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS model_runtime_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS model_download_jobs (
                    download_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS model_download_events (
                    event_id TEXT PRIMARY KEY,
                    download_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS model_catalog_overrides (
                    catalog_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS model_test_results (
                    result_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, datetime.now(UTC).isoformat()),
            )


def _profile_payload(profile: ModelProviderProfile) -> str:
    payload = profile.model_dump(mode="json")
    payload["api_key"] = None
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def default_profile(provider_kind: PlannerProviderKind) -> ModelProviderProfile:
    """为测试和首次启动构造不含 secret 的默认 profile。"""

    return ModelProviderProfile(
        profile_id="default-" + provider_kind.value.lower(),
        display_name=provider_kind.value,
        provider_kind=provider_kind,
        model_name=provider_kind.value.lower(),
        secret_store_kind=SecretStoreKind.SESSION_ONLY,
    )
