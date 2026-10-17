"""R131 metadata only: validate frozen bytes, then exclusive-create one report.

This script does not execute/import product or test code, parse AST, collect tests,
run subprocesses, or change any source, snapshot, diff, ledger, or old evidence.
ROOT must text-review this file and authorize its single invocation separately.
"""

from pathlib import Path
import difflib
import hashlib
import json
import re


WORKSPACE = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUNDS = WORKSPACE / 'artifacts/research/process/20261004-ced-development/astra-rounds'
R127 = ROUNDS / 'round127-p6-private-authority-lifecycle-repair-20261011'
R129 = ROUNDS / 'round129-p6-root-read-and-test-draft-review-20261011'
R131 = ROUNDS / 'round131-p6-test-report-count-recovery-20261011'
TEST_RELATIVE = 'tests/test_operational_runtime_closure.py'
PRODUCTION = [
    'src/cloud_edge_robot_arm/simulation_runtime/operational_lease.py',
    'src/cloud_edge_robot_arm/simulation_runtime/repository.py',
    'src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py',
    'src/cloud_edge_robot_arm/simulation_runtime/worker.py',
    'src/cloud_edge_robot_arm/simulation_runtime/recovery.py',
]
PROTECTED = 'src/cloud_edge_robot_arm/simulation_runtime/state_machine.py'
HELD = ['R113.format_check', 'R113.mypy', 'R113.green', 'R127.new_green']

