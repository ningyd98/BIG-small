"""R156 single metadata audit; no subprocesses or product imports."""
import collections
import datetime
import hashlib
import json
import re
import stat
import sys
import traceback
from pathlib import Path

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
D = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round156-p6-postpush-receipt-path-recovery-20261012'
I = D / 'implementation'
COMMIT = 'b8ef6e2708e1a9ea28ae4addbe8aeffa066e55d7'
BASE = '315fdadd8f42b0d624cafb9b5f0e4d5966a51b3e'
BRANCH = 'codex/research-20261007-p1-delivery'
R155_PREFIX = 'artifacts/research/process/20261004-ced-development/astra-rounds/round155-p6-disjoint-head-finite-delivery-20261012/'
OWNED = {
    'src/cloud_edge_robot_arm/simulation_runtime/operational_lease.py',
    'src/cloud_edge_robot_arm/simulation_runtime/repository.py',
    'src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py',
    'src/cloud_edge_robot_arm/simulation_runtime/worker.py',
    'src/cloud_edge_robot_arm/simulation_runtime/recovery.py',
    'tests/test_operational_runtime_closure.py',
}
STATUSES = {
    'artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/active-t12-state.json',
    'artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/phase-summary.md',
    'docs/research/project-status-and-next-plan-20261011.md',
}
CHECKS = []
PINS = []


def check(name, valid, **details):
    CHECKS.append({'name': name, 'valid': bool(valid), **details})
    if not valid:
        raise ValueError(name)


def integer(v):
    return type(v) is int and v >= 0


def pin(p):
    check('pin_schema', isinstance(p, dict) and isinstance(p.get('path'), str)
          and integer(p.get('bytes')) and isinstance(p.get('sha256'), str)
          and re.fullmatch('[0-9a-f]{64}', p['sha256']) is not None)
    path = Path(p['path'])
    info = path.lstat()
    check('regular_file', stat.S_ISREG(info.st_mode), path=str(path))
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    mode = stat.S_IMODE(info.st_mode)
    valid = len(raw) == p['bytes'] and digest == p['sha256']
    if 'mode' in p:
        valid = valid and integer(p['mode']) and mode == p['mode']
    check('exact_bytes_sha_mode', valid, path=str(path), bytes=len(raw), sha256=digest, mode=mode)
    PINS.append({'path': str(path), 'bytes': len(raw), 'sha256': digest, 'mode': mode})
    return raw


def json_pin(p):
    result = json.loads(pin(p))
    check('json_object', isinstance(result, dict), path=p['path'])
    return result


def rows(value, size, key):
    check('list_schema', isinstance(value, list) and len(value) == size, field=key)
    check('list_record_schema', all(isinstance(x, dict) and isinstance(x.get(key), str) for x in value), field=key)
    result = {x[key]: x for x in value}
    check('distinct_records', len(result) == size, field=key)
    return result


