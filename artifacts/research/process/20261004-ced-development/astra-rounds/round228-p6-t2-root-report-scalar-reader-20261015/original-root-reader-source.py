from pathlib import Path
import json,hashlib
r=Path('artifacts/research/process/20261004-ced-development/astra-rounds/round222-p6-t2-local-lease-dispatch-patch-recovery-20261015/implementation')
for name in ('actual-metadata-tool-return.json','step-report.json','source-index.json','change-report.json'):
 p=r/name;b=p.read_bytes();v=json.loads(b);print('FILE',name,'BYTES',len(b),'SHA256',hashlib.sha256(b).hexdigest(),'KEYS',list(v))
 for k,x in v.items():
  if k=='checks':print(k,'COUNT',len(x),'FAILURES',json.dumps([y for y in x if y.get('passed') is not True]))
  elif k in ('edit_units','function_regions','protected','unaffected_manifest_records'):print(k,'COUNT',len(x))
  elif k=='actual_apply_receipt':print(k,'REAL_RETURN',json.dumps(x['actual_tool_return']),'NUMERIC',x['numeric_exit'],'NATIVE_ARGUMENT_BYTES',len(x['tool_arguments']['input'].encode()))
  else:print(k,json.dumps(x,ensure_ascii=False))

