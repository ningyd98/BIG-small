"""合成网络流量验证物理接口约束；不访问公网、不读取系统 DNS。"""

from __future__ import annotations

import importlib
import socket
import ssl
import struct

import httpx
import pytest


def network():
    try:
        return importlib.import_module("cloud_edge_robot_arm.datasets.external.network")
    except ModuleNotFoundError:
        pytest.fail("物理接口直连传输尚未实现")


def policy(**changes):
    return {
        "mode": "direct",
        "interface": "enp7s0",
        "dns_servers": ["223.5.5.5", "223.6.6.6"],
        "allowed_hosts": ["hf-mirror.com", "cdn.example.com"],
        **changes,
    }


def dns_response(query, address="8.8.8.8", *, transaction=None, question=None, flags=0x8180):
    identity = query[:2] if transaction is None else struct.pack("!H", transaction)
    question = query[12:] if question is None else question
    answer = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 30, 4) + socket.inet_aton(address)
    return identity + struct.pack("!HHHHH", flags, 1, 1, 0, 0) + question + answer


class SyntheticSocket:
    """仅在边界模拟内核 socket，生产传输和 DNS 解析仍执行。"""

    def __init__(self, kind, *, denied=False, dns_transform=None, response_source=None):
        self.kind = kind
        self.denied = denied
        self.dns_transform = dns_transform
        self.response_source = response_source
        self.events = []
        self.bound = b""
        self.peer = None
        self.query = b""
        self.closed = False
        self.response = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"

    def setsockopt(self, level, option, value):
        self.events.append(("setsockopt", level, option, value))
        if option == socket.SO_BINDTODEVICE:
            if self.denied:
                raise PermissionError("synthetic_fixture missing bind capability")
            self.bound = value

    def getsockopt(self, level, option, length=0):
        assert option == socket.SO_BINDTODEVICE
        return self.bound

    def settimeout(self, timeout):
        self.events.append(("timeout", timeout))

    def connect(self, peer):
        assert self.bound == b"enp7s0\x00", "socket must be bound BEFORE DNS/TCP connect"
        self.events.append(("connect", peer))
        self.peer = peer

    def send(self, payload):
        self.events.append(("send", payload))
        if self.kind == socket.SOCK_DGRAM:
            self.query = payload
        return len(payload)

    def sendall(self, payload):
        self.send(payload)

    def recvfrom(self, size):
        result = dns_response(self.query)
        if self.dns_transform:
            result = self.dns_transform(self.query)
        return result, self.response_source or self.peer

    def recv(self, size):
        result, self.response = self.response[:size], self.response[size:]
        return result

    def getpeername(self):
        return self.peer

    def getsockname(self):
        return ("192.168.3.221", 12345)

    def close(self):
        self.closed = True


@pytest.fixture
def mod(monkeypatch):
    result = network()
    monkeypatch.setattr(result, "_require_physical_interface", lambda interface: None)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: pytest.fail("system DNS used"))
    monkeypatch.setattr(socket, "gethostbyname", lambda *a, **kw: pytest.fail("system DNS used"))
    return result


def install_sockets(monkeypatch, **changes):
    sockets = []

    def factory(family, kind, *args, **kwargs):
        assert family == socket.AF_INET
        result = SyntheticSocket(kind, **changes)
        sockets.append(result)
        return result

    monkeypatch.setattr(socket, "socket", factory)
    return sockets


def test_dns_and_tcp_bind_before_connect_without_system_dns(mod, monkeypatch):
    sockets = install_sockets(monkeypatch)
    backend = mod.DirectNetworkBackend(policy())
    stream = backend.connect_tcp("hf-mirror.com", 443, timeout=2)
    assert [sock.kind for sock in sockets] == [socket.SOCK_DGRAM, socket.SOCK_STREAM]
    assert sockets[0].peer == ("223.5.5.5", 53)
    assert sockets[1].peer == ("8.8.8.8", 443)
    assert all(sock.bound == b"enp7s0\x00" for sock in sockets)
    assert sockets[0].closed
    stream.close()
    assert sockets[1].closed


def test_bind_permission_failure_closes_and_has_no_fallback(mod, monkeypatch):
    sockets = install_sockets(monkeypatch, denied=True)
    with pytest.raises(mod.NetworkPolicyError, match="BLOCKED_NETWORK"):
        mod.DirectNetworkBackend(policy()).connect_tcp("hf-mirror.com", 443)
    assert len(sockets) == 1
    assert sockets[0].closed
    assert not any(event[0] == "connect" for event in sockets[0].events)


