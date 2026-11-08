"""Freeze CPU-only raw-BPE witnesses; production tokenizer is never modified."""
import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent.parent;ROOT=HERE.parents[5];OLD=HERE.parent/'round486-taichu-no-think-best-profile-20261108';R491=HERE.parent/'round491-taichu-constrained-json-20261108'
sys.path.insert(0,str(OLD/'implementation'))
from experiment_r489 import CACHE
from transformers import AutoProcessor
from tokenizers import Tokenizer
import llguidance as llg
processor=AutoProcessor.from_pretrained(str(CACHE),trust_remote_code=True,local_files_only=True,use_fast=False);tokenizer=processor.tokenizer;before=tokenizer.backend_tokenizer.to_str();raw=Tokenizer.from_str(before);raw.normalizer=None
original=json.loads(before);modified=json.loads(raw.to_str());normalized=modified.copy();normalized['normalizer']=original['normalizer'];assert normalized==original
native_copy=Tokenizer.from_str(before);native_copy.no_padding();native_copy.no_truncation();serialized=native_copy.to_str();eos=json.loads((CACHE/'generation_config.json').read_text())['eos_token_id'];native=llg.LLTokenizer(serialized,n_vocab=len(tokenizer),eos_token=eos)
fixtures=json.loads((R491/'implementation/contract-fixtures-r496.json').read_text());rows=[]
for kind,items in [('valid',[{'name':str(i),'text':text} for i,text in enumerate(fixtures['valid'])]),('invalid',fixtures['invalid']),('value_boundary',fixtures['postvalidation_candidates'])]:
 for fixture in items:
  text=fixture['text'];canonical=tokenizer.encode(text,add_special_tokens=False);raw_ids=raw.encode(text,add_special_tokens=False).ids;decoded=tokenizer.decode(canonical,skip_special_tokens=False)
  assert native.decode_bytes(canonical)==decoded.encode()
  assert native.decode_bytes(raw_ids)==text.encode() and tokenizer.decode(raw_ids,skip_special_tokens=False)==text
  rows.append({'kind':kind,'name':fixture['name'],'original_text_sha256':hashlib.sha256(text.encode()).hexdigest(),'canonical_decoded_sha256':hashlib.sha256(decoded.encode()).hexdigest(),'NFC_changed_text':decoded!=text,'canonical_ids':canonical,'raw_BPE_ids':raw_ids,'canonical_ids_sha256':hashlib.sha256(json.dumps(canonical).encode()).hexdigest(),'raw_ids_sha256':hashlib.sha256(json.dumps(raw_ids).encode()).hexdigest()})
assert tokenizer.backend_tokenizer.to_str()==before
report={'status':'PASS','original_tokenizer_unchanged':True,'CPU_copy_only_diff':[{'path':'/normalizer','old':original['normalizer'],'new':modified['normalizer']}],'all_other_backend_fields_equal':True,'original_backend_sha256':hashlib.sha256(before.encode()).hexdigest(),'native_serialized_sha256':hashlib.sha256(serialized.encode()).hexdigest(),'fixtures':rows,'model_loads':0,'generations':0}
with (HERE/'tokenization-proof.json').open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
print('TOKENIZATION_PROOF_PASS',len(rows),flush=True)
