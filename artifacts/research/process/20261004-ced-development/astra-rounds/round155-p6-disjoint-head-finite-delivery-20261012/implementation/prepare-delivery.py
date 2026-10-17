from pathlib import Path
import base64
import datetime
import hashlib
import json
import os
import stat
import subprocess
import sys

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
D = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round155-p6-disjoint-head-finite-delivery-20261012'
I = D / 'implementation'
DELIVERY = Path('/home/ningyd/.codex/worktrees/t12-p1-delivery/BIGsmall')
BASE = '315fdadd8f42b0d624cafb9b5f0e4d5966a51b3e'
PLAN = json.loads((D / 'plan.json').read_text())
SPECS = {x['id']: x for x in PLAN['git_budget']['commands']}

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def pin(p):
    p = Path(p)
    assert p.is_file() and not p.is_symlink(), str(p)
    b = p.read_bytes()
    return {'path': str(p), 'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest(), 'mode': stat.S_IMODE(p.stat().st_mode)}

def expected(p, record):
    a = pin(p)
    assert all(a[k] == record[k] for k in ('bytes', 'sha256')), (str(p), a, record)
    if 'mode' in record:
        assert a['mode'] == record['mode'], (str(p), 'mode')
    return a

def save(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')

def write_bytes(p, b):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as f:
        f.write(b)

def relative(p):
    p = Path(p)
    r = p.relative_to(ROOT)
    assert str(r) and not any(x in ('.', '..') for x in r.parts)
    assert '\x00' not in str(r) and '\n' not in str(r)
    return str(r)

def safe_parent(p, root):
    p = Path(p)
    p.relative_to(root)
    assert not root.is_symlink()
    for q in (p, *p.parents):
        if q == root:
            break
        assert not q.is_symlink(), str(q)
        if q != p and q.exists():
            assert q.is_dir(), str(q)

def git(command_id, argv=None, stdin=None, allowed=(0,)):
    spec = SPECS[command_id]
    gd = I / 'git'
    gd.mkdir(parents=True, exist_ok=True)
    ordinal = next((n for n in range(1, spec['max_runs'] + 1)
                    if not (gd / f'{command_id}-{n}.invocation.json').exists()), None)
    assert ordinal is not None, ('budget exhausted', command_id)
    args = list(argv or spec['argv'])
    prefix = gd / f'{command_id}-{ordinal}'
    invocation = {'id': command_id, 'ordinal': ordinal, 'argv': args,
                  'cwd': spec['cwd'], 'start_utc': now(), 'stdin_bytes': len(stdin or b''), 'environment_override': {'GIT_OPTIONAL_LOCKS': '0'}}
    if stdin is not None:
        write_bytes(str(prefix) + '.stdin.bin', stdin)
        invocation['stdin_sha256'] = hashlib.sha256(stdin).hexdigest()
    save(str(prefix) + '.invocation.json', invocation)
    result = subprocess.run(args, cwd=spec['cwd'], input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'})
    write_bytes(str(prefix) + '.stdout.txt', result.stdout)
    write_bytes(str(prefix) + '.stderr.txt', result.stderr)
    record = {**invocation, 'end_utc': now(), 'exit_code': result.returncode,
              'stdout': pin(str(prefix) + '.stdout.txt'), 'stderr': pin(str(prefix) + '.stderr.txt')}
    save(str(prefix) + '.result.json', record)
    assert result.returncode in allowed, ('actual Git failure preserved', command_id, ordinal, result.returncode)
    return result.stdout, result.stderr, record

def entries(b):
    parts = b.split(b'\0')
    result = []
    n = 0
    while n < len(parts) and parts[n]:
        item = parts[n].decode('utf-8')
        xy, path = item[:2], item[3:]
        other = None
        if 'R' in xy or 'C' in xy:
            n += 1
            other = parts[n].decode('utf-8')
        result.append({'status': xy, 'path': path, 'other': other})
        n += 1
    return result

def payload_records():
    index = json.loads((D / 'payload-index.json').read_text())
    rows = index['files'] + [dict(pin(D / n), relative_path=relative(D / n), role='nonselfreferential-index') for n in ('payload-index.json', 'delivery-paths.txt')]
    assert len(rows) == 848
    return sorted(rows, key=lambda x: x['relative_path'])


def unrelated_check():
    before = json.loads((I / 'unrelated-before.json').read_text())
    assert before['count'] == 100 and len(before['files']) == 100
    return [expected(x['path'], x) for x in before['files']]


def inputs():
    checks = []
    for name, size, digest in (
        ('plan.md', 7186, '117dcbd4de49c47157a0d006ca6036fd20157e2059cc6f84ea4f86adea6f778c'),
        ('plan.json', 36082, '9aaa21e14dbbf38cb0ec18885019e1062b8515470c177789b458266e6cea1b82')):
        checks.append(expected(D / name, {'bytes': size, 'sha256': digest}))
    for x in PLAN['inputs']:
        checks.append(expected(x['path'], x))
    manifest = json.loads((D / 'selected-manifest.json').read_text())
    deps = json.loads(Path(PLAN['payload']['dependency_preparation']).read_text())
    assert len(manifest['files']) == 830
    selected = {x['path']: x for x in manifest['files']}
    assert len(selected) == 830
    for x in selected.values():
        assert relative(x['path']) == x['relative_path']
        safe_parent(Path(x['path']), ROOT)
        checks.append(expected(x['path'], x))
    for x in manifest['omitted_same_bytes']:
        c = selected[x['canonical_selected_path']]
        assert all(c[k] == x[k] for k in ('bytes', 'sha256'))
    state = json.loads(Path(PLAN['metadata_update']['before'][0]['path']).read_text())
    ix = state['current_P6_stage_A']['R147']['new19_index']
    checks.append(expected(ix['path'], ix))
    frozen = json.loads(Path(ix['path']).read_text())
    assert len(frozen['sources']) == 6 and len(frozen['protected']) == 53
    for x in frozen['sources']:
        checks.extend([expected(x['source'], x), expected(x['snapshot'], x)])
    for x in frozen['protected']:
        checks.append(expected(x['path'], x))
    for x in deps['dependencies']:
        checks.extend([expected(ROOT / x['path'], x['primary']), expected(DELIVERY / x['path'], x['delivery'])])
    owned_before = {x['path']: x for x in deps['owned_delivery_baseline']}
    for x in owned_before.values():
        p = DELIVERY / x['path']
        safe_parent(p, DELIVERY)
        if x['expected_new']:
            assert not p.exists()
        else:
            checks.append(expected(p, x['delivery']))
    paths = sorted(set(selected) | set(PLAN['payload']['exact_additional_paths']))
    assert len(paths) == 848
    target_before = {}
    mutable = {x['path'] for x in PLAN['metadata_update']['before']}
    for source in paths:
        rel = relative(source)
        target = DELIVERY / rel
        safe_parent(target, DELIVERY)
        if target.exists():
            old = pin(target)
            if rel in owned_before:
                assert not owned_before[rel]['expected_new']
                expected(target, owned_before[rel]['delivery'])
            elif source in selected:
                expected(target, {k: selected[source][k] for k in ('bytes', 'sha256')})
                assert bool(old['mode'] & 0o111) == bool(selected[source]['mode'] & 0o111)
            else:
                assert source in mutable, ('unexpected existing target', source)
            target_before[rel] = old
        else:
            target_before[rel] = None
    for command_id in ('M1', 'M2', 'M3', 'G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7', 'G8'):
        out, err, record = git(command_id, allowed=(0, 1) if command_id == 'G7' else (0,))
        checks.append({'git': command_id, 'result': record})
        if command_id == 'M1':
            assert out.strip().decode() == '34c7a5595b72a3b23f4d0ca4d31aa4154cd6f24e'
        elif command_id == 'M2':
            index_path = Path(out.strip().decode())
            if not index_path.is_absolute():
                index_path = ROOT / index_path
            main_index = pin(index_path)
        elif command_id == 'M3':
            main_before = entries(out)
        elif command_id in ('G1', 'G4'):
            assert out.strip().decode() == BASE
        elif command_id == 'G2':
            assert out.strip().decode() == 'codex/research-20261007-p1-delivery'
        elif command_id == 'G3':
            assert out.strip().decode() == 'refs/remotes/origin/codex/research-20261007-p1-delivery'
        elif command_id == 'G5':
            assert out == b''
        elif command_id == 'G6':
            assert out.decode().strip().split('\t') == [BASE, 'refs/heads/codex/research-20261007-p1-delivery']
        elif command_id == 'G7':
            configured_hooks = out.strip().decode() if record['exit_code'] == 0 else None
            assert record['exit_code'] == 0 or (not out and not err)
        elif command_id == 'G8':
            hooks = Path(configured_hooks or out.strip().decode())
            if not hooks.is_absolute():
                hooks = DELIVERY / hooks
            assert hooks.is_dir() and not hooks.is_symlink()
            active = [str(hooks / n) for n in ('pre-commit', 'prepare-commit-msg', 'commit-msg', 'post-commit', 'pre-push', 'post-rewrite')
                      if (hooks / n).exists() and os.access(hooks / n, os.X_OK)]
            assert not active, ('active hook requires new plan', active)
    parallel = json.loads(Path(PLAN['payload']['unrelated_protection']['manifest']).read_text())
    assert isinstance(parallel['paths'], list) and parallel['count'] == 100 and len(parallel['paths']) == 100
    assert len(set(parallel['paths'])) == 100 and parallel['base'] == BASE
    assert len(parallel['overlaps']) == 5 and all(v == [] for v in parallel['overlaps'].values())
    assert not set(parallel['paths']) & {relative(p) for p in paths}
    parallel_files = []
    for rel in parallel['paths']:
        p = DELIVERY / rel
        safe_parent(p, DELIVERY)
        assert str(p.relative_to(DELIVERY)) == rel
        parallel_files.append(pin(p))
    save(I / 'unrelated-before.json', {'status': 'EXACT_100_UNRELATED_BYTES_MODE_BASELINE', 'count': 100,
                                       'base': BASE, 'files': parallel_files, 'semantic_qualification': False})
    save(I / 'preflight.json', {'status': 'ALL_INITIAL_GATES_VALID', 'target_before': target_before,
                               'main_index': main_index, 'main_status_before': main_before,
                               'current_owned': frozen['sources'], 'checks_count': len(checks),
                               'all_match': True, 'hooks_path': str(hooks), 'active_hooks': active})
    save(D / 'input-check.json', {'status': 'ROOT_INPUTS_AND_ACTUAL_GIT_PREFLIGHT_VALID',
                                 'checks': checks, 'selected_files': 830, 'aliases_resolved': 206,
                                 'protected': 53, 'dependencies_both_roots': 50, 'all_valid': True})
    save(D / 'root-activation.json', {'status': 'ACTIVATED_FINITE_R155_ONLY',
                                     'time_utc': now(), 'actor': 'ROOT',
                                     'plan_md': pin(D / 'plan.md'), 'plan_json': pin(D / 'plan.json'),
                                     'input_check': pin(D / 'input-check.json'),
                                     'preflight': pin(I / 'preflight.json'),
                                     'new_product_or_review_budget': 0, 'retry_budget': 0,
                                     'acceptance_not_yet_decided': True})
    print(json.dumps({'phase': 'input', 'all_valid': True, 'checks': len(checks),
                      'target_existing': sum(x is not None for x in target_before.values()),
                      'target_existing_identical_static': sum(target_before[x['relative_path']] is not None and
                           target_before[x['relative_path']]['sha256'] == x['sha256'] for x in selected.values()),
                      'protected': 53, 'dependencies': 50}, ensure_ascii=False))

def manifest_phase():
    assert json.loads((D / 'update-report.json').read_text())['allowlist_equal']
    selected = json.loads((D / 'selected-manifest.json').read_text())
    rows = []
    for x in selected['files']:
        rows.append({**expected(x['path'], x), 'relative_path': x['relative_path'], 'role': x['role']})
    nonself = {str(D / n) for n in ('payload-index.json', 'delivery-paths.txt')}
    paths = sorted({x['path'] for x in rows} | set(PLAN['payload']['exact_additional_paths']))
    assert len(paths) == 848
    for p in PLAN['payload']['exact_additional_paths']:
        if p not in nonself:
            rows.append({**pin(p), 'relative_path': relative(p), 'role': 'R155-derived-or-updated-status'})
    assert len(rows) == 846 and len({x['relative_path'] for x in rows}) == 846
    index = {'status': 'EXACT_SELECTED_PAYLOAD_NOT_FULL_REMOTE_REPRODUCTION',
             'files': sorted(rows, key=lambda x: x['relative_path']), 'total_paths': 848,
             'self_hash_exclusions': sorted(nonself), 'aliases': selected['omitted_same_bytes'],
             'exclusions': PLAN['payload']['exclusions'], 'git_delivery': 'PENDING_ACTUAL_COMMIT_AND_PUSH'}
    save(D / 'payload-index.json', index)
    rels = sorted(relative(p) for p in paths)
    write_bytes(D / 'delivery-paths.txt', ('\n'.join(rels) + '\n').encode())
    write_bytes(I / 'delivery-paths.nul', b'\0'.join(x.encode() for x in rels) + b'\0')
    all_rows = payload_records()
    print(json.dumps({'phase': 'manifest', 'count': len(all_rows), 'bytes': sum(x['bytes'] for x in all_rows),
                      'payload_index': pin(D / 'payload-index.json'), 'paths': pin(D / 'delivery-paths.txt')}, ensure_ascii=False))

def copy_phase():
    import shutil
    pf = json.loads((I / 'preflight.json').read_text())
    rows = payload_records()
    for x in rows:
        expected(x['path'], x)
        target = DELIVERY / x['relative_path']
        old = pf['target_before'][x['relative_path']]
        if old is None:
            assert not target.exists() and not target.is_symlink()
        else:
            expected(target, old)
    out, _, _ = git('G1')
    assert out.strip().decode() == BASE
    unrelated_check()
    copied = []
    for x in rows:
        target = DELIVERY / x['relative_path']
        safe_parent(target, DELIVERY)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(x['path'], target)
        os.chmod(target, x['mode'])
        copied.append(expected(target, x))
    deps = json.loads(Path(PLAN['payload']['dependency_preparation']).read_text())
    for x in deps['dependencies']:
        expected(ROOT / x['path'], x['primary'])
        expected(DELIVERY / x['path'], x['delivery'])
    unrelated_check()
    save(I / 'copy-receipt.json', {'status': 'EXPLICIT_COPY_ALL_BYTES_AND_MODES_MATCH', 'files': copied,
                                  'count': len(copied), 'bytes': sum(x['bytes'] for x in copied),
                                  'dependencies_unchanged': 50,
                                  'expected_changed_paths': sorted(x['relative_path'] for x in rows
                                      if pf['target_before'][x['relative_path']] is None or
                                      any(pf['target_before'][x['relative_path']][k] != x[k] for k in ('bytes', 'sha256')) or
                                      bool(pf['target_before'][x['relative_path']]['mode'] & 0o111) != bool(x['mode'] & 0o111))})
    print(json.dumps({'phase': 'copy', 'all_valid': True, 'count': len(copied), 'bytes': sum(x['bytes'] for x in copied)}, ensure_ascii=False))

if __name__ == '__main__':
    {'input': inputs, 'manifest': manifest_phase, 'copy': copy_phase}[sys.argv[1]]()
