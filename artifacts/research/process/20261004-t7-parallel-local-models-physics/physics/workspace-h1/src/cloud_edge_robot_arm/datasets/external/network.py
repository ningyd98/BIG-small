"""仅通过指定物理接口传输；DNS、TCP 和重定向均禁止代理或隧道回退。"""

from __future__ import annotations

import ipaddress
import math
import re
import secrets
import socket
import ssl
import struct
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpcore
import httpx
from httpcore._backends.base import SOCKET_OPTION, NetworkBackend, NetworkStream
from httpcore._backends.sync import SyncStream

_HOST = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_FAKE_IP = ipaddress.IPv4Network("198.18.0.0/15")


class NetworkPolicyError(RuntimeError):
    """网络约束无法保证时中止，不尝试系统网络默认路径。"""


def _blocked(reason: str) -> NetworkPolicyError:
    return NetworkPolicyError(f"BLOCKED_NETWORK: {reason}")


def _hostname(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 253:
        raise _blocked("invalid exact hostname")
    result = value.lower()
    if "." not in result or any(not _HOST.fullmatch(label) for label in result.split(".")):
        raise _blocked("hostname must be an exact ASCII domain without wildcard")
    try:
        ipaddress.ip_address(result)
    except ValueError:
        return result
    raise _blocked("hostname must not be an IP literal")


def _public_ipv4(value: Any) -> str:
    try:
        address = ipaddress.IPv4Address(value)
    except (ValueError, TypeError) as exc:
        raise _blocked("numeric public IPv4 address required") from exc
    if not address.is_global or address.is_multicast or address in _FAKE_IP:
        raise _blocked("fake, private or reserved IP address rejected")
    return str(address)


def _require_physical_interface(interface: str) -> None:
    path = Path("/sys/class/net") / interface
    try:
        physical = (path / "device").exists() and (path / "type").read_text().strip() == "1"
    except OSError as exc:
        raise _blocked("physical interface identity unavailable") from exc
    if not physical or not hasattr(socket, "SO_BINDTODEVICE"):
        raise _blocked("a Linux physical Ethernet/Wi-Fi interface is required")


def validate_network_policy(policy: dict[str, Any]) -> dict[str, Any]:
    """规范化显式直连设置；不访问网络、不接收隐式系统代理。"""
    if not isinstance(policy, dict) or policy.get("mode") != "direct":
        raise _blocked("network mode must be direct")
    interface = policy.get("interface")
    if not isinstance(interface, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", interface):
        raise _blocked("invalid physical interface name")
    _require_physical_interface(interface)
    hosts = policy.get("allowed_hosts")
    if not isinstance(hosts, list) or not hosts:
        raise _blocked("an explicit nonempty hostname allowlist is required")
    allowed = sorted({_hostname(host) for host in hosts})
    servers = policy.get("dns_servers")
    if not isinstance(servers, list) or not 1 <= len(servers) <= 4:
        raise _blocked("one to four explicit numeric DNS servers are required")
    resolvers = [_public_ipv4(server) for server in servers]
    mappings = policy.get("host_addresses", {})
    if not isinstance(mappings, dict):
        raise _blocked("host_addresses must be an explicit hostname mapping")
    addresses: dict[str, list[str]] = {}
    for host, values in mappings.items():
        host = _hostname(host)
        if host not in allowed or not isinstance(values, list) or not 1 <= len(values) <= 16:
            raise _blocked("fixed addresses require an allowed hostname and finite address list")
        addresses[host] = [_public_ipv4(value) for value in values]
    timeout = policy.get("dns_timeout_seconds", 3.0)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise _blocked("invalid DNS timeout")
    if not math.isfinite(timeout) or not 0 < timeout <= 10:
        raise _blocked("DNS timeout must be finite and at most ten seconds")
    return {
        "mode": "direct",
        "interface": interface,
        "allowed_hosts": allowed,
        "dns_servers": resolvers,
        "host_addresses": addresses,
        "dns_timeout_seconds": float(timeout),
    }


def require_allowed_host(url: str | httpx.URL, policy: dict[str, Any]) -> None:
    """对每次请求（包含后续重定向）检查精确域名和 HTTPS 端口。"""
    try:
        parsed = urlsplit(str(url))
        host = _hostname(parsed.hostname)
        valid = parsed.scheme == "https" and parsed.port in (None, 443)
        valid = valid and parsed.username is None and parsed.password is None
    except (ValueError, NetworkPolicyError) as exc:
        raise _blocked("invalid HTTPS request destination") from exc
    if not valid or host not in policy.get("allowed_hosts", []):
        raise _blocked("request or redirect hostname is outside the explicit HTTPS allowlist")


def _bound_socket(interface: str, kind: int, timeout: float) -> socket.socket:
    try:
        sock = socket.socket(socket.AF_INET, kind)
    except OSError as exc:
        raise _blocked("physical-interface socket creation failed") from exc
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode() + b"\x00")
        bound = sock.getsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, 256)
        if bound.rstrip(b"\x00") != interface.encode():
            raise _blocked("physical-interface binding could not be confirmed")
        sock.settimeout(timeout)
        return sock
    except (OSError, NetworkPolicyError) as exc:
        sock.close()
        raise _blocked("physical-interface binding failed; no fallback permitted") from exc


