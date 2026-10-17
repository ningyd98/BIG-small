from pathlib import Path
import json,hashlib,base64,time,signal
R=Path('/home/ningyd/文档/ChatGPT/BIGsmall')
A=R/'artifacts/research/process/20261004-ced-development/astra-rounds'
D=A/'round293-p6-t2-final-source-proof-length-disposition-20261017'
I=D/'implementation'
B=A/'round289-p6-t2-accepted-runner-validation-continuation-20261017'
deadline=time.monotonic()+120
def expired(*args):raise TimeoutError('ROOT R293 metadata gate total120s')
signal.signal(signal.SIGALRM,expired);signal.alarm(120)
checks=[]
def check(value,label):
 if time.monotonic()>=deadline:expired()
 assert value,label
 checks.append(label)
def pin(path):
 path=Path(path);raw=path.read_bytes()
 check(time.monotonic()<deadline,'read_deadline:'+str(path))
 return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def ident(row):return {k:row[k] for k in ('path','bytes','sha256')}
def checked(row):
 check(pin(row['path'])==ident(row),'pin:'+row['path'])
 return Path(row['path']).read_bytes()
def read(path):return json.loads(Path(path).read_bytes())
def fixed(path,size,sha):
 row={'path':str(path),'bytes':size,'sha256':sha};checked(row);return row
p_pin=fixed(D/'plan.json',11912,'4fa2ad28c2fe2ae45d51106ab1f81474be750bf6c400444da8de27247b8ba17d')
o_pin=fixed(D/'input-observation.json',11254,'e3a81b9b0adc450cca2721aee464ff390f1e5245c6c937f254f312e9bc6ab7b0')
m_pin=fixed(D/'before/manifest.json',333474,'b8bee835481a57a1508b60c73fa11cd8e9c0e669331a36e09ae8ac71c61e6edc')
source=fixed(I/'finalize-source-evidence.py',14880,'aba5dfb61afb5a9512685191376a0c0ba0a10386f5a3400e1b40d398bc7c9d77')
candidate=fixed(I/'prepared-finalize-source-evidence.txt',14880,source['sha256'])
native=fixed(I/'metadata-source-native-actual.json',40972,'f54e5746b6a2a1c4a61e37b24b14c579403fe59c3cb2788c8db9e1b2aacba377')
diff=fixed(I/'metadata-source.diff',18975,'0da721be32fcb6717944fb41d4c684aabff0937512f6065478d3d890f6acdb2b')
scope=fixed(I/'metadata-source-scope.json',19176,'c37b6a7095b6084d8630bf79442baff90577673595bc2dccd399046f70e8e65a')
P=read(p_pin['path']);O=read(o_pin['path']);M=read(m_pin['path']);N=read(native['path']);Q=read(scope['path'])
check(P['planner']=='actual gpt-6-astra','actual_Astra')
check(P['inputs']['complete_manifest']==o_pin and P['inputs']['before_manifest']==m_pin,'manifest_bindings')
check(P['inputs']['selector']=='inputs' and P['inputs']['count']==25 and len(O['inputs'])==25,'finite25')
check(Q['input_records']==O['inputs'],'scope_exact25')
for row in O['inputs']:checked(row)
check(type(M['records']) is list and len(M['records'])==5,'fullbefore5')
for row in M['records']:
 check(checked(row['original'])==checked(row['archive'])==base64.b64decode(row['base64'],validate=True),'fullbefore_bytes:'+row['original']['path'])
 check(Path(row['original']['path']).stat().st_mode==Path(row['archive']['path']).stat().st_mode==row['mode'],'fullbefore_modes:'+row['original']['path'])
raw=checked(source)
check(raw==checked(candidate) and len(raw.splitlines())==113,'source_whole_candidate113')
check(Path(source['path']).stat().st_mode==Path(candidate['path']).stat().st_mode==33204,'source_modes')
check(Q['source']==source and Q['candidate']==candidate and Q['native']==native and Q['limited_diff']==diff,'scope_exact_source_native')
check(Q['source_executed'] is False and Q['runtime_executed'] is False and N['source_executed'] is False,'source_not_executed')
check(len(N['stages'])==2,'native_two_stages')
for stage,path in zip(N['stages'],[candidate['path'],source['path']]):
 check(stage['tool']=='tools.apply_patch' and stage['actual_tool_return']=={},'actual_native_object:'+path)
 check(all(stage[key] is None for key in ['numeric_exit','independent_stdout','independent_stderr','target_before']),'native_nulls:'+path)
 lines=stage['arguments'].splitlines(keepends=True)
 check(lines[0]=='*** Begin Patch\n' and lines[1]=='*** Add File: '+path+'\n' and lines[-1]=='*** End Patch','native_framing:'+path)
 check(all(line.startswith('+') for line in lines[2:-1]),'native_add_lines:'+path)
 check(''.join(line[1:] for line in lines[2:-1]).encode()==raw,'native_complete_reconstruction:'+path)
