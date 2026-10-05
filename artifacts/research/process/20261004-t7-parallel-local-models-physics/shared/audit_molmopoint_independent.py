"""CPU-only final MolmoPoint audit. No model construction, endpoint or rendering.

Executes the two unchanged official point-decoding functions extracted by AST
from the independently hashed pinned model source; all arrays remain CPU NumPy.
Uses separately audited helper functions for depth deprojection and offline
standard planner validation. Both auditing helper SHA values enter the report.
"""
from __future__ import annotations
import argparse
import ast
import base64
from collections import Counter
from datetime import UTC, datetime
import hashlib
import io
import json
import logging
import math
import os
from pathlib import Path
import re
import subprocess
import sys

os.environ['CUDA_VISIBLE_DEVICES'] = ''
sys.dont_write_bytecode = True
import numpy as np
from PIL import Image
import audit_native_independent as common
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.planner import VisualDecision

BASE, BANK, MOLMO = common.BASE, common.BANK, common.MOLMO
read, sha, require, close, percentile = common.read, common.sha, common.require, common.close, common.percentile


def official_decoder():
    path = MOLMO / 'models/MolmoPoint-8B/modeling_molmo_point.py'
    tree = ast.parse(path.read_text())
    selected = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in ('get_subpatch_ids', 'extract_image_points'):
            selected.append(node)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'EXTRACT_POINT_TRIPLE' for t in node.targets):
            selected.append(node)
    require(len(selected) == 3, 'official decoder selection changed')
    namespace = {'np': np, 're': re, 'logger': logging.getLogger('point_independent_audit')}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
    config = read(MOLMO / 'models/MolmoPoint-8B/config.json')
    def decode(raw, metadata):
        return namespace['extract_image_points'](raw, np.asarray(metadata['token_pooling']),
            [np.asarray(x) for x in metadata['subpatch_mapping']], config['no_more_points_class'],
            config['patch_location'], metadata['image_sizes'])
    return decode, {'model_source_sha256': sha(path), 'functions': ['get_subpatch_ids', 'extract_image_points'],
        'execution': 'unchanged official AST function nodes and regex assignment; CPU NumPy only; no module/model import or weight construction'}


def normalized_points(decoded, image_sizes):
    points = []
    for row in decoded:
        require(len(row) == 4, 'native row length differs')
        object_id, image_id, x, y = row
        require(type(object_id) is int and type(image_id) is int and 0 <= image_id < len(image_sizes), 'native image/object IDs are invalid')
        w, h = image_sizes[image_id]
        require(0 <= x <= w and 0 <= y <= h and math.isfinite(x) and math.isfinite(y), 'native pixel invalid')
        points.append({'image_index': image_id, 'object_id': object_id,
            'normalized_1000': [math.floor(float(x) * 1000 / w + .5), math.floor(float(y) * 1000 / h + .5)],
            'pixel_xy': [float(x), float(y)]})
    return points


def selected_localization(raw, points):
    rgb = [p for p in points if p['image_index'] == 0]
    contradictory = bool(re.search(r'\bABSENT\b', raw, re.IGNORECASE)) and bool(points)
    status = ('invalid' if contradictory else 'absent' if common.clean_terminal(raw).upper() == 'ABSENT' else
        'ambiguous' if len(rgb) > 1 else 'localized' if len(rgb) == 1 else 'unavailable')
    return status, rgb[0]['normalized_1000'] if status == 'localized' else None


def float_rows_equal(first, second):
    return len(first) == len(second) and all(len(a) == len(b) and all(close(x, y) for x, y in zip(a, b)) for a, b in zip(first, second))


def verify_telemetry(path):
    data = read(path)
    require(data['exit_code'] == 0 and not data['foreign_compute_clients'] and not data['monitor_errors'], 'final performance run failed or contended')
    require(not data['initial_compute_apps'] and not data.get('foreign_abort_actions') and data.get('aborted_for_contention') is False, 'final run did not start and remain uncontended')
    own_pid = int(data['owned_pid'])
    for sample in data['samples']:
        for app in sample['compute_apps']:
            require(int(app[0]) == own_pid, 'foreign GPU process in actual telemetry')
    measured_peak = max(float(gpu[0]) for sample in data['samples'] for gpu in sample['gpu'])
    require(close(measured_peak, data['driver_wide_peak_memory_MiB']), 'driver peak differs from telemetry')
    return {'file_sha256': sha(path), 'owned_pid': own_pid, 'exit_code': data['exit_code'],
        'sample_count': len(data['samples']), 'driver_wide_peak_memory_MiB': measured_peak, 'foreign_compute_clients': [],
        'startup_and_full_screen_wall_s': data['startup_and_full_screen_wall_s'],
        'initial_compute_apps': data['initial_compute_apps'], 'final_compute_apps': data['final_compute_apps'],
        'scope': data['driver_memory_scope']}


