"""SOFTWARE_ONLY original packet and causal replay, never an authenticated provider.

The conditional intervals assume the chosen issuer's radius assertion is true.
Public tuples, local test signatures and pinned software do not establish native
application ownership, actual external acquisition or calibrated UTC accuracy.
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from cloud_edge_robot_arm.vision.worker_owner import pin_worker_source_inventory

DRAFT08 = "draft-ietf-ntp-roughtime-08"
BLIND_CONTEXT = b"BIGsmall native-clock-v2 commitment\x00"
QUANTIZATION_NS = 1_000_000_000


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _integer(value: Any, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError("original integer required, without boolean/coercion")
    return value


def _identifier(value: Any) -> str:
    if type(value) is not str or not value:
        raise ValueError("nonempty original identifier required")
    return value


def _sha(value: Any) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError("exact lowercase SHA256 required")
    return value


def _base64(value: Any, *, size: int | None = None) -> bytes:
    if type(value) is not str:
        raise ValueError("original base64 string required")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("malformed original base64") from error
    if base64.b64encode(raw).decode() != value or (size is not None and len(raw) != size):
        raise ValueError("canonical original base64/length required")
    return raw


def _shape(payload: Any, names: set[str]) -> dict[str, Any]:
    if type(payload) is not dict or set(payload) != names:
        raise ValueError("complete exact original schema required")
    return dict(payload)


@dataclass(frozen=True)
class ClockTupleV2:
    clock_domain_id: str
    sequence: int
    mono_before_ns: int
    utc_at: datetime
    mono_after_ns: int

    def __post_init__(self) -> None:
        _identifier(self.clock_domain_id)
        _integer(self.sequence, 1)
        _integer(self.mono_before_ns)
        _integer(self.mono_after_ns)
        if self.mono_after_ns < self.mono_before_ns:
            raise ValueError("reversed original pair bracket")
        if type(self.utc_at) is not datetime or self.utc_at.tzinfo is None:
            raise ValueError("aware original UTC sample required")
        if self.utc_at.utcoffset() != UTC.utcoffset(self.utc_at):
            raise ValueError("UTC original sample required")

    def to_payload(self) -> dict[str, Any]:
        return {**asdict(self), "utc_at": self.utc_at.isoformat()}

    def digest(self) -> str:
        return hashlib.sha256(canonical_bytes(self.to_payload())).hexdigest()

    @classmethod
    def from_payload(cls, payload: Any) -> ClockTupleV2:
        data = _shape(payload, {field.name for field in fields(cls)})
        if type(data["utc_at"]) is not str:
            raise ValueError("original ISO UTC string required")
        data["utc_at"] = datetime.fromisoformat(data["utc_at"])
        return cls(**data)


@dataclass(frozen=True)
class ClockExchangeOriginalV2:
    clock_domain_id: str
    exchange_id: str
    request_b64: str
    response_b64: str
    public_key_b64: str
    commitment_b64: str
    previous_reply_b64: str
    source_blind_b64: str
    effective_blind_b64: str
    send_before_ns: int
    send_after_ns: int
    receive_before_ns: int
    receive_after_ns: int
    verified_before_ns: int
    verified_after_ns: int

    def __post_init__(self) -> None:
        _identifier(self.clock_domain_id)
        _identifier(self.exchange_id)
        for name in ("request_b64", "response_b64", "previous_reply_b64"):
            _base64(getattr(self, name))
        for name in ("public_key_b64", "commitment_b64", "source_blind_b64", "effective_blind_b64"):
            _base64(getattr(self, name), size=32)
        times = [getattr(self, field.name) for field in fields(self) if field.name.endswith("_ns")]
        if any(_integer(value) != value for value in times) or times != sorted(times):
            raise ValueError("original send/receive/verify brackets must be ordered")

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: Any) -> ClockExchangeOriginalV2:
        return cls(**_shape(payload, {field.name for field in fields(cls)}))


@dataclass(frozen=True)
class SignatureDiagnosticsV2:
    protocol: str
    midpoint_unix_s: int
    radius_s: int
    native_authority: str = "UNAVAILABLE"
    utc_calibration: str = "UNAVAILABLE"


class GoWireVerifierV2:
    """Pinned local verifier; the constructor authenticates no app or issuer."""

    def __init__(
        self,
        binary: Path,
        *,
        binary_sha256: str,
        source_root: Path,
        source_hashes: Mapping[str, str],
    ) -> None:
        self.binary = Path(binary)
        self.binary_sha256 = _sha(binary_sha256)
        self.source_root = Path(source_root)
        self.source_hashes = MappingProxyType(dict(source_hashes))
        self._revalidate()

    def _revalidate(self) -> None:
        if any(p.is_symlink() for p in (self.binary.absolute(), *self.binary.absolute().parents)):
            raise ValueError("verifier lexical symlink rejected")
        if (
            not self.binary.is_file()
            or hashlib.sha256(self.binary.read_bytes()).hexdigest() != self.binary_sha256
        ):
            raise ValueError("pinned verifier binary changed")
        pin_worker_source_inventory(
            self.source_root,
            self.source_hashes,
            required_paths=frozenset(self.source_hashes),
        )

    def _invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._revalidate()
        completed = subprocess.run(
            [str(self.binary)],
            input=canonical_bytes(payload),
            capture_output=True,
            timeout=10,
            check=False,
        )
        self._revalidate()
        if completed.returncode != 0:
            raise ValueError("official wire verification rejected original packet")
        try:
            value = json.loads(completed.stdout)
        except (ValueError, TypeError) as error:
            raise ValueError("malformed pinned verifier output") from error
        if type(value) is not dict:
            raise ValueError("exact pinned verifier diagnostics required")
        return value

    def verify(
        self, request_b64: str, response_b64: str, public_key_b64: str
    ) -> SignatureDiagnosticsV2:
        _base64(request_b64)
        _base64(response_b64)
        _base64(public_key_b64, size=32)
        result = _shape(
            self._invoke(
                {
                    "op": "verify",
                    "request_b64": request_b64,
                    "response_b64": response_b64,
                    "public_key_b64": public_key_b64,
                }
            ),
            {"protocol", "midpoint_unix_s", "radius_s"},
        )
        if result["protocol"] != DRAFT08:
            raise ValueError("sole explicit draft08 diagnostics required")
        _integer(result["midpoint_unix_s"])
        _integer(result["radius_s"])
        return SignatureDiagnosticsV2(**result)


def slab_commitment(pairs: Sequence[ClockTupleV2], *, acquisition_sha256: str) -> bytes:
    if any(type(pair) is not ClockTupleV2 for pair in pairs):
        raise ValueError("exact detached original tuples required")
    return hashlib.sha256(
        canonical_bytes(
            {
                "schema_version": "native.clock.causal-slab.v2",
                "acquisition_sha256": _sha(acquisition_sha256),
                "pairs": [pair.to_payload() for pair in pairs],
            }
        )
    ).digest()


def _request_nonce(request: bytes) -> bytes:
    """Read original nonce for commitment replay; official verifier checks wire."""
    if len(request) < 16 or request[:8] != b"ROUGHTIM":
        raise ValueError("strict draft08 original framing required")
    if int.from_bytes(request[8:12], "little") != len(request) - 12:
        raise ValueError("original frame length changed")
    message = request[12:]
    count = int.from_bytes(message[:4], "little")
    header = count * 8
    if count < 1 or header > len(message):
        raise ValueError("original tag header malformed")
    offsets = [0] + [
        int.from_bytes(message[4 + i * 4 : 8 + i * 4], "little") for i in range(count - 1)
    ]
    offsets.append(len(message) - header)
    tags_at = count * 4
    tags = [message[tags_at + i * 4 : tags_at + (i + 1) * 4] for i in range(count)]
    if tags.count(b"NONC") != 1:
        raise ValueError("one original nonce required")
    index = tags.index(b"NONC")
    nonce = message[header + offsets[index] : header + offsets[index + 1]]
    if len(nonce) != 32:
        raise ValueError("draft08 nonce length required")
    return nonce


def _verify_chain(exchange: ClockExchangeOriginalV2) -> None:
    effective = hashlib.sha512(
        BLIND_CONTEXT
        + _base64(exchange.source_blind_b64, size=32)
        + _base64(exchange.commitment_b64, size=32)
    ).digest()[:32]
    if effective != _base64(exchange.effective_blind_b64, size=32):
        raise ValueError("original commitment/blinding changed")
    nonce = hashlib.sha512(
        hashlib.sha512(_base64(exchange.previous_reply_b64)).digest() + effective
    ).digest()[:32]
    if nonce != _request_nonce(_base64(exchange.request_b64)):
        raise ValueError("original nonce chain does not bind commitment")


@dataclass(frozen=True)
class CausalSlabDiagnosticsV2:
    conditional_pair_utc_intervals: tuple[tuple[str, int, int], ...]
    reasons: tuple[str, ...]
    native_authority: str = "UNAVAILABLE"
    utc_calibration: str = "UNAVAILABLE"
    issuer_accuracy: str = "CONDITIONAL_UNVERIFIED_ASSERTION"


def verify_causal_slab(
    pairs: Sequence[ClockTupleV2],
    before: ClockExchangeOriginalV2,
    after: ClockExchangeOriginalV2,
    verifier: GoWireVerifierV2,
    *,
    acquisition_sha256: str,
) -> CausalSlabDiagnosticsV2:
    """Recompute software signatures and conditional enclosure for all pairs.

    Same-domain event brackets still require the later app-owned collector.
    This public replay does not certify those events occurred or issuer accuracy.
    """
    try:
        if (
            type(before) is not ClockExchangeOriginalV2
            or type(after) is not ClockExchangeOriginalV2
            or type(verifier) is not GoWireVerifierV2
            or not pairs
            or before.exchange_id == after.exchange_id
        ):
            raise ValueError("complete distinct original exchange/pair inventory required")
        sampled_pairs = tuple(pairs)
        if any(type(pair) is not ClockTupleV2 for pair in sampled_pairs):
            raise ValueError("exact original clock tuple required")
        pairs = tuple(ClockTupleV2.from_payload(pair.to_payload()) for pair in sampled_pairs)
        before = ClockExchangeOriginalV2.from_payload(before.to_payload())
        after = ClockExchangeOriginalV2.from_payload(after.to_payload())
        if before.clock_domain_id != after.clock_domain_id or any(
            pair.clock_domain_id != before.clock_domain_id for pair in pairs
        ):
            raise ValueError("one actual process clock domain required")
        if before.public_key_b64 != after.public_key_b64:
            raise ValueError("one frozen issuer key required")
        if [pair.sequence for pair in pairs] != sorted({pair.sequence for pair in pairs}):
            raise ValueError("complete unique ordered pair sequence required")
        if any(
            a.mono_after_ns > b.mono_before_ns for a, b in zip(pairs[:-1], pairs[1:], strict=True)
        ):
            raise ValueError("original pair monotonic order reversed")
        if any(
            not before.verified_after_ns
            <= pair.mono_before_ns
            <= pair.mono_after_ns
            <= after.send_before_ns
            for pair in pairs
        ):
            raise ValueError("verified A / pair / sent B causal bracket unavailable")
        if after.previous_reply_b64 != before.response_b64:
            raise ValueError("B does not bind original A reply")
        if _base64(after.commitment_b64, size=32) != slab_commitment(
            pairs,
            acquisition_sha256=acquisition_sha256,
        ):
            raise ValueError("B does not bind complete original acquisition slab")
        _verify_chain(before)
        _verify_chain(after)
        first = verifier.verify(before.request_b64, before.response_b64, before.public_key_b64)
        last = verifier.verify(after.request_b64, after.response_b64, after.public_key_b64)
        lower = (first.midpoint_unix_s - first.radius_s) * 10**9 - QUANTIZATION_NS
        upper = (last.midpoint_unix_s + last.radius_s) * 10**9 + QUANTIZATION_NS
        if lower > upper:
            raise ValueError("issuer conditional UTC intervals reversed")
        return CausalSlabDiagnosticsV2(tuple((pair.digest(), lower, upper) for pair in pairs), ())
    except (ValueError, TypeError, OSError, subprocess.SubprocessError) as error:
        return CausalSlabDiagnosticsV2((), (str(error),))
