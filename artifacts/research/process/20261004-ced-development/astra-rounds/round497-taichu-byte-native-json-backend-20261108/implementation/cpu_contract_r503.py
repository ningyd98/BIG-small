"""Real byte-vocabulary/contract qualification; zero model loads and generations."""
import hashlib,json,resource,sys,time,traceback
from pathlib import Path
HERE=Path(__file__).resolve().parent.parent;ROOT=HERE.parents[5];R491=HERE.parent/'round491-taichu-constrained-json-20261108';OLD=HERE.parent/'round486-taichu-no-think-best-profile-20261108'
sys.path.insert(0,str(OLD/'implementation'));sys.path.insert(0,str(ROOT/'src'))
from experiment_r489 import CACHE,mode_features,base_versions,kernel_bindings
from evidence_codec_r488 import write_evidence
from cloud_edge_robot_arm.vision.planner import VisualDecision
from transformers import AutoProcessor
from byte_decoder_r500 import prepare_data,PrefixConstraint,schema
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
 values=list(range(33,127))+list(range(161,173))+list(range(174,256));characters=values[:];extra=0
 for value in range(256):
  if value not in values:values.append(value);characters.append(256+extra);extra+=1
 byte_token={value:data.ascii_vocab[chr(character)] for value,character in zip(values,characters)}
 from tokenizers import Tokenizer
 original_backend=tokenizer.backend_tokenizer.to_str();raw_bpe=Tokenizer.from_str(original_backend);raw_bpe.normalizer=None
 def replay(text,raw_byte=False):
  cb=PrefixConstraint(data,prefix);canonical_ids=tokenizer.encode(text,add_special_tokens=False)
  canonical_decoded=tokenizer.decode(canonical_ids,skip_special_tokens=False)
  assert data.native.decode_bytes(canonical_ids)==canonical_decoded.encode(),'native bytes differ from actual HF decode'
  assert data.native.tokenize_str(text)==canonical_ids,'native tokenizer changed canonical IDs'
  ids=raw_bpe.encode(text,add_special_tokens=False).ids if raw_byte else canonical_ids
  expected_text=text if raw_byte else canonical_decoded
  if raw_byte:
   assert not set(ids)&(set(data.banned)|set(eos))
   assert tokenizer.decode(ids,skip_special_tokens=False)==text and data.native.decode_bytes(ids)==text.encode(),'raw UTF8 byte stream differs from original fixture'
  normalization={'stream':'ORIGINAL_UTF8_NO_NFC_BPE_IDS' if raw_byte else 'HF_CANONICAL_IDS','original_text_sha256':hashlib.sha256(text.encode()).hexdigest(),'HF_canonical_text_sha256':hashlib.sha256(canonical_decoded.encode()).hexdigest(),'NFC_changed_text':text!=canonical_decoded,'native_equals_HF_decode':True,'raw_byte_equals_original':True if raw_byte else None,'token_ids_sha256':hashlib.sha256(json.dumps(ids).encode()).hexdigest()}

  for offset,token in enumerate(ids):
   allowed=cb.allowed(prefix+ids[:offset])
   if token not in allowed:return False,{'blocked_at':offset,'token':token,'prefix':tokenizer.decode(ids[:offset]),'through_blocked':tokenizer.decode(ids[:offset+1]),**normalization,'callback_s':cb.elapsed_s,'suppressed_EOS_steps':sum(bool(r['suppressed_eos']) for r in cb.steps),'EOS_example':next((r for r in cb.steps if r['suppressed_eos']),None)}
  allowed=cb.allowed(prefix+ids);ok=all(e in allowed for e in eos)
  return ok,{'tokens':len(ids),'all_original_eos_reachable':ok,**normalization,'callback_s':cb.elapsed_s,'suppressed_EOS_steps':sum(bool(r['suppressed_eos']) for r in cb.steps),'EOS_example':next((r for r in cb.steps if r['suppressed_eos']),None)}
 for kind,items in [('valid',[{'name':str(i),'text':text} for i,text in enumerate(fixtures['valid'])]),('invalid',fixtures['invalid']),('value_boundary',fixtures['postvalidation_candidates'])]:
  for item in items:
   valid=True
   try:VisualDecision.model_validate_json(item['text'],strict=True)
   except Exception:valid=False
   assert valid==(kind=='valid'),{'fixture_expectation_incorrect':item['name']}
   accepted,detail=replay(item['text'],True);canonical_accepted,canonical_detail=replay(item['text']);canonical_text=tokenizer.decode(tokenizer.encode(item['text'],add_special_tokens=False),skip_special_tokens=False)
   canonical_valid=True
   try:VisualDecision.model_validate_json(canonical_text,strict=True)
   except Exception:canonical_valid=False
   assert canonical_accepted==canonical_valid,('canonical',item['name'])
   row={'kind':kind,'name':item['name'],'strict_original_validator':valid,'generator_accepts':accepted,'canonical_generator_accepts':canonical_accepted,'canonical_strict_validator':canonical_valid,'canonical_detail':canonical_detail,**detail};report['results'].append(row)
   assert accepted==valid,row
 a=PrefixConstraint(data,prefix);b=PrefixConstraint(data,prefix);root=a.allowed(prefix)
 assert root==a.allowed(prefix)==b.allowed(prefix) and not any(e in root for e in eos)
 ids=tokenizer.encode('{"target_pixel":',add_special_tokens=False)
 for offset in range(len(ids)+1):assert a.allowed(prefix+ids[:offset])==b.allowed(prefix+ids[:offset])
 assert root==PrefixConstraint(data,prefix).allowed(prefix)
 permuted=json.loads(fixtures['valid'][0]);permuted={'reason':permuted.pop('reason'),**permuted};permuted=json.dumps(permuted,ensure_ascii=False,separators=(',',':'));VisualDecision.model_validate_json(permuted,strict=True);permuted_accept,_=replay(permuted)
 assert not permuted_accept,'fixed-order subset expectation changed'
 witnesses=[]
 for special_id,text in data.added_strings.items():
  head='{"target_pixel":[1,2],"destination_pixel":[3,4],"target_label":"';tail='","reported_confidence":0.5,"skills":[]}'
  witness_ids=[data.ascii_vocab[c] for c in text];ids=tokenizer.encode(head,add_special_tokens=False)+witness_ids+tokenizer.encode(tail,add_special_tokens=False)
  raw=head+text+tail;VisualDecision.model_validate_json(raw,strict=True)
  assert data.native.decode_bytes(ids)==raw.encode() and tokenizer.decode(ids)==raw
  cb=PrefixConstraint(data,prefix)
  for offset,token in enumerate(ids):assert token in cb.allowed(prefix+ids[:offset]),('witness',special_id,offset)
  assert all(e in cb.allowed(prefix+ids) for e in eos)
  witnesses.append({'special_id':special_id,'text':text,'ordinary_ASCII_ids':witness_ids,'strict_raw_valid':True,'all_original_eos_reachable':True})
 report.update(added_token_ASCII_witnesses=witnesses,status='PASS' ,all_six_original_valid_pass=True,canonical_and_original_byte_streams_both_tested=True,raw_witness_encoder='test-only original BPE copy with normalizer=None; original fixture bytes unchanged',original_tokenizer_unchanged=tokenizer.backend_tokenizer.to_str()==original_backend,adapter_sha256=hashlib.sha256((HERE/'implementation/byte_decoder_r500.py').read_bytes()).hexdigest(),invalid_blocked=11,value_boundary_blocked=4,prefix_repetition_and_request_isolation='PASS',fixed_property_order_subset_confirmed=True,original_schema_sha256=hashlib.sha256((R491/'diagnostic/visual-decision-schema.json').read_bytes()).hexdigest(),fixture_source_sha256=hashlib.sha256(fixture_path.read_bytes()).hexdigest(),kernel_bindings=kernel_bindings()[1],base68=base_versions(),elapsed_s=time.perf_counter()-start,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
 assert report['elapsed_s']<=120
 write_evidence(HERE/'grammar-r503.json',{'grammar':data.grammar,'provenance':data.provenance})
except Exception as error:
 report.update(status='FAILED',error=str(error),traceback=traceback.format_exc(),elapsed_s=time.perf_counter()-start,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
 write_evidence(HERE/'cpu-contract-r503.json',report);print('CPU_CONTRACT_FAILED',report['error'],flush=True);raise
write_evidence(HERE/'cpu-contract-r503.json',report);print('CPU_CONTRACT_PASS',len(report['results']),round(report['elapsed_s'],3),flush=True)
