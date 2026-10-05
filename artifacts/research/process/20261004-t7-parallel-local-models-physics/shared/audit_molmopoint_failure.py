"""Independent CPU audit of the actual Point INT8 compatibility failure.

No successful responses, native point quality or task outcomes are imputed.
No inference, rendering, endpoint calls or dependency/model mutation.
"""
from __future__ import annotations
import base64
from datetime import UTC, datetime
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys

os.environ['CUDA_VISIBLE_DEVICES'] = ''
sys.dont_write_bytecode = True
from PIL import Image
import audit_molmopoint_independent as point
import audit_native_independent as common
from cloud_edge_robot_arm.vision.observations import RGBDObservation

BASE, BANK, MOLMO = common.BASE, common.BANK, common.MOLMO
read, sha, require, close = common.read, common.sha, common.require, common.close


def main():
    output = BASE / 'shared/root-molmopoint-model-audit.json'
    require(not output.exists(), 'exclusive final Point audit already exists')
    run = MOLMO / 'point-development-full20-toolchain-fixed-v2'
    os.chdir(common.SNAPSHOT)
    bank = read(BANK / 'bank-manifest.json')
    for relative, digest in bank['files'].items(): require(sha(BANK / relative) == digest, 'immutable bank drift: ' + relative)
    snapshot = read(BASE / 'source-snapshot-manifest.json')
    for relative, digest in snapshot['source_sha256'].items(): require(sha(common.SNAPSHOT / relative) == digest, 'immutable source drift: ' + relative)
    metadata = read(MOLMO / 'MolmoPoint-8B-metadata-response.json')
    model_files = []
    for row in metadata['Data']['Files']:
        if row['Type'] != 'blob': continue
        path = MOLMO / 'models/MolmoPoint-8B' / row['Path']
        require(path.stat().st_size == row['Size'] and sha(path) == row['Sha256'], 'pinned model/source file changed: ' + row['Path'])
        model_files.append({k: row[k] for k in ('Path', 'Revision', 'Sha256', 'Size')})
    protocol = read(run / 'protocol.json')
    core = {k: v for k, v in protocol.items() if k != 'protocol_sha256'}
    require(hashlib.sha256(json.dumps(core, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest() == protocol['protocol_sha256'], 'prospective protocol hash differs')
    require(protocol['model'] == 'MolmoPoint-8B' and protocol['case_count'] == 20 and protocol['planned_calls_per_task'] == 3 and protocol['ground_truth_used_online'] is False, 'planned model/allocation/boundary differs')
    require(protocol['bank_manifest_sha256'] == sha(BANK / 'bank-manifest.json') and protocol['source_snapshot_manifest_sha256'] == sha(BASE / 'source-snapshot-manifest.json'), 'bank/snapshot protocol binding differs')
    for key, filename in [('bridge_sha256', 'native_bridge.py'), ('adapter_sha256', 'native_adapter.py'), ('model_source_metadata_sha256', 'MolmoPoint-8B-metadata-response.json'), ('dependency_downloads_sha256', 'dependency-downloads.json'), ('environment_freeze_sha256', 'environment-freeze.txt')]:
        require(protocol[key] == sha(MOLMO / filename), 'frozen runtime drift: ' + filename)
    require([a['case_id'] for a in protocol['allocation']] == [c['case_id'] for c in bank['cases']], 'full preassigned case order differs')
    for allocated, case in zip(protocol['allocation'], bank['cases']):
        path = BANK / 'cases' / case['case_id'] / 'observation-transport.json'
        require(allocated['transport_sha256'] == sha(path) and allocated['instruction'] == case['instruction'], 'preallocated input differs')
        obs = RGBDObservation.model_validate(read(path))
        require(obs.evidence() == allocated['observation'], 'preallocated observation binding differs')
    load = read(run / 'attempts/model-load.completed.json')
    expected_source = {'metadata_sha256': sha(MOLMO / 'MolmoPoint-8B-metadata-response.json'), 'files_verified': len(model_files), 'weights_verified': True,
        'model_source_hashes': {r['Path']: r['Sha256'] for r in metadata['Data']['Files'] if r['Type'] == 'blob' and r['Path'].endswith('.py')}}
    require(load['protocol_sha256'] == protocol['protocol_sha256'] and load['key'] == 'model-load' and load['payload']['source'] == expected_source, 'loaded source identity differs')
    require(load['payload']['model'] == protocol['model'] and load['payload']['precision'] == protocol['precision'] and load['payload']['gpu_lease'] == protocol['gpu_lease'], 'loaded model/precision/lease differs')
    for filename, digest in expected_source['model_source_hashes'].items():
        cached = MOLMO / 'hf-cache/modules/transformers_modules/MolmoPoint_hyphen_8B' / filename
        if cached.exists(): require(sha(cached) == digest, 'actual dynamic imported model cache changed: ' + filename)
    attempts = run / 'attempts'
    require(not list(attempts.glob('*.generated.json')), 'failed attempt unexpectedly generated retained output')
    complete = list(attempts.glob('*.completed.json'))
    started = list(attempts.glob('*.started.json'))
    failed = list(attempts.glob('*.failed.json'))
    require([p.name for p in complete] == ['model-load.completed.json'] and len(started) == 2 and [p.name for p in failed] == ['fixed-s01-1.target.failed.json'], 'actual attempt boundaries differ')
    require(not any((run / (c['case_id'] + '.json')).exists() for c in bank['cases']), 'failed run contains completed cases')
    start = read(attempts / 'fixed-s01-1.target.started.json'); failure = read(failed[0])
    require(start['protocol_sha256'] == protocol['protocol_sha256'] == failure['protocol_sha256'] and start['key'] == failure['key'] == 'fixed-s01-1.target', 'failed target receipt binding differs')
    obs = RGBDObservation.model_validate(read(BANK / 'cases/fixed-s01-1/observation-transport.json'))
    images = []
    for i, (role, encoded) in enumerate([('RGB', obs.rgb_png_base64), ('DEPTH', obs.depth_png_base64())]):
        image = Image.open(io.BytesIO(base64.b64decode(encoded, validate=True))).convert('RGB')
        images.append({'index': i, 'role': role, 'size': list(image.size), 'mode': 'RGB', 'decoded_rgb_pixel_sha256': hashlib.sha256(image.tobytes()).hexdigest()})
    expected_input = {'image_count': 2, 'images': images, 'observation_binding': {k: getattr(obs, k) for k in ('frame_id', 'observation_id', 'checksum_sha256')}}
    require(start['payload']['input_images'] == expected_input and start['payload']['role'] == 'target' and start['payload']['max_new_tokens'] == 160, 'actual failed-call dual-image/prompt binding differs')
    require(bank['cases'][0]['instruction'] in start['payload']['prompt_text'], 'failed-call instruction changed')
    trace = failure['payload']['traceback']
    require(failure['payload']['exception_type'] == 'RuntimeError' and 'int8_vectorwise_quant' in trace and 'torch.argwhere(outliers.any(dim=0)).view(-1)' in trace and 'view size is not compatible' in trace and 'self.model.generate' in trace, 'actual compatibility diagnosis differs')
    require('out of memory' not in trace.lower(), 'failure evidence also contains OOM')
    precision_file = MOLMO / 'point-retry-loaded-precision.json'
    precision = point.verify_precision(precision_file, protocol)
    require(close(precision['cold_load_seconds'], load['payload']['load_seconds']) and precision['Linear8bitLt_count'] == 307, 'loaded precision/cold-load receipts differ')
    telemetry_file = MOLMO / 'point-development-full20-toolchain-fixed-v2-gpu-telemetry.json'
    telemetry = read(telemetry_file)
    require(telemetry['exit_code'] == 1 and not telemetry['foreign_compute_clients'] and not telemetry['monitor_errors'] and not telemetry['initial_compute_apps'] and not telemetry['final_compute_apps'], 'failure attempt contended or GPU not released')
    require(telemetry['aborted_for_contention'] is False and telemetry['foreign_abort_actions'] == [], 'failure is a contention abort')
    for sample in telemetry['samples']:
        require(all(int(app[0]) == int(telemetry['owned_pid']) for app in sample['compute_apps']), 'actual sample includes foreign compute app')
    peak = max(float(gpu[0]) for sample in telemetry['samples'] for gpu in sample['gpu'])
    require(close(peak, telemetry['driver_wide_peak_memory_MiB']) and close(peak, 13020), 'driver telemetry peak differs')
    lease_file = MOLMO / 'point-empty-window-retry-evidence/activation-01.json'
    lease = point.verify_lease(lease_file, protocol)
    environment = point.verify_environment_and_toolchain()
    prior = point.verify_preserved_attempts(run.resolve())
    bnb_functional = BASE.parents[3] / '.venv-vlm/lib/python3.12/site-packages/bitsandbytes/functional.py'
    # Resolve the same original repository from the audited native overlay location.
    bnb_functional = MOLMO.parents[4] / '.venv-vlm/lib/python3.12/site-packages/bitsandbytes/functional.py'
    bnb_matmul = bnb_functional.parent / 'autograd/_functions.py'
    require(bnb_functional.exists() and bnb_matmul.exists(), 'recorded inherited bnb source is unavailable')
    require('outlier_cols = torch.argwhere(outliers.any(dim=0)).view(-1)' in bnb_functional.read_text(), 'recorded bnb failure source changed')
    require('if len(A.shape) == 3:' in bnb_matmul.read_text() and 'if len(input_shape) == 3:' in bnb_matmul.read_text(), 'recorded bnb dimension handling changed')
    report = {'created_at': datetime.now(UTC).isoformat(), 'valid': True, 'classification': 'Local INT8 backend compatibility failure after successful model loading; no completed quality screen',
        'audit_mode': 'CPU only; no model inference, endpoints, rendering, dependency/model edits or GPU allocation', 'audit_helper_sha256': sha(Path(__file__)),
        'audit_dependency_sha256': {'audit_molmopoint_independent.py': sha(BASE / 'shared/audit_molmopoint_independent.py'), 'audit_native_independent.py': sha(BASE / 'shared/audit_native_independent.py')},
        'frozen_source_files_verified': len(snapshot['source_sha256']), 'frozen_bank_files_verified': len(bank['files']), 'bank_manifest_sha256': sha(BANK / 'bank-manifest.json'),
        'pinned_model_files_rehashed': model_files, 'runtime_model_source_receipt': expected_source, 'protocol_file_sha256': sha(run / 'protocol.json'),
        'allocation': {'prescribed_cases': 20, 'planned_model_calls': 60, 'initiated_model_calls': 1, 'generated_response_receipts': 0, 'completed_model_calls': 0, 'completed_cases': 0},
        'actual_failed_call': {'case_id': 'fixed-s01-1', 'role': 'target', 'started_receipt_sha256': sha(attempts / 'fixed-s01-1.target.started.json'),
            'failed_receipt_sha256': sha(failed[0]), 'same_message_dual_images_binding_verified': True, 'input_images': expected_input,
            'exception_type': failure['payload']['exception_type'], 'error': failure['payload']['error'], 'failed_attempt_latency_s': failure['payload']['attempt_latency_s'],
            'full_traceback_preserved': str(failed[0].relative_to(BASE)), 'failure_is_OOM': False},
        'actual_loaded_precision': precision, 'environment_and_toolchain': environment, 'actual_empty_launch_lease': lease,
        'lease_file_sha256': sha(lease_file), 'driver_GPU_evidence': {'file_sha256': sha(telemetry_file), 'exit_code': 1, 'sample_count': len(telemetry['samples']),
            'driver_wide_peak_memory_MiB': peak, 'driver_memory_scope': telemetry['driver_memory_scope'], 'foreign_compute_clients': [], 'contention_abort': False,
            'initial_compute_apps': [], 'final_compute_apps': [], 'startup_and_failed_screen_wall_s': telemetry['startup_and_full_screen_wall_s']},
        'runtime_bnb_source_sha256': {'functional.py': sha(bnb_functional), 'autograd/_functions.py': sha(bnb_matmul)},
        'diagnosis_limit': 'Traceback proves the view/stride failure. Static source shows Point builds 4D pooled ViT features for subpatch_k while bnb0.45.2 only flattens/restores rank3. Actual failing tensor values/shapes were not instrumented; rank4 as cause is a source-backed inference, not an observed runtime shape. Replacing view with reshape alone is not demonstrated as sufficient.',
        'preserved_prior_attempts': prior,
        'unmeasured_metrics': {'target_hit_conditional_P90_mm': None, 'target_hit_conditional_coverage': '0/12 completed', 'all_valid_point_P90_mm': None,
            'warm_task_latency_P95_s': None, 'physical_task_success_rate': None, 'physical_misoperation_rate': None, 'physical_actions': 0,
            'local_API_cost_CNY_per_task': 0, 'total_cost_CNY_per_task': None, 'held_out_test': False, 'formal_G1': False},
        'interpretation': 'This backend has not passed compatibility, so model capability and complete-geometry admission remain untested. Does not establish that the base model has poor localization or task quality.'}
    with output.open('x') as stream: json.dump(report, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps({'valid': True, 'audit_sha256': sha(output), 'classification': report['classification'], 'allocation': report['allocation'],
        'driver_peak_MiB': peak, 'Linear8bitLt_count': precision['Linear8bitLt_count']}, indent=2))


if __name__ == '__main__': main()