@pytest.mark.parametrize(
    "address", ["198.18.0.8", "198.19.1.2", "127.0.0.1", "10.0.0.1", "0.0.0.0"]
)
def test_rejects_fake_or_private_fixed_addresses(mod, address):
    with pytest.raises(mod.NetworkPolicyError, match="BLOCKED_NETWORK"):
        mod.validate_network_policy(policy(host_addresses={"hf-mirror.com": [address]}))


def test_rejects_fake_ip_dns_answer_before_tcp(mod, monkeypatch):
    sockets = install_sockets(
        monkeypatch, dns_transform=lambda query: dns_response(query, "198.18.0.8")
    )
    with pytest.raises(mod.NetworkPolicyError, match="BLOCKED_NETWORK"):
        mod.DirectNetworkBackend(policy()).connect_tcp("hf-mirror.com", 443)
    assert all(sock.kind == socket.SOCK_DGRAM for sock in sockets)


@pytest.mark.parametrize(
    "changes",
    [
        {"mode": "proxy"},
        {"interface": "../Meta"},
        {"allowed_hosts": ["*.example.com"]},
        {"dns_servers": ["resolver.example.com"]},
        {"dns_servers": ["127.0.0.1"]},
        {"allowed_hosts": []},
        {"host_addresses": {"unknown.example.com": ["8.8.8.8"]}},
    ],
)
def test_invalid_policy_is_fail_closed(mod, changes):
    with pytest.raises(mod.NetworkPolicyError, match="BLOCKED_NETWORK"):
        mod.validate_network_policy(policy(**changes))


@pytest.mark.parametrize(
    "url",
    [
        "https://unreviewed.example.com/file",
        "http://hf-mirror.com/file",
        "https://secret@hf-mirror.com/file",
        "https://hf-mirror.com:8443/file",
        "https://hf-mirror.com.evil.example/file",
    ],
)
def test_unknown_redirect_and_credentials_block_before_socket(mod, monkeypatch, url):
    sockets = install_sockets(monkeypatch)
    with pytest.raises(mod.NetworkPolicyError, match="BLOCKED_NETWORK"):
        with httpx.Client(
            transport=mod.create_direct_transport(policy()), trust_env=False
        ) as client:
            client.get(url)
    assert sockets == []


@pytest.mark.parametrize(
    "transform",
    [
        lambda query: dns_response(
            query, transaction=(int.from_bytes(query[:2], "big") + 1) % 65536
        ),
        lambda query: dns_response(query, question=b"\x03bad\x03com\x00\x00\x01\x00\x01"),
        lambda query: dns_response(query, flags=0x8380),
        lambda query: dns_response(query, flags=0x8183),
        lambda query: query[:2] + struct.pack("!HHHHH", 0x8180, 1, 1, 0, 0) + b"\xc0\x0c",
    ],
)
def test_malformed_or_mismatched_dns_is_rejected(mod, monkeypatch, transform):
    sockets = install_sockets(monkeypatch, dns_transform=transform)
    with pytest.raises(mod.NetworkPolicyError, match="BLOCKED_NETWORK"):
        mod.DirectNetworkBackend(policy()).connect_tcp("hf-mirror.com", 443)
    assert all(sock.kind == socket.SOCK_DGRAM and sock.closed for sock in sockets)


def test_dns_response_source_must_match_explicit_resolver(mod, monkeypatch):
    sockets = install_sockets(monkeypatch, response_source=("8.8.4.4", 53))
    with pytest.raises(mod.NetworkPolicyError, match="BLOCKED_NETWORK"):
        mod.DirectNetworkBackend(policy()).connect_tcp("hf-mirror.com", 443)
    assert all(sock.kind == socket.SOCK_DGRAM for sock in sockets)


def test_explicit_mapping_avoids_dns_but_keeps_original_tls_sni_and_verification(mod, monkeypatch):
    sockets = install_sockets(monkeypatch)
    transport = mod.create_direct_transport(policy(host_addresses={"hf-mirror.com": ["8.8.8.8"]}))
    assert transport._pool._ssl_context.verify_mode == ssl.CERT_REQUIRED
    assert transport._pool._ssl_context.check_hostname is True
    names = []

    class SyntheticTLSContext:
        def set_alpn_protocols(self, protocols):
            assert protocols == ["http/1.1"]

        def wrap_socket(self, sock, server_hostname=None):
            names.append(server_hostname)
            return sock

    transport._pool._ssl_context = SyntheticTLSContext()
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7890")
    with httpx.Client(transport=transport) as client:
        response = client.get("https://hf-mirror.com/file")
    assert response.content == b"ok"
    assert names == ["hf-mirror.com"]
    assert len(sockets) == 1
    assert sockets[0].peer == ("8.8.8.8", 443)


