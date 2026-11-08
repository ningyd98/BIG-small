"""Offline classification of one R495 response; never calls a service."""
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
import sys

REPO = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
BASE = REPO / 'artifacts/research/process/20261004-ced-development/astra-rounds'
OUT = BASE / 'round495-persisted-sol-real-rgbd-retest-20261108'
PLAN = json.loads((OUT / 'plan.json').read_text())
for pin in PLAN['input_pins']:
    data = (REPO / pin['path']).read_bytes()
    assert len(data) == pin['bytes'] and hashlib.sha256(data).hexdigest() == pin['sha256']
schema = REPO / 'src/cloud_edge_robot_arm/contracts/models.py'
assert hashlib.sha256(schema.read_bytes()).hexdigest() == '75dedc466273ba1f02301de9880b3db533265e27c5de5c2576c7fa3859f36516'
sys.path.insert(0, str(REPO / 'src'))
from cloud_edge_robot_arm.contracts.models import TaskContract
from cloud_edge_robot_arm.vision.planner import VisualDecision

receipt = json.loads((OUT / 'http-receipt.json').read_text())
raw = Path(receipt['response_local_path']).read_bytes()
assert len(raw) == receipt['response_bytes'] and hashlib.sha256(raw).hexdigest() == receipt['response_sha256']
checks = {}


def check(name, condition):
    checks[name] = bool(condition)


def sequence(skills):
    skills = list(skills)
    if skills and skills[0] == 'HOME':
        skills.pop(0)
    if skills and skills[-1] == 'HOME':
        skills.pop()
    return skills == ['MOVE_ABOVE', 'APPROACH', 'GRASP', 'LIFT', 'MOVE_TO_REGION', 'PLACE', 'RELEASE', 'RETREAT']


def approx(actual, expected, tolerance):
    return isinstance(actual, list) and len(actual) == len(expected) and all(type(a) in (int, float) and math.isfinite(a) and abs(a-b) <= tolerance for a,b in zip(actual, expected))


lower = datetime.fromisoformat(receipt['started_utc']) - timedelta(seconds=1)
upper = datetime.fromisoformat(receipt['ended_utc']) + timedelta(seconds=1)


