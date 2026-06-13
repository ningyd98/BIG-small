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

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AppConfig:
        source = environ if env is None else env
        return cls(
            app_name=source.get("APP_NAME", "small-robot-arm-cloud-edge-control"),
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
        )
