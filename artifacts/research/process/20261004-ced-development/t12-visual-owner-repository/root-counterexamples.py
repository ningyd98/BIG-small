"""Derived SOFTWARE_ONLY source probes; no actual owner, model or action."""
import json
import tempfile
from pathlib import Path

from cloud_edge_robot_arm.contracts import RecoveryBudget
from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudget, VerificationBudgetState
from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import SQLiteEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import VisualOwnerPublicationRecord, canonical, digest
from tests.test_visual_owner_repository import fresh_source_values

def prepare(kind):
    repo = InMemoryEventAutonomyRepository() if kind == 'memory' else SQLiteEventAutonomyRepository(Path(tempfile.mkdtemp(prefix='owner-source-probe-')) / 'event.db')
    data = fresh_source_values()
    original, checkpoint = data['original'], data['source_checkpoint']
    state = VerificationBudgetState(3,2,0,original.verification_deadline_at,VerificationBudget(3,2,3,40.0))
    retry = RecoveryBudget(budget_id='original-retry-pool',task_id=original.identity.task_id,task_total_retry_limit=2,per_step_retry_limit=1,per_skill_retry_limit=2,effective_retry_limit=2,remaining_retries=2,retry_deadline=original.verification_deadline_at,scene_version=original.contract.scene_version,created_at=original.registered_at,updated_at=original.registered_at)
    record = repo.initialize_visual_owner_if_absent(original,checkpoint,state,retry)
    assert repo.get_visual_owner_publication(original.identity.task_id).digest() == record.digest()
    return repo,original,record

out = []
for backend in ('memory','sqlite'):
    for name, branch, key, value in [
        ('checkpoint_bool','checkpoint','plan_version',True),
        ('checkpoint_float','checkpoint','command_seq',1.0),
        ('checkpoint_extra','checkpoint','unregistered_policy','ignored'),
        ('retry_bool','retry_budget','retry_count_used',False),
        ('retry_extra','retry_budget','unregistered_policy','ignored'),
    ]:
        repo, original, record = prepare(backend)
        payload = record.to_payload()
        payload[branch][key] = value
        payload.pop('publication_hash')
        payload['publication_hash'] = digest(payload)
        row = {'backend':backend,'probe':name,'source_scope':'SOFTWARE_ONLY'}
        try:
            changed = VisualOwnerPublicationRecord.from_payload(payload)
        except (ValueError,TypeError) as error:
            row.update(constructor_rejected=True,error_type=type(error).__name__)
        else:
            row['constructor_rejected'] = False
            if backend == 'memory':
                repo._visual_publications[(original.identity.task_id,1)] = canonical(payload)
            else:
                repo._conn.execute('UPDATE visual_owner_publications SET payload_json=?,publication_hash=? WHERE task_id=? AND owner_revision=1',(canonical(payload),payload['publication_hash'],original.identity.task_id))
                repo._conn.commit()
            try:
                current = repo.get_visual_owner_publication(original.identity.task_id)
                row['current_getter_accepts'] = current is not None
                if current is not None:
                    row['retained_serialized_value'] = current.to_payload()[branch].get(key)
            except (ValueError,TypeError) as error:
                row.update(current_getter_accepts=False,error_type=type(error).__name__)
        out.append(row)
        if backend == 'sqlite':
            repo.close()
print(json.dumps(out,indent=2))