def interval(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.tzinfo is not None and lower <= parsed <= upper
    except (ValueError, TypeError):
        return False


result = {'round': 'R495', 'post_attempts': receipt['post_attempts'], 'http_status': receipt['http_status'], 'elapsed_seconds': receipt['elapsed_seconds'], 'response_bytes': len(raw), 'response_sha256': receipt['response_sha256'], 'request_interval': {'lower_utc': lower.isoformat(), 'upper_utc': upper.isoformat()}, 'provider_wire_call_count_measured': None, 'provider_inference_requests_source_ceiling': 1, 'actual_tokens': None, 'actual_cost': None, 'local_repairs_measured': None, 'local_deterministic_repairs_source_ceiling': 2, 'normal_render_passes_source_inferred': 2, 'render_passes_measured': None, 'formal_research_R469': 'NOT_RUN', 'retry': 0, 'fallback': 0}
body = None
try:
    body = json.loads(raw)
except (ValueError, UnicodeError):
    pass
check('http_complete_json_object', receipt['complete'] and receipt['http_status'] == 200 and isinstance(body, dict))
if not isinstance(body, dict):
    result['classification'] = receipt.get('classification', 'INVALID_JSON')
else:
    result['parse_result'] = body.get('parse_result')
    result['reason'] = body.get('reason') if isinstance(body.get('reason'), str) else None
    for field, expected in {'input_mode': 'RGBD', 'evaluation_scope': 'RGBD_PLANNING_ONLY', 'provider_kind': 'OPENAI_COMPATIBLE', 'model_name': 'gpt-6.1-sol'}.items():
        check('envelope_' + field, body.get(field) == expected)
    for field in ('dispatch', 'hardware_execution'):
        check('envelope_' + field, body.get(field) is False)
    check('validation_errors_list', isinstance(body.get('validation_errors'), list))
    observation = body.get('observation')
    if not isinstance(observation, dict):
        observation = {}
    result['observation'] = observation
    for field, expected in {'source': 'mujoco_camera', 'scene_id': 'S01_NORMAL_STATIC', 'sim_time_s': 0, 'width': 320, 'height': 240, 'depth_convention': 'optical_z_m', 'model_image_count': 2, 'calibration_version': 'f33940579c533afe'}.items():
        check('observation_' + field, observation.get(field) == expected)
    check('observation_no_ground_truth_control', observation.get('ground_truth_used_for_control') is False)
    for field in ('episode_id', 'frame_id', 'observation_id', 'calibration_version'):
        check('observation_nonempty_' + field, isinstance(observation.get(field), str) and bool(observation[field]))
    check('observation_frame_id_agreement', bool(observation.get('frame_id')) and observation.get('frame_id') == observation.get('observation_id'))
    for field in ('checksum_sha256', 'rgb_sha256', 'depth_sha256'):
        check('observation_hash_' + field, isinstance(observation.get(field), str) and re.fullmatch('[0-9a-f]{64}', observation[field]) is not None)
    check('observation_capture_interval', interval(observation.get('captured_at')))
    check('observation_intrinsics', approx(observation.get('intrinsics'), [257.34083046114705, 257.34083046114705, 159.5, 119.5], 1e-6))
    check('observation_camera_to_world', approx(observation.get('camera_to_world'), [1,0,0,0.35,0,-1,0,0,0,0,-1,1.4,0,0,0,1], 1e-9))
    decision = None
    text = body.get('raw_planner_output')
    try:
        if isinstance(text, str) and text:
            decision = VisualDecision.model_validate_json(text, strict=True)
    except ValueError:
        pass
    check('strict_visual_schema', decision is not None)
    if decision is not None:
        result['visual_decision'] = decision.model_dump(mode='json')
        for field in ('target_pixel', 'destination_pixel'):
            point = getattr(decision, field)
            check('visual_normalized_' + field, isinstance(point, tuple) and len(point) == 2 and all(type(v) is int and 0 <= v <= 1000 for v in point))
        check('visual_confidence', decision.reported_confidence >= 0.5)
        check('visual_skill_sequence', sequence(decision.skills))
        label = re.sub(r'[_\s-]+', ' ', decision.target_label.casefold()).strip()
        check('visual_target_semantic_red_cube', label in ('red cube', 'cube red', '红色方块', '红色立方体'))
    contract = None
    final = body.get('final_contract')
    try:
        if isinstance(final, dict):
            contract = TaskContract.model_validate_json(json.dumps(final), strict=True)
    except ValueError:
        pass
    check('parse_result_planned', body.get('parse_result') == 'PLANNED')
    check('validation_errors_empty', body.get('validation_errors') == [])
    check('strict_task_contract_schema', contract is not None)
    if contract is not None:
        result['contract_summary'] = {field: final.get(field) for field in ('control_mode', 'task_id', 'plan_version', 'command_seq', 'scene_version', 'expected_scene_version', 'issued_at', 'valid_until', 'timestamp', 'user_instruction', 'task_target')}
        result['contract_summary']['skills'] = [str(step.skill) for step in contract.steps]
        check('contract_control_mode', str(contract.control_mode) == 'PERIODIC_CLOUD_SUPERVISION')
        check('contract_instruction', contract.user_instruction == PLAN['request']['user_instruction'])
        check('contract_object_id', contract.task_target.object_id == 'visual_target')
        check('contract_destination_id', contract.task_target.target_region_id == 'visual_destination')
        check('contract_object_class', decision is not None and contract.task_target.object_class == decision.target_label)
        check('contract_scene_version', contract.scene_version == contract.expected_scene_version == 1)
        check('contract_plan_command_version', contract.plan_version == contract.command_seq == 1)
        check('contract_task_id', isinstance(contract.task_id, str) and bool(contract.task_id))
        check('contract_skill_sequence', decision is not None and [str(step.skill) for step in contract.steps] == decision.skills and sequence([str(step.skill) for step in contract.steps]))
        check('contract_issued_interval', interval(final.get('issued_at')))
        check('contract_validity_order', contract.valid_until > contract.issued_at)
        check('contract_timestamp', contract.timestamp == contract.issued_at)
    if body.get('parse_result') == 'PLANNED':
        result['classification'] = 'PLANNED_INTEGRATION' if all(checks.values()) else 'INTEGRATION_EVIDENCE_MISMATCH'
    elif body.get('parse_result') in ('PLANNER_FAILED', 'REQUEST_MORE_OBSERVATION', 'BLOCKED_BY_ENV'):
        result['classification'] = body['parse_result']
    else:
        result['classification'] = 'UNEXPECTED_RESULT'
result['predicates'] = checks
result['all_positive_predicates_passed'] = all(checks.values())
result['failed_predicates'] = [name for name, passed in checks.items() if not passed]
result['evidence_limits'] = ['API excludes full RGB/depth bytes and instance/grounding truth; hashes and calibration only.', 'Provider wire count, usage/cost, actual local repairs and render count are not exposed.', 'Integration planning only; no dispatch, hardware action or nominal research qualification.']
with (OUT / 'integration-result.json').open('x') as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print(json.dumps({'classification': result['classification'], 'parse_result': result.get('parse_result'), 'failed_predicates': result['failed_predicates'], 'http_status': receipt['http_status'], 'post_attempts': receipt['post_attempts'], 'elapsed_seconds': receipt['elapsed_seconds']}, ensure_ascii=False))
