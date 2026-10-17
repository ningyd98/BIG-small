from pathlib import Path
import datetime
import hashlib
import json
import stat
import subprocess

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
D = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round154-p6-delivery-head-diagnostic-recovery-20261012'
I = D / 'implementation'
DELIVERY = Path('/home/ningyd/.codex/worktrees/t12-p1-delivery/BIGsmall')
PLAN = json.loads((D / 'plan.json').read_text())
SPECS = {x['id']: x for x in PLAN['commands']}
HEAD = PLAN['facts']['observed_HEAD']

def pin(p):
    p = Path(p)
    assert p.is_file() and not p.is_symlink(), str(p)
    b = p.read_bytes()
    return {'path': str(p), 'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest(), 'mode': stat.S_IMODE(p.stat().st_mode)}

def save(p, x):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x', encoding='utf-8') as f:
        f.write(json.dumps(x, ensure_ascii=False, indent=2) + '\n')

def raw(p, b):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as f:
        f.write(b)

def git(cid, args=None, allowed=(0,)):
    spec = SPECS[cid]
    prefix = I / 'git' / cid
    inv = {'id': cid, 'argv': args or spec['argv'], 'cwd': spec['cwd'], 'start_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    save(Path(str(prefix) + '.invocation.json'), inv)
    r = subprocess.run(inv['argv'], cwd=inv['cwd'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    raw(Path(str(prefix) + '.stdout.txt'), r.stdout)
    raw(Path(str(prefix) + '.stderr.txt'), r.stderr)
    result = {**inv, 'end_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'exit_code': r.returncode,
              'stdout': pin(str(prefix) + '.stdout.txt'), 'stderr': pin(str(prefix) + '.stderr.txt')}
    save(Path(str(prefix) + '.result.json'), result)
    assert r.returncode in allowed, ('unexpected actual Git exit', cid, r.returncode)
    return r.stdout, result

def main():
    assert json.loads((D / 'root-activation.json').read_text())['status'] == 'ACTIVATED_DIAGNOSTIC_ONLY'
    checks = []
    def compare(p, expected):
        actual = pin(p)
        valid = all(actual[k] == expected[k] for k in ('bytes', 'sha256')) and ('mode' not in expected or actual['mode'] == expected['mode'])
        checks.append({'actual': actual, 'expected': expected, 'valid': valid})
    for x in PLAN['inputs']:
        compare(x['path'], x)
    oldplan = json.loads(Path(PLAN['transitive_inputs']['R153_plan']).read_text())
    for x in oldplan['inputs']:
        compare(x['path'], x)
    selected = json.loads(Path(PLAN['transitive_inputs']['static_payload']).read_text())
    for x in selected['files']:
        compare(x['path'], x)
    deps = json.loads(Path(PLAN['transitive_inputs']['dependency_and_owned_baseline']).read_text())
    for x in deps['dependencies']:
        compare(ROOT / x['path'], x['primary'])
        compare(DELIVERY / x['path'], x['delivery'])
    baseline_checks = []
    for x in deps['owned_delivery_baseline']:
        p = DELIVERY / x['path']
        if x['expected_new']:
            baseline_checks.append({'path': str(p), 'expected_absent': True, 'valid': not p.exists() and not p.is_symlink()})
        else:
            compare(p, x['delivery'])
    index = Path(PLAN['transitive_inputs']['source_protected_authority'])
    assert pin(index)['sha256'] == PLAN['transitive_inputs']['source_index_sha256']
    ix = json.loads(index.read_text())
    assert len(ix['sources']) == 6 and len(ix['protected']) == 53
    for x in ix['sources']:
        compare(x['source'], x)
        compare(x['snapshot'], x)
    for x in ix['protected']:
        compare(x['path'], x)
    review_path = next(x['path'] for x in oldplan['inputs'] if x['path'].endswith('/review/final-review.json'))
    review = json.loads(Path(review_path).read_text())
    for x in review['output_authority']['files']:
        compare(x['path'], x)
    assert all(x['valid'] for x in checks) and all(x['valid'] for x in baseline_checks)
    outputs = {}
    records = []
    for cid in ('D01', 'D02', 'D03', 'D04', 'D05', 'D06', 'D07', 'D08', 'D09', 'D10', 'D11'):
        out, rec = git(cid, allowed=(0, 1) if cid == 'D08' else (0,))
        outputs[cid] = out
        records.append(rec)
        if cid == 'D01':
            assert out.strip().decode() == HEAD
        if cid == 'D02':
            assert out.strip().decode() == 'codex/research-20261007-p1-delivery'
        if cid == 'D03':
            assert out.strip().decode() == 'refs/remotes/origin/codex/research-20261007-p1-delivery'
    upstream = outputs['D04'].strip().decode()
    live, remote_ref = outputs['D05'].strip().decode().split('\t')
    assert remote_ref == 'refs/heads/codex/research-20261007-p1-delivery'
    history = []
    for line in outputs['D09'].decode().splitlines():
        commit, parents, subject = line.split('\0', 2)
        history.append({'commit': commit, 'parents': parents.split(), 'subject': subject})
    parts = outputs['D10'].split(b'\0')
    changed = []
    n = 0
    while n < len(parts) and parts[n]:
        status = parts[n].decode()
        path = parts[n + 1].decode()
        n += 2
        other = None
        if status.startswith(('R', 'C')):
            other = parts[n].decode()
            n += 1
        changed.append({'status': status, 'path': path, 'other': other})
    binary = []
    parts = outputs['D11'].split(b'\0')
    n = 0
    while n < len(parts) and parts[n]:
        added, deleted, path = parts[n].decode().split('\t', 2)
        n += 1
        if not path:
            path = parts[n].decode()
            other = parts[n + 1].decode()
            n += 2
        if added == '-' or deleted == '-':
            binary.append(path)
    groups = {
        'selected': {x['relative_path'] for x in selected['files']},
        'dependencies': {x['path'] for x in deps['dependencies']},
        'owned': {x['path'] for x in deps['owned_delivery_baseline']},
        'protected': {str(Path(x['path']).relative_to(ROOT)) for x in ix['protected']},
        'status_targets': {str(Path(x['path']).relative_to(ROOT)) for x in oldplan['metadata_update']['before']}
    }
    paths = sorted({x['path'] for x in changed} | {x['other'] for x in changed if x['other']})
    overlaps = {k: sorted(set(paths) & v) for k, v in groups.items()}
    unsafe = []
    for p in paths:
        q = Path(p)
        safe_prefix = p.startswith(('docs/research/', 'artifacts/research/process/'))
        unsafe_token = any(t in p.lower() for t in ('credential', 'secret', '.env', '/sdk/', '/weights/', '/fixture/', '/fixtures/', '.sqlite', '.db', '/sources/'))
        if not safe_prefix or unsafe_token or q.suffix.lower() not in ('.md', '.json', '.txt', '.xml', '.patch', '.yaml', '.toml', '.csv') or p in binary:
            unsafe.append(p)
    ancestor = records[7]['exit_code'] == 0
    reasons = []
    if not ancestor:
        reasons.append('oldbase is not ancestor')
    if len(history) > 32:
        reasons.append('history exceeds32')
    if len(paths) > 64:
        reasons.append('changedpaths exceed64')
    if unsafe:
        reasons.append('unsafe or unsupported text content')
    diff_record = None
    if not reasons:
        diff, diff_record = git('D12', SPECS['D12']['argv'][:-1] + paths)
        records.append(diff_record)
        if len(diff) > 2 * 1024 * 1024:
            reasons.append('actualdiff exceeds2MiB')
    out, end_record = git('D13')
    records.append(end_record)
    assert out.strip().decode() == HEAD
    if outputs['D06']:
        reasons.append('delivery dirty')
    if upstream != HEAD or live != HEAD:
        reasons.append('local upstream/live remote not same observed HEAD')
    if overlaps['owned'] or overlaps['dependencies'] or overlaps['protected']:
        reasons.append('affected code/dependency/protected overlap needs new review')
    result = {'status': 'READ_ONLY_DIAGNOSTIC_COMPLETE', 'observed_HEAD': HEAD,
              'branch': outputs['D02'].strip().decode(), 'upstream': upstream, 'live_remote': live,
              'clean': not outputs['D06'], 'oldbase_ancestor': ancestor,
              'commit_raw': outputs['D07'].decode(), 'intervening_commits': history,
              'changed': changed, 'overlaps': overlaps, 'unsafe': unsafe, 'binary': binary,
              'diff_raw': diff_record['stdout'] if diff_record else None,
              'checks': checks, 'checks_count': len(checks), 'all_valid': True,
              'new_paths_absent_baseline_checks': baseline_checks,
              'R153_derived_presence': [{'path': p, 'exists': Path(p).exists()} for p in oldplan['payload']['exact_additional_paths']],
              'actual_Git': records, 'Git_commands_used': len(records), 'diagnostic_runner_used': 1,
              'diagnostic_runner_remaining': 0, 'eligible_for_new_delivery_plan': not reasons,
              'ineligible_reasons': reasons, 'delivery_authorized': False,
              'acceptance': False, 'new_product_commands': 0, 'R153_budget_reset': False}
    save(I / 'diagnostic.json', result)
    save(D / 'step-report.json', {'status': result['status'], 'actual_diagnostic': pin(I / 'diagnostic.json'),
                                 'Git_used': len(records), 'diagnostic_spent': '1/0',
                                 'eligible_for_new_delivery_plan': not reasons,
                                 'writes_or_acceptance_authorized': False})
    raw(D / 'step-report.md', ('# R154 只读诊断步骤报告\n\n'
        '实际诊断及原始Git流已完整保存；本轮不接受A、不修改交付或状态。'
        'R153原失败和四次Git消费保留，不重置预算。'
        '是否可按当前HEAD恢复交付，以diagnostic.json的真实lineage、diff、依赖和远端核对为准。\n').encode())
    print(json.dumps({'status': result['status'], 'HEAD': HEAD, 'upstream': upstream, 'live_remote': live,
                      'clean': result['clean'], 'oldbase_ancestor': ancestor, 'intervening_commits': len(history),
                      'changedpaths': len(paths), 'Git_used': len(records), 'checks': len(checks),
                      'eligible_for_new_delivery_plan': not reasons, 'reasons': reasons,
                      'report': pin(I / 'diagnostic.json')}, ensure_ascii=False))

if __name__ == '__main__':
    main()
