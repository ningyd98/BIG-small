"""Observe every fixed fixture after final negative gate; no implementation repair."""
import hashlib,json,resource,sys,time,traceback
from pathlib import Path
HERE=Path(__file__).resolve().parent.parent;ROOT=HERE.parents[5];OLD=HERE.parent/'round486-taichu-no-think-best-profile-20261108'
sys.path.insert(0,str(OLD/'implementation'));sys.path.insert(0,str(ROOT/'src'))
from experiment_r489 import CACHE
from transformers import AutoProcessor
from backend_r496 import build_data,decoder_schema,PrefixConstraint
from cloud_edge_robot_arm.vision.planner import VisualDecision
from evidence_codec_r488 import write_evidence
start=time.perf_counter();p=AutoProcessor.from_pretrained(str(CACHE),trust_remote_code=True,local_files_only=True,use_fast=False)
e=json.loads((CACHE/'generation_config.json').read_text())['eos_token_id'];d=build_data(p.tokenizer,e);s,changes=decoder_schema();prefix=json.loads((CACHE/'actual/round486/run-fla-r489/request-2/input-token-ids.json').read_text())[0]
fixtures=json.loads((HERE/'implementation/contract-fixtures-r496.json').read_text());rows=[]
for kind,items in [('valid',[{'name':str(i),'text':t} for i,t in enumerate(fixtures['valid'])]),('invalid',fixtures['invalid']),('value_keyword',fixtures['postvalidation_candidates'])]:
 for item in items:
  cb=PrefixConstraint(d,s,prefix);ids=p.tokenizer.encode(item['text'],add_special_tokens=False);row={'kind':kind,'name':item['name'],'fixture_text_sha256':hashlib.sha256(item['text'].encode()).hexdigest(),'strict_validator':False}
  try:VisualDecision.model_validate_json(item['text'],strict=True);row['strict_validator']=True
  except Exception as error:row['strict_error']=str(error)
  try:
   for i in range(len(ids)+1):
    a=cb.allowed(prefix+ids[:i])
    if i<len(ids) and ids[i] not in a:
     row.update(accepted=False,blocked_at=i,token=ids[i],token_string=p.tokenizer.convert_ids_to_tokens(ids[i]),token_single_decode=p.tokenizer.decode([ids[i]]),prefix=p.tokenizer.decode(ids[:i]),prefix_through_blocked=p.tokenizer.decode(ids[:i+1]),allowed_count=len(a),last_can_end=cb.enforcer.prefix_states[tuple(ids[:i])].parser.can_end());break
   else:row.update(accepted=all(x in a for x in e),all_original_eos_reachable=all(x in a for x in e),tokens=len(ids))
  except Exception as error:row.update(accepted=False,error=str(error),traceback=traceback.format_exc())
  row.update(callback_s=cb.elapsed_s,callback_calls=len(cb.steps));rows.append(row)
  print(kind,item['name'],row['accepted'],round(cb.elapsed_s,3),flush=True)
summary={'status':'UNICODE_TOKENIZER_INCOMPATIBLE','scope':'CPU_DIAGNOSTIC_NO_REPAIR_NO_MODEL_NO_GENERATION','all_fixture_results':rows,'core_valid_accepted':sum(x['accepted'] for x in rows if x['kind']=='valid'),'core_valid_total':len(fixtures['valid']),'core_invalid_blocked':sum(not x['accepted'] for x in rows if x['kind']=='invalid'),'core_invalid_total':len(fixtures['invalid']),'original_filter':d.r493_evidence,'unicode_alphabet':d.r496_evidence,'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,'elapsed_s':time.perf_counter()-start,'schema_changes':changes,'stage_a':'NOT_RUN_SOFTWARE_CONTRACT_GATE','stage_b':'NOT_RUN_STAGE_A_GATE','model_loads':0,'model_generations':0,'formal_acceptance':'NOT_PERFORMED'}
write_evidence(HERE/'final-cpu-audit.json',summary)
print('FINAL_CPU_AUDIT_COMPLETE',summary['core_valid_accepted'],summary['core_valid_total'],summary['elapsed_s'],flush=True)
