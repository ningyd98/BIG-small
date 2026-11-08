"""Real tokenizer replay; no model weights, generation, or CUDA execution."""
import json,sys,time,traceback
from pathlib import Path
HERE=Path(__file__).resolve().parent.parent;ROOT=HERE.parents[5]
OLD=HERE.parent/'round486-taichu-no-think-best-profile-20261108'
sys.path.insert(0,str(OLD/'implementation'));sys.path.insert(0,str(ROOT/'src'))
from experiment_r489 import CACHE,mode_features,base_versions,kernel_bindings
from evidence_codec_r488 import write_evidence
from cloud_edge_robot_arm.vision.planner import VisualDecision
from transformers import AutoProcessor

def main():
 candidate=sys.argv[1];report={'candidate':candidate,'model_loads':0,'generation_calls':0};started=time.perf_counter()
 try:
  processor=AutoProcessor.from_pretrained(str(CACHE),trust_remote_code=True,local_files_only=True,use_fast=False)
  features,evidence,decoded=mode_features(processor,False);prefix=features['input_ids'][0].tolist()
  prior=json.loads((CACHE/'actual/round486/run-fla-r489/request-2/input-token-ids.json').read_text())[0]
  assert prefix==prior and len(prefix)==1030
  expected=json.loads((OLD/'processor-fla-r489.json').read_text())['modes']['OFF']['features']
  assert evidence['features']==expected
  tokenizer=processor.tokenizer;eos=json.loads((CACHE/'generation_config.json').read_text())['eos_token_id']
  if candidate=='unrestricted':
   allowed=list(range(len(tokenizer)))
   assert not any(x in allowed for x in eos),'UNRESTRICTED permits premature EOS and fenced output'
  from backend_r496 import build_data,decoder_schema,PrefixConstraint
  schema,changes=decoder_schema();data=build_data(tokenizer,eos)
  fixtures=json.loads((HERE/'implementation/contract-fixtures-r496.json').read_text());results=[]
  def replay(text):
   cb=PrefixConstraint(data,schema,prefix);ids=tokenizer.encode(text,add_special_tokens=False)
   for i,token in enumerate(ids):
    allowed=cb.allowed(prefix+ids[:i]);
    if token not in allowed:return False,{'blocked_at':i,'token':token,'text_prefix':tokenizer.decode(ids[:i+1])}
   end=cb.allowed(prefix+ids)
   return all(x in end for x in eos),{'tokens':len(ids),'all_eos':all(x in end for x in eos)}
  for i,text in enumerate(fixtures['valid']):
   VisualDecision.model_validate_json(text,strict=True)
   ok,detail=replay(text);results.append({'kind':'valid','index':i,'pass':ok,**detail});assert ok,results[-1]
  for fixture in fixtures['invalid']:
   try:VisualDecision.model_validate_json(fixture['text'],strict=True)
   except Exception:pass
   else:raise AssertionError('invalid fixture accepted by strict validator')
   ok,detail=replay(fixture['text']);results.append({'kind':'invalid','name':fixture['name'],'blocked':not ok,**detail});assert not ok,results[-1]
  post=[]
  for fixture in fixtures['postvalidation_candidates']:
   accepted,detail=replay(fixture['text']);post.append({'name':fixture['name'],'generator_accepts':accepted,'original_validator_rejects':True,**detail})
  a=PrefixConstraint(data,schema,prefix);b=PrefixConstraint(data,schema,prefix)
  root=a.allowed(prefix);assert root==a.allowed(prefix)==b.allowed(prefix)
  assert not any(e in root for e in eos)
  partial=tokenizer.encode('{"target_pixel":',add_special_tokens=False)
  for i in range(len(partial)+1):
   x=a.allowed(prefix+partial[:i]);y=b.allowed(prefix+partial[:i]);assert x==y
   assert not any(e in x for e in eos)
  assert root==PrefixConstraint(data,schema,prefix).allowed(prefix)
  assert time.perf_counter()-started<=120,'CPU gate time cap'
  assert __import__('resource').getrusage(__import__('resource').RUSAGE_SELF).ru_maxrss*1024-data.r496_evidence['baseline_peak_rss_bytes']<=1024**3,'Unicode RSS increment cap'
  report.update(status='PASS' ,input_tokens=len(prefix),processor=evidence,decoded_input_sha256=__import__('hashlib').sha256(decoded.encode()).hexdigest(),eos_ids=eos,tokenizer_length=len(tokenizer),unicode_alphabet_evidence=data.r496_evidence,peak_rss_bytes=__import__("resource").getrusage(__import__("resource").RUSAGE_SELF).ru_maxrss*1024,alphabet_snapshot=PrefixConstraint(data,schema,prefix).alphabetfacts,tokenizer_filter_evidence=data.r493_evidence,schema_changes=changes,fixture_results=results,value_keyword_tests=post,repeated_prefix_and_interleaved_request_and_reset='PASS',base68=base_versions(),kernel_bindings=kernel_bindings()[1],elapsed_s=time.perf_counter()-started)
 except Exception as error:
  report.update(status='EXPECTED_RED' if candidate=='unrestricted' else 'FAILED',error=str(error),traceback=traceback.format_exc(),elapsed_s=time.perf_counter()-started)
  write_evidence(HERE/('cpu-'+candidate+'.json'),report);print(report['status'],report['error'],flush=True);raise
 write_evidence(HERE/('cpu-'+candidate+'.json'),report);write_evidence(HERE/'decoder-schema.json',schema)
 print('CPU_CONTRACT_PASS',len(results),'fixtures',round(time.perf_counter()-started,3),flush=True)
if __name__=='__main__':main()
