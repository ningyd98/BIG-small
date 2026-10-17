const D="/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round251-p6-t2-event3-entry-fence-continuation-20261017";
const raw=load("t2_R251_ROOT_initial_gate_reference_source_read_actual");
if(raw.exit_code!==0||raw.output.includes("truncated"))throw Error("full own metadata reference unavailable");
let src=raw.output.slice(0,raw.output.index("roles = {}\nrole_raws = {}"));
function rep(a,b){if(src.split(a).length!==2)throw Error("ambiguous own draft span");src=src.replace(a,b);}
rep('import os\n','import os\nimport sys\nimport shlex\n');
rep("baseline = json.loads(fixed(plan['inputs']['legal_RED_baseline']))\n",`baseline = json.loads(fixed(plan['inputs']['legal_RED_baseline']))
runtime_path = D/'root-runtime-source-contract.json'
runtime = json.loads(runtime_path.read_bytes())
KEYS = ['prepare_green','ruff','green','root_settlement']
if len(sys.argv)!=2 or sys.argv[1] not in KEYS:
    raise ValueError('one exact original command key required')
selected = sys.argv[1]
ordinal = KEYS.index(selected)
check('fixed_runtime_source_contract',runtime['source_plan']==plan_pin and runtime['runtime_release'] is False)
for row in runtime['input_records']:
    fixed(row,'new_fixed_metadata_source_input')
after_by_path = {x['path']:x for x in runtime['target_after_pins']}
check('only_exact_three_after_sources',set(after_by_path)==set(plan['scope']['product_paths']) and len(after_by_path)==3)
for row in runtime['scripts']+[runtime['prerequisite_source']]:
    fixed(row,'reviewed_actual_script')
check('three_new_scripts_plus_import_prerequisite',len(runtime['scripts'])==3)
source_report = json.loads(fixed(runtime['source_report_pin']))
scope = json.loads(fixed(runtime['fence_inventory_pin']))
corrected = json.loads((A/'round253-p6-t2-checkpoint-prelock-read-candidate-20261017/implementation/prepared-product-values.json').read_bytes())
check('exact_final72_source_inventory',scope['entries']==corrected['entries'] and len(scope['entries'])==72)
`);
rep(`for row in observation['current_sources']:
    raw = fixed(row['original'],'current27')
    check('physical_current_fullbytes',raw==fixed(row['physical']))
for row in baseline['sources']:
    raw = fixed(row,'current_full27')
    check('full_source_base64_and_mode',raw==base64.b64decode(row['base64'],validate=True)
          and raw==fixed(row['physical']) and Path(row['path']).stat().st_mode==row['mode'])
`, `for row in observation['current_sources']:
    original_raw = fixed(row['physical'],'accepted_original_physical27')
    check('original_source_identity',original_raw is not None
          and pin(Path(row['original']['path']),original_raw)==identity(row['original']))
    expected = after_by_path.get(row['original']['path'],row['original'])
    fixed(expected,'actual_current27')
for row in baseline['sources']:
    raw = base64.b64decode(row['base64'],validate=True)
    check('full_original_source_base64',pin(Path(row['path']),raw)==identity(row) and raw==fixed(row['physical']))
    current = fixed(after_by_path.get(row['path'],row),'current_full27')
    check('source_mode_retained',Path(row['path']).stat().st_mode==row['mode'])
    if row['path'] not in after_by_path:
        check('unowned24_entire_bytes_retained',current==raw)
`);
rep("    lines = Path(row['path']).read_text().splitlines()\n", "    original_row = next(x for x in baseline['sources'] if x['path']==row['path'])\n    lines = base64.b64decode(original_row['base64'],validate=True).decode().splitlines()\n");
src += `
# The following is ordinary ROOT metadata reservation, never a product/static/test command.
role_paths = [Path(plan['budget_continuation'][name]) for name in ('ROOT_ledger','author_ledger')]
role_raw = {path:path.read_bytes() for path in role_paths}
roles = {path:json.loads(raw) for path,raw in role_raw.items()}
root_role,author_role = [roles[path] for path in role_paths]
commands = {x['id']:x for x in plan['commands']}
check('same_original_four_keys',list(commands)==KEYS)
for original in observation['R223_role_values']:
    live = roles[Path(original['pin']['path'])]
    check('historical_top_fields_unchanged',{k:v for k,v in live.items() if k!='commands'}==
          {k:v for k,v in original['value'].items() if k!='commands'})
    for name in ('prepare_red','red'):
        check('original_failed_chain_spent_immutable',live['commands'][name]==original['value']['commands'][name])
for name in KEYS:
    normative = commands[name]
    contract = {k:v for k,v in normative.items() if k not in ('authorized','used','remaining','state')}
    for role in (root_role,author_role):
        entry = role['commands'][name]
        check('same_original_continuation_contract',entry['authorized']==1
              and entry['continuation']==dict(round='R251',plan=plan_pin,
                  execution_contract=contract,not_a_new_budget=True))
        if KEYS.index(name)<ordinal:
            check('prior_same_identity_spent',entry['used']==1 and entry['remaining']==0)
        else:
            check('unspent_same_identity_held',entry['used']==0 and entry['remaining']==1
                  and entry['state'].startswith('HELD'))
check('author_root_slot_stays_nonexecutable',author_role['commands']['root_settlement']['owner']=='ROOT'
      and author_role['commands']['root_settlement']['author_executable'] is False)
accepted = {}
source_index = None
for name in KEYS[:ordinal]:
    path = D/('root-'+name+'-acceptance.json')
    value = json.loads(path.read_bytes())
    check('independent_prior_ROOT_acceptance',value['round']=='R251' and value['command']==name
          and value['status']=='ACCEPTED'
          and value['result']==pin(D/'implementation'/name/'result.json')
          and value['actual_tool_return']==pin(D/'implementation'/name/'actual-tool-return.json'))
    actual = json.loads(fixed(value['actual_tool_return']))
    check('actual_prior_exit0',actual['final']['exit_code']==0 and actual['attempt']==1 and actual['retry']==0)
    fixed(value['result'])
    fixed(value['source_index'])
    if source_index is None:
        source_index = value['source_index']
    check('one_accepted_source_index_generation',source_index==value['source_index'])
    accepted[name] = pin(path)
if ordinal:
    snapshot = json.loads(fixed(source_index))
    check('accepted_new_full_source_counts',len(snapshot['sources'])==27 and len(snapshot['protected'])==211
          and len(snapshot['scripts'])==4)
    for row in snapshot['sources']:
        raw = fixed(row)
        check('accepted_current_source_entire_bytes',raw==base64.b64decode(row['base64'],validate=True)
              and raw==fixed(row['physical']))
    for row in snapshot['scripts']:
        check('accepted_script_entire_bytes',fixed(row)==base64.b64decode(row['base64'],validate=True))
    check('same_after_targets_inventory_report',snapshot['target_after_pins']==runtime['target_after_pins']
          and snapshot['fence_inventory_pin']==runtime['fence_inventory_pin']
          and snapshot['source_report_pin']==runtime['source_report_pin'])
command = commands[selected]
transport = runtime['transports'][selected]
expected_cap = 630 if selected=='green' else 150
args = [k+'='+v for k,v in command['finite_env'].items()]+command['launcher_argv']
stdout = D/'implementation'/(selected+'.tool.stdout.raw')
stderr = D/'implementation'/(selected+'.tool.stderr.raw')
expected_cmd = ('set -C\\nexec /usr/bin/timeout --signal=TERM --kill-after=5s '+str(expected_cap)
    +'s /usr/bin/env -i '+shlex.join(args)+' > '+shlex.quote(str(stdout))
    +' 2> '+shlex.quote(str(stderr)))
check('literal_finite_transport',transport['invocation']==dict(cmd=expected_cmd,workdir=str(R),
    max_output_tokens=1800,yield_time_ms=1000) and transport['outer_timeout_seconds']==expected_cap
    and transport['kill_after_seconds']==5 and transport['stdout']==str(stdout) and transport['stderr']==str(stderr))
for path in (stdout,stderr,Path(command['evidence_directory'])):
    check('selected_original_outputs_absent',not path.exists() and not path.is_symlink(),path=str(path))
mutable = [D/'source-gate.json',D/'script-gate.json',D/'root-activation.json',*role_paths]
check('exact_five_mutable_controls',{str(p) for p in mutable}==set(runtime['mutable_controls']))
check('no_live_mutable_fixed_loop',not {str(p) for p in mutable}&{x['path'] for x in runtime['input_records']})
failures = [x for x in checks if not x['ok']]
if failures:
    save(D/('root-'+selected+'-reservation-failure.json'),dict(checks=checks,failures=failures,runtime_release=False))
    raise ValueError('ROOT source/input/original budget gate failed')
raw_before = {path:path.read_bytes() for path in mutable}
before = []
before_dir = D/'before'/('root-reserve-'+selected)
for i,path in enumerate(mutable):
    raw = raw_before[path]
    archive = before_dir/(str(i)+'-'+path.name)
    save(archive,raw)
    before.append(dict(original=pin(path,raw),archive=pin(archive),
                       base64=base64.b64encode(raw).decode(),mode=path.stat().st_mode))
before_index = save(before_dir/'index.json',dict(round='R251',command=selected,records=before))
old_gate = json.loads(raw_before[D/'script-gate.json'])
entries = old_gate.get('commands',{})
history = []
for entry in entries.values():
    history.extend(entry.get('context_history',[]))
history.extend(before)
history = list({key(x['original']):x for x in history}.values())
inputs = list(runtime['input_records'])+[pin(runtime_path)]+list(accepted.values())
inputs = list({key(x):identity(x) for x in inputs}.values())
for name in KEYS:
    if name not in entries:
        c = commands[name]
        script = c['launcher_argv'][1]
        entries[name] = dict(state='HELD_PENDING_PREVIOUS_ROOT_ACCEPTANCE',full_source_reviewed=True,
            source=next(x for x in runtime['scripts'] if x['path']==script),
            launcher_argv=c['launcher_argv'],argv=c.get('child_argv',c['launcher_argv']),
            cwd=c['cwd'],finite_env=c['finite_env'],timeout_seconds=c['timeout_seconds'],
            transport=runtime['transports'][name],scripts=runtime['scripts'],
            prerequisite_source=runtime['prerequisite_source'],target_after_pins=runtime['target_after_pins'],
            fence_inventory_pin=runtime['fence_inventory_pin'],source_report_pin=runtime['source_report_pin'],
            input_records=inputs,context_history=history)
for name in KEYS[:ordinal]:
    root_role['commands'][name].update(state='SPENT_ACCEPTED_BY_ROOT',ROOT_acceptance=accepted[name])
    entries[name]['state']='SPENT_ACCEPTED_BY_ROOT'
reservation_id = 'R251:R223.'+selected+':original-once'
entry = entries[selected]
entry.update(state='APPROVED',full_source_reviewed=True,reservation_id=reservation_id,
             input_records=inputs,context_history=history)
if source_index is not None:
    entry['source_index_pin']=source_index
if selected=='root_settlement':
    entry['acceptances']=accepted
new_gates = dict(round='R251',status='ONE_ORIGINAL_SLOT_RESERVED',selected=selected,
                 commands=entries,new_slots=0,source_contract=pin(runtime_path))
gate_raw = encoded(new_gates)
root_role['commands'][selected].update(state='RESERVED_BY_ROOT',used=1,remaining=0,
    reservation_id=reservation_id,gate_pin=pin(D/'script-gate.json',gate_raw))
source_gate = dict(round='R251',status='FULL_SOURCE_AND_INPUTS_APPROVED',selected=selected,
    execution_released=True,only_original_slot=True,new_slots=0,source_contract=pin(runtime_path),
    check_count=len(checks),before=before_index,T2_complete=False)
activation = dict(round='R251',status='ONE_ORIGINAL_SLOT_RESERVED',selected=selected,
    execution_released=True,actor=command['actor'],reservation_id=reservation_id,new_slots=0)
mutations = {D/'script-gate.json':gate_raw,D/'source-gate.json':encoded(source_gate),
             D/'root-activation.json':encoded(activation),role_paths[0]:encoded(root_role)}
for path,raw in raw_before.items():
    if path.read_bytes()!=raw:
        raise ValueError('immediate full five-control CAS differs')
for path,raw in mutations.items():
    temp = D/('.ROOT-reserve-'+selected+'-'+path.name+'.tmp')
    save(temp,raw)
    if path.read_bytes()!=raw_before[path]:
        raise ValueError('immediate per-control CAS differs')
    os.replace(temp,path)
for path,raw in raw_before.items():
    if path.read_bytes()!=mutations.get(path,raw):
        raise ValueError('exact final five-control transition differs')
receipt = dict(round='R251',command=selected,status='RESERVED_ONE_ORIGINAL_SLOT',
    checks=checks,check_count=len(checks),original_budget_owner=command['budget_owner'],
    reservation_id=reservation_id,source_contract=pin(runtime_path),before=before_index,
    script_gate=pin(D/'script-gate.json'),ROOT_ledger=pin(role_paths[0]),author_ledger=pin(role_paths[1]),
    transport=transport,source_index_pin=source_index,prior_acceptances=accepted,
    author_consumption_pending=selected!='root_settlement',new_slots=0,T2_complete=False)
receipt_pin = save(D/('root-'+selected+'-reservation.json'),receipt)
print(json.dumps(dict(status=receipt['status'],command=selected,checks=len(checks),
    receipt=receipt_pin,source_contract=pin(runtime_path)),ensure_ascii=False))
`;
const newp=D+"/root-reserve-original-command.py";store("t2_R251_ROOT_original_command_reserver_unexecuted_draft_source",src);
const patch="*** Begin Patch\n*** Add File: "+newp+"\n"+src.trimEnd().split("\n").map(x=>"+"+x).join("\n")+"\n*** End Patch";
store("t2_R251_ROOT_original_command_reserver_native_patch",patch);const a=await tools.apply_patch(patch);store("t2_R251_ROOT_original_command_reserver_native_actual",a);text(a);