def verify_lease(path, protocol):
    lease = read(path)
    empty = lease['fresh_actual_empty_window']
    require(lease['root_conditional_lease'] == protocol['gpu_lease'] and empty['empty'] is True and not empty['compute_apps'].strip(), 'actual root lease or empty compute window differs')
    require(empty['Ollama_resident']['models'] == [] and empty['owned_physics_renderer_processes'] == [], 'actual launch overlapped resident models or physics renderers')
    require(lease['bank_manifest_sha256'] == sha(BANK / 'bank-manifest.json') and lease['all20_same_allocation'] is True and lease['no_method_retuning'] is True, 'actual empty-window allocation differs')
    for name, digest in lease['source_and_model_metadata_hashes'].items():
        require(sha(MOLMO / name) == digest, 'actual activation runtime source changed: ' + name)
    require(sha(MOLMO / 'point-toolchain-environment-prospective-amendment.json') == lease['toolchain_amendment_sha256'], 'activation toolchain amendment differs')
    require(sha(MOLMO / 'point-toolchain-header-provenance.json') == lease['header_provenance_sha256'], 'activation header provenance differs')
    require(sha(MOLMO / 'run_monitor_guarded.py') == lease['guarded_monitor_sha256'] and sha(MOLMO / 'launch_point_when_empty.py') == lease['watcher_sha256'], 'activation control source changed')
    amendment = read(MOLMO / 'point-toolchain-environment-prospective-amendment.json')
    require(lease['process_env'] == amendment['process_env'], 'activation process environment differs from prospectively approved toolchain amendment')
    command = lease['command']
    require(command[command.index('--gpu-lease') + 1] == protocol['gpu_lease'], 'actual argv lease differs')
    return lease