F=read(Q['original_failure']['path']);cmd=F['invocation']['cmd'];C=N['construction'];prefix=C['command_prefix'];suffix=C['command_suffix']
check(F['actual_tool_return']==Q['original_actual'] and F['actual_tool_return']['chunk_id']=='702f9d' and F['actual_tool_return']['exit_code']==1,'original_remains_failed')
check(cmd.startswith(prefix) and cmd.endswith(suffix) and suffix=='\nPY' and not cmd.endswith('\n'),'exact_command_boundary')
body=cmd[len(prefix):-len(suffix)]
check(prefix+body+suffix==cmd,'exact_original_command_reconstruction')
check(len(cmd.encode())==10924 and hashlib.sha256(cmd.encode()).hexdigest()=='a3cf479fa39e27e0c4a06a3812cd5f18b7827619cac494138db5ea249ae2c9e6','original_command_bytes')
check(len(body.encode())==10856 and hashlib.sha256(body.encode()).hexdigest()=='9e04d8bedb6b19286418a999ed81e4849df8d1f54d3beb06e1f64cf390377784','original_body_bytes')
check(len(C['edits'])==len(Q['construction_edits'])==18,'finite18_adaptations')
constructed=body+'\n'
for edit,proof in zip(C['edits'],Q['construction_edits']):
 check(edit['label']==proof['label'] and constructed.count(edit['old'])==proof['old_count']==1,'unique_edit:'+edit['label'])
 for key in ['old','new']:
  data=edit[key].encode()
  check(len(data)==proof[key+'_bytes'] and hashlib.sha256(data).hexdigest()==proof[key+'_sha256'],'edit_identity:'+edit['label']+':'+key)
 constructed=constructed.replace(edit['old'],edit['new'],1)
check(constructed.encode()==raw,'whole_source18_exact')
outputs=[str(B/'implementation'/name) for name in ['limited.diff','final-source-scope-proof.json','source-index.json','change-report.json']]
check(P['execution']['outputs']==Q['future_outputs']==outputs,'four_output_allowlist')
for path in outputs:check(not Path(path).exists() and not Path(path).is_symlink(),'absent:'+path)
exact={'cmd':"env -i 'PATH=/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin:/usr/bin:/bin' LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 /usr/bin/timeout --signal=TERM --kill-after=5s 125s '/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python' '"+source['path']+"'",'workdir':str(R),'yield_time_ms':10000,'max_output_tokens':2000}
check(P['execution']['tool_arguments']==Q['planned_execution']==exact,'literal_argv')
check(P['execution']['attempts']==1 and P['execution']['timeout_seconds']==Q['program_deadline_seconds']==120 and P['execution']['outer_timeout_seconds']==125 and P['execution']['outer_kill_after_seconds']==5,'finite_attempt_deadlines')
for marker in ["signal.alarm(120)","assert str(Path(p)) in OUTPUT_PATHS","with Path(p).open('xb')","assert len((rendered+'\\n').encode())<=6000"]:
 check(marker.encode() in raw,'reviewed_guard:'+marker)
for path,size,sha in [
 (R/'artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/active-t12-state.json',180405,'f854dd7801af2dbd06397820153ce342b161551650c56528a3064409ff08eaba'),
 (R/'artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/phase-summary.md',102453,'4aeca541d66dd7d93dc1a3029a899108b3e830597f38432ef43eefcfb3e50fc5')]:fixed(path,size,sha)
receipt={'round':'R293','status':'ROOT_METADATA_SOURCE_NATIVE_INPUT_ARGV_ACCEPTED_ONLY','plan':p_pin,'observation':o_pin,'before_manifest':m_pin,'source':source,'candidate':candidate,'native':native,'limited_diff':diff,'scope':scope,'inputs':O['inputs'],'checks':checks,'check_count':len(checks),'tool_arguments':exact,'release':'soleSol one metadata attempt only; no runtime roles Git','original_actual':F['actual_tool_return'],'original_failure_remains_failed':True,'runtime':False}
out=D/'root-metadata-source-native-acceptance.json'
with out.open('xb') as stream:stream.write((json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode())
display=json.dumps({'status':receipt['status'],'check_count':len(checks),'receipt':pin(out),'runtime':False},ensure_ascii=False)
check(len((display+'\n').encode())<=6000,'console_bound')
print(display)
signal.alarm(0)