# These exact parameter lists were read as text in both frozen drafts. They are
# checked against decorators and frozen plan argv, never presented as collection.
TEXT_MANIFEST = [
    ('test_two_issuer_threads_keep_domains_distinct', []),
    ('test_caller_cannot_register_locked_view', ['dict', 'copy', 'foreign_repo', 'foreign_thread']),
    ('test_locked_view_terminal_states_cannot_authorize',
     ['rollback', 'cas_zero', 'connection_close', 'commit_close', 'replay']),
    ('test_lease_acquire_reads_after_lock', []),
    ('test_heartbeat_preserves_original_task_budget', []),
    ('test_late_heartbeat_cannot_revive', ['expired', 'cancelled', 'reassigned']),
    ('test_pending_proposal_requires_commit_confirmation', ['rollback', 'cas_zero', 'confirmation_lost']),
    ('test_restart_terminates_without_reissue', ['recovery_service', 'manual_retry']),
    ('test_operational_status_cas_cannot_grant_without_session',
     ['worker_mismatch', 'lease_mismatch', 'revoked_cleanup']),
    ('test_private_transaction_helpers_require_writer_owner', ['direct_legacy', 'forged_tls', 'nested_foreign_job']),
    ('test_operational_failure_cleanup_closes_actual_attempt',
     ['bind_ack_lost', 'initial_heartbeat_failed', 'acquire_ack_lost']),
    ('test_orphan_terminal_cleanup_covers_durable_phase', ['committed', 'revoked', 'terminated']),
    ('test_locked_view_issued_bindings_cannot_be_retargeted',
     ['purpose', 'operation_digest', 'identity_snapshot', 'lifecycle_replay']),
    ('test_confirmation_consumption_keeps_previous_bound', ['exact_deadline', 'after_deadline']),
    ('test_actual_main_and_thread_heartbeat_producers', []),
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def receipt(path, data=None):
    path = Path(path)
    require(path.is_absolute(), 'Receipt path must be absolute: ' + str(path))
    if data is None:
        data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def text_review(text):
    """Finite textual review of explicit lists; no Python parser or execution."""
    matches = list(re.finditer(r'^def (test_[A-Za-z0-9_]+)\(', text, re.MULTILINE))
    require([m.group(1) for m in matches] == [n for n, _ in TEXT_MANIFEST],
            'Top-level test function list differs from reviewed manifest')
    entries = []
    for match, (name, ids) in zip(matches, TEXT_MANIFEST, strict=True):
        prefix = text[:match.start()]
        decorator = re.search(
            r'@pytest\.mark\.parametrize\(\s*"variant",\s*(\[[^\]]*\]),\s*'
            r'ids=(\[[^\]]*\])\s*,?\s*\)\s*$', prefix)
        if ids:
            require(decorator is not None, 'Missing reviewed explicit decorator: ' + name)
            require(json.loads(decorator.group(1)) == ids, 'Variant list differs: ' + name)
            require(json.loads(decorator.group(2)) == ids, 'Parameter IDs differ: ' + name)
        else:
            require(decorator is None, 'Unexpected parametrization: ' + name)
        line = text.count('\n', 0, match.start()) + 1
        entries.append({'function': name, 'function_line': line, 'parameter_ids': ids,
                        'decorator_line': (text.count('\n', 0, decorator.start()) + 1) if decorator else None,
                        'nodeids': [TEST_RELATIVE + '::' + name + ('[' + x + ']' if x else '')
                                    for x in (ids or [''])]})
    return entries


def function_text(text, name):
    starts = list(re.finditer(r'^(?:def|class) ([A-Za-z0-9_]+)\b', text, re.MULTILINE))
    found = [i for i, match in enumerate(starts) if match.group(1) == name]
    require(len(found) == 1, 'Expected one text block: ' + name)
    i = found[0]
    end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
    return text[starts[i].start():end]


def lifecycle_review(text, nodeids):
    # Only four actual poll call sites exist: generic fixture, lock fixture,
    # nested second worker, and failure fixture. The status trial loop is size2.
    calls = re.findall(r'^\s*(?:assert )?([A-Za-z_][A-Za-z0-9_]*)\.poll_once\(\)', text, re.MULTILINE)
    require(calls == ['worker', 'worker', 'second', 'worker'], 'Poll call-site map drift')
    status = function_text(text, 'test_operational_status_cas_cannot_grant_without_session')
    require('trials = [(RuntimeJobStatus.RUNNING, RuntimeJobStatus.FINALIZING),\n'
            '              (RuntimeJobStatus.FINALIZING, RuntimeJobStatus.SUCCEEDED)]' in status,
            'Status legal-source trials are not the reviewed fixed two-entry list')
    require(status.count('_exercise(') == 2 and 'for source, target in trials:' in status,
            'Status fixture dispatch differs')
    require(function_text(text, '_exercise').count('.poll_once()') == 1, 'Generic fixture poll count')
    require(function_text(text, '_faulted_poll').count('.poll_once()') == 1, 'Fault fixture poll count')
    require(function_text(text, '_unfinished_clone').count('_exercise(') == 1, 'Clone fixture poll count')
    require(function_text(text, 'test_private_transaction_helpers_require_writer_owner').count('second.poll_once()') == 1,
            'Second worker poll count')
    bindings = function_text(text, 'test_locked_view_issued_bindings_cannot_be_retargeted')
    require(bindings.count('_exercise(') == 1 and 'for field, value in mutations:' in bindings,
            'Binding subcases must reuse one poll')
    require('for key in ("job_id", "lease_id", "worker_id", "attempt", "generation", "row_revision"):' in bindings,
            'Binding snapshot keys differ from fixed six')
    rows = []
    for node in nodeids:
        name = node.split('::', 1)[1]
        polls, legacy, route = 1, 0, '_exercise -> one actual poll'
        if name.startswith('test_operational_status_cas_cannot_grant_without_session['):
            if not name.endswith('[revoked_cleanup]'):
                polls, route = 2, 'fixed two legal status sources; one fresh _exercise each'
        elif name.endswith('[nested_foreign_job]'):
            polls, route = 2, 'one _exercise poll plus one genuine second.poll_once'
        elif name.startswith('test_operational_failure_cleanup_closes_actual_attempt['):
            route = '_faulted_poll -> one actual faulted poll'
        elif name.startswith('test_restart_terminates_without_reissue['):
            legacy, route = 1, '_unfinished_clone -> one _exercise; one legacy acquire/start-only fixture'
        elif name.startswith('test_orphan_terminal_cleanup_covers_durable_phase['):
            route = '_unfinished_clone -> one _exercise; recovery calls add no worker poll'
        elif name == 'test_lease_acquire_reads_after_lock':
            route = 'one direct actual worker.poll_once plus one lock-holder helper thread'
        elif name.startswith('test_locked_view_issued_bindings_cannot_be_retargeted['):
            route = 'one _exercise; finite transaction mutation subcases reuse same worker'
        rows.append({'nodeid': node, 'poll_upper_bound': polls,
                     'other_worker_acquire_start_only_upper_bound': legacy, 'source_route': route})
    polls = sum(row['poll_upper_bound'] for row in rows)
    other = sum(row['other_worker_acquire_start_only_upper_bound'] for row in rows)
    require(polls + other <= 64, 'Applicable worker lifecycle cap exceeded')
    return {'evidence_kind': 'source-only upper bounds, not measured runs', 'nodes': rows,
            'poll_upper_bound': polls, 'other_worker_acquire_start_only_upper_bound': other,
            'full_worker_lifecycle_upper_bound': polls + other, 'applicable_cap': 64}


def main():
    plan_bytes = (R131 / 'plan.json').read_bytes()
    require(hashlib.sha256(plan_bytes).hexdigest() == 'fbb1448e23d4d8b95724847e68f7b3c9e99b254b23491246966c6b1fbcc163e4',
            'R131 JSON pin mismatch')
    plan = json.loads(plan_bytes)
    require(receipt(R131 / 'plan.md')['sha256'] == plan['plan_md_sha256'], 'R131 MD pin mismatch')
    pins = plan['inputs']
    require(len({pin['path'] for pin in pins}) == len(pins), 'Duplicate input pin paths')
    pinned = {pin['path']: pin for pin in pins}
    observed = []
    for pin in pins:
        actual = receipt(pin['path'])
        require(actual == pin, 'Frozen input mismatch: ' + pin['path'])
        observed.append(actual)

    p127, p129 = load_json(R127 / 'plan.json'), load_json(R129 / 'plan.json')
    owned = p127['scope']['owned_paths']
    require(len(owned) == 6 and len(set(owned)) == 6 and owned.count(TEST_RELATIVE) == 1,
            'Owned paths must be unique exact six with one exact test')
    selected = [path for path in owned if path != TEST_RELATIVE]
    require(selected == PRODUCTION, 'Exact ordered five-production selection mismatch')
    production = []
    for relative in selected:
        absolute = str(WORKSPACE / relative)
        records = [pin for pin in p129['inputs'] if pin['path'] == absolute]
        require(len(records) == 1, 'Exact R129 input record count: ' + absolute)
        actual = receipt(absolute)
        require(actual == records[0] and actual == pinned[absolute], 'Production pin mismatch: ' + absolute)
        production.append(actual)
    protected = receipt(WORKSPACE / PROTECTED)
    require(protected == pinned[protected['path']], 'Protected state-machine pin mismatch')
    require(protected['path'] not in {row['path'] for row in production}, 'Protected file included as production')

    before_path = R129 / 'implementation/author-draft-repair/before-test.py'
    after_path = R129 / 'implementation/author-draft-repair/after-test.py'
    diff_path = R129 / 'implementation/author-draft-repair/limited-change.diff'
    before_bytes, after_bytes = before_path.read_bytes(), after_path.read_bytes()
    current_path = WORKSPACE / TEST_RELATIVE
    require(current_path.read_bytes() == after_bytes, 'Current test differs from frozen after bytes')
    before, after = before_bytes.decode('utf-8'), after_bytes.decode('utf-8')
    expected_diff = ''.join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile='before/' + TEST_RELATIVE, tofile='after/' + TEST_RELATIVE)).encode('utf-8')
    require(diff_path.read_bytes() == expected_diff, 'Saved diff differs from in-memory rendering')
    before_review, after_review = text_review(before), text_review(after)
    manifest = [node for row in after_review for node in row['nodeids']]
    require([node for row in before_review for node in row['nodeids']] == manifest,
            'Textual IDs differ between frozen before and after')
    original = [arg for arg in p127['inherited_commands']['green']['argv'] if arg.startswith(TEST_RELATIVE + '::')]
    new = p127['new_nodeids']
    red = [arg for arg in p127['new_commands']['red']['argv'] if arg.startswith(TEST_RELATIVE + '::')]
    require(manifest == original + new and len(original) == 20 and len(new) == 19 and len(set(manifest)) == 39,
            'Textual manifest differs from original20 plus new19')
    require(red == new + p127['corrected_existing_nodeids'] and len(red) == 23, 'Frozen RED23 node mismatch')
    author = load_json(R127 / 'command-ledger.json')
    root = load_json(R127 / 'root-command-ledger.json')
    for key, frozen in p127['new_commands'].items():
        for source in [author['commands'], root['commands']]:
            require(source[key]['argv'] == frozen['argv'] and
                    (source[key]['authorized'], source[key]['used'], source[key]['remaining']) == (1, 0, 1),
                    'R127 command argv/counter mismatch: ' + key)
    for key, frozen in p127['inherited_commands'].items():
        entry = root['inherited_commands'][key]
        require(entry['argv'] == frozen['argv'] and (entry['authorized'], entry['used'], entry['remaining']) == (1, 0, 1),
                'Inherited command mismatch: ' + key)
    require(root['final_gate'] == 'HELD' and root['no_budget_reset'] is True, 'Final gate/no-reset mismatch')
    require(all((entry['used'], entry['remaining']) == (1, 0) for entry in root['inherited_consumed'].values()),
            'Original consumed history changed')

    lifecycle = {name: lifecycle_review(after, ids) for name, ids in
                 [('RED23', red), ('newGREEN19', new), ('originalGREEN20', original)]}
    require([lifecycle[name]['poll_upper_bound'] for name in lifecycle] == [26, 22, 20], 'Poll upper bounds differ')
    require([lifecycle[name]['full_worker_lifecycle_upper_bound'] for name in lifecycle] == [28, 22, 22],
            'Full lifecycle upper bounds differ')
    changed = ['_denied_with_unchanged_rows', 'test_operational_status_cas_cannot_grant_without_session',
               'test_locked_view_issued_bindings_cannot_be_retargeted', 'test_actual_main_and_thread_heartbeat_producers']
    changes = []
    for name in changed:
        require(function_text(before, name) != function_text(after, name), 'Expected repaired function unchanged: ' + name)
        for_text = re.search(r'^def ' + re.escape(name) + r'\(', after, re.MULTILINE)
        changes.append({'function': name, 'current_start_line': after.count('\n', 0, for_text.start()) + 1})

    report = {
        'schema': 'ced.p6.test-draft-repair.source-only.v1', 'round': 'R129', 'metadata_recovery_round': 'R131',
        'author': {'agent': '/root/p6_stage_a_sol', 'model': 'gpt-6.1-sol', 'role': 'replacement sole implementation writer'},
        'status': 'SOURCE_ONLY_REPAIR_REPORT_PENDING_ROOT_TEXT_DIFF_REVIEW',
        'acceptance': 'No software validation, actual run, formal research or stage acceptance claimed.',
        'plan_references': [receipt(R127 / 'plan.md'), receipt(R127 / 'plan.json'),
                            receipt(R129 / 'plan.md'), receipt(R129 / 'plan.json'),
                            receipt(R131 / 'plan.md'), receipt(R131 / 'plan.json')],
        'original_failure': {**plan['original_failure'],
            'finding': receipt(R129 / 'implementation/stopped-report-count/finding.json'),
            'source_index': receipt(R129 / 'implementation/stopped-report-count/source-index.json'),
            'exact_command': receipt(R129 / 'implementation/stopped-report-count/exact-command.txt'),
            'combined_output': receipt(R129 / 'implementation/stopped-report-count/observed-combined-output.txt'),
            'history_preserved': True, 'old_script_replayed': False},
        'source_evidence': {'before': receipt(before_path, before_bytes), 'after': receipt(after_path, after_bytes),
                            'current_test': receipt(current_path, after_bytes), 'limited_diff': receipt(diff_path),
                            'current_equals_after': True, 'diff_checked_in_memory_only': True,
                            'R129_test_edits_already_saved': True, 'recovery_product_or_test_writes': 0,
                            'unchanged_owned_production': production, 'protected_state_machine_separate': protected},
        'repairs': {
            'evidence_kind': 'source-only descriptions; pending ROOT full diff/text review, not runtime conclusions',
            'changed_functions': changes,
            'D1': 'Only OperationalLeaseError authorizes a negative result; status CAS may explicitly return None. Void writers must throw; no ValueError/AttributeError masking in denial helper. All actual SQL rows compared.',
            'D2': 'Existing _invalidate_view(view, reason) creates INVALIDATED while real _tx connection remains in_transaction/readable and no proposal exists. Ordinary state=OPEN then must reject assignment or true evaluate. No rollback/registry absence supplies the terminal condition.',
            'D3': 'Saved real heartbeat called once per actual wrapper invocation. Main _run code-object and Python/native thread identify true P5 _current_owner scope. Original owner/clock/window/token/_hard/deadline origins and immediate export retained before/after with genuine D_app read_current receipts. Background never reads main P5; later episode compares original budgets/origins while allowing enrichment.',
            'D4': 'Two mismatch IDs each use independent fresh actual RUNNING->FINALIZING and FINALIZING->SUCCEEDED legal-source trials. Exact expected old worker/lease retained. Revoked positive challenge occurs in actual RUNNING before request_cancel; subsequent void payload denials and safe negative release remain.'},
        'expected_manifest_source_review': {'kind': 'source text plus frozen plan argv; NOT pytest collection',
            'actual_collection_performed': False, 'original20': original, 'new19': new, 'all39': manifest,
            'before_decorators_and_ids': before_review, 'after_decorators_and_ids': after_review,
            'unchanged_RED23': p127['new_commands']['red']},
        'finite_source_lifecycle_review': {'commands': lifecycle, 'bound_kind': 'worker lifecycle cap includes polls and separate legacy acquire/start-only activity',
            'binding_subcases': 'One poll per binding node; identity uses six direct fields plus six snapshot keys plus empty snapshot =13 mutation transactions, and one resolved-database transaction; other binding nodes one mutation each.',
            'resources': [
                {'helper': '_exercise', 'source_lines': [99, 164], 'lifetime': 'One factory/poll, broker owner and main P5 owner; true worker finally closes session/clocks. Test finally closes events and any residual session.'},
                {'helper': '_unfinished_clone', 'source_lines': [639, 665], 'lifetime': 'One _exercise poll only; source/destination SQLite backup connections both outer closing; clone repository introduces no worker/poll.'},
                {'helper': '_faulted_poll', 'source_lines': [845, 906], 'lifetime': 'One factory/faulted poll. Original repository connection context owns pass-through connection; after real COMMIT close is deliberate fault. Finally events.close and residual session close.'},
                {'helper': 'status mismatch subcases', 'source_lines': [715, 759], 'lifetime': 'Exactly two fixed source-status trials per mismatch ID. One foreign challenge thread each; bounded joins and finally join; no separate worker in those threads.'},
                {'helper': 'nested_foreign_job', 'source_lines': [784, 828], 'lifetime': 'Exactly one additional genuine second worker poll, shares original event repository; finally restores physical fixture and closes residual second session. Outer _exercise owns shared events.'},
                {'helper': 'queue barriers', 'source_lines': [587, 636, 1023, 1072], 'lifetime': 'One helper thread per lost-confirm or prior-bound case. Finally release barrier, bounded join, restore queue.get. No second worker/poll or reissued clock.'},
                {'helper': 'direct SQLite reads/preparation', 'source_lines': [59, 83, 935, 944, 1081, 1085], 'lifetime': 'Reads and fixture updates use outer closing plus original connection transaction contexts. Seven _all_sql tables fixed. Binding transactions are finite and reuse same lifecycle; no poll per SQL transaction.'},
                {'helper': 'legacy restart control', 'source_lines': [557, 576], 'lifetime': 'One _queued_closed_loop_worker object plus one legacy acquire/start attempt per restart ID; no poll and no operational broker/P5 startup. Included as separate worker activity in full cap.'},
                {'helper': 'issuer/lock/producer helper threads', 'source_lines': [167, 209, 305, 367, 1075, 1184], 'lifetime': 'Finite one foreign issuer thread, one lock-holder thread, or one false-heartbeat-scope thread in its applicable node. No worker poll inside these threads; clocks belong to original real worker owners.'}],
            'caution': 'SQL transaction counts and heartbeat iterations are not extra worker lifecycles. Bounds are source-derived; no measured resource/runtime pass is asserted.'},
        'budget_evidence': {'author_ledger': receipt(R127 / 'command-ledger.json'),
                            'root_ledger': receipt(R127 / 'root-command-ledger.json'),
                            'author_commands': author['commands'], 'root_commands': root['commands'],
                            'inherited_commands': root['inherited_commands'],
                            'inherited_consumed_original_history': root['inherited_consumed'],
                            'held_final_gates': HELD, 'budget_reset': False,
                            'new_product_validation_by_metadata_recovery': 0,
                            'old_RED_note': 'Original R113 RED belongs to its frozen old draft and is never replayed.'},
        'validated_frozen_inputs': observed,
        'continuation': 'ROOT must review corrected test, report and full saved diff before separately resuming original R127 RED23. All four final gates remain HELD. B/C/D and actual/formal authority unchanged.',
    }
    output = Path(plan['scope']['report_output'])
    require(output == R129 / 'test-draft-repair.json', 'Report target mismatch')
    require(not output.exists(), 'Report target already exists; exclusive create required')
    # Complete all validation and serialization before the sole allowed write.
    payload = json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8') + b'\n'
    with output.open('xb') as stream:
        stream.write(payload)
    print(json.dumps({'report': receipt(output, payload), 'evidence_kind': 'source-only',
                      'product_validation_commands_run': 0, 'held': HELD}, ensure_ascii=False))


if __name__ == '__main__':
    main()
