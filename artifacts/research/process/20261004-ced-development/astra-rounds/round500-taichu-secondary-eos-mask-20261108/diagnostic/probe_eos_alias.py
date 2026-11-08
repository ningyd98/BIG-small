import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from experiment_r489 import CACHE
sys.path.insert(0,sys.argv[2]);from byte_decoder_r499 import prepare_data,PrefixConstraint
from transformers import AutoProcessor
p=AutoProcessor.from_pretrained(str(CACHE),trust_remote_code=True,local_files_only=True,use_fast=False);t=p.tokenizer;e=json.loads((CACHE/'generation_config.json').read_text())['eos_token_id'];data=prepare_data(t,e);prefix=json.loads((CACHE/'actual/round486/run-fla-r489/request-2/input-token-ids.json').read_text())[0];text=json.loads(Path(sys.argv[3]).read_text())['valid'][0];ids=t.encode(text,add_special_tokens=False);cb=PrefixConstraint(data,prefix)
for i in range(len(ids)+1):
 try:cb.allowed(prefix+ids[:i])
 except Exception as error:
  mask=cb.matcher.compute_logit_bias();print(json.dumps({'offset':i,'raw_prefix':t.decode(ids[:i]),'error':str(error),'native_accepting':cb.matcher.is_accepting(),'native_eos_mask':{str(k):mask[k] for k in e},'native_eos':data.native.eos_tokens,'prompt_tokens':len(prefix)},ensure_ascii=False));break
