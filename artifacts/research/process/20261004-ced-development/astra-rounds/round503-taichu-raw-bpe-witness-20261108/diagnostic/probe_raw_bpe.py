import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from experiment_r489 import CACHE
sys.path.insert(0,sys.argv[2]);from byte_decoder_r500 import prepare_data,PrefixConstraint
from transformers import AutoProcessor
from tokenizers import Tokenizer
p=AutoProcessor.from_pretrained(str(CACHE),trust_remote_code=True,local_files_only=True,use_fast=False);t=p.tokenizer;before=t.backend_tokenizer.to_str();copy=Tokenizer.from_str(before);copy.normalizer=None;e=json.loads((CACHE/'generation_config.json').read_text())['eos_token_id'];data=prepare_data(t,e);prefix=json.loads((CACHE/'actual/round486/run-fla-r489/request-2/input-token-ids.json').read_text())[0];fixtures=json.loads(Path(sys.argv[3]).read_text())['valid'];rows=[]
for index,text in enumerate(fixtures):
 ids=copy.encode(text,add_special_tokens=False).ids;cb=PrefixConstraint(data,prefix);row={'fixture':index,'raw_BPE_ids':ids,'raw_HF_decode_equals_original':t.decode(ids,skip_special_tokens=False)==text,'native_bytes_equals_original':data.native.decode_bytes(ids)==text.encode(),'D_or_EOS_present':bool(set(ids)&(set(data.banned)|set(e)))}
 for i,token in enumerate(ids):
  if token not in cb.allowed(prefix+ids[:i]):row.update(accepted=False,blocked_at=i,token=token);break
 else:row.update(accepted=all(x in cb.allowed(prefix+ids) for x in e),all_original_eos_reachable=all(x in cb.allowed(prefix+ids) for x in e))
 rows.append(row)
assert before==t.backend_tokenizer.to_str()
print(json.dumps({'original_tokenizer_unchanged':True,'test_only_copy_normalizer':'None','all_results':rows},ensure_ascii=False,indent=2))
