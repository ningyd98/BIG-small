"""R501: one request per frozen existing case, reusing the resident model."""
import hashlib,json,signal,time
from datetime import datetime
from pathlib import Path
import torch
from byte_decoder_r500 import PrefixConstraint
from experiment_r489 import CACHE,ROOT,save
HERE=Path(__file__).resolve().parent.parent

def run_multiscene(model,processor,decoder_data,inventory,counts,bindings,authorization):
 import sys
 auth=json.loads(authorization.read_text());r501=ROOT/auth['round_path']
 for row in auth['frozen_files']:
  p=ROOT/row['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],p
 plan=json.loads((r501/'plan.json').read_text())
 for row in plan['input_sha256']:
  p=ROOT/row['path'];assert p.stat().st_size==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],p
 end=datetime.fromisoformat('2026-11-08T16:09:00+00:00').timestamp();assert end-time.time()>=auth['estimated_seconds'],'B_NOT_RUN_TIME'
 sys.path.insert(0,str(r501));from case_inputs import frozen_cases,process_case
 gate={row['case_id']:row for row in json.loads((r501/'processor-preflight.json').read_text())['cases']}
 raw=CACHE/'actual/round501/generation';raw.mkdir(parents=True,exist_ok=False);state={'status':'STARTED','actual_requests':[],'model_loads':0,'generation_calls':0,'original_model_reused':True,'formal_acceptance':'NOT_PERFORMED','spatial_3D_error':'NOT_MEASURED','P90_3D_error':'NOT_MEASURED','source_profile':'mujoco_upright_box_v1'}
 try:
  for index,case in enumerate(frozen_cases(),1):
   if time.time()>=end:state['status']='PARTIAL_TIME';break
   signal.alarm(max(1,min(180,int(end-time.time()))));directory=raw/case['case_id'];directory.mkdir();start=time.perf_counter()
   features,evidence,messages,decoded=process_case(processor,case);expected=gate[case['case_id']]
   for name in ['features','input_ids_sha256','image_sha256','template_calls']:assert evidence[name]==expected[name],(case['case_id'],name)
   save(directory/'processor.json',evidence);save(directory/'input-token-ids.json',features['input_ids'].tolist());save(directory/'native-messages.json',messages);(directory/'decoded-input.txt').write_text(decoded)
   callback=PrefixConstraint(decoder_data,features['input_ids'][0].tolist());features=features.to('cuda:0');length=features['input_ids'].shape[-1];before=counts.copy();torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();generation_start=time.perf_counter();state['generation_calls']+=1
   with torch.inference_mode():output=model.generate(**features,do_sample=False,max_new_tokens=512,num_beams=1,use_cache=True,return_dict_in_generate=False,output_scores=False,prefix_allowed_tokens_fn=callback)
   torch.cuda.synchronize();generation_s=time.perf_counter()-generation_start;ids=output[0,length:].tolist();response=processor.tokenizer.decode(ids,skip_special_tokens=True);special=processor.tokenizer.decode(ids,skip_special_tokens=False)
   (directory/'raw-response.txt').write_text(response);(directory/'raw-response-with-special-tokens.txt').write_text(special);save(directory/'output-token-ids.json',ids);detail=callback.evidence();detail.update(callback.verify_output(ids));save(directory/'constraint.json',detail)
   loaded=inventory();preserved=loaded['all_parameters_cuda'] and len(loaded['fp8_layers'])==248 and all('float8' in r['dtype'] for r in loaded['fp8_layers']);assert preserved
   row={'index':index,'case_id':case['case_id'],'status':'COMPLETED','raw_directory':str(directory),'input_tokens':length,'output_tokens':len(ids),'generation_s':generation_s,'end_to_end_s':time.perf_counter()-start,'constraint_callback_s':callback.elapsed_s,'raw_response_sha256':hashlib.sha256(response.encode()).hexdigest(),'ended_with_eos':bool(ids and ids[-1] in decoder_data.eos),'reached_token_cap':len(ids)==512,'fp8_weights_preserved':preserved,'torch_peak_allocated_bytes':torch.cuda.max_memory_allocated(),'torch_peak_reserved_bytes':torch.cuda.max_memory_reserved(),'kernel_call_counts':{name:counts[name]-before[name] for name in bindings},'ttft':'NOT_MEASURED'}
   save(directory/'attempt.json',row);state['actual_requests'].append(row);signal.alarm(0);print('B_REQUEST_COMPLETED',index,case['case_id'],len(ids),round(generation_s,3),flush=True)
  else:state['status']='SIXTEEN_REQUESTS_COMPLETED'
 except Exception as error:
  import traceback
  state.update(status='PARTIAL_RUNTIME_ERROR',error=str(error),traceback=traceback.format_exc())
 finally:
  signal.alarm(0);state['finished_at']=datetime.now().isoformat();save(r501/'run-stage-b.json',state);save(raw/'run-result.json',state)
 return state
