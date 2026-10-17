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
D = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round153-p6-stage-a-finite-git-delivery-20261012'
I = D / 'implementation'
DELIVERY = Path('/home/ningyd/.codex/worktrees/t12-p1-delivery/BIGsmall')
BASE = 'cb59be66fe281d7ee2c1ca90bc803c3b80f37c76'
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
                  'cwd': spec['cwd'], 'start_utc': now(), 'stdin_bytes': len(stdin or b'')}
    if stdin is not None:
        write_bytes(str(prefix) + '.stdin.bin', stdin)
        invocation['stdin_sha256'] = hashlib.sha256(stdin).hexdigest()
    save(str(prefix) + '.invocation.json', invocation)
    result = subprocess.run(args, cwd=spec['cwd'], input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
    assert len(rows) == 759
    return sorted(rows, key=lambda x: x['relative_path'])


import re
import shlex

def stage():
    rows = payload_records()
    byrel = {x['relative_path']: x for x in rows}
    copied = json.loads((I / 'copy-receipt.json').read_text())
    expected_changed = set(copied['expected_changed_paths'])
    for x in rows:
        expected(x['path'], x)
        expected(DELIVERY / x['relative_path'], x)
    git('G9')
    out, _, name_record = git('G10')
    parts = out.split(b'\0')
    changed = {}
    n = 0
    while n < len(parts) and parts[n]:
        change = parts[n].decode()
        name = parts[n + 1].decode()
        assert change in ('A', 'M'), (change, name)
        assert name not in changed
        changed[name] = change
        n += 2
    assert set(changed) == expected_changed, ('staged path mismatch', sorted(set(changed) ^ expected_changed))
    out, _, mode_record = git('G11', ['git', 'ls-files', '--stage', '-z', '--', *sorted(byrel)])
    staged = []
    for item in out.split(b'\0'):
        if item:
            left, name = item.decode().split('\t', 1)
            mode, oid, stage_number = left.split()
            assert stage_number == '0' and mode in ('100644', '100755')
            assert name in byrel
            assert mode == ('100755' if byrel[name]['mode'] & 0o111 else '100644')
            staged.append({'path': name, 'mode': mode, 'oid': oid})
    assert len(staged) == 759 and {x['path'] for x in staged} == set(byrel)
    out, _, blob_record = git('G12', stdin=b''.join((x['oid'] + '\n').encode() for x in staged))
    pos = 0
    for x in staged:
        end = out.index(b'\n', pos)
        oid, kind, size = out[pos:end].decode().split()
        assert oid == x['oid'] and kind == 'blob'
        start = end + 1
        b = out[start:start + int(size)]
        pos = start + int(size)
        assert out[pos:pos + 1] == b'\n'
        pos += 1
        p = byrel[x['path']]
        assert len(b) == p['bytes'] and hashlib.sha256(b).hexdigest() == p['sha256']
    assert pos == len(out)
    diff, _, diff_record = git('G13')
    headers = []
    hunk_counts = {}
    current = None
    for line in diff.splitlines():
        if line.startswith(b'diff --git '):
            a, b = shlex.split(line.decode())[2:]
            assert a.startswith('a/') and b.startswith('b/') and a[2:] == b[2:]
            current = a[2:]
            headers.append(current)
            hunk_counts[current] = 0
        elif line.startswith(b'@@ '):
            hunk_counts[current] += 1
    assert set(headers) == expected_changed and len(headers) == len(expected_changed)
    strict = {x['relative_path'] for x in rows if x['role'] == 'current-owned-source'}
    owned = json.loads((I / 'preflight.json').read_text())['current_owned']
    strict.update(relative(x['source']) for x in owned)
    strict.update(relative(p) for p in PLAN['payload']['exact_additional_paths'])
    out, err, ws_record = git('G14', allowed=(0, 1, 2))
    exceptions = []
    diagnostics = out.decode().splitlines()
    for line in diagnostics:
        m = re.fullmatch(r'(.+):(\d+): (.+)', line)
        if m:
            path, number, diagnosis = m.groups()
            assert path in byrel and path not in strict, ('unexpected whitespace', path, line)
            p = byrel[path]
            assert p['role'] != 'R153-derived-or-updated-status'
            original_lines = Path(p['path']).read_bytes().splitlines(keepends=True)
            number = int(number)
            assert 1 <= number <= len(original_lines)
            exceptions.append({'path': path, 'role': p['role'], 'file_sha256': p['sha256'],
                               'line': number, 'line_bytes_sha256': hashlib.sha256(original_lines[number - 1]).hexdigest(),
                               'actual_diagnostic': line, 'reason': 'Frozen historical evidence, exact bytes preserved.'})
        else:
            assert line.startswith('+') or not line.strip(), ('unrecognized diff-check output', line)
    assert not err
    assert ws_record['exit_code'] == 0 or exceptions
    save(I / 'whitespace-exceptions.json', {'actual_exit_code': ws_record['exit_code'], 'exceptions': exceptions,
                                           'original_artifact_bytes_unchanged': True})
    out, err, strict_record = git('G15', ['git', 'diff', '--cached', '--check', '--', *sorted(strict)])
    assert not out and not err
    receipt = {'status': 'STAGED_ALL_759_BLOBS_BYTE_MODE_AND_PATHS_MATCH',
               'payload_count': 759, 'changed_count': len(changed), 'changed': changed,
               'unchanged_selected_paths': sorted(set(byrel) - expected_changed),
               'bytes': sum(x['bytes'] for x in rows), 'staged': staged,
               'full_diff': diff_record['stdout'], 'diff_headers': headers, 'hunk_counts': hunk_counts,
               'blob_capture': blob_record['stdout'], 'whitespace_exceptions': pin(I / 'whitespace-exceptions.json'),
               'strict_diff_check': strict_record, 'pending_ROOT_finite_diff_gate': True}
    save(I / 'staged-receipt.json', receipt)
    save(I / 'precommit-receipt.json', {'status': 'ALL_PAYLOAD_BYTES_VERIFIED_PENDING_ROOT_COMMIT_GATE',
                                       'files': rows, 'payload_index': pin(D / 'payload-index.json'),
                                       'delivery_paths': pin(D / 'delivery-paths.txt'),
                                       'staged_receipt': pin(I / 'staged-receipt.json')})
    print(json.dumps({'phase': 'staged_audit', 'payload_files': 759, 'changed_files': len(changed),
                      'bytes': receipt['bytes'], 'all_blobs_match': True, 'strict_check_exit': 0,
                      'historical_whitespace_exit': ws_record['exit_code'], 'historical_exceptions': len(exceptions),
                      'code_hunks': {relative(x['source']): hunk_counts.get(relative(x['source']), 0) for x in owned},
                      'full_diff': receipt['full_diff'], 'receipt': pin(I / 'staged-receipt.json')}, ensure_ascii=False))

def deliver():
    receipt = json.loads((I / 'staged-receipt.json').read_text())
    assert receipt['status'] == 'STAGED_ALL_759_BLOBS_BYTE_MODE_AND_PATHS_MATCH'
    for x in payload_records():
        expected(x['path'], x)
        expected(DELIVERY / x['relative_path'], x)
    out, _, _ = git('G1')
    assert out.strip().decode() == BASE
    commit_out, _, commit_result = git('G16')
    gd_text = (DELIVERY / '.git').read_text().strip()
    assert gd_text.startswith('gitdir: ')
    gd = Path(gd_text[8:])
    if not gd.is_absolute():
        gd = DELIVERY / gd
    common_dir = gd
    if (gd / 'commondir').exists():
        c = Path((gd / 'commondir').read_text().strip())
        common_dir = c if c.is_absolute() else gd / c
    ref = common_dir / 'refs/heads/codex/research-20261007-p1-delivery'
    created = ref.read_text().strip()
    assert re.fullmatch('[0-9a-f]{40}', created) and created != BASE
    assert created[:7].encode() in commit_out
    out, _, _ = git('G6')
    assert out.decode().strip().split('\t') == [BASE, 'refs/heads/codex/research-20261007-p1-delivery']
    git('G17')
    identity = {}
    for command_id in ('G1', 'G4', 'G6', 'G5'):
        out, _, result = git(command_id)
        if command_id == 'G6':
            value, remote_ref = out.decode().strip().split('\t')
            assert remote_ref == 'refs/heads/codex/research-20261007-p1-delivery'
            identity['live_remote'] = value
        elif command_id == 'G5':
            assert not out
            identity['delivery_clean'] = True
        else:
            identity['local_HEAD' if command_id == 'G1' else 'upstream_HEAD'] = out.strip().decode()
    assert identity['local_HEAD'] == identity['upstream_HEAD'] == identity['live_remote'] == created
    pf = json.loads((I / 'preflight.json').read_text())
    expected(pf['main_index']['path'], pf['main_index'])
    out, _, _ = git('M3')
    after = entries(out)
    allowed_files = {relative(x['path']) for x in PLAN['metadata_update']['before']}
    prefix = relative(D) + '/'
    def preserved(es):
        return sorted((x['status'], x['path'], x['other'] or '') for x in es
                      if x['path'] not in allowed_files and not x['path'].startswith(prefix))
    assert preserved(pf['main_status_before']) == preserved(after)
    rows = payload_records()
    for x in rows:
        expected(x['path'], x)
        expected(DELIVERY / x['relative_path'], x)
    specs = []
    used = 0
    for command_id, spec in SPECS.items():
        for n in range(1, spec['max_runs'] + 1):
            p = I / 'git' / f'{command_id}-{n}.result.json'
            if p.exists():
                specs.append(pin(p))
                used += 1
    assert used <= 28
    final = {'status': 'BOUNDED_STAGE_A_SELECTED_DELIVERY_COMMITTED_PUSHED_VERIFIED',
             'time_utc': now(), 'branch': 'codex/research-20261007-p1-delivery',
             'base': BASE, 'commit': created, 'identity': identity, 'git_commands_used': used,
             'git_commands_remaining': 28 - used, 'retry_budget': 0,
             'files': 759, 'changed_files': receipt['changed_count'], 'bytes': sum(x['bytes'] for x in rows),
             'payload_index': pin(D / 'payload-index.json'), 'delivery_paths': pin(D / 'delivery-paths.txt'),
             'plan': pin(D / 'plan.json'), 'acceptance': pin(D / 'acceptance.json'),
             'staged_receipt': pin(I / 'staged-receipt.json'), 'precommit_receipt': pin(I / 'precommit-receipt.json'),
             'actual_git_results': specs, 'main_index_unchanged': True, 'main_unrelated_dirty_entries_retained': True,
             'B9_open': True, 'whole_P6_complete': False, 'native_physics_actual_formal_accepted': False,
             'remote_reproduction': 'SELECTED_PACKAGE_ONLY_NOT_FULL_FIXTURE_RAW_DATABASE_PACKAGE',
             'receipt_location': 'LOCAL_OUTSIDE_COMMIT_NO_SELF_REFERENCE'}
    save(D / 'postpush-receipt.json', final)
    print(json.dumps({k: final[k] for k in ('status', 'commit', 'identity', 'git_commands_used', 'files', 'changed_files', 'bytes', 'B9_open', 'whole_P6_complete')}, ensure_ascii=False))

if __name__ == '__main__':
    {'stage': stage, 'deliver': deliver}[sys.argv[1]]()
