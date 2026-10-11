from pathlib import Path
from copy import deepcopy
import hashlib
import json

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
BASE = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds'
ROUND = BASE / 'round150-p6-metadata-lifecycle-and-review-recovery-20261012'
OUT = ROUND / 'implementation'
R147 = BASE / 'round147-p6-foreign-repository-fixture-lock-recovery-20261012'


def pin(path, data=None):
    path = Path(path)
    data = path.read_bytes() if data is None else data
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def load(path):
    return json.loads(Path(path).read_bytes())


plan = load(ROUND / 'plan.json')
assert pin(ROUND / 'plan.json')['sha256'] == 'c2cca65a5a83601ef7db1837bddb4ba29bada9f1117edfd8b4521284f817d0da'
receipt = load(OUT / 'reader.json')
reader_pin = pin(OUT / 'reader.json')
assert reader_pin['sha256'] == '4630f9d49ecf1efb71f59f891cb090565d452fdbdd3ea80b2ce93f3a51dd0fed'
assert receipt['status'] == 'PASS_SCENARIO_AWARE_NEW19_METADATA'
assert len(receipt['checks']) == 2605 and all(x['match'] for x in receipt['checks'])
assert load(OUT / 'result.json')['actual_tool_result']['exit_code'] == 0
assert receipt['unique_terminal_pass_nodes'] == 40 and receipt['single40_run'] is False and receipt['acceptance'] is False
index = load(R147 / 'implementation/new19-freeze/source-index.json')
input_pins = {x['path']: x for x in plan['inputs']}
root_ledger_pins = [index['ledgers'][k]['file'] for k in ['r127_root', 'r147_root']]
state_path = Path(plan['sync']['state'])
phase_path = Path(plan['sync']['phase'])
paths = [Path(x['source']) for x in root_ledger_pins] + [state_path, phase_path]
expected = [{**x, 'path': x['source']} for x in root_ledger_pins] + [input_pins[str(state_path)], input_pins[str(phase_path)]]
before = [p.read_bytes() for p in paths]
assert all(len(b) == x['bytes'] and hashlib.sha256(b).hexdigest() == x['sha256'] for b, x in zip(before, expected))
original = [json.loads(b) for b in before[:3]]
new = deepcopy(original)
actual_result_entry = [x for x in index['raw'] if Path(x['source']).name == 'result.json']
assert len(actual_result_entry) == 1
actual_result = load(actual_result_entry[0]['snapshot'])
assert actual_result['used'] == 1 and actual_result['remaining'] == 0 and actual_result['exit_code'] == 0
provenance = {'actual_result': actual_result_entry[0], 'complete_root_reader': reader_pin, 'nodes': 19, 'failures': 0, 'errors': 0, 'skipped': 0, 'no_rerun': True, 'review': 'FRESH_FINAL_REVIEW_PENDING'}
for target in [new[0]['commands']['new_green'], new[1]['inherited_new_green19']]:
    assert target['authorized'] == 1 and target['used'] == 0 and target['remaining'] == 1
    assert target['argv'] == actual_result['argv']
    target.update({'used': 1, 'remaining': 0, 'exit_code': 0, 'status': 'SPENT_ACTUAL19PASS_ROOT_METADATA_VERIFIED', 'provenance': provenance})
