"""Read-only diagnosis of the failed real-tokenizer gate."""
import sys,json,traceback
from pathlib import Path
HERE=Path(__file__).resolve().parent.parent;ROOT=HERE.parents[5];OLD=HERE.parent/'round486-taichu-no-think-best-profile-20261108'
sys.path.insert(0,str(OLD/'implementation'))
from experiment_r489 import CACHE
from transformers import AutoProcessor
from backend_r495 import build_data,decoder_schema,PrefixConstraint
p=AutoProcessor.from_pretrained(str(CACHE),trust_remote_code=True,local_files_only=True,use_fast=False)
e=json.loads((CACHE/'generation_config.json').read_text())['eos_token_id'];d=build_data(p.tokenizer,e);s,_=decoder_schema();prefix=json.loads((CACHE/'actual/round486/run-fla-r489/request-2/input-token-ids.json').read_text())[0]
rows=[]
for ix,text in enumerate(json.loads((HERE/'implementation/contract-fixtures.json').read_text())['valid']):
 cb=PrefixConstraint(d,s,prefix);ids=p.tokenizer.encode(text,add_special_tokens=False)
 for i in range(len(ids)+1):
  try:
   allowed=cb.allowed(prefix+ids[:i])
   if i<len(ids) and ids[i] not in allowed:
    rows.append({'fixture':ix,'offset':i,'kind':'next_token_blocked','prefix':p.tokenizer.decode(ids[:i]),'next_id':ids[i],'next_decoded':p.tokenizer.decode(ids[:i+1]),'allowed_count':len(allowed),'regular_entry':next((list(row) for row in d.regular_tokens if row[0]==ids[i]),None),'tokenizer_single_decode':p.tokenizer.decode([ids[i]]),'is_special':ids[i] in p.tokenizer.all_special_ids,'filter_evidence':d.r493_evidence,'parser_class':type(cb.enforcer.prefix_states[tuple(ids[:i])].parser).__name__,'parser_shortcut':cb.enforcer.prefix_states[tuple(ids[:i])].parser.shortcut_key(),'parser_allowed_chars_prefix':cb.enforcer.prefix_states[tuple(ids[:i])].parser.get_allowed_characters()[:100],'emoji_in_alphabet':'🦾' in d.tokenizer_alphabet,'last8token_ids':ids[max(0,i-8):i],'last8individual_decode':[p.tokenizer.decode([t]) for t in ids[max(0,i-8):i]]});break
  except Exception as error:
   state=cb.enforcer.prefix_states.get(tuple(ids[:i]));a=state.allowed_tokens.allowed_tokens if state else []
   rows.append({'fixture':ix,'offset':i,'kind':'guard_error','prefix':p.tokenizer.decode(ids[:i]),'error':str(error),'allowed_count':len(a),'allowed_eos':[x for x in e if x in a],'can_end':state.parser.can_end() if state else None,'parser_type':type(state.parser).__name__ if state else None,'allowed_first30':a[:30]});break
 else:rows.append({'fixture':ix,'status':'COMPLETE'})
with (HERE/'emoji-gate-diagnostic.json').open('x') as f:json.dump(rows,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps(rows,ensure_ascii=False))
