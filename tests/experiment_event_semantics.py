"""实验测试的语义事件摘要；仅给随机模式事务身份建立一对一别名。"""

from cloud_edge_robot_arm.experiments.models import ExperimentEvent
from cloud_edge_robot_arm.experiments.reproducibility import stable_hash


def semantic_event_digest(
    events: list[ExperimentEvent], *, exclude_lifecycle: bool = False
) -> str:
    """保留顺序、时间、行为载荷及身份关联，不改原事件或其原始哈希。"""
    aliases: dict[str, str] = {}
    rows = []
    for event in events:
        if exclude_lifecycle and event.event_type in {"run_started", "run_completed"}:
            continue
        entity_id = event.entity_id
        if event.event_type in {
            "mode_transition_prepared",
            "mode_transition_deferred",
            "mode_transition_committed",
        }:
            entity_id = aliases.setdefault(entity_id, f"transition-{len(aliases)}")
        rows.append(
            {
                "t": event.virtual_time_ms,
                "event_type": event.event_type,
                "entity_id": entity_id,
                "payload": event.payload,
            }
        )
    return stable_hash(rows)
