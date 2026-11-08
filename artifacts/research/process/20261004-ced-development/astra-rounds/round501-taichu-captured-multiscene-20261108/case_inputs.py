"""Read only existing captures with their frozen original system/user text."""
import functools,hashlib,json,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[5];OLD=HERE.parent/'round486-taichu-no-think-best-profile-20261108'
sys.path.insert(0,str(OLD/'implementation'))
from experiment_r489 import CACHE
from evidence_codec_r488 import write_evidence
import torch

def frozen_cases():return json.loads((HERE/'diagnostic/frozen-message-inputs.json').read_text())
def process_case(processor,case):
 rgb=ROOT/case['rgb_path'];depth=ROOT/case['depth_visualization_path']
 messages=[{'role':'system','content':case['messages'][0]['content']},{'role':'user','content':[{'type':'image','image':str(rgb)},{'type':'image','image':str(depth)},{'type':'text','text':case['messages'][1]['content']}]}]
 for index,message in enumerate(case['messages']):assert hashlib.sha256(message['content'].encode()).hexdigest()==case['text_sha256'][index]
 tokenizer=processor.tokenizer;had='apply_chat_template' in tokenizer.__dict__;previous=tokenizer.__dict__.get('apply_chat_template');original=tokenizer.apply_chat_template;traces=[]
 @functools.wraps(original)
 def render(*args,**kwargs):
  assert 'enable_thinking' not in kwargs;kwargs['enable_thinking']=False;prompt=original(*args,**kwargs);traces.append({'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'assistant_suffix':prompt.rsplit('<|im_start|>assistant\n',1)[1]});return prompt
 tokenizer.apply_chat_template=render;start=time.perf_counter()
 try:features=processor.from_messages(messages,return_tensors='pt')
 finally:
  if had:tokenizer.apply_chat_template=previous
  else:del tokenizer.apply_chat_template
  assert ('apply_chat_template' in tokenizer.__dict__)==had and tokenizer.apply_chat_template==original
 assert len(traces)==1 and traces[0]['assistant_suffix']=='<think>\n\n</think>\n\n'
 tensors={}
 for name,value in features.items():
  if hasattr(value,'shape'):
   raw=value.detach().contiguous().reshape(-1).view(torch.uint8).cpu().numpy().tobytes();tensors[name]={'shape':list(value.shape),'dtype':str(value.dtype),'byte_count':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
   if name in ['num_patches','image_grid_thw','image_flags']:tensors[name]['values']=value.tolist()
  else:tensors[name]={'value':value}
 patches=features.get('num_patches');grid=features.get('image_grid_thw');assert (len(patches)==2 if patches is not None else grid is not None and len(grid)==2)
 ids=features['input_ids'][0].tolist();decoded=tokenizer.decode(ids,skip_special_tokens=False);assert decoded.endswith(traces[0]['assistant_suffix']) and len(ids)<=8192
 evidence={'case_id':case['case_id'],'thinking':False,'two_distinct_original_images':True,'input_image_order':['RGB','depth_visualization'],'image_sha256':[hashlib.sha256(p.read_bytes()).hexdigest() for p in [rgb,depth]],'input_tokens':len(ids),'input_ids_sha256':hashlib.sha256(json.dumps(ids).encode()).hexdigest(),'features':tensors,'template_calls':traces,'tokenizer_override_restored':True,'processor_s':time.perf_counter()-start,'source_grasp_profile':'mujoco_upright_box_v1','no_recalibration':True}
 return features,evidence,messages,decoded

def main():
 from transformers import AutoProcessor
 inventory=json.loads((HERE/'diagnostic/source-inventory.json').read_text())
 for case in inventory['cases']:
  for row in case['files']:
   p=ROOT/row['path'];assert p.stat().st_size==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
 processor=AutoProcessor.from_pretrained(str(CACHE),trust_remote_code=True,local_files_only=True,use_fast=False);directory=CACHE/'actual/round501/cpu-cases';directory.mkdir(parents=True,exist_ok=False);rows=[]
 for case in frozen_cases():
  features,evidence,messages,decoded=process_case(processor,case);path=directory/case['case_id'];path.mkdir();write_evidence(path/'input-ids.json',features['input_ids'][0].tolist());write_evidence(path/'native-messages.json',messages);(path/'decoded-input.txt').write_text(decoded);write_evidence(path/'processor.json',evidence);rows.append(evidence)
 write_evidence(HERE/'processor-preflight.json',{'status':'PASS','scope':'CPU_PROCESSOR_ONLY_CONDITIONAL_B_NOT_AUTHORIZED','model_loads':0,'generations':0,'cases':rows,'case_count':len(rows),'raw_directory':str(directory),'re_rendered':False,'image_resize_or_edit':False,'calibration_profile_preserved':'mujoco_upright_box_v1'})
 print('CAPTURED_PROCESSOR_PASS',len(rows),flush=True)
if __name__=='__main__':main()