def test_tls_sni_override_cannot_escape_hostname_policy(mod, monkeypatch):
    sockets = install_sockets(monkeypatch)
    with httpx.Client(transport=mod.create_direct_transport(policy()), trust_env=False) as client:
        with pytest.raises(mod.NetworkPolicyError, match="BLOCKED_NETWORK"):
            client.get(
                "https://hf-mirror.com/file", extensions={"sni_hostname": "evil.example.com"}
            )
    assert sockets == []


def test_virtual_loopback_interface_is_rejected_without_network():
    with pytest.raises(network().NetworkPolicyError, match="BLOCKED_NETWORK"):
        network().validate_network_policy(policy(interface="lo"))


def test_followed_redirect_cannot_leave_allowlist(mod, monkeypatch):
    sockets = install_sockets(monkeypatch)
    transport = mod.create_direct_transport(policy(host_addresses={"hf-mirror.com": ["8.8.8.8"]}))

    class SyntheticRedirectTLS:
        def set_alpn_protocols(self, protocols):
            pass

        def wrap_socket(self, sock, server_hostname=None):
            sock.response = (
                b"HTTP/1.1 302 Found\r\nContent-Length: 0\r\nConnection: close\r\n"
                b"Location: https://unreviewed.example.com/file\r\n\r\n"
            )
            return sock

    transport._pool._ssl_context = SyntheticRedirectTLS()
    with httpx.Client(transport=transport, trust_env=False, follow_redirects=True) as client:
        with pytest.raises(mod.NetworkPolicyError, match="BLOCKED_NETWORK"):
            client.get("https://hf-mirror.com/file")
    assert len(sockets) == 1
    assert sockets[0].closed


def test_dns_cname_compression_resolves_only_requested_chain(mod, monkeypatch):
    def cname_response(query):
        alias = b"\x03cdn\x07example\x03com\x00"
        cname = b"\xc0\x0c" + struct.pack("!HHIH", 5, 1, 30, len(alias)) + alias
        alias_offset = len(query) + 12
        pointer = struct.pack("!H", 0xC000 | alias_offset)
        address = pointer + struct.pack("!HHIH", 1, 1, 30, 4) + socket.inet_aton("8.8.8.8")
        return query[:2] + struct.pack("!HHHHH", 0x8180, 1, 2, 0, 0) + query[12:] + cname + address

    sockets = install_sockets(monkeypatch, dns_transform=cname_response)
    stream = mod.DirectNetworkBackend(policy()).connect_tcp("hf-mirror.com", 443)
    assert sockets[-1].peer == ("8.8.8.8", 443)
    stream.close()


def test_tcp_bind_permission_failure_uses_no_proxy_or_system_dns(mod, monkeypatch):
    sockets = install_sockets(monkeypatch, denied=True)
    backend = mod.DirectNetworkBackend(policy(host_addresses={"hf-mirror.com": ["8.8.8.8"]}))
    with pytest.raises(mod.NetworkPolicyError, match="BLOCKED_NETWORK"):
        backend.connect_tcp("hf-mirror.com", 443)
    assert len(sockets) == 1
    assert sockets[0].kind == socket.SOCK_STREAM
    assert sockets[0].closed
    assert not any(event[0] == "connect" for event in sockets[0].events)


def test_fake_ip_from_first_resolver_blocks_without_second_resolver_fallback(mod, monkeypatch):
    responses = 0

    def first_fake_then_valid(query):
        nonlocal responses
        responses += 1
        return dns_response(query, "198.18.0.1" if responses == 1 else "8.8.8.8")

    sockets = install_sockets(monkeypatch, dns_transform=first_fake_then_valid)
    with pytest.raises(mod.NetworkPolicyError, match="BLOCKED_NETWORK"):
        mod.DirectNetworkBackend(policy()).connect_tcp("hf-mirror.com", 443)
    assert len(sockets) == 1
    assert sockets[0].closed
