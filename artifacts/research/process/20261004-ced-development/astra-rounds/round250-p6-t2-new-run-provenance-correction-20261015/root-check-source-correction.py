"""ROOT R250 one-byte source correction integrity gate, stdlib only."""
import base64
import hashlib
import json
import os
from pathlib import Path

R = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
A = R / 'artifacts/research/process/20261004-ced-development/astra-rounds'
D = A / 'round248-p6-t2-writer-start-condition-synchronization-20261015'
checks = []
def identity(x):
    return {k: x[k] for k in ('path', 'bytes', 'sha256')}
def key(x):
    return tuple(x[k] for k in ('path', 'bytes', 'sha256'))
def pin(p, raw=None):
    raw = p.read_bytes() if raw is None else raw
    return {'path': str(p), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
def check(label, ok, **facts):
    checks.append({'label': label, 'ok': bool(ok), **facts})
def fixed(row, label='fixed'):
    p = Path(row['path'])
    raw = p.read_bytes() if p.is_file() and not p.is_symlink() else None
    check(label, raw is not None and pin(p, raw) == identity(row), expected=identity(row))
    return raw
def encoded(x):
    return (json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
def save(p, x):
    raw = x if isinstance(x, bytes) else encoded(x)
    with p.open('xb') as stream:
        stream.write(raw)
    if p.read_bytes() != raw:
        raise ValueError('exclusive metadata write differs')
    return pin(p, raw)

def native(record):
    fixed(record, 'native_record')
    obj = json.loads(Path(record['path']).read_bytes())
    check('native_actual_null_unknowns', obj['actual_tool_return'] == {}
          and obj['numeric_exit'] is None and obj['independent_stdout'] is None
          and obj['independent_stderr'] is None)
    return obj['tool_arguments']

def add_source(patch, target):
    lines = patch.splitlines()
    check('native_add_header', lines[:2] == ['*** Begin Patch', '*** Add File: ' + str(target)]
          and lines[-1] == '*** End Patch')
    body = lines[2:-1]
    check('native_add_all_lines', all(line.startswith('+') for line in body))
    return ('\n'.join(line[1:] for line in body) + '\n').encode()

def update_source(raw, patch, target):
    lines = patch.splitlines()
    check('native_update_header', lines[:2] == ['*** Begin Patch', '*** Update File: ' + str(target)]
          and lines[-1] == '*** End Patch')
    chunks, current = [], None
    for line in lines[2:-1]:
        if line.startswith('@@'):
            if current is not None:
                chunks.append(current)
            current = []
        else:
            if current is None or not line or line[0] not in ' +-':
                raise ValueError('unknown native update source shape')
            current.append(line)
    if current is not None:
        chunks.append(current)
    for chunk in chunks:
        old = ('\n'.join(x[1:] for x in chunk if x[0] in ' -') + '\n').encode()
        new = ('\n'.join(x[1:] for x in chunk if x[0] in ' +') + '\n').encode()
        check('native_unique_update_hunk', bool(old) and raw.count(old) == 1)
        if not old or raw.count(old) != 1:
            raise ValueError('native hunk not unique')
        raw = raw.replace(old, new, 1)
    return raw


C = A / 'round250-p6-t2-new-run-provenance-correction-20261015'
plan_pin = {'path':str(C/'plan.json'),'bytes':9503,'sha256':'10be27236d9350a159dc178b4e6e3f49c0b93ef9fce0d7d3547ac0a798fdba43'}
md_pin = {'path':str(C/'plan.md'),'bytes':2444,'sha256':'fb7e753e837ef5dce2bc3b473a9d06ca1a0efbf93bc788462495de9f5cdd7ecf'}
report_pin = {'path':str(C/'implementation/change-report.json'),'bytes':4542,
              'sha256':'433fc1dec5a94990b1da4b4c4a12b435465baf402110c289d9cac34015ff9766'}
plan = json.loads(fixed(plan_pin))
fixed(md_pin)
for row in plan['inputs']:
    fixed(row, 'exact_plan_input')
obs_pin = next(x for x in plan['inputs'] if x['path'] == str(C/'input-observation.json'))
obs = json.loads(fixed(obs_pin))
report = json.loads(fixed(report_pin))
before = fixed(report['runner_before'], 'complete_R250_physical_before')
after = fixed(report['runner_after'], 'actual_current_corrected_runner')
candidate = fixed(report['candidate'], 'immutable_corrected_candidate')
check('expected_after_identity', report['runner_after'] == plan['scope']['expected_after'])
check('physical_before_original_equivalence',
      pin(Path(plan['scope']['before']['path']),before) == plan['scope']['before'])
check('observation_full_before_base64', before == base64.b64decode(obs['source_before']['base64'],validate=True)
      and report['runner_before'] == obs['source_before']['archive'])
for row in obs['inputs']:
    expected = report['runner_before'] if identity(row) == plan['scope']['before'] else row
    raw = fixed(expected, 'actual_observed_input_generation')
    check('observed_input_byte_equivalence', pin(Path(row['path']),raw) == identity(row))
old,new = plan['scope']['exact_old'].encode(),plan['scope']['exact_new'].encode()
check('only_one_byte_provenance_correction', len(before) == len(after) == 47902 and before.count(old) == 1
      and before.find(old) == plan['scope']['old_literal_byte_offset']
      and after == before.replace(old,new,1) and sum(x!=y for x,y in zip(before,after)) == 1
      and after == candidate and before[-1:] == after[-1:] == b'\n')
old_report_pin = {'path':str(D/'implementation/change-report.json'),'bytes':162277,
                  'sha256':'49c5a9856ee174450e33d73ab391c768e9746df52d12987a978b9128a94a05d2'}
old_report = json.loads(fixed(old_report_pin))
old_runner = next(x for x in old_report['scripts'] if x['path'] == report['runner_after']['path'])
old_candidate = fixed(old_runner['candidate'])
check('old_R248_immutable_candidate_fullbase64', before == old_candidate
      == base64.b64decode(old_runner['base64'],validate=True))
old_native = old_report['native_receipts'][2]
check('original_AddFile_complete_reconstruction',
      add_source(native(old_native),Path(report['runner_after']['path'])) == before)
new_patch = native(report['native_receipt'])
check('new_single_Update_complete_reconstruction',
      update_source(before,new_patch,Path(report['runner_after']['path'])) == after)
fixed(report['limited_diff'])
fixed(report['unchanged_fixture'])
fixed(report['unchanged_prepare'])
for row in report['roles_HELD']:
    role = json.loads(fixed(row,'original_role_unchanged'))
    check('all_slots_still_HELD', all(x == {'total':1,'used':0,'remaining':1,'state':'HELD'}
          for x in role['commands'].values()))
check('no_validation_or_completion_claim', report['source_preparation_only'] is True
      and report['source_execution'] is False and report['new_execution_slots'] == 0
      and report['old_slots_reset'] is False and report['legal_RED'] is False
      and report['T2_complete'] is False and report['T12_complete'] is False)
immutable_inputs = [plan_pin,md_pin,obs_pin,report_pin,report['runner_before'],report['candidate'],
                    report['native_receipt'],report['limited_diff'],pin(C/'root-plan-input-check.json'),
                    pin(C/'root-plan-acceptance.json')]
failures = [x for x in checks if not x['ok']]
if failures:
    save(C/'root-source-correction-failure.json',{'checks':checks,'failures':failures})
    print(json.dumps({'status':'STOP','failures':failures[:3]},ensure_ascii=False))
    raise SystemExit(1)
acceptance = {**{k:report[k] for k in ('runner_before','runner_after','candidate','native_receipt')},
    'status':'ACCEPTED_SOURCE_CORRECTION_ONLY','checks':checks,'check_count':len(checks),
    'immutable_input_records':immutable_inputs,'runtime_execution_count':0,'new_slots':0,
    'legal_RED':False,'T2_complete':False,'T12_complete':False}
accepted_pin = save(C/'root-source-correction-acceptance.json',acceptance)
save(C/'root-step-report.json',{'round':'R250','status':acceptance['status'],'acceptance':accepted_pin,
    'scope':'Exactly one provenance ASCII byte; R248 runtime slots remain HELD',
    'runtime_evidence':None,'native_research_acceptance':False,'formal':False,'Git_commands':0})
print(json.dumps({'status':acceptance['status'],'check_count':len(checks),'runner':report['runner_after'],
                  'runtime_execution_count':0},ensure_ascii=False))