def _dns_name(packet: bytes, offset: int) -> tuple[str, int]:
    labels: list[str] = []
    end: int | None = None
    visited: set[int] = set()
    for _ in range(128):
        if offset >= len(packet) or offset in visited:
            raise _blocked("invalid DNS name or compression loop")
        visited.add(offset)
        length = packet[offset]
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(packet):
                raise _blocked("truncated DNS compression pointer")
            pointer = ((length & 0x3F) << 8) | packet[offset + 1]
            if pointer >= offset:
                raise _blocked("DNS compression must reference an earlier name")
            if end is None:
                end = offset + 2
            offset = pointer
            continue
        if length & 0xC0 or length > 63:
            raise _blocked("invalid DNS label")
        offset += 1
        if length == 0:
            name = ".".join(labels).lower()
            if len(name) > 253:
                raise _blocked("DNS name exceeds maximum length")
            return name, end if end is not None else offset
        if offset + length > len(packet):
            raise _blocked("truncated DNS label")
        try:
            label = packet[offset : offset + length].decode("ascii")
        except UnicodeDecodeError as exc:
            raise _blocked("non-ASCII DNS label") from exc
        if not _HOST.fullmatch(label.lower()):
            raise _blocked("invalid DNS hostname label")
        labels.append(label)
        offset += length
    raise _blocked("DNS compression hop limit exceeded")


def _dns_answers(packet: bytes, identity: int, host: str) -> list[str]:
    if len(packet) < 12:
        raise _blocked("truncated DNS response")
    transaction, flags, questions, answers, authority, additional = struct.unpack(
        "!6H", packet[:12]
    )
    if transaction != identity or flags & 0x8000 == 0 or flags & 0x780F or flags & 0x0200:
        raise _blocked("mismatched, failed or truncated DNS response")
    if questions != 1 or not 1 <= answers <= 128 or authority + additional > 128:
        raise _blocked("invalid DNS record counts")
    question, offset = _dns_name(packet, 12)
    if (
        question != host
        or offset + 4 > len(packet)
        or packet[offset : offset + 4] != b"\x00\x01\x00\x01"
    ):
        raise _blocked("DNS response question mismatch")
    offset += 4
    records: list[tuple[str, int, Any]] = []
    for index in range(answers + authority + additional):
        owner, offset = _dns_name(packet, offset)
        if offset + 10 > len(packet):
            raise _blocked("truncated DNS record header")
        kind, group, _ttl, size = struct.unpack("!HHIH", packet[offset : offset + 10])
        offset += 10
        record_end = offset + size
        if record_end > len(packet):
            raise _blocked("truncated DNS record data")
        if index < answers and group == 1:
            if kind == 1:
                if size != 4:
                    raise _blocked("invalid DNS IPv4 record")
                records.append((owner, kind, socket.inet_ntoa(packet[offset:record_end])))
            elif kind == 5:
                target, name_end = _dns_name(packet, offset)
                if name_end != record_end:
                    raise _blocked("invalid DNS CNAME size")
                records.append((owner, kind, _hostname(target)))
        offset = record_end
    if offset != len(packet):
        raise _blocked("unexpected trailing DNS response bytes")
    reachable = {host}
    for _ in range(8):
        targets = {value for owner, kind, value in records if kind == 5 and owner in reachable}
        new_targets = targets - reachable
        if not new_targets:
            break
        reachable.update(new_targets)
    else:
        raise _blocked("DNS CNAME hop limit exceeded")
    addresses = [
        _public_ipv4(value) for owner, kind, value in records if kind == 1 and owner in reachable
    ]
    if not addresses:
        raise _blocked("DNS returned no public IPv4 answer for the requested hostname")
    return list(dict.fromkeys(addresses))


