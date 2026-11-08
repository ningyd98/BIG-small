"""Artifact-only LMFE 0.11.3 official TF adapter, with explicit suffix/EOS guards."""
import copy,json,time
from pathlib import Path
from lmformatenforcer import JsonSchemaParser
from lmformatenforcer.characterlevelparser import CharacterLevelParserConfig
from lmformatenforcer import TokenEnforcer, TokenEnforcerTokenizerData
HERE=Path(__file__).resolve().parent.parent

def decoder_schema():
 original=json.loads((HERE/'diagnostic/visual-decision-schema.json').read_text());schema=copy.deepcopy(original);changes=[]
 for name in ['target_pixel','destination_pixel']:
  array=schema['properties'][name]['anyOf'][0]
  assert array['prefixItems']==[{'type':'integer'},{'type':'integer'}] and array['minItems']==array['maxItems']==2
  array['items']=array.pop('prefixItems')[0]
  changes.append({'path':f'/properties/{name}/anyOf/0','change':'homogeneous integer prefixItems -> items; exactly two elements; equivalent accepted JSON language'})
 # The library parses number syntax, but does not enforce numerical bounds.
 for key in ['minimum','maximum']:
  value=schema['properties']['reported_confidence'].pop(key)
  changes.append({'path':'/properties/reported_confidence/'+key,'value':value,'status':'UNENFORCED_POSTVALIDATED'})
 return schema,changes

def build_data(tokenizer,eos):
 # Preserve the official integration's boundary-aware full-sequence decoder semantics.
 token_0=tokenizer.encode('0')[-1];special=set(tokenizer.all_special_ids);excluded=special|set(eos);regular=[]
 for token in range(len(tokenizer)):
  if token in excluded:continue
  after=tokenizer.decode([token_0,token])[1:];single=tokenizer.decode([token])
  regular.append((token,after,len(after)>len(single)))
 def decode(tokens):return tokenizer.decode(tokens).rstrip('�')
 data=TokenEnforcerTokenizerData(regular,decode,list(eos),False,len(tokenizer))
 old_ids=set(range(len(tokenizer)))-special;new_ids={row[0] for row in regular}
 assert old_ids-new_ids==set(eos)-special and not new_ids-old_ids
 data.r493_evidence={'all_special_ids':sorted(special),'original_eos':list(eos),'new_excluded_ids':sorted(set(eos)-special),'new_excluded_tokens':{str(i):tokenizer.convert_ids_to_tokens(i) for i in set(eos)-special},'regular_tokens':len(regular),'regular_tuple_sha256':__import__('hashlib').sha256(json.dumps(regular,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),'difference_exactly_eos_minus_special':True}
 return data

class PrefixConstraint:
 def __init__(self,data,schema,prompt_ids):
  self.prefix=list(prompt_ids);self.eos=list(data.eos_token_id)
  old_parser=JsonSchemaParser(copy.deepcopy(schema))
  parser=JsonSchemaParser(copy.deepcopy(schema),config=CharacterLevelParserConfig(alphabet=data.tokenizer_alphabet))
  assert parser.context.alphabet_without_quotes==data.tokenizer_alphabet.replace('"','')
  def facts(alphabet):return {'length':len(alphabet),'sha256':__import__('hashlib').sha256(alphabet.encode()).hexdigest(),'红色方块_membership':{c:c in alphabet for c in '红色方块'}}
  self.alphabetfacts={'old_config':facts(old_parser.config.alphabet),'old_context':facts(old_parser.context.alphabet_without_quotes),'new_config':facts(parser.config.alphabet),'new_context':facts(parser.context.alphabet_without_quotes),'tokenizer_alphabet':facts(data.tokenizer_alphabet),'exact_context_matches_tokenizer_without_quote':True}
  self.enforcer=TokenEnforcer(data,parser)
  self.steps=[];self.elapsed_s=0.0;self.last_length=-1
 def allowed(self,full_ids):
  start=time.perf_counter()
  if full_ids[:len(self.prefix)]!=self.prefix:raise ValueError('prompt prefix changed')
  suffix=full_ids[len(self.prefix):]
  enforcer=self.enforcer
  # Initialize at the empty generation suffix. Never send image/prompt tokens to the parser.
  if not enforcer.prefix_states:
   if suffix:raise ValueError('first callback must precede generation')
  elif tuple(suffix) not in enforcer.prefix_states and tuple(suffix[:-1]) not in enforcer.prefix_states:
   raise ValueError('nonsequential uncached suffix')
  allowed=enforcer.get_allowed_tokens(suffix).allowed_tokens
  state=enforcer.prefix_states[tuple(suffix)]
  can_end=state.parser.can_end()
  eos_present=[token for token in self.eos if token in allowed]
  if not allowed or bool(eos_present)!=can_end or (can_end and len(eos_present)!=len(self.eos)):
   raise ValueError('empty allowlist or premature/missing original EOS; no fallback')
  elapsed=time.perf_counter()-start;self.elapsed_s+=elapsed
  self.steps.append({'suffix_tokens':len(suffix),'allowed_count':len(allowed),'can_end':can_end,'eos_allowed':eos_present,'callback_s':elapsed})
  return allowed
 def __call__(self,batch_id,sent):
  if batch_id!=0:raise ValueError('only batch1/beam1 registered')
  return self.allowed(sent.tolist())
 def evidence(self):
  return {'implementation':'lm-format-enforcer 0.11.3 backend-agnostic TokenEnforcer; official tokenizer-data algorithm; explicit suffix guard','calls':len(self.steps),'callback_s':self.elapsed_s,'steps':self.steps,'prompt_tokens':len(self.prefix),'eos_ids':self.eos,'fallback':'FORBIDDEN','state_isolation':'new parser and enforcer per request'}
