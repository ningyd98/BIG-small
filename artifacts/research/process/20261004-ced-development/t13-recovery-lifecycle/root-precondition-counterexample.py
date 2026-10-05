"""SOFTWARE_ONLY pure authorization guard probe; no transaction or execution."""
from dataclasses import replace
from datetime import UTC,datetime
import json
from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository
from cloud_edge_robot_arm.contracts.models import replan_payload_hash
from cloud_edge_robot_arm.edge.recovery.lifecycle import authorization_reasons
from tests.test_recovery_lifecycle_module import detected_record,authorization_proof
repo=InMemoryEventAutonomyRepository();record=detected_record(repo);active=repo.get_active_contract("task")
steps=[s.model_copy(update={"preconditions":["target_visible"]}) if s.step_id==record.step_id else s for s in active.contract.steps]
contract=active.contract.model_copy(update={"steps":steps});h=replan_payload_hash(contract)
active=active.model_copy(update={"contract":contract,"contract_hash":h});record=replace(record,payload_hash=h)
proof=authorization_proof(record);proof=replace(proof,action=replace(proof.action,preconditions=()))
reasons=authorization_reasons(record,repo.get_verification_budget("task"),repo.get_retry_budget("task"),repo.get_event(record.event_id),active,repo.get_latest_execution_checkpoint("task"),False,proof,record.step_id,record.skill,datetime.now(UTC))
print(json.dumps({"scope":"SOFTWARE_ONLY","original_preconditions":["target_visible"],"proposed_preconditions":[],"authorization_reasons":reasons,"accepted_by_pure_guard":not reasons,"physical_actions":0,"retry_consumed":0}))
