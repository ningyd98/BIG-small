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


def _read_float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    return float(raw)


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
    skill_cache_backend: str = "inmemory"
    skill_cache_db_path: str | None = None
    skill_promotion_min_successes: int = 3
    skill_promotion_success_rate: float = 0.9
    skill_quarantine_failures: int = 2
    skill_template_ttl_seconds: int = 86_400
    risk_policy_version: str = "risk-v1"
    risk_component_weights: str = (
        "task=0.15,scene=0.15,perception=0.15,network=0.15,execution=0.2,safety=0.2"
    )
    risk_level_thresholds: str = "low=25,medium=50,high=75,critical=90"
    auto_mode_enabled: bool = False
    auto_mode_repository: str = "inmemory"
    auto_mode_db_path: str | None = None
    auto_min_dwell_seconds: int = 120
    auto_switch_cooldown_seconds: int = 300
    auto_confirmation_count: int = 2
    auto_max_switches_per_task: int = 5

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AppConfig:
        source = environ if env is None else env
        runtime_profile = source.get("RUNTIME_PROFILE", "test").strip().lower()
        if runtime_profile not in {"test", "simulation", "production"}:
            raise ValueError(
                f"RUNTIME_PROFILE must be test|simulation|production, got {runtime_profile!r}"
            )
        if runtime_profile == "production":
            production_keys = [
                "DATABASE_URL",
                "MQTT_BROKER_URL",
                "PLANNER_API_ENDPOINT",
                "PLANNER_API_KEY",
                "ROBOT_ADAPTER",
                "TELEMETRY_PROVIDER",
                "SCENE_STATE_PROVIDER",
                "SUPERVISION_REPOSITORY",
                "SUPERVISION_SCHEDULER",
            ]
            if _read_bool(source, "AUTO_MODE_ENABLED", False):
                production_keys.extend(
                    [
                        "SKILL_CACHE_BACKEND",
                        "SKILL_CACHE_DB_PATH",
                        "AUTO_MODE_REPOSITORY",
                        "AUTO_MODE_DB_PATH",
                        "RISK_POLICY_VERSION",
                        "RISK_COMPONENT_WEIGHTS",
                        "RISK_LEVEL_THRESHOLDS",
                    ]
                )
            _require_production_keys(source, production_keys)
            _reject_phase7_production_defaults(source)
            _reject_production_test_doubles(source, production_keys)
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
            skill_cache_backend=source.get("SKILL_CACHE_BACKEND", "inmemory").strip().lower(),
            skill_cache_db_path=_optional(source, "SKILL_CACHE_DB_PATH"),
            skill_promotion_min_successes=_read_int(source, "SKILL_PROMOTION_MIN_SUCCESSES", 3),
            skill_promotion_success_rate=_read_float(source, "SKILL_PROMOTION_SUCCESS_RATE", 0.9),
            skill_quarantine_failures=_read_int(source, "SKILL_QUARANTINE_FAILURES", 2),
            skill_template_ttl_seconds=_read_int(source, "SKILL_TEMPLATE_TTL", 86_400),
            risk_policy_version=source.get("RISK_POLICY_VERSION", "risk-v1"),
            risk_component_weights=source.get(
                "RISK_COMPONENT_WEIGHTS",
                "task=0.15,scene=0.15,perception=0.15,network=0.15,execution=0.2,safety=0.2",
            ),
            risk_level_thresholds=source.get(
                "RISK_LEVEL_THRESHOLDS", "low=25,medium=50,high=75,critical=90"
            ),
            auto_mode_enabled=_read_bool(source, "AUTO_MODE_ENABLED", False),
            auto_mode_repository=source.get("AUTO_MODE_REPOSITORY", "inmemory").strip().lower(),
            auto_mode_db_path=_optional(source, "AUTO_MODE_DB_PATH"),
            auto_min_dwell_seconds=_read_int(source, "AUTO_MIN_DWELL_SECONDS", 120),
            auto_switch_cooldown_seconds=_read_int(source, "AUTO_SWITCH_COOLDOWN_SECONDS", 300),
            auto_confirmation_count=_read_int(source, "AUTO_CONFIRMATION_COUNT", 2),
            auto_max_switches_per_task=_read_int(source, "AUTO_MAX_SWITCHES_PER_TASK", 5),
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


def _reject_production_test_doubles(env: Mapping[str, str], keys: list[str]) -> None:
    markers = ("mock", "fake", "inmemory", "place" + "holder")
    invalid = [
        key
        for key in keys
        if (value := _optional(env, key)) is not None
        and any(marker in value.lower() for marker in markers)
    ]
    if invalid:
        joined = ", ".join(invalid)
        raise ValueError(f"production RUNTIME_PROFILE forbids test-double values in {joined}")


def _reject_phase7_production_defaults(env: Mapping[str, str]) -> None:
    if not _read_bool(env, "AUTO_MODE_ENABLED", False):
        return
    skill_backend = _optional(env, "SKILL_CACHE_BACKEND")
    auto_repo = _optional(env, "AUTO_MODE_REPOSITORY")
    if skill_backend is None:
        raise ValueError("production AUTO requires explicit SKILL_CACHE_BACKEND")
    if skill_backend.strip().lower() == "inmemory":
        raise ValueError("production AUTO forbids InMemory Skill Cache repository")
    if auto_repo is None:
        raise ValueError("production AUTO requires explicit AUTO_MODE_REPOSITORY")
    if auto_repo.strip().lower() == "inmemory":
        raise ValueError("production AUTO forbids InMemory AUTO repository")