def verify_environment_and_toolchain():
    amendment = read(MOLMO / 'point-toolchain-environment-prospective-amendment.json')
    for name, digest in amendment['source_and_model_metadata_hashes'].items():
        require(sha(MOLMO / name) == digest, 'post-amendment source/environment drift: ' + name)
    headers = read(MOLMO / 'point-toolchain-header-provenance.json')
    require(sha(MOLMO / 'point-toolchain-header-provenance.json') == amendment['header_provenance_sha256'], 'toolchain provenance differs')
    require(sha(Path(headers['archive'])) == headers['archive_sha256'], 'header archive changed')
    for name, info in headers['files'].items():
        path = Path(headers['literal_include_copy']) / name
        require(path.stat().st_size == info['bytes'] and sha(path) == info['sha256'], 'copied literal header changed: ' + name)
    compiled = amendment['CPU_actual_Triton_driver_compile']
    require(compiled['exit_code'] == 0 and compiled['GPU_loaded'] is False and compiled['extension_imported'] is False, 'Triton CPU compile evidence differs')
    output = Path(compiled['command'][compiled['command'].index('-o') + 1])
    require(sha(output) == compiled['compiled_SHA256'], 'CPU compiled driver bytes differ')
    env = dict(os.environ, CUDA_VISIBLE_DEVICES='', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    script = 'import importlib.metadata as m,json,sys;print(json.dumps({"python":sys.version,"executable":sys.executable,"versions":{n:m.version(n) for n in ["torch","transformers","tokenizers","bitsandbytes","triton","numpy"]}}))'
    process = subprocess.run([str(MOLMO / '.venv/bin/python'), '-c', script], env=env, capture_output=True, text=True, check=True)
    actual = json.loads(process.stdout)
    require(actual['versions']['transformers'] == '4.57.1' and actual['versions']['tokenizers'] == '0.22.1' and actual['versions']['bitsandbytes'] == '0.45.2' and actual['versions']['torch'].startswith('2.6.0'), 'live interpreter package metadata differs')
    dependency = read(MOLMO / 'dependency-downloads.json')
    for wheel in dependency['wheels']:
        path = MOLMO / 'wheelhouse' / wheel['filename']
        require(path.stat().st_size == wheel['size'] and sha(path) == wheel['sha256'], 'pinned dependency wheel differs')
    return {'amendment_sha256': sha(MOLMO / 'point-toolchain-environment-prospective-amendment.json'),
        'header_provenance_sha256': sha(MOLMO / 'point-toolchain-header-provenance.json'), 'literal_headers_verified': len(headers['files']),
        'actual_package_metadata': actual, 'CPU_driver_compile_exit_code': 0, 'compiled_driver_sha256': sha(output),
        'scope': 'Toolchain headers and isolated compiled cache amendment only; package metadata query does not import torch/bnb or allocate GPU.'}


def verify_precision(path, protocol):
    data = read(path)
    require(data['model'] == 'MolmoPoint-8B' and data['gpu_lease'] == protocol['gpu_lease'] and data['bridge_sha256'] == protocol['bridge_sha256'], 'loaded precision identity differs')
    require(data['observer_sha256'] == sha(MOLMO / 'observe_point_precision.py'), 'observer bytes changed')
    require(data['observer_disabled_before_metadata_and_timed_inference'] is True, 'precision observer active during inference')
    config = data['quantization_config']
    require(config['load_in_8bit'] is True and config['load_in_4bit'] is False and close(config['llm_int8_threshold'], 6.0) and config['llm_int8_skip_modules'] == ['lm_head'], 'actual quantization differs from registration')
    require(data['is_loaded_in_8bit'] is True and data['Linear8bitLt_count'] > 0 and not data['non_CUDA_parameter_names'], 'actual load is not GPU INT8-linears')
    require(any('torch.int8' in key and 'cuda:0' in key for key in data['parameter_groups']) and
        any('torch.bfloat16' in key and 'cuda:0' in key for key in data['parameter_groups']), 'loaded INT8/BF16 groups not observed')
    require(all('cuda:0' in key for key in data['parameter_groups']), 'CPU/offload parameter group found')
    observer = (MOLMO / 'observe_point_precision.py').read_text()
    require(observer.index('sys.setprofile(None)') < observer.index('model = instance.model'), 'observer disable does not precede metadata access')
    require('model.forward' not in observer and 'model.generate' not in observer and 'tensor.copy' not in observer, 'observer changes model calls')
    return {'file_sha256': sha(path), 'observer_disabled_before_metadata_and_timed_inference': True,
        'observer_sha256': data['observer_sha256'], 'is_loaded_in_8bit': True, 'Linear8bitLt_count': data['Linear8bitLt_count'],
        'parameter_groups': data['parameter_groups'], 'quantization_config': config, 'hf_device_map': data['hf_device_map'],
        'cold_load_seconds': data['load_seconds'], 'profile_interval_wall_s': data['profile_interval_wall_s'],
        'metadata_observer_wall_s_excluding_artifact_write': data['metadata_observer_wall_s_excluding_artifact_write'],
        'allocator_load_current_bytes': data['allocator_load_current_bytes'], 'allocator_load_peak_bytes': data['allocator_load_peak_bytes'],
        'allocator_load_reserved_bytes': data['allocator_load_reserved_bytes'], 'parameter_bytes_note': data['parameter_bytes_note']}


def verify_preserved_attempts(final_run):
    first = MOLMO / 'point-development-full20-first-v2'
    failure = read(first / 'attempts/model-load.failed.json')
    log = MOLMO / 'point-development-full20-first-v2.log'
    require('fatal error: Python.h: No such file' in log.read_text(), 'prior first-attempt compiler diagnosis differs')
    require(not list((first / 'attempts').glob('*.generated.json')) and not list((first / 'attempts').glob('*.completed.json')), 'first attempt unexpectedly made inference')
    require(failure['key'] == 'model-load' and failure['phase'] == 'failed', 'first failure was not during load')
    old_telemetry = read(MOLMO / 'point-development-full20-first-v2-gpu-telemetry.json')
    require(old_telemetry['exit_code'] == 1 and close(old_telemetry['driver_wide_peak_memory_MiB'], 309), 'first attempt resource evidence differs')
    require('out of memory' not in log.read_text().lower(), 'first failure may include OOM')
    attempts = []
    for directory in sorted(MOLMO.glob('point-development-*')):
        if not directory.is_dir() or directory.resolve() == final_run or not (directory / 'protocol.json').exists():
            continue
        files = {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}
        attempts.append({'directory': str(directory.relative_to(BASE)), 'files_sha256': files,
            'generated_call_receipts': len(list((directory / 'attempts').glob('*.generated.json'))),
            'completed_call_receipts': len(list((directory / 'attempts').glob('*.completed.json'))),
            'used_for_final_performance': False})
    return {'first_attempt_classification': 'Triton C extension compile failed on missing Python.h before weight/model load or inference; not OOM or a model-quality outcome',
        'first_attempt_inference_calls': 0, 'first_attempt_sampled_driver_peak_MiB': 309,
        'first_attempt_failed_receipt_sha256': sha(first / 'attempts/model-load.failed.json'),
        'first_attempt_log_sha256': sha(log), 'preserved_prior_attempts': attempts}


def audit(run, scores, bank):
    protocol = read(run / 'protocol.json')
    core = {k: v for k, v in protocol.items() if k != 'protocol_sha256'}
    require(hashlib.sha256(json.dumps(core, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest() == protocol['protocol_sha256'], 'protocol hash differs')
    require(protocol['bank_manifest_sha256'] == sha(BANK / 'bank-manifest.json') and protocol['case_count'] == 20 and protocol['planned_calls_per_task'] == 3 and protocol['ground_truth_used_online'] is False, 'final allocation/online boundary differs')
    for key, name in [('bridge_sha256', 'native_bridge.py'), ('adapter_sha256', 'native_adapter.py'), ('model_source_metadata_sha256', 'MolmoPoint-8B-metadata-response.json'), ('dependency_downloads_sha256', 'dependency-downloads.json'), ('environment_freeze_sha256', 'environment-freeze.txt')]:
        require(protocol[key] == sha(MOLMO / name), 'frozen method/dependency drift: ' + name)
    require(protocol['source_snapshot_manifest_sha256'] == sha(BASE / 'source-snapshot-manifest.json'), 'wrong frozen source')
    require(protocol['model'] == 'MolmoPoint-8B' and protocol['precision'] == 'bitsandbytes INT8 linear + BF16 remaining', 'wrong final model/precision')
    require([a['case_id'] for a in protocol['allocation']] == [a['case_id'] for a in bank['cases']], 'prescribed order changed')
    decode, decoder_info = official_decoder()
    gate = common.load_gate()
    recorded_scores = {r['case_id']: r for r in read(scores / 'results.json')}
    metadata = read(MOLMO / 'MolmoPoint-8B-metadata-response.json')
    expected_source = {'metadata_sha256': sha(MOLMO / 'MolmoPoint-8B-metadata-response.json'), 'files_verified': sum(r['Type'] == 'blob' for r in metadata['Data']['Files']), 'weights_verified': True,
        'model_source_hashes': {r['Path']: r['Sha256'] for r in metadata['Data']['Files'] if r['Type'] == 'blob' and r['Path'].endswith('.py')}}
    load = read(run / 'attempts/model-load.completed.json')
    require(load['payload']['source'] == expected_source and load['protocol_sha256'] == protocol['protocol_sha256'], 'model-load source receipt differs')
    rows, calls_total, errors, rejected_proposals, decoder_failures = [], 0, Counter(), [], []
    for case, allocation in zip(bank['cases'], protocol['allocation']):
        key = case['case_id']; directory = BANK / 'cases' / key
        result = read(run / (key + '.json'))
        require(allocation['transport_sha256'] == sha(directory / 'observation-transport.json') and allocation['instruction'] == case['instruction'], 'prospective input binding differs')
        obs = RGBDObservation.model_validate(read(directory / 'observation-transport.json'))
        require(result['observation'] == obs.evidence() == allocation['observation'], 'observation result differs')
        require(result['case_id'] == key and result['protocol_sha256'] == protocol['protocol_sha256'], 'result identity differs')
        for field in ('model', 'precision', 'method', 'adapter_sha256', 'bridge_sha256', 'gpu_lease'):
            require(result[field] == protocol[field], 'runtime identity differs: ' + field)
        require(result['source'] == expected_source and result['load_seconds'] == load['payload']['load_seconds'], 'load/source changed across cases')
        require(result['ground_truth_used_online'] is False and result['call_count'] == 3 and [c['role'] for c in result['calls']] == ['target', 'destination', 'evidence'], 'calls or online boundary changed')
        images = []
        for i, (role, encoded) in enumerate([('RGB', obs.rgb_png_base64), ('DEPTH', obs.depth_png_base64())]):
            im = Image.open(io.BytesIO(base64.b64decode(encoded, validate=True))).convert('RGB')
            images.append({'index': i, 'role': role, 'size': list(im.size), 'mode': 'RGB', 'decoded_rgb_pixel_sha256': hashlib.sha256(im.tobytes()).hexdigest()})
        expected_input = {'image_count': 2, 'images': images, 'observation_binding': {k: getattr(obs, k) for k in ('frame_id', 'observation_id', 'checksum_sha256')}}
        for call in result['calls']:
            role = call['role']; call_key = key + '.' + role
            require(call['input_images'] == expected_input, 'same-message actual RGB/depth hashes differ')
            require(len(call['raw_token_ids']) == call['output_token_count'] and case['instruction'] in call['prompt_text'], 'raw response/prompt accounting differs')
            require(call['generation'] == {'max_new_tokens': 256 if role == 'evidence' else 160, 'do_sample': False, 'num_beams': 1, 'native_logits_processor': True}, 'official native generation settings differ')
            require(call['cloud_invoice_cny'] == 0 and call['local_energy_cost_cny'] is None, 'unsupported cost')
            for phase in ('started', 'generated', 'completed'):
                journal = read(run / 'attempts' / (call_key + '.' + phase + '.json'))
                require(journal['key'] == call_key and journal['phase'] == phase and journal['protocol_sha256'] == protocol['protocol_sha256'], 'journal identity differs')
                if phase == 'completed': require(journal['payload'] == call, 'completed raw call changed')
                elif phase == 'generated': require(all(call[k] == v for k, v in journal['payload'].items()), 'literal generation mutated')
                else: require(journal['payload']['input_images'] == expected_input and journal['payload']['prompt_text'] == call['prompt_text'], 'started call differs')
            calls_total += 1
            require(call['metadata'] is not None and call['metadata']['image_sizes'] == [[320, 240], [320, 240]], 'official multi-image metadata differs')
            if role != 'evidence':
                try:
                    decoded = decode(call['raw_text'], call['metadata'])
                    points = normalized_points(decoded, call['metadata']['image_sizes'])
                except (ValueError, IndexError) as exc:
                    require(call['localization']['status'] == 'unavailable' and call['localization']['point'] is None and call['localization']['error'] == str(exc), 'official decoder failure differs from retained receipt')
                    decoder_failures.append({'case_id': key, 'role': role, 'error': str(exc)})
                    points, status = [], 'unavailable'
                else:
                    require(float_rows_equal(decoded, call.get('native_decoded_pixels', [])), 'official decoder does not reproduce native pixel receipt')
                    status, point = selected_localization(call['raw_text'], points)
                    require(call['localization']['status'] == status and call['localization']['point'] == point and call['localization']['native_points'] == points, 'pixel-normalized conversion or selection differs')
                require(call['localization']['raw_text'] == call['raw_text'] and call['localization']['raw_token_ids'] == call['raw_token_ids'], 'parser changed raw response')
                if points and status != 'localized': rejected_proposals.append({'case_id': key, 'role': role, 'status': status, 'raw_native_points': points})
            else:
                try: expected_evidence = json.loads(common.clean_terminal(call['raw_text']))
                except json.JSONDecodeError: expected_evidence = None
                require(expected_evidence == call.get('evidence'), 'free-decoded evidence differs from raw text')
        calls = result['calls']; metrics = result['task_metrics']
        require(metrics['model_call_count'] == 3 and metrics['input_tokens_total'] == sum(c['input_token_count'] for c in calls) and metrics['output_tokens_total'] == sum(c['output_token_count'] for c in calls), 'token/call aggregate differs')
        require(close(metrics['call_latency_total_s'], sum(c['latency_s'] for c in calls)) and close(metrics['model_inference_total_s'], sum(c['inference_s'] for c in calls)) and metrics['task_latency_s'] >= metrics['call_latency_total_s'], 'latency aggregate differs')
        for stem in ('allocated', 'reserved'): require(metrics['peak_torch_' + stem + '_bytes'] == max(c['max_memory_' + stem + '_bytes'] for c in calls), 'Torch peak differs')
        target, destination = [calls[i]['localization'] for i in (0, 1)]
        try:
            decision = gate.build_visual_decision(target, destination, calls[2].get('evidence'))
            decision = VisualDecision.model_validate(decision).model_dump(mode='json'); error = None
        except ValueError as exc: decision, error = None, str(exc)
        require(decision == result['visual_decision'] and error == result.get('contract_error'), 'complete decision gate differs')
        require(result['execution_eligible'] == bool(decision and decision['skills']), 'execution admission differs')
        errors[error or 'complete_model_decision'] += 1
        checks = [common.deproject(directory, point['point']) for point in (target, destination)]
        hits = [check['world'] is not None and check['geom_label'] == label for check, label in zip(checks, ('object_geom', 'target_region_geom'))]
        truth = next(t for t in read(directory / 'initial-truth.json')['instances'] if t['role'] == 'target')
        top = [*truth['position'][:2], truth['position'][2] + truth['half_size'][2]]
        error_mm = math.dist(checks[0]['world'], top) * 1000 if checks[0]['world'] is not None else None
        replay = common.replay_decision(decision, obs, case['instruction'], metrics['task_latency_s'], result['model']) if decision is not None else None
        full = bool(replay and replay['parse_error'] is None and replay['observed_scene_present'] and replay['parsed_json_present'] and replay['calibrated_offset'] and all(hits))
        prior = recorded_scores[key]
        require(prior['target_hit'] == hits[0] and prior['destination_hit'] == hits[1] and close(prior['target_top_center_error_mm'], error_mm) and prior['full_contract_geometry_pass'] == full, 'reported geometry/P90 input/contract differs')
        for role, check in zip(('target', 'destination'), checks): require(prior[role + '_offline_check'] == check, 'scorer deprojection differs')
        rows.append({'case_id': key, 'kind': case['kind'], 'result_sha256': sha(run / (key + '.json')), 'target_hit': hits[0], 'destination_hit': hits[1],
            'full_contract_geometry_pass': full, 'target_top_center_error_mm': error_mm, 'target_status': target['status'], 'destination_status': destination['status'],
            'task_latency_s': metrics['task_latency_s'], 'contract_error': error, 'offline_adapter_replay': replay})
    require(calls_total == 60 and not list((run / 'attempts').glob('*.failed.json')), 'final run incomplete or failed')
    positives = [r for r in rows if r['kind'] == 'positive']; fixed = [r for r in rows if r['kind'] == 'FIXED_S01']; absent = [r for r in rows if r['kind'] == 'negative_absent']
    conditional = [r['target_top_center_error_mm'] for r in positives if r['target_hit']]; allvalid = [r['target_top_center_error_mm'] for r in positives if r['target_top_center_error_mm'] is not None]
    summary = {'recorded_cases': 20, 'all_actual_model_calls': calls_total, 'positive_target_hit': sum(r['target_hit'] for r in positives),
        'positive_both_hit': sum(r['target_hit'] and r['destination_hit'] for r in positives), 'fixed_both_hit': sum(r['target_hit'] and r['destination_hit'] for r in fixed),
        'fixed_full_contract_geometry_pass': sum(r['full_contract_geometry_pass'] for r in fixed), 'positive_full_contract_geometry_pass': sum(r['full_contract_geometry_pass'] for r in positives),
        'negative_native_explicit_absence': sum(r['target_status'] == 'absent' for r in absent), 'negative_native_point_proposals': sum(r['target_status'] == 'localized' for r in absent),
        'target_hit_conditional_P90_mm': percentile(conditional, .9), 'target_hit_conditional_coverage': f'{len(conditional)}/12', 'all_valid_point_P90_mm': percentile(allvalid, .9),
        'all_valid_point_coverage': f'{len(allvalid)}/12', 'warm_task_latency_P95_s': percentile([r['task_latency_s'] for r in rows[1:]], .95)}
    prior = read(scores / 'summary.json')
    for key, value in summary.items(): require(close(value, prior[key]) if type(value) is float else value == prior[key], 'reported summary differs: ' + key)
    require(prior['physical_task_success_rate'] is None and prior['physical_misoperation_rate'] is None and prior['physical_actions'] == 0 and prior['local_API_cost_CNY_per_task'] == 0 and prior['total_cost_CNY_per_task'] is None and prior['held_out_test'] is False and prior['formal_G1'] is False, 'unmeasured physical/total cost misrepresented')
    return protocol, {'valid': True, 'same_message_dual_image_calls_verified': calls_total, 'raw_journals_verified': 180, 'official_decoder': decoder_info,
        'summary': summary, 'reported_summary_sha256': sha(scores / 'summary.json'), 'contract_error_counts': dict(errors),
        'rejected_raw_proposals': rejected_proposals, 'official_decoder_failures_reproduced': decoder_failures, 'cases': rows}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--run', type=Path, required=True); parser.add_argument('--scores', type=Path, required=True)
    parser.add_argument('--telemetry', type=Path, required=True); parser.add_argument('--precision', type=Path, required=True); parser.add_argument('--lease', type=Path, required=True)
    args = parser.parse_args(); paths = {k: v.resolve() for k, v in vars(args).items()}
    destination = BASE / 'shared/root-molmopoint-model-audit.json'; require(not destination.exists(), 'exclusive final audit already exists')
    os.chdir(common.SNAPSHOT)
    bank = read(BANK / 'bank-manifest.json')
    for relative, digest in bank['files'].items(): require(sha(BANK / relative) == digest, 'immutable bank drift: ' + relative)
    snapshot = read(BASE / 'source-snapshot-manifest.json')
    for relative, digest in snapshot['source_sha256'].items(): require(sha(common.SNAPSHOT / relative) == digest, 'immutable source drift: ' + relative)
    model_files = []
    for row in read(MOLMO / 'MolmoPoint-8B-metadata-response.json')['Data']['Files']:
        if row['Type'] != 'blob': continue
        path = MOLMO / 'models/MolmoPoint-8B' / row['Path']; require(path.stat().st_size == row['Size'] and sha(path) == row['Sha256'], 'pinned source/weight drift: ' + row['Path'])
        model_files.append({k: row[k] for k in ('Path', 'Revision', 'Sha256', 'Size')})
    environment = verify_environment_and_toolchain()
    protocol, result = audit(paths['run'], paths['scores'], bank)
    precision = verify_precision(paths['precision'], protocol); telemetry = verify_telemetry(paths['telemetry'])
    previous = verify_preserved_attempts(paths['run'])
    lease = verify_lease(paths['lease'], protocol)
    report = {'created_at': datetime.now(UTC).isoformat(), 'valid': True, 'scope': 'CPU-only independent final development screen audit; no model inference, endpoints, rendering or physical actions',
        'audit_helper_sha256': sha(Path(__file__)), 'auditing_dependency_sha256': sha(BASE / 'shared/audit_native_independent.py'),
        'bank_manifest_sha256': sha(BANK / 'bank-manifest.json'), 'bank_files_verified': len(bank['files']), 'source_snapshot_files_verified': len(snapshot['source_sha256']),
        'model_files_verified': model_files, 'run_path': str(paths['run'].relative_to(BASE)), 'run_protocol_sha256': sha(paths['run'] / 'protocol.json'),
        'method_source_sha256': {'native_bridge.py': protocol['bridge_sha256'], 'native_adapter.py': protocol['adapter_sha256']},
        'environment_and_toolchain': environment, 'actual_loaded_precision': precision, 'actual_GPU_telemetry': telemetry,
        'preserved_prior_attempts': previous,
        'lease_file_sha256': sha(paths['lease']), 'lease_snapshot': lease, 'screen': result,
        'execution_and_cost_scope': {'physical_task_success_rate': None, 'physical_misoperation_rate': None, 'physical_actions': 0, 'local_API_cost_CNY_per_task': 0, 'total_cost_CNY_per_task': None, 'held_out_test': False, 'formal_G1': False},
        'limitations': ['Performance describes this registered native three-call prototype, not universal base-model quality.', 'Native coordinate proposals, parser acceptance and complete geometry admission are separate layers.',
            'Warm task P95 excludes prescribed first case; cold model load is separate and includes constructor precision-profile overhead. Metadata observer is disabled before all forward/generation/task timing.',
            'Driver peak is sampled whole-device memory including display; Torch allocator and parameter metadata byte estimates are distinct.', 'Failed or contended attempts remain preserved and are not converted into measured task outcomes.']}
    with destination.open('x') as stream: json.dump(report, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps({'valid': True, 'audit_sha256': sha(destination), 'summary': result['summary'], 'full_geometry_fixed_gate_pass': result['summary']['fixed_full_contract_geometry_pass'] == 4}, indent=2))


if __name__ == '__main__': main()
