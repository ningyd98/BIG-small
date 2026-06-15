from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IsaacCommand:
    command_type: str
    payload: dict[str, object]
    command_seq: int


@dataclass(frozen=True)
class IsaacStatus:
    status: str
    sim_time_s: float
    message: str