def audit():
    plan_raw = (D / 'plan.json').read_bytes()
    check('frozen_R156_plan', len(plan_raw) == 26523 and hashlib.sha256(plan_raw).hexdigest()
          == '1d85c4b3b87e31c72342e6b01e9092bc9b631d46b708018488873945c1da8b9a')
    plan = json.loads(plan_raw)
    gate = json.loads((D / 'script-gate.json').read_bytes())
    activation = json.loads((D / 'root-activation.json').read_bytes())
    check('ROOT_activation', activation.get('activated') is True and gate.get('full_text_reviewed') is True)
    check('gated_script', pin(gate['script']) == Path(__file__).read_bytes())
    check('input_gate', json.loads((D / 'input-check.json').read_bytes()).get('all_valid') is True)
    direct = {p['path']: pin(p) for p in plan['inputs']}
    receipt_path = plan['independent_finding']['actual_receipt']
    check('resolved_receipt_is_pinned', receipt_path in direct)
    receipt = json.loads(direct[receipt_path])
    check('receipt_identity', isinstance(receipt, dict) and receipt.get('commit') == COMMIT
          and receipt.get('base') == BASE and receipt.get('branch') == BRANCH)
    identity = receipt['identity']
    check('three_recorded_SHAs_and_clean', identity == {'local_HEAD': COMMIT, 'upstream_HEAD': COMMIT,
          'live_remote': COMMIT, 'delivery_clean': True})
    expected_counts = {'git_commands_used': 28, 'git_commands_remaining': 0, 'retry_budget': 0,
                       'files': 848, 'changed_files': 837, 'bytes': 26791130}
    for key, value in expected_counts.items():
        check('receipt_count_' + key, type(receipt.get(key)) is int and receipt[key] == value)
    check('bounded_acceptance_only', receipt.get('B9_open') is True and receipt.get('whole_P6_complete') is False
          and receipt.get('native_physics_actual_formal_accepted') is False
          and receipt.get('remote_reproduction') == 'SELECTED_PACKAGE_ONLY_NOT_FULL_FIXTURE_RAW_DATABASE_PACKAGE')
    relations = plan['schema']['receipt']['metadata_relations']
    actual_refs = [receipt[k] for k in relations] + receipt['actual_git_results']
    check('all_36_references_are_plan_pins', actual_refs == plan['referenced_inputs'] and len(actual_refs) == 36)
    referenced = {p['path']: pin(p) for p in actual_refs}
    metadata = {k: json.loads(referenced[receipt[k]['path']]) for k in relations if k != 'delivery_paths'}
    path_list = referenced[receipt['delivery_paths']['path']].decode().splitlines()
    check('848_distinct_relative_paths', len(path_list) == 848 and len(set(path_list)) == 848
          and all(not p.startswith('/') and '..' not in Path(p).parts for p in path_list))
    payload = metadata['payload_index']; pre = metadata['precommit_receipt']; staged = metadata['staged_receipt']
    primary = rows(pre['files'], 848, 'relative_path')
    payload_rows = rows(payload['files'], 846, 'relative_path')
    check('payload_pathsets', payload.get('total_paths') == 848 and set(primary) == set(path_list))
    exclusions = {str(Path(receipt[k]['path']).relative_to(ROOT)) for k in ('payload_index', 'delivery_paths')}
    check('only_two_self_hash_exclusions', set(payload['self_hash_exclusions'])
          == {receipt[k]['path'] for k in ('payload_index', 'delivery_paths')}
          and set(payload_rows) | exclusions == set(primary) and not (set(payload_rows) & exclusions))
    for path, record in payload_rows.items():
        check('payload_precommit_same_record', record == primary[path], path=path)
    for key in ('payload_index', 'delivery_paths', 'staged_receipt'):
        check('precommit_reference_' + key, pre[key] == receipt[key])
    for key in ('payload_index', 'delivery_paths'):
        p = receipt[key]; rel = str(Path(p['path']).relative_to(ROOT)); record = primary[rel]
        check('nonself_pin_' + key, all(record[k] == p[k] for k in ('path', 'bytes', 'sha256', 'mode')))
    check('payload_total_bytes', all(integer(x.get('bytes')) for x in primary.values())
          and sum(x['bytes'] for x in primary.values()) == receipt['bytes'])
    stage_rows = rows(staged['staged'], 848, 'path')
    check('all_stage_paths', set(stage_rows) == set(primary))
    for path, record in stage_rows.items():
        check('stage_mode', record.get('mode') == ('100755' if primary[path]['mode'] & 0o111 else '100644'), path=path)
    changed = staged['changed']; unchanged = staged['unchanged_selected_paths']
    check('837_plus_11_equals_848', isinstance(changed, dict) and len(changed) == 837
          and isinstance(unchanged, list) and len(unchanged) == 11
          and len(set(unchanged)) == 11 and not (set(changed) & set(unchanged))
          and set(changed) | set(unchanged) == set(primary))
    check('changed_only_A_M', all(x in ('A', 'M') for x in changed.values()))
    check('staged_counts', staged.get('payload_count') == 848 and staged.get('changed_count') == 837
          and staged.get('bytes') == receipt['bytes'] and set(staged['diff_headers']) == set(changed)
          and len(staged['diff_headers']) == 837)
    old_plan = metadata['plan']
    contracts = {c['id']: c for c in old_plan['git_budget']['commands']}
    git = {}; streams = {}; counts = collections.Counter()
    for ref in receipt['actual_git_results']:
        result = json.loads(referenced[ref['path']])
        check('Git_result_schema', isinstance(result, dict) and isinstance(result.get('id'), str)
              and integer(result.get('ordinal')) and result['ordinal'] > 0
              and isinstance(result.get('argv'), list) and all(isinstance(x, str) for x in result['argv'])
              and type(result.get('exit_code')) is int)
        key = (result['id'], result['ordinal']); command = contracts[result['id']]
        check('Git_unique_and_cwd', key not in git and result.get('cwd') == command['cwd'])
        expected_argv = command['argv']
        if result['id'] == 'G11':
            expected_argv = ['git', 'ls-files', '--stage', '-z', '--'] + sorted(path_list)
        if result['id'] == 'G15':
            strict = sorted(p for p in path_list if p in OWNED | STATUSES or p.startswith(R155_PREFIX))
            check('strict_includes_all_current_sources_and_statuses', OWNED | STATUSES <= set(strict))
            expected_argv = ['git', 'diff', '--cached', '--check', '--'] + strict
        check('Git_actual_argv', result['argv'] == expected_argv, id=result['id'], ordinal=result['ordinal'])
        check('Git_optional_locks_history', result.get('environment_override') == {'GIT_OPTIONAL_LOCKS': '0'})
        expected_exit = {'G7': 1, 'G14': 2}.get(result['id'], 0)
        check('Git_planned_actual_exit', result['exit_code'] == expected_exit, id=result['id'], ordinal=result['ordinal'])
        for field in ('stdout', 'stderr'):
            streams[(key, field)] = pin(result[field])
        git[key] = result; counts[result['id']] += 1
    check('28_actual_results_56_actual_streams', len(git) == 28 and len(streams) == 56)
    check('all_finite_Git_allowances_spent', dict(counts) == {k: v['max_runs'] for k, v in contracts.items()}
          and old_plan['git_budget']['maximum_subprocesses'] == 28)

    def output(id_, ordinal, field='stdout'):
        return streams[((id_, ordinal), field)]

    for id_, ordinal in (('G1', 4), ('G4', 2)):
        check('recorded_final_SHA_' + id_, output(id_, ordinal).decode().strip() == COMMIT)
    check('recorded_final_live_remote_SHA', output('G6', 3).decode().split() == [COMMIT, 'refs/heads/' + BRANCH])
    check('recorded_final_clean', output('G5', 2) == b'')
    for id_, ordinal in (('G1', 1), ('G1', 2), ('G1', 3), ('G4', 1)):
        check('recorded_base_' + id_, output(id_, ordinal).decode().strip() == BASE, ordinal=ordinal)
    for ordinal in (1, 2):
        check('recorded_remote_base', output('G6', ordinal).decode().split() == [BASE, 'refs/heads/' + BRANCH], ordinal=ordinal)
    check('recorded_initial_clean', output('G5', 1) == b'')
    check('recorded_branch_and_upstream', output('G2', 1).decode().strip() == BRANCH
          and output('G3', 1).decode().strip() == 'refs/remotes/origin/' + BRANCH)
    commit_text = output('G16', 1).decode(); push_text = (output('G17', 1) + output('G17', 1, 'stderr')).decode()
    check('actual_commit_output', bool(commit_text.splitlines()) and COMMIT[:7] in commit_text.splitlines()[0])
    check('actual_nonforce_push_output', BRANCH in push_text and BASE[:7] in push_text and COMMIT[:7] in push_text)
    for field in ('full_diff', 'blob_capture', 'whitespace_exceptions'):
        pin(staged[field])
    check('raw_diff_blob_reference_chain', staged['full_diff'] == git[('G13', 1)]['stdout']
          and staged['blob_capture'] == git[('G12', 1)]['stdout'])
    ws = json.loads(Path(staged['whitespace_exceptions']['path']).read_bytes())
    exceptions = ws['exceptions']
    check('650_frozen_historical_whitespace', ws.get('actual_exit_code') == 2
          and ws.get('original_artifact_bytes_unchanged') is True and isinstance(exceptions, list) and len(exceptions) == 650)
    diagnostics = [x for x in output('G14', 1).decode().splitlines()
                   if re.fullmatch(r'.+:\d+: (?:trailing whitespace\.|new blank line at EOF\.)', x)]
    check('all_actual_historical_diagnostics_recorded', diagnostics == [x['actual_diagnostic'] for x in exceptions])
    for x in exceptions:
        path = x['path']
        check('historical_whitespace_authority', path in primary and path not in OWNED | STATUSES
              and not path.startswith(R155_PREFIX) and x['file_sha256'] == primary[path]['sha256']
              and isinstance(x.get('line_bytes_sha256'), str)
              and re.fullmatch('[0-9a-f]{64}', x['line_bytes_sha256']) is not None, path=path)
    check('strict_check_actual_reference', staged['strict_diff_check'] == git[('G15', 1)])
    before = metadata['unrelated_before']; after = metadata['unrelated_after']
    before_rows = rows(before['files'], 100, 'path'); after_rows = rows(after['files'], 100, 'path')
    check('all_100_historical_byte_mode_records_equal', before_rows == after_rows
          and before.get('count') == 100 and after.get('count') == 100 and before.get('base') == BASE)
    check('unrelated_before_after_reference', after['before'] == receipt['unrelated_before'])
    check('unrelated_history_remains_unqualified', before.get('semantic_qualification') is False
          and after.get('semantic_qualification') is False)
    check('preserved_main_state_recorded', receipt.get('main_index_unchanged') is True
          and receipt.get('main_unrelated_dirty_entries_retained') is True
          and receipt.get('unrelated_100_unchanged') is True)
    return {'status': 'EXISTING_BOUNDED_STAGE_A_PUSH_METADATA_VERIFIED', 'identity': identity,
            'receipt_time_utc': receipt['time_utc'], 'commit': COMMIT, 'files': 848, 'changed_files': 837,
            'bytes': 26791130, 'metadata_references': 36, 'Git_results': 28, 'Git_streams': 56,
            'unrelated_proof_records': 100, 'historical_whitespace_exceptions': 650,
            'new_Git_commands': 0, 'new_product_or_review_commands': 0, 'reader_runs': 1,
            'reader_remaining': 0, 'B9_open': True, 'whole_P6_complete': False,
            'native_physics_actual_formal_accepted': False,
            'claim_time_boundary': 'Verifies actual R155 saved postpush evidence; no fresh live query.',
            'remote_reproduction': 'Selected package only; not full fixture/raw/database reproduction.'}


if __name__ == '__main__':
    I.mkdir(exist_ok=True)
    if (I / 'reader.json').exists():
        raise RuntimeError('Single reader allowance already consumed; never overwrite/retry.')
    report = {'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    code = 0
    try:
        report.update(audit())
    except Exception as error:
        code = 1
        report.update({'status': 'STOPPED_ACTUAL_METADATA_FAILURE', 'error_type': type(error).__name__, 'error': str(error)})
        traceback.print_exc()
    report.update({'all_valid': code == 0, 'checks': CHECKS, 'pins': PINS,
                   'ended_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()})
    raw = (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode()
    with (I / 'reader.json').open('xb') as handle:
        handle.write(raw)
    print(json.dumps({'status': report['status'], 'all_valid': report['all_valid'],
                      'checks': len(CHECKS), 'path': str(I / 'reader.json'), 'bytes': len(raw),
                      'sha256': hashlib.sha256(raw).hexdigest()}, ensure_ascii=False))
    sys.exit(code)
