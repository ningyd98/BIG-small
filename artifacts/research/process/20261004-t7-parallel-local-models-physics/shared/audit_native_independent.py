"""CPU-only independent audit of Molmo2 retained calls, transport and 3D scoring.

Never invokes inference or an endpoint. Does not import the existing scoring helper.
The preserved runtime adapter is used only to reproduce its complete decision gate;
point parsing, image hashes, deprojection and percentile arithmetic are independent.
"""
from __future__ import annotations
import base64
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import struct
import sys
from collections import Counter
from datetime import UTC, datetime

os.environ['CUDA_VISIBLE_DEVICES'] = ''
sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parents[1]
SNAPSHOT = BASE / 'source-snapshot'
BANK = BASE / 'shared/scene-bank'
MOLMO = BASE / 'molmo'
sys.path[:0] = [str(SNAPSHOT), str(SNAPSHOT / 'src')]
from PIL import Image
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter, VisualDecision
from cloud_edge_robot_arm.vision.messages import build_visual_messages
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot
from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
from cloud_edge_robot_arm.vision.top_grasp import CALIBRATED_ASSET_SHA256


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(value, message):
    if not value:
        raise AssertionError(message)


def close(a, b):
    return a is None and b is None or (a is not None and b is not None and math.isclose(a, b, rel_tol=1e-11, abs_tol=1e-10))


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * q
    lo, hi = math.floor(rank), math.ceil(rank)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


def clean_terminal(raw):
    text = raw.strip()
    for terminal in ('<|im_end|>', '<|endoftext|>'):
        if text.endswith(terminal):
            text = text[:-len(terminal)].strip()
    return text


def parse_points(raw):
    """Independent strict normalized-1000 grammar, without magnitude heuristics."""
    tags = list(re.finditer(r'<points\b[^>]*\bcoords="([^"]*)"[^>]*>', raw))
    if not tags:
        require(clean_terminal(raw).upper() == 'ABSENT', 'neither points nor literal ABSENT')
        return []
    rows = []
    for tag in tags:
        for group in re.split(r'[\t:;,]', tag.group(1)):
            fields = group.strip().split()
            require(fields and all(re.fullmatch(r'\d+', x) for x in fields), 'malformed coordinate group')
            ints = [int(x) for x in fields]
            require(len(ints) >= 4 and (len(ints) - 1) % 3 == 0 and 1 <= ints[0] <= 2, 'invalid IDs/triples')
            for offset in range(1, len(ints), 3):
                object_id, x, y = ints[offset:offset + 3]
                require(0 <= x <= 1000 and 0 <= y <= 1000, 'normalized coordinate outside declared range')
                rows.append({'image_index': ints[0] - 1, 'object_id': object_id, 'normalized_1000': [x, y], 'pixel_xy': None})
    return rows


def localization(raw):
    points = parse_points(raw)
    rgb = [p for p in points if p['image_index'] == 0]
    contradictory = bool(re.search(r'\bABSENT\b', raw, re.IGNORECASE)) and bool(points)
    status = ('invalid' if contradictory else 'absent' if clean_terminal(raw).upper() == 'ABSENT' else
              'ambiguous' if len(rgb) > 1 else 'localized' if len(rgb) == 1 else 'unavailable')
    return status, rgb[0]['normalized_1000'] if status == 'localized' else None, points


