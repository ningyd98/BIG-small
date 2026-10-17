"""ROOT R251 actual plan/source preparation and original R223 continuation gate; stdlib only."""
import base64
import hashlib
import json
import os
from pathlib import Path

R = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
A = R/'artifacts/research/process/20261004-ced-development/astra-rounds'
D = A/'round251-p6-t2-event3-entry-fence-continuation-20261017'
checks = []
def identity(x):
    return {k:x[k] for k in ('path','bytes','sha256')}
def key(x):
    return tuple(x[k] for k in ('path','bytes','sha256'))
def pin(p,raw=None):
    raw = p.read_bytes() if raw is None else raw
    return {'path':str(p),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def check(label,ok,**facts):
    checks.append({'label':label,'ok':bool(ok),**facts})
def fixed(row,label='fixed'):
    p = Path(row['path'])
    raw = p.read_bytes() if p.is_file() and not p.is_symlink() else None
    check(label,raw is not None and pin(p,raw)==identity(row),expected=identity(row))
    return raw
def encoded(x):
    return (json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    raw = x if isinstance(x,bytes) else encoded(x)
    with p.open('xb') as stream:
        stream.write(raw)
    if p.read_bytes()!=raw:
        raise ValueError('exclusive full metadata write differs')
    return pin(p,raw)

plan_pin = {'path':str(D/'plan.json'),'bytes':37541,'sha256':'5a59a5e3f9e0f80071d083187f69eb9ba791ced7d62a65c64a07e126b2a4cd68'}
plan = json.loads(fixed(plan_pin,'actual_Astra_plan'))
fixed({'path':str(D/'plan.md'),'bytes':5100,'sha256':'93fdd97dad01b7fb1e5472dfdee0917d216902fab8a24c43647badfcb0fe4042'})
observation = json.loads(fixed(plan['inputs']['observation']))
baseline = json.loads(fixed(plan['inputs']['legal_RED_baseline']))
check('actual_schema',len(observation['inputs'])==379 and len(baseline['sources'])==27
      and len(baseline['protected'])==211 and len(baseline['scripts'])==3
      and len(baseline['history_observations'])==1223 and len(baseline['explicit_maps'])==26
      and len(baseline['input_records'])==32)
maps = {}
pairs = (observation['prior_exact_maps']+observation['event3_before']
         +observation['R248_final_before_maps']+observation['R223_role_before'])
check('exact_declared_mapping_sets',len(observation['prior_exact_maps'])==26
      and len(observation['event3_before'])==3 and len(observation['R248_final_before_maps'])==7
      and len(observation['R223_role_before'])==2)
for pair in pairs:
    raw = fixed(pair['archive'],'physical_generation_archive')
    check('physical_full_original_equivalence',raw is not None
          and pin(Path(pair['original']['path']),raw)==identity(pair['original']))
    if 'base64' in pair:
        check('full_base64_equivalence',raw==base64.b64decode(pair['base64'],validate=True))
    maps[key(pair['original'])]=pair['archive']
registry = {key(x['original']):x for x in observation['known_missing']}
check('exact35_unique_unavailable',len(registry)==len(observation['known_missing'])==35)
for row in observation['known_missing']:
    p = Path(row['original']['path'])
    check('exact_missing_still_absent',not p.exists() and not p.is_symlink()
          and row['current_bytes'] is None and row['current_sha256'] is None and row['hash_match'] is None,
          original=row['original'])
    authority = row['authority']
    container = json.loads(fixed(authority['pin'],'exact_missing_authority'))
    ordinal = authority['ordinal']
    check('authority_nonnegative_integer',type(ordinal) is int and ordinal>=0)
    if authority['selector']=='input_records':
        authoritative = container['input_records'][ordinal]
    elif authority['selector']=='new_retained_databases.pin':
        authoritative = container['new_retained_databases'][ordinal]['pin']
    else:
        raise ValueError('unknown exact missing authority selector')
    check('exact_registry_identity',identity(authoritative)==identity(row['original']))
for row in observation['inputs']:
    if key(row) in registry:
        check('explicit_unavailable_not_hash_pass',True,original=row,hash_match=None)
    else:
        raw = fixed(maps.get(key(row),row),'available_direct379')
        check('direct_original_equivalence',raw is not None
              and pin(Path(row['path']),raw)==identity(row))
        if raw is not None and row['path'].endswith('/invocation.json'):
            invocation = json.loads(raw)
            for control in invocation.get('controls_before',[]):
                decoded = base64.b64decode(control['base64'],validate=True)
                check('invocation_own_recorded_generation',pin(Path(control['path']),decoded)==identity(control))
for row in baseline['history_observations']:
    original = row['original']
    if key(original) in registry:
        check('historical_unavailable_not_pass',row['hash_match'] is None)
    else:
        resolved = row['resolved']
        raw = fixed(maps.get(key(original),maps.get(key(resolved),resolved)),'available_history1223')
        check('historical_full_equivalence',raw is not None
              and pin(Path(original['path']),raw)==identity(original))
for row in observation['current_sources']:
    raw = fixed(row['original'],'current27')
    check('physical_current_fullbytes',raw==fixed(row['physical']))
for row in baseline['sources']:
    raw = fixed(row,'current_full27')
    check('full_source_base64_and_mode',raw==base64.b64decode(row['base64'],validate=True)
          and raw==fixed(row['physical']) and Path(row['path']).stat().st_mode==row['mode'])
for row in observation['protected']:
    fixed(row,'protected211')
for row in baseline['scripts']:
    check('prior_scripts_full_base64',fixed(row)==base64.b64decode(row['base64'],validate=True))
for row in observation['old_absent_sidecars']:
    p = Path(row['path'])
    check('old90_sidecar_absent',row['exists'] is False and not p.exists() and not p.is_symlink())
for row in observation['retained_workspace_databases']:
    fixed(row['pin'],'strict_current_workspace_DB12')
    check('available_DB_not_old_missing',key(row['pin']) not in registry)
    for side in row['sidecars']:
        p = Path(side['path'])
        check('current_workspace_sidecar36',side['exists'] is False and side['is_symlink'] is False
              and not p.exists() and not p.is_symlink())
check('exact12_and36_current_DB_states',len(observation['retained_workspace_databases'])==12
      and sum(len(x['sidecars']) for x in observation['retained_workspace_databases'])==36)
context = observation['current_context']
for row in [context['STATE'],context['PHASE']]+context['R248_final_controls']:
    fixed(row,'current_final_context')
acceptance = json.loads(fixed(plan['inputs']['legal_RED_acceptance']))
receipt = json.loads(fixed(plan['inputs']['legal_RED_receipt']))
check('independent_legal_RED_predecessor',acceptance['legal_RED'] is True and receipt['legal_RED'] is True
      and acceptance['status']=='ACCEPTED_LEGAL_ORIGINAL_RACE_RED')
writers = observation['writer_inventory']
names = observation['writer_names']
check('72_unique_entries_36_each',len(writers)==72 and len(names)==len(set(names))==36
      and len({(x['path'],x['method']) for x in writers})==72
      and all({x['method'] for x in writers if x['path']==str(R/'src/cloud_edge_robot_arm/repositories/event_autonomy'/name)}
              ==set(names) for name in ('memory.py','sqlite.py')))
for row in writers:
    lines = Path(row['path']).read_text().splitlines()
    check('literal_original_method_range',0<row['start_line']<=row['end_line']<=len(lines)
          and lines[row['start_line']-1].strip().startswith('def '+row['method']+'('))
    for item in row['current_controls']:
        check('actual_original_control_text',lines[item['line']-1].strip()==item['text'])
check('scope_targets_not_protected',not set(plan['scope']['product_paths']) & {x['path'] for x in observation['protected']})
roles = {}
role_raws = {}
for row in observation['R223_role_values']:
    path = Path(row['pin']['path'])
    raw = fixed(row['pin'],'original_R223_actual_ledger')
    value = json.loads(raw)
    check('exact_original_role_value',value==row['value'])
    check('original_two_spent_stay_spent',all(value['commands'][k]['used']==1
          and value['commands'][k]['remaining']==0 for k in ('prepare_red','red')))
    for k in plan['budget_continuation']['keys']:
        x = value['commands'][k]
        check('same_unspent_budget_identity',x['authorized']==1 and x['used']==0 and x['remaining']==1
              and x['state'].startswith('HELD'),path=str(path),key=k)
    roles[path]=value
    role_raws[path]=raw
for command in plan['commands']:
    check('all_four_normative_slots_unspent',command['authorized']==1 and command['used']==0 and command['remaining']==1)
    p = Path(command['evidence_directory'])
    check('new_output_directory_absent',not p.exists() and not p.is_symlink(),path=str(p))
for value in plan['scope']['new_author_scripts']+[plan['scope']['new_ROOT_script']]:
    p = Path(value)
    check('new_script_absent',not p.exists() and not p.is_symlink(),path=value)
failures = [x for x in checks if not x['ok']]
input_pin = save(D/'input-check.json',{'status':'STOP' if failures else 'ACCEPTED_SOURCE_PREPARATION_ONLY',
    'checks':checks,'check_count':len(checks),'failures':failures,'plan':plan_pin,
    'legal_RED':True,'execution_released':False,'T2_complete':False,'new_slots':0})
if failures:
    print(json.dumps({'status':'STOP','failures':failures[:4]},ensure_ascii=False))
    raise SystemExit(1)
before_dir = D/'before/root-continuation-activation'
role_pairs = []
for path,raw in role_raws.items():
    archive = before_dir/path.name
    save(archive,raw)
    role_pairs.append({'original':pin(path,raw),'archive':pin(archive),'base64':base64.b64encode(raw).decode()})
before_pin = save(before_dir/'index.json',{'records':role_pairs})
for path,value in roles.items():
    original = json.loads(role_raws[path])
    for command in plan['commands']:
        k = command['id']
        contract = {a:b for a,b in command.items() if a not in ('authorized','used','remaining','state')}
        value['commands'][k]['continuation']={'round':'R251','plan':plan_pin,'execution_contract':contract,
                                             'not_a_new_budget':True}
    comparison = json.loads(encoded(value))
    for k in plan['budget_continuation']['keys']:
        del comparison['commands'][k]['continuation']
    if comparison!=original:
        raise ValueError('continuation changed original values outside four added execution contracts')
for path,raw in role_raws.items():
    if path.read_bytes()!=raw:
        raise ValueError('immediate full original ledger CAS differs')
for path,value in roles.items():
    temp = D/('.activation-'+path.name+'.tmp')
    save(temp,value)
    os.replace(temp,path)
save(D/'ledger-links.json',{'round':'R251','origin_round':'R223','new_slots':0,
    'author_ledger':plan['budget_continuation']['author_ledger'],
    'ROOT_ledger':plan['budget_continuation']['ROOT_ledger'],'keys':plan['budget_continuation']['keys'],
    'activation_before':before_pin,'context_history':role_pairs,
    'authority':'Only original per-command identities; legacy top-level aggregate fields preserved as historical summaries.'})
for name in ('source-gate.json','script-gate.json'):
    save(D/name,{'round':'R251','status':'PENDING_FULL_SOURCE_REVIEW','execution_released':False,'input_check':input_pin})
save(D/'root-activation.json',{'round':'R251','status':'SOURCE_PREPARATION_ONLY','execution_released':False,
    'sole_author':'/root/p6_stage_b_sol','input_check':input_pin,'original_role_before':before_pin})
save(D/'root-source-preparation-activation.json',{'status':'R251_SOURCE_PREPARATION_ONLY','checks':len(checks),
    'input_check':input_pin,'original_role_before':before_pin,'new_slots':0,
    'current_roles_after_activation':[pin(p) for p in roles],'counts_unchanged':True,
    'execution_released':False,'T2_complete':False})
print(json.dumps({'status':'R251_SOURCE_PREPARATION_ONLY','checks':len(checks),
                  'new_slots':0,'command_execution_released':False},ensure_ascii=False))