class DirectNetworkBackend(NetworkBackend):
    """DNS 和 TCP 都先绑定物理设备，再连接数字地址。"""

    def __init__(self, policy: dict[str, Any]) -> None:
        self.policy = validate_network_policy(policy)

    def _resolve(self, host: str) -> list[str]:
        if host in self.policy["host_addresses"]:
            return list(self.policy["host_addresses"][host])
        identity = secrets.randbits(16)
        question = b"".join(bytes([len(label)]) + label.encode() for label in host.split("."))
        packet = (
            struct.pack("!6H", identity, 0x0100, 1, 0, 0, 0) + question + b"\x00\x00\x01\x00\x01"
        )
        for resolver in self.policy["dns_servers"]:
            # 绑定权限错误不可通过换 DNS 服务器掩盖，因此创建在重试范围之外。
            sock = _bound_socket(
                self.policy["interface"], socket.SOCK_DGRAM, self.policy["dns_timeout_seconds"]
            )
            try:
                sock.connect((resolver, 53))
                sock.send(packet)
                response, source = sock.recvfrom(4096)
                if source != (resolver, 53):
                    raise _blocked("DNS response source does not match the explicit resolver")
                return _dns_answers(response, identity, host)
            except OSError:
                continue
            finally:
                sock.close()
        raise _blocked("explicit physical-interface DNS failed; system DNS fallback prohibited")

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> NetworkStream:
        host = _hostname(host)
        if host not in self.policy["allowed_hosts"] or port != 443:
            raise _blocked("TCP destination is outside the HTTPS allowlist")
        if local_address is not None or socket_options:
            raise _blocked("custom source addresses or socket options are prohibited")
        timeout = 15.0 if timeout is None else timeout
        if not math.isfinite(timeout) or timeout <= 0:
            raise _blocked("TCP timeout must be finite and positive")
        for address in self._resolve(host):
            sock = _bound_socket(self.policy["interface"], socket.SOCK_STREAM, min(timeout, 15.0))
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.connect((address, port))
                if sock.getpeername()[0] != address:
                    raise _blocked("TCP peer differs from the verified public address")
                return SyncStream(sock)
            except (OSError, NetworkPolicyError):
                sock.close()
        raise _blocked("physical-interface HTTPS connection failed; no network fallback permitted")

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> NetworkStream:
        raise _blocked("UNIX/proxy socket connections are prohibited")


class _DirectHTTPTransport(httpx.HTTPTransport):
    def __init__(self, policy: dict[str, Any]) -> None:
        self.policy = validate_network_policy(policy)
        super().__init__(verify=True, trust_env=False, retries=0)
        self._pool.close()
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl.create_default_context(),
            network_backend=DirectNetworkBackend(self.policy),
            max_connections=4,
            max_keepalive_connections=0,
            retries=0,
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        require_allowed_host(request.url, self.policy)
        sni = request.extensions.get("sni_hostname")
        if sni is not None and sni != request.url.host:
            raise _blocked("TLS SNI override differs from the allowed original hostname")
        return super().handle_request(request)


def create_direct_transport(policy: dict[str, Any]) -> httpx.HTTPTransport:
    """返回开启证书/域名校验、忽略代理环境的严格直连传输。"""
    return _DirectHTTPTransport(policy)
