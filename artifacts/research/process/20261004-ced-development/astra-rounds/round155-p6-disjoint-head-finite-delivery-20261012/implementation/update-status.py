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


def main():
    assert json.loads((D / 'root-activation.json').read_text())['status'] == 'ACTIVATED_FINITE_R155_ONLY'
    before = PLAN['metadata_update']['before']
    original = {x['path']: Path(x['path']).read_bytes() for x in before}
    for x in before:
        expected(x['path'], x)
        write_bytes(I / 'before' / Path(x['path']).name, original[x['path']])
    review_path = next(x['path'] for x in PLAN['inputs'] if x['path'].endswith('/review/final-review.json'))
    review = json.loads(Path(review_path).read_text())
    assert review['assessment']['new_confirmed_product_defects'] == 0
    assert review['assessment']['recommendation'] == 'ELIGIBLE_FOR_ROOT_BOUNDED_STAGE_A_SOFTWARE_DECISION'
    pf = json.loads((I / 'preflight.json').read_text())
    acceptance = {'status': 'ROOT_BOUNDED_STAGE_A_SOFTWARE_ACCEPTED', 'actor': 'ROOT', 'time_utc': now(),
                  'ceiling': PLAN['acceptance']['allowed_ceiling'], 'six_sources': pf['current_owned'],
                  'final_review': pin(review_path), 'confirmed_findings': {'critical': 0, 'important': 0, 'minor': 0},
                  'runs': review['evidence']['runs'][:4], 'unique_terminal_pass_nodes': 40,
                  'single40_run': False, 'old19PASS1FAIL_preserved': True,
                  'bridges': review['evidence']['bridges'], 'static_actual': review['evidence']['actual_static'],
                  'positive': review['evidence']['positive'],
                  'limitations': {'B9': review['issues']['known_open_followup'],
                                  'precise_terminal_COMMIT_ackloss': 'NOT_ACTUALLY_EXECUTED',
                                  'legacy_UTC_veto': 'RETAINED', 'remaining_product_commands': 0,
                                  'remaining_independent_review_reads': 0, 'no_rerun': True},
                  'explicit_false': {k: False for k in PLAN['acceptance']['explicit_false']},
                  'git_delivery': 'PENDING_ACTUAL_COMMIT_AND_PUSH',
                  'disjoint_head_adoption': PLAN['disposition'],
                  'unrelated_100_before': pin(I / 'unrelated-before.json'),
                  'remote_boundary': 'Selected code/metadata/raw/proofs only; full fixture databases and batch raw remain local;206 equal-byte aliases reference retained records, omitted original paths are not remotely present.'}
    save(D / 'acceptance.json', acceptance)
    source_lines = '\n'.join('- ' + x['source'] + ' SHA256 ' + x['sha256'] for x in pf['current_owned'])
    append = (
        '\n\n## 2026-10-12 当前 P6 A 阶段状态（R155）\n\n'
        '本段更新并覆盖此前正文中 P6 A 待执行、待终审或未验收的当前状态描述；此前正文和各轮记录保留为历史。\n\n'
        'ROOT 已依据 R152 独立终审限定接受 A 阶段软件交付，上限为 LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO。'
        '终审在此范围内 Critical、Important、Minor 已确认问题均为0，24/24读取已用尽。\n\n'
        '40个唯一通过节点来自四次实际运行：历史 GREEN20 的19 PASS（原1 FAIL完整保留）、R147修正foreign单例1 PASS、new19的19 PASS、R141 CPU受控正链1 PASS。'
        '这不是一次40节点运行；R145类型变更和R147夹具变更仅按已核精确证明沿用证据。原静态失败与过程工具失败未删除。\n\n'
        'CPU正链先调用原episode一次，仅注入六项结局flags，22个自然文件hash已核；模型调用、动作和物理量证据均为0。'
        'legacy UTC veto保留。B9公开确认与SQL历史区分仍为OPEN，精确terminal COMMIT成功后失确认组合未实际执行。'
        'B/C/D为NOT_ACTIVATED，P6_complete=false；native、physics、硬件真实运行与formal验收均未提升。\n\n'
        '下一步依既定顺序推进B9/B、C、P7/P8、D；B9需显式区分SQL事实与已确认发布，并先按Astra计划限定验证。'
        'R153旧HEAD前置失败原件保留；R154只读诊断的文本覆盖限制及eligible=false未改写。R155明确采用315fd不相交基线，保全100个开题文档相关既有文件，不对其语义作本轮判断。'
        '本段编制时Git交付待执行，实际提交、推送与三SHA结果以本轮提交外postpush-receipt.json为准。'
        '远端选定载荷不是完整raw/数据库复现包。\n\n'
        '验收记录：' + str(D / 'acceptance.json') + '\n\n'
        '终审原件：' + review_path + ' SHA256 ' + acceptance['final_review']['sha256'] + '\n\n'
        '交付实际收据：' + str(D / 'postpush-receipt.json') + '\n'
    )
    write_bytes(D / 'acceptance.md', (
        '# P6 Stage A ROOT 限定软件验收\n\n'
        '决定：ROOT_BOUNDED_STAGE_A_SOFTWARE_ACCEPTED；完整P6、公开发布闭合、native/physics/hardware/actual/formal均未验收。\n'
        + append + '\n六份冻结源码：\n\n' + source_lines + '\n').encode())
    state_path = Path(before[0]['path'])
    old_state = json.loads(original[str(state_path)])
    state = json.loads(original[str(state_path)])
    a = state['current_P6_stage_A']
    a['status'] = 'ROOT_BOUNDED_STAGE_A_SOFTWARE_ACCEPTED_GIT_PENDING'
    a['production_writes'] = 'Final six-source freeze unchanged; independent R152 review complete; ROOT accepted bounded software A only.'
    a['fresh_final_review'] = {'status': 'INDEPENDENT_FINAL_REVIEW_COMPLETE', 'round': 'R152',
                               'ceiling': PLAN['acceptance']['allowed_ceiling'], 'report': pin(review_path),
                               'critical': 0, 'important': 0, 'minor': 0, 'used': 24, 'remaining': 0}
    a['software_acceptance'] = {'status': acceptance['status'], 'ceiling': acceptance['ceiling'],
                                'record': pin(D / 'acceptance.json'), 'whole_P6_complete': False}
    a['current_limitations'] = acceptance['limitations']
    a['git_delivery'] = {'status': 'PENDING_ACTUAL_FINITE_R155_DELIVERY',
                         'actual_receipt': str(D / 'postpush-receipt.json')}
    assert 'R155' not in state['planning']
    state['planning']['R155'] = {'status': 'ACTIVATED_A_ONLY_FINITE_GIT_DELIVERY',
                                'plan': pin(D / 'plan.json'), 'new_product_or_review_budget': 0,
                                'explicit_disjoint_head_adoption': PLAN['disposition']}
    allowed = ('status', 'production_writes', 'fresh_final_review', 'software_acceptance', 'current_limitations', 'git_delivery')
    left = json.loads(json.dumps(old_state))
    right = json.loads(json.dumps(state))
    for x in allowed:
        left['current_P6_stage_A'].pop(x, None)
        right['current_P6_stage_A'].pop(x, None)
    right['planning'].pop('R155')
    assert left == right
    assert a['P6_complete'] is False and a['B_C_D'] == 'NOT_ACTIVATED' and a['remaining_validation_commands'] == 0
    updated = {str(state_path): (json.dumps(state, ensure_ascii=False, indent=2) + '\n').encode()}
    for x in before[1:]:
        updated[x['path']] = original[x['path']] + append.encode()
        assert updated[x['path']].startswith(original[x['path']])
    for x in before:
        assert Path(x['path']).read_bytes() == original[x['path']], ('concurrent change', x['path'])
    for p, b in updated.items():
        Path(p).write_bytes(b)
    report = {'status': 'EXACT_ALLOWLIST_AND_APPEND_UPDATE_COMPLETED', 'allowlist_equal': True,
              'allowed_fields': PLAN['metadata_update']['STATE_allowed'], 'before': before,
              'after': [pin(x['path']) for x in before], 'append_prefix_preserved': True,
              'historical_records_unchanged': True, 'git_status': 'PENDING',
              'acceptance': pin(D / 'acceptance.json')}
    save(D / 'update-report.json', report)
    step = {'status': 'METADATA_AND_ACCEPTANCE_READY_GIT_NOT_YET_EXECUTED',
            'input': pin(D / 'input-check.json'), 'acceptance': pin(D / 'acceptance.json'),
            'update': pin(D / 'update-report.json'), 'product_commands': 0, 'new_review_reads': 0,
            'complete_P6': False, 'B9_open': True,
            'actual_git_identity_receipt_local_only': str(D / 'postpush-receipt.json')}
    save(D / 'step-report.json', step)
    write_bytes(D / 'step-report.md', ('# R155 步骤报告（提交前快照）\n\n'
        'A阶段软件范围已由ROOT限定验收；状态allowlist等价与两文档原字节前缀保持均通过。\n'
        '精确848路径的载荷准备按计划进行；commit/push尚未执行，实际结果写提交外postpush收据。\n'
        '四运行40唯一PASS、原19PASS1FAIL、类型/夹具桥接与CPU六flags边界保留；B9未闭合。\n'
        '完整raw/fixture/数据库仍本地，不宣称完整远端复现。未新增产品命令、终审额度或重试。\n').encode())
    print(json.dumps({'phase': 'acceptance_and_update', 'allowlist_equal': True,
                      'bounded_A_accepted': True, 'whole_P6': False, 'update_report': pin(D / 'update-report.json')}, ensure_ascii=False))

if __name__ == '__main__':
    main()
