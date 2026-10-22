"""R300 finite metadata continuation; no product imports or runtime invocation."""
from pathlib import Path
import base64
import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import time
import traceback

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
B = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds'
D = B / 'round300-p6-t2-executor-and-baseline-continuation-20261022'
R = B / 'round296-p6-t2-rpc-timeout-passive-evidence-completion-20261017'
E = B / 'round298-p6-t2-plugin-finalization-eof-byte-generation-20261017'
F = B / 'round297-p6-t2-selected-event-attempt-accounting-20261017'
OLD = B / 'round289-p6-t2-accepted-runner-validation-continuation-20261017'
PLAN_SHA = '2c705dbe548521f06a817f0a9268e5b40747db992874bf9e2c9aabf434c742e9'
CHECKS = []
DEADLINE = time.monotonic() + 120

def expired(*args):
    raise TimeoutError('R300 metadata120s')

signal.signal(signal.SIGALRM, expired)
signal.alarm(120)

def check(ok, label):
    if time.monotonic() >= DEADLINE:
        expired()
    if not ok:
        raise ValueError(label)
    CHECKS.append(label)

def identity(q):
    return {k: q[k] for k in ('path', 'bytes', 'sha256')}

def raw(path):
    p = Path(path)
    before = p.lstat()
    check(stat.S_ISREG(before.st_mode), 'regular:' + str(p))
    b = p.read_bytes()
    after = p.lstat()
    coords = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    check(coords(before) == coords(after) and len(b) == before.st_size, 'stable:' + str(p))
    return b

def pin(path, data=None):
    p = Path(path)
    b = raw(p) if data is None else data
    return dict(path=str(p), bytes=len(b), sha256=hashlib.sha256(b).hexdigest())

def checked(q):
    b = raw(q['path'])
    check(pin(q['path'], b) == identity(q), 'pin:' + q['path'])
    return b

def read(path):
    return json.loads(raw(path))

def absent(path):
    p = Path(path)
    check(not p.exists() and not p.is_symlink(), 'absent:' + str(p))

