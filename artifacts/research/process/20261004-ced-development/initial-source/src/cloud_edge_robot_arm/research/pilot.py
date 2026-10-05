"""Foundation pilot report; absent baseline successes block timeout freeze."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np


def derive_tcap(successful_b0_durations_s: list[float]) -> int:
    if not successful_b0_durations_s:
        raise ValueError("no B0 successes; Tcap freeze is BLOCKED")
    if any(not math.isfinite(v) or v <= 0 for v in successful_b0_durations_s):
        raise ValueError("successful durations must be positive finite measured seconds")
    p99 = float(np.quantile(successful_b0_durations_s, .99))
    return min(600, max(120, math.ceil(2 * p99 / 10) * 10))


@dataclass
class PilotReport:
    assigned: int
    records: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        successes = [row for row in self.records if row.get("success", False)]
        return {
            "assigned": self.assigned, "recorded": len(self.records),
            "unrecorded": self.assigned - len(self.records),
            "succeeded": len(successes),
            "blocked": sum(bool(row.get("blocked")) for row in self.records),
            "success_rate_all_assigned": len(successes) / self.assigned if self.assigned else None,
            "tcap_derivable": len(self.records) == self.assigned and bool(successes)
                            and not any(row.get("blocked") for row in self.records),
            # Only the independent evidence verifier can accept a protocol.
            "freeze_ready": False,
        }