def deproject(case_dir, normalized):
    if normalized is None:
        return {'pixel': None, 'world': None, 'geom_label': None}
    require(isinstance(normalized, list) and len(normalized) == 2 and all(type(x) is int and 0 <= x <= 1000 for x in normalized), 'non-strict normalized point')
    meta = read(case_dir / 'initial-offline/observation.json')
    width, height = meta['width'], meta['height']
    x, y = min(width - 1, normalized[0] * width // 1000), min(height - 1, normalized[1] * height // 1000)
    index = y * width + x
    z = struct.unpack_from('<f', (case_dir / 'initial-offline/depth.f32').read_bytes(), 4 * index)[0]
    mask = (case_dir / 'initial-offline/valid_mask.u8').read_bytes()[index]
    geom = struct.unpack_from('<i', (case_dir / 'initial-offline/instance_geom_ids.i32').read_bytes(), 4 * index)[0]
    label = meta['instance_labels'].get(str(geom))
    if not mask or not math.isfinite(z) or z <= 0:
        return {'pixel': [x, y], 'world': None, 'geom_label': label}
    fx, fy, cx, cy = meta['intrinsics']
    ray = [(x - cx) * z / fx, (y - cy) * z / fy, z]
    matrix = meta['camera_to_world']
    world = [sum(matrix[4 * row + col] * ray[col] for col in range(3)) + matrix[4 * row + 3] for row in range(3)]
    return {'pixel': [x, y], 'world': world, 'geom_label': label}


def load_gate():
    path = MOLMO / 'v1-exact-source-archive/native_adapter.py'
    spec = importlib.util.spec_from_file_location('audited_archived_gate', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def replay_decision(decision, observation, instruction, latency, model):
    snapshot = ModelConfigSnapshot(provider='openai_compatible', model=model, endpoint='http://127.0.0.1:11439',
        weight_digest='', quantization='NATIVE_RESEARCH', image_size=(320, 240), generation_parameters={'temperature': 0, 'num_predict': 256},
        timeout_s=180, coordinate_system='normalized_1000', grasp_profile='mujoco_upright_box_v1')
    planner = RGBDPlannerAdapter(model=model, provider='openai_compatible', model_snapshot=snapshot)
    planner._post = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('offline replay tried an endpoint'))
    request = InitialPlanningRequest(request_id='independent-offline-audit', user_instruction=instruction, observation=observation,
        scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)))
    messages = build_visual_messages(instruction, observation, image_size=(320, 240), coordinate_system='normalized_1000', decision_schema=VisualDecision.model_json_schema())
    response = {'choices': [{'message': {'content': json.dumps(decision)}}]}
    draft = planner._ground_response(request, response, round(latency * 1000), observation, messages, (320, 240), 'normalized_1000', 'mujoco_upright_box_v1')
    evidence = draft.observation_evidence
    tcp = evidence.get('resolved_top_grasp_tcp')
    calibrated = (evidence.get('top_grasp_offset_status') == 'CALIBRATED_RGBD_TOP_GRASP_V1' and
        evidence.get('grasp_profile') == 'mujoco_upright_box_v1' and evidence.get('grasp_calibration_asset_sha256') == CALIBRATED_ASSET_SHA256 and
        isinstance(tcp, dict) and set(tcp) == {'x', 'y', 'z'} and all(type(v) in (int, float) and math.isfinite(v) for v in tcp.values()))
    return {'parse_error': draft.parse_error, 'observed_scene_present': draft.observed_scene is not None,
        'parsed_json_present': draft.parsed_json is not None, 'calibrated_offset': calibrated}


