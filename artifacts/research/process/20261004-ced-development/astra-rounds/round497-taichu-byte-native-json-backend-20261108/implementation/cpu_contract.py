"""Real byte-vocabulary/contract qualification; zero model loads and generations."""
import hashlib,json,resource,sys,time,traceback
from pathlib import Path
HERE=Path(__file__).resolve().parent.parent;ROOT=HERE.parents[5];R491=HERE.parent/'round491-taichu-constrained-json-20261108';OLD=HERE.parent/'round486-taichu-no-think-best-profile-20261108'
sys.path.insert(0,str(OLD/'implementation'));sys.path.insert(0,str(ROOT/'src'))
from experiment_r489 import CACHE,mode_features,base_versions,kernel_bindings
from evidence_codec_r488 import write_evidence
from cloud_edge_robot_arm.vision.planner import VisualDecision
from transformers import AutoProcessor
from byte_decoder import prepare_data,PrefixConstraint,schema
start=time.perf_counter();report={'status':'STARTED','model_loads':0,'generation_calls':0,'results':[]}
try:
 processor=AutoProcessor.from_pretrained(str(CACHE),trust_remote_code=True,local_files_only=True,use_fast=False);tokenizer=processor.tokenizer
 features,processor_evidence,decoded=mode_features(processor,False);prefix=features['input_ids'][0].tolist()
 prior=json.loads((CACHE/'actual/round486/run-fla-r489/request-2/input-token-ids.json').read_text())[0]
 assert prefix==prior and len(prefix)==1030
 assert processor_evidence['features']==json.loads((OLD/'processor-fla-r489.json').read_text())['modes']['OFF']['features']
 eos=json.loads((CACHE/'generation_config.json').read_text())['eos_token_id'];data=prepare_data(tokenizer,eos)
 report.update(tokenizer=data.provenance,processor=processor_evidence,input_tokens=len(prefix),eos_ids=eos)
 fixture_path=R491/'implementation/contract-fixtures-r496.json';fixtures=json.loads(fixture_path.read_text())
 def replay(text):
  cb=PrefixConstraint(data,prefix);ids=tokenizer.encode(text,add_special_tokens=False)
  assert data.native.decode_bytes(ids)==text.encode(),'composite raw-byte decode mismatch'
  assert data.native.tokenize_str(text)==ids,'native tokenizer changed canonical token IDs'
  for offset,token in enumerate(ids):
   allowed=cb.allowed(prefix+ids[:offset])
   if token not in allowed:return False,{'blocked_at':offset,'token':token,'prefix':tokenizer.decode(ids[:offset]),'through_blocked':tokenizer.decode(ids[:offset+1]),'callback_s':cb.elapsed_s}
  allowed=cb.allowed(prefix+ids);ok=all(e in allowed for e in eos)
  return ok,{'tokens':len(ids),'all_original_eos_reachable':ok,'callback_s':cb.elapsed_s}
 for kind,items in [('valid',[{'name':str(i),'text':text} for i,text in enumerate(fixtures['valid'])]),('invalid',fixtures['invalid']),('value_boundary',fixtures['postvalidation_candidates'])]:
  for item in items:
   valid=True
   try:VisualDecision.model_validate_json(item['text'],strict=True)
   except Exception:valid=False
   assert valid==(kind=='valid'),{'fixture_expectation_incorrect':item['name']}
   accepted,detail=replay(item['text']);row={'kind':kind,'name':item['name'],'strict_original_validator':valid,'generator_accepts':accepted,**detail};report['results'].append(row)
   assert accepted==valid,row
 a=PrefixConstraint(data,prefix);b=PrefixConstraint(data,prefix);root=a.allowed(prefix)
 assert root==a.allowed(prefix)==b.allowed(prefix) and not any(e in root for e in eos)
 ids=tokenizer.encode('{"target_pixel":',add_special_tokens=False)
 for offset in range(len(ids)+1):assert a.allowed(prefix+ids[:offset])==b.allowed(prefix+ids[:offset])
 assert root==PrefixConstraint(data,prefix).allowed(prefix)
 permuted=json.loads(fixtures['valid'][0]);permuted={'reason':permuted.pop('reason'),**permuted};permuted=json.dumps(permuted,ensure_ascii=False,separators=(',',':'));VisualDecision.model_validate_json(permuted,strict=True);permuted_accept,_=replay(permuted)
 assert not permuted_accept,'fixed-order subset expectation changed'
 report.update(status='PASS',all_six_original_valid_pass=True,invalid_blocked=11,value_boundary_blocked=4,prefix_repetition_and_request_isolation='PASS',fixed_property_order_subset_confirmed=True,original_schema_sha256=hashlib.sha256((R491/'diagnostic/visual-decision-schema.json').read_bytes()).hexdigest(),fixture_source_sha256=hashlib.sha256(fixture_path.read_bytes()).hexdigest(),kernel_bindings=kernel_bindings()[1],base68=base_versions(),elapsed_s=time.perf_counter()-start,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
 assert report['elapsed_s']<=120
 write_evidence(HERE/'grammar.json',{'grammar':data.grammar,'provenance':data.provenance})
except Exception as error:
 report.update(status='FAILED',error=str(error),traceback=traceback.format_exc(),elapsed_s=time.perf_counter()-start,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
 write_evidence(HERE/'cpu-contract.json',report);print('CPU_CONTRACT_FAILED',report['error'],flush=True);raise
write_evidence(HERE/'cpu-contract.json',report);print('CPU_CONTRACT_PASS',len(report['results']),round(report['elapsed_s'],3),flush=True)
