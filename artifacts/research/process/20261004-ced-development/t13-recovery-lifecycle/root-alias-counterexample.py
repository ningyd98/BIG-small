"""Frozen action tolerance alias probe, SOFTWARE_ONLY, no transaction or dispatch."""
from dataclasses import replace
import json
from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository
from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
from tests.test_recovery_lifecycle_module import detected_record,authorization_proof
repo=InMemoryEventAutonomyRepository();original=authorization_proof(detected_record(repo))
tolerances={"nested":{"source":"original"}}
action=replace(original.action,preconditions=(ConditionSpec("target_visible",target_id="obj-1",tolerances=tolerances),))
proof=replace(original,action=action);before=proof.digest()
tolerances["nested"]["source"]="changed-after-proof-freeze"
print(json.dumps({"scope":"SOFTWARE_ONLY","frozen_action_changed_by_original_mapping":proof.digest()!=before,"physical_actions":0,"retry_consumed":0}))
