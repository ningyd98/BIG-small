"""JSONL索引保存官方划分，派生验证集只按完整episode/scene分组。"""

from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any


def group_key(row: dict[str, Any]) -> str:
    identity = row.get("episode_id") or row.get("scene_id")
    if not identity:
        raise ValueError("sample requires episode_id or scene_id")
    return f"{row['dataset_id']}:{row.get('protocol', '')}:{row.get('task_id', '')}:{identity}"


def audit_splits(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, set[str]] = defaultdict(set)
    contents: dict[str, set[str]] = defaultdict(set)
    identities: dict[str, int] = defaultdict(int)
    for row in rows:
        split = row.get("split") or row.get("official_split") or "unknown"
        groups[group_key(row)].add(split)
        signature = row.get("content_sha256") or (
            f"{row.get('source_sha256')}:{row['frame_index']}:{row['camera_id']}"
        )
        if row.get("source_sha256") or row.get("content_sha256"):
            contents[signature].add(split)
        identities[f"{group_key(row)}:{row['frame_index']}:{row['camera_id']}"] += 1
    conflicts = {key: sorted(value) for key, value in groups.items() if len(value) > 1}
    duplicates = {key: sorted(value) for key, value in contents.items() if len(value) > 1}
    repeated = {key: count for key, count in identities.items() if count > 1}
    return {
        "valid": not (conflicts or duplicates or repeated),
        "groups": len(groups),
        "samples": len(rows),
        "group_conflicts": conflicts,
        "content_conflicts": duplicates,
        "duplicate_ids": repeated,
    }


def build_index(
    rows: list[dict[str, Any]],
    path: Path,
    *,
    validation_fraction: float = 0.2,
    seed: int = 20261003,
) -> dict[str, Any]:
    if not rows:
        raise ValueError("dataset has no real indexed samples")
    if not 0 <= validation_fraction < 1:
        raise ValueError("validation fraction must be in [0,1)")
    original_audit = audit_splits(rows)
    # 上游异常保留于报告，不重命名官方成员来掩盖泄漏。
    train_groups = sorted({group_key(row) for row in rows if row.get("official_split") == "train"})
    random.Random(seed).shuffle(train_groups)
    count = min(max(len(train_groups) - 1, 0), int(len(train_groups) * validation_fraction))
    validation = set(train_groups[:count])
    output = []
    for row in rows:
        split = row.get("official_split") or "unknown"
        if split == "train" and group_key(row) in validation:
            split = "derived_val"
        identity = (
            f"{row['source_revision']}:{group_key(row)}:{row['frame_index']}:{row['camera_id']}"
        )
        output.append(
            {**row, "split": split, "sample_id": hashlib.sha256(identity.encode()).hexdigest()[:32]}
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.with_suffix(path.suffix + ".partial")
    stage.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in output))
    stage.replace(path)
    report = {
        "index": str(path.resolve()),
        "seed": seed,
        "validation_fraction": validation_fraction,
        "derived_validation_groups": sorted(validation),
        "official_audit": original_audit,
        "audit": audit_splits(output),
    }
    path.with_suffix(".splits.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    return report


def load_index(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        raise ValueError("index is empty; no synthetic fallback is permitted")
    return rows
