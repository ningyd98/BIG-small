"""模型 endpoint SSRF 防护策略。"""

from __future__ import annotations

import hashlib
import ipaddress
from urllib.parse import urlparse

from cloud_edge_robot_arm.model_control.models import PlannerProviderKind


class EndpointSecurityError(ValueError):
    """endpoint 安全策略拒绝时抛出。"""


def endpoint_hash(base_url: str) -> str:
    """返回脱敏 endpoint hash，避免记录原始 credential URL。"""

    return hashlib.sha256(base_url.strip().encode("utf-8")).hexdigest()


class EndpointSecurityPolicy:
    """限制模型服务 endpoint，防止本地文件、metadata 和远程 Ollama 滥用。"""

    allowed_schemes = {"http", "https"}
    metadata_addresses = {
        ipaddress.ip_address("169.254.169.254"),
        ipaddress.ip_address("100.100.100.200"),
    }

    def validate(self, provider_kind: PlannerProviderKind, base_url: str) -> str:
        if provider_kind in {PlannerProviderKind.MOCK, PlannerProviderKind.RULE_BASED}:
            return ""
        parsed = urlparse(base_url)
        if parsed.scheme not in self.allowed_schemes:
            raise EndpointSecurityError("unsupported_endpoint_scheme")
        if not parsed.hostname:
            raise EndpointSecurityError("missing_endpoint_host")
        host = parsed.hostname.strip()
        ip = _host_ip(host)
        if ip in self.metadata_addresses:
            raise EndpointSecurityError("metadata_address_blocked")
        if ip is not None and (ip.is_link_local or ip.is_multicast or ip.is_unspecified):
            raise EndpointSecurityError("unsafe_endpoint_address")
        if provider_kind == PlannerProviderKind.OLLAMA and not _is_loopback(host, ip):
            raise EndpointSecurityError("remote_ollama_blocked")
        if provider_kind == PlannerProviderKind.OPENAI_COMPATIBLE:
            if parsed.scheme != "https" and not _is_loopback(host, ip):
                raise EndpointSecurityError("openai_compatible_requires_https")
        return base_url.rstrip("/")


def _host_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _is_loopback(host: str, ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None) -> bool:
    normalized = host.lower()
    return normalized in {"localhost"} or bool(ip and ip.is_loopback)
