#!/usr/bin/env python
"""契约样例校验脚本，确保文档中的任务契约能被当前模型解析。"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cloud_edge_robot_arm.contracts import TaskContract  # noqa: E402
from cloud_edge_robot_arm.edge.contract_validator import EdgeContractValidator  # noqa: E402


@dataclass(frozen=True)
class ContractExampleValidationResult:
    valid_total: int
    invalid_total: int
    valid_failures: list[str]
    invalid_failures: list[str]

    @property
    def success(self) -> bool:
        return not self.valid_failures and not self.invalid_failures


def _load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def validate_contract_examples(base_dir: Path) -> ContractExampleValidationResult:
    valid_dir = base_dir / "valid"
    invalid_dir = base_dir / "invalid"
    valid_paths = sorted(valid_dir.glob("*.json"))
    invalid_paths = sorted(invalid_dir.glob("*.json"))
    valid_failures: list[str] = []
    invalid_failures: list[str] = []

    for path in valid_paths:
        payload = _load_json(path)
        try:
            contract = TaskContract.model_validate(payload)
        except Exception as exc:
            valid_failures.append(f"{path.name}: schema rejected valid example: {exc}")
            continue
        result = EdgeContractValidator(min_plan_version=1).accept_payload(
            contract.model_dump(mode="json"),
            now=contract.issued_at,
        )
        if not result.accepted:
            valid_failures.append(f"{path.name}: edge validator rejected valid example")

    for path in invalid_paths:
        payload = _load_json(path)
        try:
            contract = TaskContract.model_validate(payload)
        except Exception:
            continue
        result = EdgeContractValidator(min_plan_version=1).accept_payload(
            contract.model_dump(mode="json"),
            now=contract.valid_until,
        )
        if result.accepted:
            invalid_failures.append(f"{path.name}: invalid example was accepted")

    return ContractExampleValidationResult(
        valid_total=len(valid_paths),
        invalid_total=len(invalid_paths),
        valid_failures=valid_failures,
        invalid_failures=invalid_failures,
    )


def main() -> int:
    result = validate_contract_examples(ROOT / "contracts" / "examples")
    print(
        json.dumps(
            {
                "valid_total": result.valid_total,
                "invalid_total": result.invalid_total,
                "valid_failures": result.valid_failures,
                "invalid_failures": result.invalid_failures,
                "success": result.success,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if result.success and result.valid_total >= 5 and result.invalid_total >= 5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