def save(path, value):
    p = Path(path)
    b = (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode()
    with p.open('xb') as stream:
        check(stream.write(b) == len(b), 'write:' + str(p))
        stream.flush()
        os.fsync(stream.fileno())
    check(raw(p) == b, 'readback:' + str(p))
    return pin(p, b)

def before(row, current=True):
    b = checked(row['archive'])
    check(b == base64.b64decode(row['base64'], validate=True), 'before-base64')
    check(pin(row['original']['path'], b) == identity(row['original']), 'before-original-identity')
    check(Path(row['archive']['path']).lstat().st_mode == row['mode'], 'before-archive-mode')
    if current:
        check(checked(row['original']) == b, 'before-current')
        check(Path(row['original']['path']).lstat().st_mode == row['mode'], 'before-current-mode')
    return b

def git(*args):
    result = subprocess.run(['git', *args], cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=30, check=False)
    check(result.returncode == 0 and not result.stderr, 'git:' + args[0])
    return result.stdout

def common():
    p = read(D / 'plan.json')
    check(pin(D / 'plan.json')['sha256'] == PLAN_SHA, 'R300-frozen-plan')
    obs = json.loads(checked(p['input_observation']))
    check(p['inputs'] == obs['inputs'] and len(p['inputs']) == 65, 'R300-65-inputs')
    for q in p['inputs']:
        checked(q)
    binding = read(D / 'executor-binding.json')
    check(binding['actual_agent'] == '/root/runtime_repair_sol'
          and binding['actual_model'] == 'gpt-6.1-sol'
          and binding['spawn_actual'] == {'task_name': '/root/runtime_repair_sol'}
          and binding['sole_writer_accepted'] is True, 'actual-bound-Sol')
    check(binding['plan'] == pin(D / 'plan.json'), 'binding-plan')
    review = read(D / 'root-continuation-metadata-source-review.json')
    check(review['status'] == 'FULL_SOURCE_NATIVE_ARGV_REVIEWED'
          and review['source'] == pin(Path(__file__)), 'metadata-source-review')
    check(review['commands'] == {k: p['commands'][k] for k in ('applicability', 'publish_gates')},
          'two-literal-metadata-commands')
    check(git('rev-parse', 'HEAD').decode().strip() == p['HEAD_applicability']['required'], 'current-HEAD')
    check(git('branch', '--show-current').decode().strip() == p['HEAD_applicability']['branch'], 'branch')
    status = git('status', '--porcelain=v1', '-z').decode().split('\0')
    nested = set(obs['git']['status_porcelain'])
    new_outputs = set(p['R298_original_recovery_outputs'].values())
    new_outputs.update(p['metadata_contract']['modes']['publish-gates']['outputs'])
    observed_nested = set()
    for entry in filter(None, status):
        if entry in nested:
            observed_nested.add(entry)
        else:
            target = ROOT / entry[3:]
            check(entry.startswith('?? ') and (target.is_relative_to(D)
                  or str(target) in new_outputs), 'authorized-new-workspace-path:' + entry)
    check(observed_nested == nested, 'nested-dirty-preserved')
    r = read(R / 'plan.json')
    e = read(E / 'plan.json')
    check(p['commands']['r298_metadata'] == e['recovery_metadata']['tool_arguments']
          and p['commands']['diagnostic'] == r['commands']['dual_rpc_timeout_evidence']['tool_arguments'],
          'original-literal-commands-unchanged')
    return p, obs, r, e

def applicability(p, obs, r, e):
    absent(D / 'applicability.json')
    diff = git('diff', '--name-only', '-z', p['HEAD_applicability']['comparison_base'],
               p['HEAD_applicability']['required'])
    expected = obs['git']['diff_name_only_z']
    check(len(diff) == expected['bytes'] and hashlib.sha256(diff).hexdigest() == expected['sha256']
          and diff.decode().rstrip('\0').split('\0') == expected['paths'], 'exact-195-Git-paths')
    container = json.loads(checked(obs['authority_container']['pin']))
    sources = container['sources']
    prior = container['authority_before']
    check(len(r['inputs']) == 30 and len(sources) == 27 and len(prior['protected']) == 211
          and len(prior['accepted_history_generations']) == 68, 'finite30-27-211-container68')
    finite = r['inputs'] + sources + prior['protected'] + p['inputs']
    relative = {str(Path(q['path']).relative_to(ROOT)) for q in finite if Path(q['path']).is_relative_to(ROOT)}
    check(not (set(expected['paths']) & relative), 'changed-paths-no-authority-overlap')
    for q in r['inputs']:
        checked(q)
    for q in sources:
        data = checked(q)
        check(data == checked(q['physical']) == base64.b64decode(q['base64'], validate=True)
              and Path(q['path']).lstat().st_mode == q['mode'], 'current27-wholebytes-mode')
    for q in prior['protected']:
        checked(q)
    manifest = json.loads(checked(r['before_manifest']))
    check(len(manifest['files']) == 8, 'eight-R296-before')
    for row in manifest['files']:
        before(row)
    context = read(OLD / 'root-context-update.json')
    check(context['round'] == 'R289' and context['T2_complete'] is False and len(context['changes']) == 2,
          'R289-context')
    for row in context['changes']:
        before(row['before'], False)
        check(checked(row['after']) == checked(row['after_archive']), 'current-context-after')
    settlement = read(OLD / 'root-dual-first-invalidation-role-settlement.json')
    before(settlement['root_before'], False)
    check(checked(settlement['root_after']) == checked(settlement['after_archive']), 'old-root-settled')
    checked(settlement['author_unchanged'])
    for role, path in [('ROOT', OLD / 'root-command-ledger.json'),
                       ('AUTHOR', OLD / 'implementation/command-ledger.json')]:
        ledger = read(path)
        for key in ('wait_memory', 'wait_sqlite', 'dual_first_invalidation'):
            q = ledger['commands'][key]
            check(q['used'] == 1 and q['remaining'] == 0 and q['state'].startswith('SPENT'), role + key)
    command = r['commands']['dual_rpc_timeout_evidence']
    check((command['authorized'], command['used'], command['remaining']) == (1, 0, 1), 'R296-original-held')
    check(len(e['inputs']) == 11, 'R298-eleven-inputs')
    for q in e['inputs']:
        checked(q)
    manifest = json.loads(checked(e['before_manifest']))
    check(len(manifest['files']) == 5, 'R298-five-before')
    for row in manifest['files']:
        before(row)
    for row in obs['outputs_observed']:
        check(row['exists'] is False and row['is_symlink'] is False, 'planning-absence')
        absent(row['path'])
    old = read(F / 'plan.json')
    for key in ('diff', 'proof', 'report'):
        absent(old['outputs'][key])
    absent(old['scope']['after_archive'])
    review = read(R / 'root-candidate-source-fulltext-review.json')
    reconstruction = {}
    for key in ('runner', 'plugin_first_generation'):
        entry = review[key]
        check(all(q['status'] == 'fulfilled' and q['value']['exit_code'] == 0
                  for q in entry['source_pieces']), 'original-fullreads:' + key)
        data = ''.join(q['value']['output'] for q in entry['source_pieces']).encode()
        check(pin(entry['path'], data) == identity(entry), 'source-fulltext-reconstruction:' + key)
        reconstruction[key] = pin(entry['path'], data)
    check(checked(e['scope']['target']) + b'\n' == checked(e['scope']['approved_candidate']), 'actual08df-plus-one-LF')
    source_pins = p['gate_schema']['source_gate']['required']['sources']
    for q in source_pins.values():
        checked(q)
        check(Path(q['path']).lstat().st_mode == 33204, 'current-source-mode')
    fixed = p['inputs'] + [pin(D / n) for n in ('plan.json', 'input-observation.json', 'executor-binding.json',
             'root-continuation-metadata.py', 'root-continuation-metadata-source-review.json')]
    return save(D / 'applicability.json', {'round': 'R300', 'status': 'R300_CONTINUATION_APPLICABLE_NO_RUNTIME_RELEASE',
        'plan': pin(D / 'plan.json'), 'fixed_inputs': fixed, 'sources': source_pins,
        'source_reconstruction': reconstruction, 'checks': list(CHECKS), 'runtime': 0, 'T2_complete': False})

def publish(p, obs, r, e):
    app = read(D / 'applicability.json')
    check(app['status'] == 'R300_CONTINUATION_APPLICABLE_NO_RUNTIME_RELEASE', 'applicability-success')
    for q in app['fixed_inputs']:
        checked(q)
    acceptance = read(D / 'r298-metadata-acceptance.json')
    check(acceptance['status'] == 'R298_METADATA_ACCEPTED_SOURCE_ONLY'
          and acceptance['actual_exit'] == 0 and acceptance['metadata_complete'] is True, 'R298-independent-acceptance')
    for q in acceptance['output_pins'].values():
        checked(q)
    proof = read(e['recovery_metadata']['outputs']['proof'])
    check(proof['original_R297_expected_match'] is False and proof['R298_exact_generation_match'] is True
          and len(proof['four_planned_edits']) == 4 and len(proof['byte_deltas']) == 5
          and checked(proof['target']) == checked(proof['after'])
          == base64.b64decode(proof['after_base64'], validate=True), 'four-edits-plus-exact-EOF')
    final = read(D / 'final-source-review.json')
    check(final['status'] == 'FULL_SOURCE_NATIVE_ARGV_ACCEPTED'
          and final['sources'] == app['sources']
          and final['commands'] == r['commands'], 'final-source-and-original-command-review')
    for q in final['evidence']:
        checked(q)
    outputs = p['metadata_contract']['modes']['publish-gates']['outputs']
    for path in outputs:
        absent(path)
    native = save(outputs[0], {'round': 'R300', 'status': 'ACTUAL_NATIVE_GENERATION_CHAIN',
        'evidence': final['evidence'], 'R298_acceptance': pin(D / 'r298-metadata-acceptance.json'),
        'original_empty_native_numeric_exit': None, 'historical_failure_preserved': True})
    all_fixed = r['inputs'] + p['inputs'] + [pin(D / n) for n in ('plan.json', 'input-observation.json',
        'executor-binding.json', 'applicability.json', 'r298-metadata-acceptance.json', 'final-source-review.json')]
    all_fixed += [native] + final['evidence'] + list(acceptance['output_pins'].values())
    fixed = list({(q['path'], q['sha256']): identity(q) for q in all_fixed}.values())
    sg = {'round': 'R296', 'status': 'VERIFIED_SOURCE_ONLY', 'plan': pin(R / 'plan.json'),
        'observation': pin(R / 'input-observation.json'), 'supplement': pin(R / 'prerequisite-supplement.json'),
        'sources': app['sources'], 'input_check': pin(D / 'applicability.json'), 'native': native,
        'context_manifest': pin(OLD / 'root-context-update.json'), 'fixed_inputs': fixed, 'runtime': 0, 'T2_complete': False}
    sg_pin = save(outputs[1], sg)
    roles = {k: r['runner_contract']['roles'][k] for k in ('ROOT', 'AUTHOR')}
    jg = {'round': 'R296', 'status': 'VERIFIED_BY_ROOT', 'plan': sg['plan'], 'source_gate': sg_pin,
          'sources': sg['sources'], 'commands': r['commands'], 'role_files': roles,
          'reservation_directory': str(R / 'root-reservations'), 'runtime': 0, 'T2_complete': False}
    jg_pin = save(outputs[2], jg)
    ag_pin = save(outputs[3], {'round': 'R296', 'status': 'FULL_SOURCE_NATIVE_INPUT_ARGV_ACCEPTED_NO_DISPATCH',
        'source_gate': sg_pin, 'script_gate': jg_pin, 'R300_continuation': pin(D / 'plan.json'),
        'executor_binding': pin(D / 'executor-binding.json'), 'final_review': pin(D / 'final-source-review.json'),
        'runtime': 0, 'T2_complete': False})
    return {'status': 'R300_SOURCE_GATES_PUBLISHED_NO_DISPATCH', 'source_gate': sg_pin,
            'script_gate': jg_pin, 'final_acceptance': ag_pin, 'checks_passed': len(CHECKS)}

def main():
    check(len(sys.argv) == 2 and sys.argv[1] in ('applicability', 'publish-gates'), 'explicit-two-modes')
    p, obs, r, e = common()
    result = applicability(p, obs, r, e) if sys.argv[1] == 'applicability' else publish(p, obs, r, e)
    text = json.dumps(result, ensure_ascii=False)
    check(len((text + '\n').encode()) <= 6000, 'console6000')
    print(text)

if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        failure = {'round': 'R300', 'mode': sys.argv[1:] , 'status': 'FAILED_NO_RETRY',
                   'type': type(error).__name__, 'error': str(error), 'traceback': traceback.format_exc(),
                   'checks_completed': CHECKS, 'runtime': 0}
        destination = D / ('metadata-' + (sys.argv[1] if len(sys.argv) == 2 else 'invalid') + '-failure.json')
        with destination.open('xb') as stream:
            stream.write((json.dumps(failure, ensure_ascii=False, indent=2) + '\n').encode())
        raise
    finally:
        signal.alarm(0)
