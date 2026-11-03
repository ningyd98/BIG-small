"""Reconcile completed Phase12 files without running any experiment."""
from collections import Counter
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

ROUND = Path(__file__).resolve().parents[1]
ART = ROUND / 'implementation/phase12-full/artifacts'


def read(path):
    return json.loads(path.read_text()) if path.is_file() else None


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.is_file() else []


def counts(rows, key):
    return dict(Counter(row.get(key, '<absent>') for row in rows))


def main():
    expected = read(ROUND / 'reports/phase12-expected-matrix.json')
    raw_path = ART / 'runs/raw_runs.jsonl'
    manifest_path = ART / 'manifests/run_manifests.jsonl'
    rows = lines(raw_path)
    manifests = lines(manifest_path)
    summary = read(ART / 'runs/run_summary.json')
    verification = read(ROUND / 'implementation/phase12-verify/verification/phase12_summary.json')
    provenance = read(ART / 'manifests/provenance.json')
    statistics = read(ART / 'statistics/phase12_statistics.json')
    paired = read(ART / 'paired/paired_summary.json')
    stages = {name: read(ROUND / 'implementation' / name / 'result.json') for name in
              ['phase12-full', 'phase12-analysis', 'phase12-export', 'phase12-verify']}
    issues = []
    if len(rows) != expected['expected_result_rows']:
        issues.append({'issue': 'RESULT_ROW_COUNT_MISMATCH', 'actual': len(rows), 'expected': expected['expected_result_rows']})
    if len(manifests) != len(rows):
        issues.append({'issue': 'MANIFEST_COUNT_MISMATCH', 'actual': len(manifests), 'rows': len(rows)})
    ids = [row.get('run_id') for row in rows]
    if len(ids) != len(set(ids)):
        issues.append({'issue': 'DUPLICATE_RUN_IDS'})
    if Counter(ids) != Counter(row.get('run_id') for row in manifests):
        issues.append({'issue': 'MANIFEST_RESULT_IDS_DIFFER'})
    by_experiment = []
    for item in expected['experiments']:
        actual = [row for row in rows if row.get('experiment_id') == item['experiment_id']]
        entry = {**item, 'actual_result_rows': len(actual), 'status_counts': counts(actual, 'status'),
                 'runtime_invocations': sum(row.get('runtime_invoked') is True for row in actual),
                 'runtime_completions': sum(row.get('runtime_completed') is True for row in actual),
                 'declared_authoritative_rows': sum(row.get('authoritative_for_thesis') is True for row in actual)}
        by_experiment.append(entry)
        if len(actual) != item['expected_result_rows']:
            issues.append({'issue': 'EXPERIMENT_ROW_COUNT_MISMATCH', 'experiment_id': item['experiment_id'],
                           'expected': item['expected_result_rows'], 'actual': len(actual)})
    recomputed = {
        'run_count': len(rows),
        'adapter_attempt_count': sum(row.get('adapter_attempted') is True for row in rows),
        'runtime_invocation_count': sum(row.get('runtime_invoked') is True for row in rows),
        'runtime_completion_count': sum(row.get('runtime_completed') is True for row in rows),
        'blocked_by_env_count': sum(row.get('status') == 'BLOCKED_BY_ENV' for row in rows),
        'blocked_before_runtime_count': sum(row.get('status') == 'BLOCKED_BY_ENV' and
                                            row.get('environment_check_completed') is True and
                                            row.get('runtime_invoked') is not True for row in rows),
        'synthetic_sample_count': sum(row.get('execution_source') == 'SYNTHETIC_PIPELINE_SAMPLE' for row in rows),
        'authoritative_thesis_run_count': sum(row.get('authoritative_for_thesis') is True for row in rows)}
    for key, value in recomputed.items():
        if summary is not None and summary.get(key) != value:
            issues.append({'issue': 'SUMMARY_RAW_MISMATCH', 'field': key, 'summary': summary.get(key), 'raw': value})
    fields = ['real_controller_contacted', 'hardware_motion_observed', 'hardware_write_operations',
              'highest_real_hardware_acceptance_level', 'real_robot_validation']
    hardware = {key: sorted({json.dumps(row.get('hardware_claims', {}).get(key), sort_keys=True) for row in rows}) for key in fields}
    actual_hardware_activity = any(row.get('hardware_claims', {}).get('real_controller_contacted') is True or
                                   row.get('hardware_claims', {}).get('hardware_motion_observed') is True or
                                   bool(row.get('hardware_claims', {}).get('hardware_write_operations')) for row in rows)
    if actual_hardware_activity:
        issues.append({'issue': 'UNEXPECTED_HARDWARE_CLAIM'})
    # Top-level adapter flags are declarations; inspect actual Phase11 worker receipts.
    phase11_receipts = []
    for row in rows:
        if row.get('execution_source') != 'PHASE11_RUNTIME_ACTUAL':
            continue
        relative = Path(row.get('source_artifact_path', ''))
        path = ART / relative
        if relative.is_absolute() or not path.resolve().is_relative_to(ART.resolve()):
            issues.append({'issue': 'PHASE11_RECEIPT_PATH_OUT_OF_SCOPE', 'run_id': row.get('run_id')})
            continue
        receipt = read(path)
        main_job = (receipt or {}).get('main_job', {})
        duplicate = (receipt or {}).get('duplicate_competition_evidence', {})
        recovery = (receipt or {}).get('recovery_evidence', {})
        consistent = bool(receipt and main_job.get('status') == 'SUCCEEDED' and
                          duplicate.get('runner_invocation_count') == 1 and
                          duplicate.get('final_status') == 'SUCCEEDED' and
                          recovery.get('final_status') == 'SUCCEEDED')
        phase11_receipts.append({'run_id': row.get('run_id'), 'experiment_id': row.get('experiment_id'),
                             'raw_status': row.get('status'),
                             'raw_runtime_completed': row.get('runtime_completed'),
                             'raw_task_success': row.get('task_success'),
                             'raw_declared_authoritative': row.get('authoritative_for_thesis'),
                             'receipt_exists': receipt is not None,
                             'main_job_status': main_job.get('status'),
                             'duplicate_runner_invocations': duplicate.get('runner_invocation_count'),
                             'duplicate_final_status': duplicate.get('final_status'),
                             'recovery_final_status': recovery.get('final_status'),
                             'receipt_supports_phase11_completion': consistent,
                             'source_artifact_path': str(relative)})
    f20_receipts = [row for row in phase11_receipts if row['experiment_id'] == 'F20_STRESS_AND_RECOVERY']
    phase11_unsupported = [row for row in phase11_receipts if not row['receipt_supports_phase11_completion']]
    f20_unsupported = [row for row in f20_receipts if not row['receipt_supports_phase11_completion']]
    if phase11_unsupported:
        issues.append({'issue': 'PHASE11_TOP_LEVEL_CLAIM_UNSUPPORTED_BY_INNER_RECEIPT',
                       'count': len(phase11_unsupported),
                       'by_experiment': dict(Counter(row['experiment_id'] for row in phase11_unsupported))})
    if f20_unsupported:
        issues.append({'issue': 'F20_TOP_LEVEL_CLAIM_UNSUPPORTED_BY_INNER_RECEIPT',
                       'count': len(f20_unsupported), 'run_ids': [row['run_id'] for row in f20_unsupported]})
    pins = []
    for path in [raw_path, manifest_path, ART / 'runs/run_summary.json', ART / 'manifests/provenance.json',
                 ART / 'statistics/phase12_statistics.json', ART / 'paired/paired_summary.json',
                 ROUND / 'implementation/phase12-verify/verification/phase12_summary.json']:
        if path.is_file():
            pins.append({'path': str(path.relative_to(ROUND)), 'bytes': path.stat().st_size,
                         'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    result = {'schema': 'r413.phase12-offline-audit.v1', 'generated_utc': datetime.now(UTC).isoformat(),
              'expected_result_rows': expected['expected_result_rows'], 'recomputed_counts': recomputed,
              'manifest_count': len(manifests), 'unique_run_ids': len(set(ids)),
              'status_counts': counts(rows, 'status'), 'registered_backend_counts': counts(rows, 'backend'),
              'runtime_invoked_registered_backend_counts': counts([row for row in rows if row.get('runtime_invoked') is True], 'backend'),
              'execution_source_counts': counts(rows, 'execution_source'), 'experiments': by_experiment,
              'stages': stages, 'run_summary': summary, 'provenance': provenance,
              'statistics_counts': {key: statistics.get(key) for key in recomputed if key != 'run_count'} if statistics else None,
              'verification': verification, 'verification_failed_checks': [key for key, value in (verification or {}).get('checks', {}).items() if value is not True],
              'paired': paired, 'hardware_claim_values': hardware, 'actual_hardware_activity_claimed': actual_hardware_activity,
              'f20_receipt_checks': f20_receipts,
              'phase11_receipt_checks': phase11_receipts,
              'phase11_unsupported_claims': len(phase11_unsupported),
              'f20_receipts_supporting_claim': len(f20_receipts) - len(f20_unsupported),
              'f20_unsupported_claims': len(f20_unsupported),
              'count_semantics': 'recomputed_counts sums raw declared flags. These counts do not establish successful execution or research acceptance; F20 inner receipts and verifier gates are reported separately.',
              'issues': issues, 'evidence_pins': pins,
              'formal_accepted': False,
              'boundary': 'Registered rows, adapter attempts, actual software/simulation runtime invocations, and formal research acceptance are distinct. F20 task_count=100 is policy metadata, not proof of 100 executed tasks per row. No physical validation or complete remote raw package is claimed.'}
    with (ROUND / 'reports/phase12-audit.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'rows': len(rows), 'counts': recomputed, 'verification_status': (verification or {}).get('status'),
                      'failed_checks': result['verification_failed_checks'], 'issues': issues}, ensure_ascii=False))


if __name__ == '__main__':
    main()
