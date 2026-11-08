"""Byte-native hard prefix mask; no prompt edits, forced tokens or output repair."""
import copy,hashlib,json,time
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import llguidance as llg
from tokenizers import Tokenizer
HERE=Path(__file__).resolve().parent.parent
BANNED=[187, 248045, 248047, 248048, 248049, 248050, 248051, 248052, 248055, 248058, 248059, 248060, 248061, 248062, 248063, 248064, 248065, 248066, 248067, 248068, 248069, 248070, 248071, 248072, 248073, 248074, 248075, 248076]
R491=HERE.parent/'round491-taichu-constrained-json-20261108'
def schema():return json.loads((R491/'diagnostic/visual-decision-schema.json').read_text())
def prepare_data(tokenizer,eos):
 before=tokenizer.backend_tokenizer.to_str();backend=Tokenizer.from_str(before);backend.no_padding();backend.no_truncation();serialized=backend.to_str()
 native=llg.LLTokenizer(serialized,n_vocab=len(tokenizer),eos_token=list(eos))
 assert native.vocab_size==len(tokenizer) and set(native.eos_tokens)==set(eos)
 assert tokenizer.backend_tokenizer.to_str()==before,'original tokenizer was mutated'
 grammar=llg.LLMatcher.grammar_from_json_schema(schema(),overrides={'whitespace_flexible':True,'json_allow_general_unicode_escapes':True,'lenient':False,'coerce_one_of':False})
 error=llg.LLMatcher.validate_grammar(grammar,native)
 if error:raise ValueError('grammar validation: '+error)
 hf_special=set(tokenizer.all_special_ids);skip=hf_special|set(eos);digest=hashlib.sha256();mismatch=[];special_differences=[]
 document=json.loads(serialized)
 assert document['decoder']['type']=='ByteLevel' and document['model']['type']=='BPE','unsupported byte decoder rule'
 values=list(range(33,127))+list(range(161,173))+list(range(174,256));characters=values[:];extra=0
 for value in range(256):
  if value not in values:values.append(value);characters.append(256+extra);extra+=1
 byte_map={chr(character):value for value,character in zip(values,characters)}
 vocab={value:key for key,value in document['model']['vocab'].items()};added={item['id']:item for item in document['added_tokens']}

 for token in range(len(tokenizer)):
  expected_special=token in hf_special
  if token not in eos and native.is_special_token(token)!=expected_special:special_differences.append(token)
  if token in skip:continue
  actual=native.decode_bytes([token]);expected=added[token]['content'].encode() if token in added else bytes(byte_map[c] for c in vocab[token])
  if actual!=expected:mismatch.append({'id':token,'native_hex':actual.hex(),'hf_rule_hex':expected.hex()})
  digest.update(str(token).encode()+b'\0'+actual+b'\0')
 assert mismatch==[{'id':187,'native_hex':'','hf_rule_hex':'ff'}],{'unexpected_byte_differences':mismatch}
 assert set(special_differences)==set(BANNED),{'unexpected_special_differences':special_differences}
 assert not set(BANNED)&set(eos)
 assert all(i in added and added[i]['content'].isascii() for i in BANNED if i!=187)
 provenance={'library':'llguidance','version':__import__('importlib.metadata').metadata.version('llguidance'),'tokenizer_serialized_sha256':hashlib.sha256(serialized.encode()).hexdigest(),'original_tokenizer_unmutated':True,'vocab_size':native.vocab_size,'eos_ids':list(eos),'hf_special_ids':sorted(hf_special),'EOS_override_extra_ids':sorted(set(eos)-hf_special),'bytelevel_decoder_rule':document['decoder'],'regular_single_id_byte_mapping_sha256':digest.hexdigest(),'single_id_byte_differences':mismatch,'special_classification_difference_ids':special_differences,'exact_hard_banned_ids':BANNED,'claim':'token-sequence subset; classification and all canonical representations are not equivalent','grammar_sha256':hashlib.sha256(grammar.encode()).hexdigest(),'original_schema_unmodified':True,'language_subset':'original schema property order; no leading/trailing whitespace; all generated values still strictly postvalidated','forced_tokens':False,'backtracking':False,'grammar_options':{'whitespace_flexible':True,'json_allow_general_unicode_escapes':True,'lenient':False,'coerce_one_of':False}}
 return SimpleNamespace(native=native,eos=list(eos),grammar=grammar,provenance=provenance,banned=BANNED,added_strings={i:added[i]["content"] for i in BANNED if i!=187},ascii_vocab=document["model"]["vocab"])