def audit_run(version, bank, gate):
    run = MOLMO / ('development-full20-' + version)
    scores = MOLMO / ('development-full20-v1-offline-scores' if version == 'v1' else 'development-full20-v2-offline-scores-corrected')
    protocol = read(run / 'protocol.json')
    core = {k: v for k, v in protocol.items() if k != 'protocol_sha256'}
    require(hashlib.sha256(json.dumps(core, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest() == protocol['protocol_sha256'], 'protocol digest mismatch')
    require(protocol['bank_manifest_sha256'] == sha(BANK / 'bank-manifest.json'), 'wrong bank manifest')
    require(protocol['source_snapshot_manifest_sha256'] == sha(BASE / 'source-snapshot-manifest.json'), 'wrong source manifest')
    bridge = MOLMO / ('v1-exact-source-archive/native_bridge.py' if version == 'v1' else 'native_bridge.py')
    require(sha(bridge) == protocol['bridge_sha256'] and sha(MOLMO / 'v1-exact-source-archive/native_adapter.py') == protocol['adapter_sha256'], 'runtime bytes changed')
    for key, filename in [('model_source_metadata_sha256', 'Molmo2-4B-metadata-response.json'), ('dependency_downloads_sha256', 'dependency-downloads.json'), ('environment_freeze_sha256', 'environment-freeze.txt')]:
        require(sha(MOLMO / filename) == protocol[key], 'runtime dependency drift: ' + key)
    require(protocol['case_count'] == 20 and protocol['planned_calls_per_task'] == 3 and protocol['ground_truth_used_online'] is False, 'planned allocation changed')
    require([a['case_id'] for a in protocol['allocation']] == [c['case_id'] for c in bank['cases']], 'allocation/order changed')
    existing = {row['case_id']: row for row in read(scores / 'results.json')}
    result_rows, calls_total, invalid_proposals = [], 0, []
    contract_errors = Counter()
    for case, allocated in zip(bank['cases'], protocol['allocation']):
        key = case['case_id']; path = BANK / 'cases' / key
        require(allocated['transport_sha256'] == sha(path / 'observation-transport.json') and allocated['instruction'] == case['instruction'], 'input prebinding changed')
        obs = RGBDObservation.model_validate(read(path / 'observation-transport.json'))
        result = read(run / (key + '.json'))
        require(result['case_id'] == key and result['protocol_sha256'] == protocol['protocol_sha256'], 'result binding changed')
        for field in ('model', 'precision', 'method', 'adapter_sha256', 'bridge_sha256', 'gpu_lease'):
            require(result[field] == protocol[field], 'runtime identity drift: ' + field)
        require(result['source']['metadata_sha256'] == protocol['model_source_metadata_sha256'] and result['source']['weights_verified'] is True and result['source']['files_verified'] == 26, 'model source identity changed')
        require(result['observation'] == obs.evidence() == allocated['observation'], 'observation evidence changed')
        require(result['ground_truth_used_online'] is False and result['call_count'] == 3 and [c['role'] for c in result['calls']] == ['target', 'destination', 'evidence'], 'online boundary/calls changed')
        expected_images = []
        for i, (role, encoded) in enumerate([('RGB', obs.rgb_png_base64), ('DEPTH', obs.depth_png_base64())]):
            im = Image.open(io.BytesIO(base64.b64decode(encoded, validate=True))).convert('RGB')
            expected_images.append({'index': i, 'role': role, 'size': list(im.size), 'mode': 'RGB', 'decoded_rgb_pixel_sha256': hashlib.sha256(im.tobytes()).hexdigest()})
        input_evidence = {'image_count': 2, 'images': expected_images, 'observation_binding': {k: getattr(obs, k) for k in ('frame_id', 'observation_id', 'checksum_sha256')}}
        for call in result['calls']:
            role = call['role']; journal_key = key + '.' + role
            require(call['input_images'] == input_evidence, 'actual dual-image pixel binding mismatch')
            require(len(call['raw_token_ids']) == call['output_token_count'] and all(type(t) is int for t in call['raw_token_ids']), 'raw token accounting differs')
            require(case['instruction'] in call['prompt_text'] and call['generation'] == {'max_new_tokens': 256 if role == 'evidence' else 160, 'do_sample': False, 'num_beams': 1, 'native_logits_processor': False}, 'prompt/inference settings changed')
            require(call['cloud_invoice_cny'] == 0 and call['local_energy_cost_cny'] is None, 'unsupported costs')
            for phase in ('started', 'generated', 'completed'):
                journal = read(run / 'attempts' / (journal_key + '.' + phase + '.json'))
                require(journal['protocol_sha256'] == protocol['protocol_sha256'] and journal['phase'] == phase and journal['key'] == journal_key, 'call journal binding changed')
                if phase == 'completed':
                    require(journal['payload'] == call, 'completed call differs from retained literal response')
                elif phase == 'generated':
                    require(all(call[k] == v for k, v in journal['payload'].items()), 'raw generation mutated after receipt')
                else:
                    require(journal['payload']['input_images'] == input_evidence and journal['payload']['prompt_text'] == call['prompt_text'], 'started call differs')
            calls_total += 1
            if role != 'evidence':
                status, point, points = localization(call['raw_text'])
                require(call['localization']['status'] == status and call['localization']['point'] == point and call['localization']['native_points'] == points, 'independent native parsing differs')
                require(call['localization']['raw_text'] == call['raw_text'] and call['localization']['raw_token_ids'] == call['raw_token_ids'], 'localization altered raw response')
                if status == 'invalid' and points:
                    invalid_proposals.append({'case_id': key, 'role': role, 'raw_points': points, 'reason': 'ABSENT word in retained raw text with point tags; coordinate proposal is rejected by frozen strict parser'})
            else:
                require(json.loads(clean_terminal(call['raw_text'])) == call.get('evidence'), 'free JSON evidence differs from raw text')
        metrics = result['task_metrics']; calls = result['calls']
        require(metrics['model_call_count'] == 3 and metrics['input_tokens_total'] == sum(c['input_token_count'] for c in calls) and metrics['output_tokens_total'] == sum(c['output_token_count'] for c in calls), 'task token/call aggregates differ')
        require(close(metrics['model_inference_total_s'], sum(c['inference_s'] for c in calls)) and close(metrics['call_latency_total_s'], sum(c['latency_s'] for c in calls)) and metrics['task_latency_s'] >= metrics['call_latency_total_s'], 'latency aggregates differ')
        for stem in ('allocated', 'reserved'):
            require(metrics['peak_torch_' + stem + '_bytes'] == max(c['max_memory_' + stem + '_bytes'] for c in calls), 'Torch memory metric differs')
        target, destination = [calls[i]['localization'] for i in (0, 1)]
        try:
            candidate = gate.build_visual_decision(target, destination, calls[2].get('evidence'))
            candidate = VisualDecision.model_validate(candidate).model_dump(mode='json')
            error = None
        except (ValueError, gate.NativeProtocolError) as exc:
            candidate, error = None, str(exc)
        require(candidate == result['visual_decision'] and error == result.get('contract_error'), 'complete model contract gate differs')
        require(result['execution_eligible'] == bool(candidate and candidate['skills']), 'eligibility differs')
        contract_errors[error or 'complete_model_decision'] += 1
        checks = [deproject(path, localization_result['point']) for localization_result in (target, destination)]
        hits = [check['world'] is not None and check['geom_label'] == label for check, label in zip(checks, ('object_geom', 'target_region_geom'))]
        truth = read(path / 'initial-truth.json')
        truth_target = next(t for t in truth['instances'] if t['role'] == 'target')
        top = [*truth_target['position'][:2], truth_target['position'][2] + truth_target['half_size'][2]]
        error_mm = math.dist(checks[0]['world'], top) * 1000 if checks[0]['world'] is not None else None
        replay = replay_decision(candidate, obs, case['instruction'], metrics['task_latency_s'], result['model']) if candidate is not None else None
        full = bool(replay and replay['parse_error'] is None and replay['observed_scene_present'] and replay['parsed_json_present'] and all(hits) and replay['calibrated_offset'])
        old = existing[key]
        require(old['target_hit'] == hits[0] and old['destination_hit'] == hits[1] and close(old['target_top_center_error_mm'], error_mm) and old['full_contract_geometry_pass'] == full, 'independent offline arithmetic/contract replay differs')
        for role, check in zip(('target', 'destination'), checks):
            require(old[role + '_offline_check']['pixel'] == check['pixel'] and old[role + '_offline_check']['geom_label'] == check['geom_label'], 'pixel/geometry differs')
            require(old[role + '_offline_check']['world'] == check['world'], 'actual depth deprojection differs')
        result_rows.append({'case_id': key, 'kind': case['kind'], 'result_sha256': sha(run / (key + '.json')), 'target_hit': hits[0], 'destination_hit': hits[1],
            'target_top_center_error_mm': error_mm, 'full_contract_geometry_pass': full, 'target_status': target['status'], 'destination_status': destination['status'],
            'task_latency_s': metrics['task_latency_s'], 'contract_error': error, 'offline_standard_adapter_replay': replay})
    require(len(list((run / 'attempts').glob('*.failed.json'))) == 0 and calls_total == 60, 'missing or failed actual calls')
    positives = [r for r in result_rows if r['kind'] == 'positive']
    fixed = [r for r in result_rows if r['kind'] == 'FIXED_S01']
    absent = [r for r in result_rows if r['kind'] == 'negative_absent']
    conditional = [r['target_top_center_error_mm'] for r in positives if r['target_hit']]
    all_valid = [r['target_top_center_error_mm'] for r in positives if r['target_top_center_error_mm'] is not None]
    summary = {'recorded_cases': 20, 'all_actual_model_calls': calls_total, 'positive_target_hit': sum(r['target_hit'] for r in positives),
        'positive_both_hit': sum(r['target_hit'] and r['destination_hit'] for r in positives), 'fixed_both_hit': sum(r['target_hit'] and r['destination_hit'] for r in fixed),
        'fixed_full_contract_geometry_pass': sum(r['full_contract_geometry_pass'] for r in fixed), 'positive_full_contract_geometry_pass': sum(r['full_contract_geometry_pass'] for r in positives),
        'negative_native_explicit_absence': sum(r['target_status'] == 'absent' for r in absent), 'negative_native_point_proposals': sum(r['target_status'] == 'localized' for r in absent),
        'target_hit_conditional_P90_mm': percentile(conditional, .9), 'target_hit_conditional_coverage': f'{len(conditional)}/12',
        'all_valid_point_P90_mm': percentile(all_valid, .9), 'all_valid_point_coverage': f'{len(all_valid)}/12',
        'warm_task_latency_P95_s': percentile([r['task_latency_s'] for r in result_rows[1:]], .95)}
    old_summary = read(scores / 'summary.json')
    for key, value in summary.items():
        require(close(value, old_summary[key]) if type(value) is float else value == old_summary[key], 'reported aggregate differs: ' + key)
    require(old_summary['physical_task_success_rate'] is None and old_summary['physical_misoperation_rate'] is None and old_summary['physical_actions'] == 0 and old_summary['local_API_cost_CNY_per_task'] == 0 and old_summary['total_cost_CNY_per_task'] is None and old_summary['held_out_test'] is False and old_summary['formal_G1'] is False, 'unmeasured physical/cost scope misrepresented')
    return {'valid': True, 'protocol_file_sha256': sha(run / 'protocol.json'), 'runtime_bridge_sha256': sha(bridge), 'runtime_adapter_sha256': protocol['adapter_sha256'],
        'same_message_two_image_calls_verified': 60, 'raw_started_generated_completed_journals_verified': 180,
        'summary_sha256': sha(scores / 'summary.json'), 'summary': summary, 'contract_error_counts': dict(contract_errors),
        'invalid_raw_coordinate_proposals': invalid_proposals, 'cases': result_rows,
        'interpretation': 'Development evidence for this frozen three-call prototype. Full task/misoperation rates are unmeasured; does not establish that the base model is universally unsuitable.',
        'warm_latency_definition': 'Linear-interpolated P95 across prescribed cases 2 through 20; model load and first case excluded.'}


def main():
    os.chdir(SNAPSHOT)
    bank = read(BANK / 'bank-manifest.json')
    for relative, digest in bank['files'].items():
        require(sha(BANK / relative) == digest, 'immutable bank changed: ' + relative)
    manifest = read(BASE / 'source-snapshot-manifest.json')
    for relative, digest in manifest['source_sha256'].items():
        require(sha(SNAPSHOT / relative) == digest, 'immutable source changed: ' + relative)
    metadata = read(MOLMO / 'Molmo2-4B-metadata-response.json')
    verified_model_files = []
    for row in metadata['Data']['Files']:
        if row['Type'] != 'blob':
            continue
        path = MOLMO / 'models/Molmo2-4B' / row['Path']
        require(path.stat().st_size == row['Size'] and sha(path) == row['Sha256'], 'pinned model file changed: ' + row['Path'])
        verified_model_files.append({k: row[k] for k in ('Path', 'Revision', 'Sha256', 'Size')})
    gate = load_gate()
    runs = {version: audit_run(version, bank, gate) for version in ('v1', 'v2')}
    report = {'created_at': datetime.now(UTC).isoformat(), 'valid': True, 'audit_mode': 'CPU only, no inference, no endpoint requests, no physical actions',
        'audit_helper_sha256': sha(Path(__file__)), 'source_snapshot_files_verified': len(manifest['source_sha256']), 'bank_files_verified': len(bank['files']),
        'bank_manifest_sha256': sha(BANK / 'bank-manifest.json'), 'source_snapshot_manifest_sha256': sha(BASE / 'source-snapshot-manifest.json'),
        'pinned_model_files_verified': verified_model_files, 'runs': runs,
        'online_ground_truth_review': {'checked_runtime_files': ['molmo/v1-exact-source-archive/native_bridge.py', 'molmo/native_bridge.py', 'molmo/v1-exact-source-archive/native_adapter.py'],
            'findings': ['Runtime bank path reads case instruction and observation-transport.json; labels, masks and initial-truth are read only by offline scorers after retained model outputs.',
                'build_messages creates one user message containing text, decoded RGB image and aligned depth image; every recorded invocation is bound to matching decoded RGB pixel hashes.',
                'Complete VisualDecision uses only free model-generated evidence fields plus native localization. No instruction-derived label, imposed confidence, coordinate search or ground-truth repair.',
                'Model initialization verifies per-file pinned model source/weight sizes and SHA before local-only loading; full model files were independently rehashed by this audit.'],
            'limitation': 'Recorded receipts plus code review establish the experimental online boundary; this is not adversarial OS isolation proof.'},
        'standard_offline_adapter_signature': 'request, response, latency_ms, observation, messages, image_size, coordinate_system, grasp_profile',
        'cost_and_execution_scope': {'local_API_cost_CNY_per_task': 0, 'total_cost_CNY_per_task': None, 'physical_task_success_rate': None, 'physical_misoperation_rate': None, 'physical_actions': 0, 'held_out_test': False, 'formal_G1': False}}
    destination = BASE / 'shared/root-native-model-audit.json'
    with destination.open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'valid': True, 'report_sha256': sha(destination), 'cases': {v: r['summary'] for v, r in runs.items()}}, indent=2))


if __name__ == '__main__':
    main()
