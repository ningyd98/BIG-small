"""Bounded SOFTWARE_ONLY probes against the frozen774 worker/compiler overlay."""
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import tempfile

from cloud_edge_robot_arm.vision.worker_owner import (
    WorkerLeaseObservation, compile_worker_original_plan,
    grounded_worker_effect_conditions, pin_worker_source_inventory,
)
from tests.test_visual_worker_owner import running, read, compilation, effect_values

records = []

def good(name, check):
    check()
    records.append({'name': name, 'result': 'PASS', 'scope': 'SOFTWARE_ONLY'})

def closed(name, operation):
    try:
        operation()
    except (ValueError, TypeError) as error:
        records.append({'name': name, 'result': 'REJECTED', 'error': type(error).__name__,
                        'reason': str(error), 'scope': 'SOFTWARE_ONLY'})
    else:
        raise AssertionError(name + ' unexpectedly accepted')

case_root = Path(tempfile.mkdtemp(prefix='worker-independent-matrix-'))
case_root.mkdir(exist_ok=True)
data = running.__wrapped__(case_root)
repo, stale, lease, attempt = data
source = read(data)
assert stale.attempt == 0 and source.attempt == 1
assert source.scope == 'WORKER_LEASE_SOURCE_ONLY'
assert not any(hasattr(source, x) for x in ('execution_admitted', 'method_accepted', 'native_certificate'))
good('current attempt reread and scope remains source-only', lambda: None)
closed('observed before open attempt starts', lambda: read(data, now=attempt.started_at-timedelta(microseconds=1)))
closed('observed before lease acquisition', lambda: read(data, now=lease.acquired_at-timedelta(microseconds=1)))
closed('exact expiry closed', lambda: read(data, now=lease.expires_at))
closed('positive attempt rejects bool', lambda: replace(source, attempt=True))
closed('source rejects naive observation', lambda: replace(source, observed_at=source.observed_at.replace(tzinfo=None)))
closed('source rejects malformed state hash', lambda: replace(source, job_state_hash='source-only'))

compiled_data = compilation(data)
original = compile_worker_original_plan(**compiled_data)
assert [x.step_id for x in original.dependencies] == [x.step_id for x in original.contract.steps]
assert original.dependencies[0].depends_on == ()
assert original.dependencies[1].depends_on == (original.contract.steps[0].step_id,)
assert all(not x.completed for x in original.dependencies)
assert all(r.sensor_requirements == ('rgbd',) and r.ordinary_ttl_s == 5.0 for r in original.requirements.values())
assert all(r.original_step.retry_limit == s.retry_limit and r.original_step.timeout_ms == s.timeout_ms
           for s in original.contract.steps for r in [original.requirements[s.step_id]])
assert original.effective_deadline_at == compiled_data['verification_deadline_at']
before = original.digest()
compiled_data['contract'].steps[0].parameters['object_id'] = 'mutation'
compiled_data['source_hashes']['injected.py'] = 'f'*64
assert original.digest() == before
assert 'injected.py' not in original.source_hashes
good('ordered original graph full original requirements deadlines and aliases frozen', lambda: None)

# One ordered eight-skill contract independently checks shared and original policy fields.
from cloud_edge_robot_arm.contracts import SkillName
full_data = compilation(data)
base_step = full_data['contract'].steps[0]
skills = (SkillName.MOVE_ABOVE, SkillName.APPROACH, SkillName.GRASP, SkillName.LIFT,
          SkillName.MOVE_TO_REGION, SkillName.PLACE, SkillName.RELEASE, SkillName.RETREAT)
post_required = ({'tcp_at_resolved_target'}, {'tcp_at_resolved_target'}, {'gripper_holding'},
                 {'gripper_holding','tcp_at_resolved_target','object_lifted','object_stable'},
                 {'gripper_holding','tcp_at_resolved_target'}, {'gripper_holding','tcp_at_resolved_target'},
                 {'gripper_released'}, {'gripper_released','tcp_at_resolved_target'})
steps = [base_step.model_copy(update={'step_id': f'ordered-{i}', 'skill': skill,
         'preconditions': ['target_visible'], 'success_conditions': ['tcp_above_target'],
         'retry_limit': 2, 'timeout_ms': 17000, 'expected_duration_ms': 12000}, deep=True)
         for i,skill in enumerate(skills)]
