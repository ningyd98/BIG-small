"""模型控制中心应用服务。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from cloud_edge_robot_arm.model_control.catalog import load_small_model_catalog
from cloud_edge_robot_arm.model_control.downloads import ModelDownloadJob, ModelDownloadStatus
from cloud_edge_robot_arm.model_control.endpoint_security import (
    EndpointSecurityPolicy,
    endpoint_hash,
)
from cloud_edge_robot_arm.model_control.models import (
    ModelProviderProfile,
    PlannerProviderKind,
    PlannerRuntimeStatus,
)
from cloud_edge_robot_arm.model_control.providers.ollama import OllamaTransport
from cloud_edge_robot_arm.model_control.repository import PlannerProfileRepository
from cloud_edge_robot_arm.model_control.secret_store import SecretStore


class ModelControlService:
    """模型 profile、secret 和 active planner 的安全门面。"""

    def __init__(
        self,
        *,
        repository: PlannerProfileRepository,
        secret_store: SecretStore,
        endpoint_policy: EndpointSecurityPolicy | None = None,
    ) -> None:
        self.repository = repository
        self.secret_store = secret_store
        self.endpoint_policy = endpoint_policy or EndpointSecurityPolicy()

    def create_profile(
        self,
        *,
        display_name: str,
        provider_kind: PlannerProviderKind,
        model_name: str,
        base_url: str = "",
        chat_completions_path: str = "/v1/chat/completions",
        api_key: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        json_mode: bool = True,
    ) -> ModelProviderProfile:
        """创建模型 profile，并把 API key 写入 SecretStore 而不是 SQLite。"""

        safe_url = self.endpoint_policy.validate(provider_kind, base_url)
        now = datetime.now(UTC)
        profile = ModelProviderProfile(
            profile_id="profile-" + uuid4().hex[:16],
            display_name=display_name,
            provider_kind=provider_kind,
            base_url=safe_url,
            chat_completions_path=chat_completions_path,
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            json_mode=json_mode,
            secret_present=bool(api_key),
            secret_store_kind=self.secret_store.kind,
            endpoint_hash=endpoint_hash(safe_url) if safe_url else "",
            created_at=now,
            updated_at=now,
            secret_updated_at=now if api_key else None,
        )
        if api_key:
            self.secret_store.set_secret(profile.profile_id, api_key)
        return self.repository.create_profile(profile)

    def update_profile(
        self,
        profile_id: str,
        *,
        display_name: str | None = None,
        base_url: str | None = None,
        chat_completions_path: str | None = None,
        model_name: str | None = None,
        api_key: str | None = None,
    ) -> ModelProviderProfile:
        """更新 profile 配置，必要时轮换或清除 secret。"""

        current = self.repository.get_profile(profile_id)
        provider_kind = current.provider_kind
        safe_url = (
            self.endpoint_policy.validate(provider_kind, base_url)
            if base_url is not None
            else current.base_url
        )
        now = datetime.now(UTC)
        updated = current.model_copy(
            update={
                "display_name": display_name if display_name is not None else current.display_name,
                "base_url": safe_url,
                "chat_completions_path": chat_completions_path
                if chat_completions_path is not None
                else current.chat_completions_path,
                "model_name": model_name if model_name is not None else current.model_name,
                "secret_present": current.secret_present or api_key is not None,
                "secret_store_kind": self.secret_store.kind,
                "endpoint_hash": endpoint_hash(safe_url) if safe_url else "",
                "config_version": current.config_version + 1,
                "updated_at": now,
                "secret_updated_at": now if api_key is not None else current.secret_updated_at,
                "api_key": None,
            }
        )
        if api_key is not None:
            if api_key:
                self.secret_store.set_secret(profile_id, api_key)
            else:
                self.secret_store.delete_secret(profile_id)
                updated = updated.model_copy(update={"secret_present": False})
        return self.repository.update_profile(updated)

    def get_profile(self, profile_id: str) -> ModelProviderProfile:
        """读取 profile 并标记是否为当前 active。"""

        return self._with_active_flag(self.repository.get_profile(profile_id))

    def list_profiles(self) -> list[ModelProviderProfile]:
        """列出所有 profile，并附加 active 标记。"""

        return [self._with_active_flag(profile) for profile in self.repository.list_profiles()]

    def delete_profile(self, profile_id: str) -> None:
        """删除非 active profile，同时清理对应 secret。"""

        if self.repository.get_active_profile_id() == profile_id:
            raise ValueError("active_profile_delete_rejected")
        self.repository.delete_profile(profile_id)
        self.secret_store.delete_secret(profile_id)

    def activate_profile(
        self, profile_id: str, *, expected_config_version: int | None = None
    ) -> PlannerRuntimeStatus:
        """按版本可选 CAS 激活 profile，避免过期配置被误切换。"""

        profile = self.repository.get_profile(profile_id)
        if (
            expected_config_version is not None
            and profile.config_version != expected_config_version
        ):
            raise ValueError("profile_version_conflict")
        if not profile.enabled:
            raise ValueError("profile_disabled")
        self.repository.set_active_profile_id(profile_id)
        return self.runtime_status()

    def runtime_status(self) -> PlannerRuntimeStatus:
        """返回当前 active planner 的脱敏运行状态。"""

        active_id = self.repository.get_active_profile_id()
        if not active_id:
            return PlannerRuntimeStatus()
        profile = self.repository.get_profile(active_id)
        return PlannerRuntimeStatus(
            active_profile_id=profile.profile_id,
            active_provider=profile.provider_kind,
            active_model=profile.model_name,
            endpoint_hash=profile.endpoint_hash,
            config_version=profile.config_version,
            health="READY",
        )

    def ollama_status(self, transport: OllamaTransport) -> dict[str, Any]:
        """探测 Ollama 是否可达，并只返回脱敏错误类型。"""

        try:
            version = transport.get_version()
        except Exception as exc:
            return {"reachable": False, "version": "", "error_code": type(exc).__name__}
        return {"reachable": True, "version": str(version.get("version", ""))}

    def ollama_models(self, transport: OllamaTransport) -> list[dict[str, Any]]:
        """列出 Ollama 已安装模型；不可达时返回空列表。"""

        try:
            return transport.list_models()
        except Exception:
            return []

    def small_model_catalog(self, transport: OllamaTransport | None = None) -> list[dict[str, Any]]:
        """返回小模型目录，并用 Ollama 实时列表标记 installed。"""

        installed: set[str] = set()
        if transport is not None:
            try:
                installed = {str(item.get("name", "")) for item in transport.list_models()}
            except Exception:
                installed = set()
        return [
            item.model_dump(mode="json")
            for item in load_small_model_catalog(installed_models=installed)
        ]

    def start_ollama_download(
        self,
        *,
        model_name: str,
        transport: OllamaTransport,
        requested_by: str = "",
    ) -> ModelDownloadJob:
        """启动一次 Ollama 模型下载任务，只接受模型名而不是任意 URL。"""

        _validate_model_name(model_name)
        now = datetime.now(UTC)
        job = ModelDownloadJob(
            download_id="download-" + uuid4().hex[:16],
            model_name=model_name,
            status=ModelDownloadStatus.CONNECTING,
            created_at=now,
            started_at=now,
            requested_by=requested_by,
        )
        self.repository.save_download_job(job)
        try:
            events = transport.pull_model(model_name)
            final = events[-1] if events else {}
            completed = int(final.get("completed", final.get("total", 0)) or 0)
            total = int(final.get("total", completed) or completed)
            if total <= 0:
                total = completed
            models = {str(item.get("name", "")) for item in transport.list_models()}
            if model_name not in models:
                raise RuntimeError("model_not_installed_after_pull")
            job = job.model_copy(
                update={
                    "status": ModelDownloadStatus.SUCCEEDED,
                    "completed_bytes": completed,
                    "total_bytes": total,
                    "progress_ratio": 1.0,
                    "message": str(final.get("status", "success")),
                    "completed_at": datetime.now(UTC),
                }
            )
        except Exception as exc:
            job = job.model_copy(
                update={
                    "status": ModelDownloadStatus.FAILED,
                    "error_code": type(exc).__name__,
                    "error_message": str(exc),
                    "completed_at": datetime.now(UTC),
                }
            )
        return self.repository.save_download_job(job)

    def list_downloads(self) -> list[ModelDownloadJob]:
        """列出模型下载任务历史。"""

        return self.repository.list_download_jobs()

    def activate_ollama_model(
        self,
        *,
        model_name: str,
        transport: OllamaTransport,
    ) -> PlannerRuntimeStatus:
        """校验本地模型已安装且可 chat 后激活 Ollama profile。"""

        _validate_model_name(model_name)
        installed = {str(item.get("name", "")) for item in transport.list_models()}
        if model_name not in installed:
            raise ValueError("ollama_model_not_installed")
        transport.chat(model_name, [{"role": "user", "content": "return {}"}])
        profile = self.create_profile(
            display_name=f"Ollama {model_name}",
            provider_kind=PlannerProviderKind.OLLAMA,
            base_url="http://127.0.0.1:11434",
            model_name=model_name,
        )
        return self.activate_profile(profile.profile_id)

    def planner_dry_run(
        self,
        *,
        user_instruction: str,
        sample_scene: str,
        control_mode: str,
        transport: OllamaTransport | None = None,
    ) -> dict[str, Any]:
        """执行 planner dry-run，明确 dispatch=false 且 hardware_execution=false。"""

        active_id = self.repository.get_active_profile_id()
        profile = self.repository.get_profile(active_id) if active_id else None
        provider = profile.provider_kind if profile else PlannerProviderKind.MOCK
        raw_output = "{}"
        if provider == PlannerProviderKind.OLLAMA and profile is not None:
            if transport is None:
                raise ValueError("ollama_transport_unavailable")
            response = transport.chat(
                profile.model_name,
                [{"role": "user", "content": user_instruction}],
            )
            raw_output = str(response["choices"][0]["message"]["content"])
        return {
            "dispatch": False,
            "hardware_execution": False,
            "user_instruction": user_instruction,
            "sample_scene": sample_scene,
            "control_mode": control_mode,
            "provider_kind": provider.value,
            "model_name": profile.model_name if profile else "mock",
            "raw_planner_output": raw_output,
            "parse_result": "NOT_DISPATCHED",
            "validation_errors": [],
            "repair_attempts": 0,
            "final_contract": {},
        }

    def _with_active_flag(self, profile: ModelProviderProfile) -> ModelProviderProfile:
        return profile.model_copy(
            update={"active": self.repository.get_active_profile_id() == profile.profile_id}
        )


def _validate_model_name(model_name: str) -> None:
    if not model_name or "://" in model_name or "/" in model_name or "\\" in model_name:
        raise ValueError("invalid_ollama_model_name")
