"""Read-only semantic witness; no adapter repair and no model call."""
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from experiment_r489 import CACHE
from transformers import AutoProcessor
import llguidance as llg
p=AutoProcessor.from_pretrained(str(CACHE),trust_remote_code=True,local_files_only=True,use_fast=False);t=p.tokenizer;doc=json.loads(t.backend_tokenizer.to_str());e=json.loads((CACHE/'generation_config.json').read_text())['eos_token_id'];n=llg.LLTokenizer(t.backend_tokenizer.to_str(),n_vocab=len(t),eos_token=e)
schema=json.loads(Path(sys.argv[2]).read_text());g=llg.LLMatcher.grammar_from_json_schema(schema,overrides={'lenient':False,'coerce_one_of':False,'whitespace_flexible':True,'json_allow_general_unicode_escapes':True})
match=llg.LLMatcher(n,g);prefix='{"target_pixel":[1,2],"destination_pixel":[3,4],"target_label":"';assert match.consume_tokens(t.encode(prefix,add_special_tokens=False))
mask=match.compute_logit_bias();hf_special=set(t.all_special_ids);extra=[i for i in range(len(t)) if i not in hf_special|set(e) and n.is_special_token(i)];added={row['id']:row for row in doc['added_tokens']}
rows=[{'id':i,'content':t.convert_ids_to_tokens(i),'added_metadata':added.get(i),'native_bytes_hex':n.decode_bytes([i]).hex(),'inside_string_mask':mask[i]} for i in extra]
text='<think>';witness=[doc['model']['vocab'][c] for c in text];assert n.decode_bytes(witness)==text.encode() and t.decode(witness)==text
accepted=match.consume_tokens(witness);tail='","reported_confidence":0.5,"skills":[]}';accepted=accepted and match.consume_tokens(t.encode(tail,add_special_tokens=False));last=match.compute_logit_bias()
result={'extras':rows,'all_extra_except187_are_added_tokens':all(i==187 or i in added for i in extra),'all_extra_masks_zero_in_string':all(mask[i]==0 for i in extra),'ASCII_literal_tag_witness':{'text':text,'ids':witness,'native_and_hf_raw_bytes_match':True,'consume_success':accepted,'accepting':match.is_accepting(),'error':match.get_error(),'all_original_eos_allowed':all(last[i]!=0 for i in e),'resulting_valid_raw':prefix+text+tail}}
print(json.dumps(result,ensure_ascii=False,indent=2))