class PrefixConstraint:
 def __init__(self,data,prompt_ids):
  self.data=data;self.prefix=list(prompt_ids);self.matcher=llg.LLMatcher(data.native,data.grammar);self.committed=[];self.cache={};self.steps=[];self.elapsed_s=0.0
  if self.matcher.is_error():raise ValueError(self.matcher.get_error())
 def allowed(self,full_ids):
  start=time.perf_counter()
  if full_ids[:len(self.prefix)]!=self.prefix:raise ValueError('original prompt changed')
  suffix=full_ids[len(self.prefix):];key=tuple(suffix)
  if key not in self.cache:
   if suffix:
    if suffix[:-1]!=self.committed:raise ValueError('unregistered nonsequential generation state')
    previous=self.cache[tuple(self.committed)]['mask']
    if suffix[-1]>=len(previous) or previous[suffix[-1]]==0:raise ValueError('chosen token violated prior mask')
    if not self.matcher.consume_token(suffix[-1]) or self.matcher.is_error():raise ValueError('matcher consume: '+self.matcher.get_error())
   elif self.committed:raise ValueError('missing root cache')
   self.committed=list(suffix);mask=self.matcher.compute_logit_bias()
   if self.matcher.is_error():raise ValueError('matcher mask: '+self.matcher.get_error())
   if len(mask)!=self.data.native.vocab_size:raise ValueError('native mask vocabulary mismatch')
   effective=bytearray(mask)
   for token in self.data.banned:effective[token]=0
   mask=bytes(effective)
   accepting=self.matcher.is_accepting();stopped=self.matcher.is_stopped();stop_reason=self.matcher.stop_reason();eos_allowed=[e for e in self.data.eos if mask[e]!=0]
   if (bool(eos_allowed)!=accepting) or (accepting and len(eos_allowed)!=len(self.data.eos)):raise ValueError('premature or missing original EOS')
   self.cache[key]={'mask':mask,'accepting':accepting,'eos_allowed':eos_allowed,'stopped':stopped,'stop_reason':stop_reason}
  row=self.cache[key];allowed=np.flatnonzero(np.frombuffer(row['mask'],dtype=np.uint8)).tolist()
  if not allowed:raise ValueError('empty hard mask; fallback forbidden')
  elapsed=time.perf_counter()-start;self.elapsed_s+=elapsed
  self.steps.append({'suffix_tokens':len(suffix),'allowed_count':len(allowed),'can_end':row['accepting'],'eos_allowed':row['eos_allowed'],'stopped':row['stopped'],'stop_reason':row['stop_reason'],'mask_sha256':hashlib.sha256(row['mask']).hexdigest(),'callback_s':elapsed})
  return allowed
 def __call__(self,batch_id,sent):
  if batch_id!=0:raise ValueError('batch1 beam1 only')
  return self.allowed(sent.tolist())
 def verify_output(self,ids):
  for offset,token in enumerate(ids):
   mask=self.cache[tuple(ids[:offset])]['mask']
   if token>=len(mask) or mask[token]==0:raise ValueError('generated token outside hard mask')
  return {'offline_token_membership_replay':'PASS','replayed_tokens':len(ids)}
 def evidence(self):
  return {'implementation':'llguidance1.9.1 byte-native LLMatcher','calls':len(self.steps),'callback_s':self.elapsed_s,'steps':self.steps,'prompt_tokens':len(self.prefix),'eos_ids':self.data.eos,'mask_cache_bytes':sum(len(r['mask']) for r in self.cache.values()),'fallback':'FORBIDDEN','state_isolation':'fresh matcher and mask cache per request','forced_tokens':False,'backtracking':False}
