"""Thread-safe append-only application costs; no tokens or invented wire overhead."""

from __future__ import annotations

import threading
from collections import Counter
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RequestCost(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_id: str = Field(min_length=1)
    sent_at: datetime | None
    finished_at: datetime | None
    is_cloud_model: bool
    model_role: Literal["PLANNER", "SUPERVISOR", "REPLANNER", "JUDGE"]
    deployment: Literal["EDGE", "CLOUD"]
    provider_location: Literal["LOCAL_HOST", "REMOTE_SERVICE"]
    provider_version: str = Field(min_length=1)
    status: Literal["IN_FLIGHT", "SUCCESS", "ERROR", "TIMEOUT", "CANCELLED"]
    serialized_sent_bytes: int = Field(ge=0)
    serialized_received_bytes: int = Field(ge=0)
    monetary_cost: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_identity(self) -> RequestCost:
        if self.is_cloud_model != (self.deployment == "CLOUD"):
            raise ValueError("is_cloud_model must agree with logical deployment")
        if self.provider_location == "REMOTE_SERVICE" and self.deployment != "CLOUD":
            raise ValueError("remote model judgment belongs in the cloud total")
        if (self.finished_at is not None and self.finished_at.tzinfo is None) or (
            self.sent_at is not None and self.sent_at.tzinfo is None
        ):
            raise ValueError("request timestamps must be timezone-aware")
        if self.sent_at is None and (
            self.serialized_sent_bytes or self.serialized_received_bytes
        ):
            raise ValueError("unsent cancellation cannot have wire bytes")
        if (self.sent_at is not None and self.finished_at is not None
                and self.finished_at < self.sent_at):
            raise ValueError("request cannot finish before it was sent")
        if (self.status == "IN_FLIGHT") != (self.finished_at is None):
            raise ValueError("only in-flight requests have no finish timestamp")
        return self


class CostSnapshot(BaseModel):
    model_requests: int = 0
    cloud_model_requests: int = 0
    requests_by_role: dict[str, int] = Field(default_factory=dict)
    telemetry_messages: int = 0
    application_bytes: int = 0
    queue_s: float = 0
    inference_s: float | None = None
    provider_roundtrip_s: float = 0
    network_s: float = 0
    commit_check_s: float = 0
    switch_s: float = 0
    latency_scope: Literal["MEASURED_COMPONENT_SUM"] = "MEASURED_COMPONENT_SUM"

    @property
    def decision_latency_s(self) -> float:
        return sum((self.queue_s, self.inference_s or 0, self.provider_roundtrip_s,
                    self.network_s, self.commit_check_s,
                    self.switch_s))


class CostLedger:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._requests: dict[str, RequestCost] = {}
        self._telemetry_messages = self._telemetry_bytes = 0
        self._timings: dict[str, float | None] = dict.fromkeys(
            ("queue_s", "provider_roundtrip_s", "network_s", "commit_check_s", "switch_s"), 0.0
        )
        self._timings["inference_s"] = None

    def record_request(self, cost: RequestCost) -> None:
        # Revalidate also model_copy/update inputs; an update must not bypass invariants.
        cost = RequestCost.model_validate(cost.model_dump())
        with self._lock:
            old = self._requests.get(cost.request_id)
            if old is not None and old != cost:
                identity = ("request_id", "sent_at", "is_cloud_model", "model_role", "deployment",
                            "provider_location", "provider_version", "serialized_sent_bytes")
                if old.status != "IN_FLIGHT" or any(
                    getattr(old, key) != getattr(cost, key) for key in identity
                ):
                    raise ValueError("conflicting request cost with the same attempt ID")
            self._requests[cost.request_id] = cost

    def record_telemetry(self, sent_bytes: int, received_bytes: int) -> None:
        if min(sent_bytes, received_bytes) < 0:
            raise ValueError("telemetry bytes must be nonnegative")
        with self._lock:
            self._telemetry_messages += 1
            self._telemetry_bytes += sent_bytes + received_bytes

    def record_timing(self, **values: float) -> None:
        import math

        if any(k not in self._timings or not math.isfinite(v) or v < 0 for k, v in values.items()):
            raise ValueError("timings must name finite nonnegative measured components")
        with self._lock:
            for key, value in values.items():
                self._timings[key] = (self._timings[key] or 0) + value

    def requests(self) -> tuple[RequestCost, ...]:
        with self._lock:
            return tuple(self._requests.values())

    def export(self) -> dict:
        """Publish request rows and totals from one locked ledger state."""
        with self._lock:
            return {"summary": self.snapshot().model_dump(),
                    "requests": [r.model_dump(mode="json") for r in self._requests.values()]}

    def snapshot(self) -> CostSnapshot:
        with self._lock:
            sent = [row for row in self._requests.values() if row.sent_at is not None]
            return CostSnapshot.model_validate({
                "model_requests": len(sent),
                "cloud_model_requests": sum(row.is_cloud_model for row in sent),
                "requests_by_role": dict(Counter(row.model_role for row in sent)),
                "telemetry_messages": self._telemetry_messages,
                "application_bytes": self._telemetry_bytes + sum(
                    row.serialized_sent_bytes + row.serialized_received_bytes for row in sent
                ),
                **self._timings,
            })
