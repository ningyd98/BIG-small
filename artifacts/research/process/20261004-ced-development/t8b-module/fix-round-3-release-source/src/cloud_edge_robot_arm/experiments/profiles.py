"""内置网络 profile。

Profile 只描述仿真通信条件，如延迟、抖动和丢包；它不配置真实网络设备或控制器。
"""

from __future__ import annotations

from cloud_edge_robot_arm.experiments.models import NetworkProfile, NetworkProfileName

_NETWORK_PROFILES: dict[NetworkProfileName, NetworkProfile] = {
    NetworkProfileName.GOOD: NetworkProfile(
        name=NetworkProfileName.GOOD,
        base_latency_ms=20,
        jitter_ms=0,
        loss_rate=0.0,
    ),
    NetworkProfileName.NORMAL: NetworkProfile(
        name=NetworkProfileName.NORMAL,
        base_latency_ms=100,
        jitter_ms=50,
        loss_rate=0.0,
    ),
    NetworkProfileName.DEGRADED: NetworkProfile(
        name=NetworkProfileName.DEGRADED,
        base_latency_ms=300,
        jitter_ms=100,
        loss_rate=0.05,
    ),
    NetworkProfileName.POOR: NetworkProfile(
        name=NetworkProfileName.POOR,
        base_latency_ms=500,
        jitter_ms=300,
        loss_rate=0.10,
    ),
    NetworkProfileName.SEVERE: NetworkProfile(
        name=NetworkProfileName.SEVERE,
        base_latency_ms=1_000,
        jitter_ms=300,
        loss_rate=0.20,
    ),
    NetworkProfileName.INTERMITTENT: NetworkProfile(
        name=NetworkProfileName.INTERMITTENT,
        base_latency_ms=100,
        jitter_ms=50,
        loss_rate=0.0,
        outage_duration_ms=1_000,
    ),
}


def get_network_profile(name: NetworkProfileName) -> NetworkProfile:
    return _NETWORK_PROFILES[name].model_copy(deep=True)


def list_network_profiles() -> list[NetworkProfile]:
    return [profile.model_copy(deep=True) for profile in _NETWORK_PROFILES.values()]