p6 = new[2]['current_P6_stage_A']
assert p6['P6_complete'] is False and p6['B_C_D'] == 'NOT_ACTIVATED'
p6['status'] = 'ACTUAL40_UNIQUE_PASS_PENDING_FRESH_FINAL_REVIEW'
p6['remaining_validation_commands'] = 0
p6['production_writes'] = 'Final six-source freeze verified; five production files fixed after R145 type-only bridge, test fixed after R147 exact foreign fixture-only repair. Independent final review pending.'
p6['R127']['final_gates'] = 'ALL_PRODUCT_COMMANDS_SPENT_FRESH_FINAL_REVIEW_PENDING'
p6['R127']['new_green_actual'] = deepcopy(provenance)
p6['R147']['original_new19'] = 'ACTUAL19PASS_SPENT1_0_ROOT_VERIFIED_NO_RERUN'
p6['R147']['new19_index'] = pin(R147 / 'implementation/new19-freeze/source-index.json')
p6['terminal_pass_evidence'] = {'unique_nodes': 40, 'single40_run': False, 'runs': [{'run': x['run'], 'passed': len(x['passed']), 'failed': len(x['failed'])} for x in receipt['actual_runs']], 'complete_root_reader': reader_pin, 'original19pass1fail_preserved': True, 'source_proof_bridge': 'R145 type-only and R147 exact test-fixture delta', 'controlled_positive': 'CPU_CONTROLLED_OUTCOME_NOT_PHYSICS_EVIDENCE'}
p6['R148'] = {'status': 'OPTIONAL_AUTHOR_PREFLIGHT_ABANDONED_ZERO_RETRY', 'evidence': [x for x in index['references'] if '/round148-' in x['path']], 'product_commands': 0, 'software_accepted': False}
p6['R149'] = {'status': 'ACTUAL_METADATA_EXIT1_PRESERVED_NO_SYNC', 'used': 1, 'remaining': 0, 'reader': receipt['prior_actual_exit1_preserved'], 'result': pin(BASE / 'round149-p6-root-new19-index-null-recovery-20261012/implementation/result.json'), 'product_commands': 0, 'software_accepted': False}
p6['R150'] = {'status': 'SCENARIO_AWARE_METADATA_VERIFIED_FINAL_REVIEW_PENDING', 'plan_sha256': pin(ROUND / 'plan.json')['sha256'], 'reader': reader_pin, 'actual_exit': 0, 'used': 1, 'remaining': 0, 'product_commands': 0, 'original2560_preserved': True, 'checks': 2605, 'lifecycle': '17 single-worker shutdown1; one pinned two-worker shared-log shutdown2; per-worker attribution source-supported inference', 'old_review_protocol': '2 failures and 3 unplanned replacement reads preserved, no retrospective approval', 'software_accepted': False}
p6['fresh_final_review'] = {'status': 'PENDING_INDEPENDENT_REVIEW', 'round': 'R150', 'ceiling': 'LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO', 'software_accepted': False}
masked = deepcopy(new)
masked[0]['commands']['new_green'] = original[0]['commands']['new_green']
masked[1]['inherited_new_green19'] = original[1]['inherited_new_green19']
masked[2]['current_P6_stage_A'] = original[2]['current_P6_stage_A']
assert masked == original
assert new[2]['full_objective_complete'] is False and new[2]['formal_accepted'] is False
appendix = """
## 2026-10-12 P6 阶段 A：40 个唯一节点证据齐备，终审待完成

R127 new_green 实际退出0、19 PASS，原一次额度已耗用1/0；ROOT两账本旧待执行值在保存 before 后按事实同步，绝不形成新运行额度。四份实际运行提供40个唯一通过节点：旧20运行19 PASS/1 FAIL保留，R147修正 foreign fixture 单例1 PASS，R127原新增19例19 PASS，R141 CPU受控结果正链1 PASS。不是单次40例通过；原失败保留。

R149实际汇总退出1：共享日志双worker用例被过窄 shutdown1 条件拒绝。R150 genuine Astra 审查后仅该固定原件要求 shutdown2，其余17份仍shutdown1；真实有序调用、两不同job/lease终态及第二worker BLOCKED_BY_ENV/INTERRUPTED ended-at交叉核对。逐worker归因是源代码支持的推断，未捏造逐实例日志。新reader实际0，2605项全部有效，原2560项逐一对应。完整1208快照、1207来源、1192fixture、53保护文件、7symlink与四run映射已核对。

独立终审两次读取失败及随后3次未经新计划的替代读取全部保留；R150只读恢复已激活，终态结论仍待完成。此更新不授予阶段A验收、B/C/D、native、真实物理或正式研究验收；当前可申请的软件上限为 LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO。
"""
after = [encoded(x) for x in new] + [before[3] + appendix.encode()]
names = ['before-r127-root-ledger.json', 'before-r147-root-ledger.json', 'before-state.json', 'before-phase-summary.md']
for name, data in zip(names, before):
    with (OUT / name).open('xb') as f:
        f.write(data)
for path, data in zip(paths, before):
    assert path.read_bytes() == data, 'Concurrent metadata change; stop before all writes'
for path, data in zip(paths, after):
    path.write_bytes(data)
assert all(path.read_bytes() == data for path, data in zip(paths, after))
report = {'status': 'CONTROLLED_FACT_SYNC_COMPLETE_NO_ACCEPTANCE', 'authorized': 1, 'used': 1, 'remaining': 0, 'reader': reader_pin, 'before': [pin(p, b) for p, b in zip(paths, before)], 'after': [pin(p, b) for p, b in zip(paths, after)], 'unrelated_json_fields_preserved': masked == original, 'phase_append_only': after[3].startswith(before[3]), 'product_execution': 0, 'budget_reset': False, 'software_acceptance': False}
with (OUT / 'sync-report.json').open('xb') as f:
    f.write(encoded(report))
print(json.dumps({'status': report['status'], 'sync_report': pin(OUT / 'sync-report.json'), 'writes': len(paths)}, ensure_ascii=False))
