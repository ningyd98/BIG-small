from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from os import environ


def _read_int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    return int(raw)


def _read_bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class CoordinationModeDefaults:
    periodic_supervision_ms: int = 1_000
    command_ttl_ms: int = 2_500
    network_loss_grace_ms: int = 3_000


@dataclass(frozen=True)
class AppConfig:
    app_name: str
    app_env: str
    database_url: str
    mqtt_broker_url: str
    mode_defaults: CoordinationModeDefaults
    safety_shield_enabled: bool
    log_level: str
    runtime_profile: str = "test"
    planner_api_endpoint: str | None = None
    planner_api_key: str | None = None
    planner_model: str | None = None
    robot_adapter: str | None = None
    telemetry_provider: str | None = None
    scene_state_provider: str | None = None
    supervision_repository: str | None = None
    supervision_scheduler: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AppConfig:
        source = environ if env is None else env
        runtime_profile = source.get("RUNTIME_PROFILE", "test").strip().lower()
        if runtime_profile not in {"test", "simulation", "production"}:
            raise ValueError(
                f"RUNTIME_PROFILE must be test|simulation|production, got {runtime_profile!r}"
            )
        if runtime_profile == "production":
            _require_production_keys(
                source,
                [
                    "DATABASE_URL",
                    "MQTT_BROKER_URL",
                    "PLANNER_API_ENDPOINT",
                    "PLANNER_API_KEY",
                    "ROBOT_ADAPTER",
                    "TELEMETRY_PROVIDER",
                    "SCENE_STATE_PROVIDER",
                    "SUPERVISION_REPOSITORY",
                    "SUPERVISION_SCHEDULER",
                ],
            )
        return cls(
            app_name=source.get("APP_NAME", "BIG-small"),
            app_env=source.get("APP_ENV", "development"),
            database_url=source.get("DATABASE_URL", "sqlite:///./data/robot_control.db"),
            mqtt_broker_url=source.get("MQTT_BROKER_URL", "mqtt://localhost:1883"),
            mode_defaults=CoordinationModeDefaults(
                periodic_supervision_ms=_read_int(source, "CLOUD_SUPERVISION_PERIOD_MS", 1_000),
                command_ttl_ms=_read_int(source, "COMMAND_TTL_MS", 2_500),
                network_loss_grace_ms=_read_int(source, "NETWORK_LOSS_GRACE_MS", 3_000),
            ),
            safety_shield_enabled=_read_bool(source, "SAFETY_SHIELD_ENABLED", True),
            log_level=source.get("LOG_LEVEL", "INFO"),
            runtime_profile=runtime_profile,
            planner_api_endpoint=_optional(source, "PLANNER_API_ENDPOINT"),
            planner_api_key=_optional(source, "PLANNER_API_KEY"),
            planner_model=source.get("PLANNER_MODEL", "gpt-4o-mini"),
            robot_adapter=_optional(source, "ROBOT_ADAPTER"),
            telemetry_provider=_optional(source, "TELEMETRY_PROVIDER"),
            scene_state_provider=_optional(source, "SCENE_STATE_PROVIDER"),
            supervision_repository=_optional(source, "SUPERVISION_REPOSITORY"),
            supervision_scheduler=_optional(source, "SUPERVISION_SCHEDULER"),
        )


def _optional(env: Mapping[str, str], key: str) -> str | None:
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return None
    return raw.strip()


def _require_production_keys(env: Mapping[str, str], keys: list[str]) -> None:
    missing = [key for key in keys if _optional(env, key) is None]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"production RUNTIME_PROFILE requires explicit {joined}")