safety = full_data['contract'].safety_constraints.model_copy(update={'minimum_safe_height': .21})
full_data['contract'] = full_data['contract'].model_copy(update={'steps': steps, 'safety_constraints': safety}, deep=True)
full = compile_worker_original_plan(**full_data)
for i,step in enumerate(full.contract.steps):
    requirement = full.requirements[step.step_id]
    assert requirement.original_step.model_dump(mode='json') == steps[i].model_dump(mode='json')
    assert {'tcp_above_target'} | post_required[i] <= {c.name for c in requirement.postconditions}
    assert 'target_visible' in {c.name for c in requirement.preconditions}
    assert requirement.ordinary_ttl_s == 5 and requirement.allowed_error_m == .01
    assert requirement.expected_duration_s == 17
    assert requirement.sensor_requirements == ('rgbd',)
    assert dict(requirement.compiler_source_hashes) == dict(full_data['source_hashes'])
    for condition in (*requirement.preconditions,*requirement.postconditions):
        assert condition.tolerances['minimum_safe_height'] == .21
        assert condition.tolerances['max_age_s'] == 5
        assert condition.tolerances['calibration_version'] == full_data['observation'].calibration_version
    assert full.dependencies[i].depends_on == (() if i==0 else (steps[i-1].step_id,))
    assert full.dependencies[i].evidence_ids == (full_data['observation'].observation_id,)
    assert full.dependencies[i].completed is False
good('all eight skills in one ordered graph preserve full policy and original semantics', lambda: None)

class CallerLease(WorkerLeaseObservation):
    pass
forged = CallerLease(**{k:v for k,v in source.__dict__.items()})
subclass_data = compilation(data)
subclass_data['lease_source'] = forged
closed('caller lease subclass cannot compile', lambda: compile_worker_original_plan(**subclass_data))
for field in ('task_deadline_at', 'verification_deadline_at'):
    values = compilation(data)
    values[field] = values['registered_at']
    closed('nonfuture original '+field, lambda values=values: compile_worker_original_plan(**values))

original, binding = effect_values(data)
before = original.digest()
for kind, coordinates in [
    ('bool', {'x': True, 'y': .1, 'z': .16}),
    ('huge-int', {'x': 10**500, 'y': .1, 'z': .16}),
    ('numeric-string', {'x': '0.2', 'y': .1, 'z': .16}),
    ('nonfinite', {'x': float('inf'), 'y': .1, 'z': .16}),
    ('extra-coordinate', {'x': .2, 'y': .1, 'z': .16, 'w': 1}),
]:
    def altered(coordinates=coordinates):
        step = binding.grounded_step
        step.parameters['target_pose'] = coordinates
        updated = replace(binding, _grounded_step_json=json.dumps(step.model_dump(mode='json')))
        return grounded_worker_effect_conditions(original, updated)
    closed('strict bound pose '+kind, altered)
closed('grounded binding beyond original absolute deadline', lambda: grounded_worker_effect_conditions(
    original, replace(binding, valid_until=original.effective_deadline_at+timedelta(microseconds=1))))
closed('grounded binding before original registration', lambda: grounded_worker_effect_conditions(
    original, replace(binding, created_at=original.registered_at-timedelta(microseconds=1))))
conditions = grounded_worker_effect_conditions(original, binding)
tcp = next(x for x in conditions if x.name == 'tcp_at_resolved_target')
assert [tcp.tolerances['target_'+axis] for axis in 'xyz'] == [.2,.1,.16]
assert original.digest() == before
assert not any(hasattr(tcp,x) for x in ('verdict','accepted','execution_admitted','certificate'))
good('exact target pose instantiates only check inputs and preserves original template', lambda: None)

sources = case_root / 'pin-root'
sources.mkdir()
(sources/'s.py').write_text('VALUE=1\n', encoding='utf-8')
sha = hashlib.sha256((sources/'s.py').read_bytes()).hexdigest()
expected={'s.py':sha}
pinned = pin_worker_source_inventory(sources, expected, required_paths={'s.py'})
expected['s.py']='f'*64
assert pinned['s.py']==sha
good('pinned input map copied immutable and local only', lambda: None)
closed('changed source bytes', lambda: pin_worker_source_inventory(sources, {'s.py':'f'*64}, required_paths={'s.py'}))
closed('noncanonical source filename', lambda: pin_worker_source_inventory(sources, {'./s.py':sha}, required_paths={'./s.py'}))
closed('filename parent traversal', lambda: pin_worker_source_inventory(sources, {'../s.py':sha}, required_paths={'../s.py'}))
(sources/'file-alias.py').symlink_to(sources/'s.py')
closed('lexical source file alias', lambda: pin_worker_source_inventory(sources, {'file-alias.py':sha}, required_paths={'file-alias.py'}))
(case_root/'root-alias').symlink_to(sources, target_is_directory=True)
closed('direct lexical root alias', lambda: pin_worker_source_inventory(case_root/'root-alias', {'s.py':sha}, required_paths={'s.py'}))
(sources/'ancestor-alias').symlink_to(sources, target_is_directory=True)
closed('lexical source ancestor alias', lambda: pin_worker_source_inventory(sources, {'ancestor-alias/s.py':sha}, required_paths={'ancestor-alias/s.py'}))

print(json.dumps({'scope':'SOFTWARE_ONLY', 'count':len(records), 'records':records,
                  'actual_factory_created':False, 'actual_execution_admitted':False,
                  'provider_requests':0, 'simulator_or_controller_calls':0}, indent=2, sort_keys=True))
