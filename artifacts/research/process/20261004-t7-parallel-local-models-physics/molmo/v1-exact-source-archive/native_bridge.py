"""Offline research-native Molmo runner. GPU inference requires a root lease.

Reads observation-transport.json only. Never reads initial-truth, masks, scene
labels or offline scoring assets. Native localization is a distinct method
(two calls); optional complete-contract evidence is a third free-decoding call.
"""
from __future__ import annotations
import argparse,base64,hashlib,io,json,os,sys,time,re,traceback
sys.dont_write_bytecode=True
from pathlib import Path
from PIL import Image
from native_adapter import (NativeProtocolError,parse_molmo2,convert_molmopoint,
                            localization_result,build_visual_decision,task_metrics)
HERE=Path(__file__).resolve().parent
SNAPSHOT=HERE.parent/'source-snapshot'
sys.path.insert(0,str(SNAPSHOT/'src'))
os.environ['HF_HOME']=str(HERE/'hf-cache')
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'

_METHOD='molmo.native.rgbd.two_localization_calls.v1'
_EVIDENCE_PROMPT=(
 'Inspect image 1 RGB and image 2 aligned depth for the task. Return only a JSON object with exactly '
 'target_label (your observed object description), target_present (boolean), destination_present '
 '(boolean), reported_confidence (your own uncertainty estimate from 0 to 1), observed_scene '
 '(your observed scene description), skills (your action sequence). Do not invent an unseen object. '
 'For visible and certain pick-and-place tasks skills must be '
 '["HOME","MOVE_ABOVE","APPROACH","GRASP","LIFT","MOVE_TO_REGION","PLACE","RELEASE","RETREAT","HOME"]. '
 'If uncertain or either requested item is absent, use skills [].')

def require_gpu_lease(lease):
    if not isinstance(lease,str) or not lease.strip():
        raise ValueError('GPU inference requires the explicit active lease supplied by root')

def build_messages(instruction,observation,role):
    if role=='target':
        query=('Point to the visible top-center of the object requested to be picked up in the task '
               'instruction. Select only the requested object, only in image 1. If that object is '
               'not visible, return exactly ABSENT and no points.')
    elif role=='destination':
        query=('Point to the visible interior of the destination requested in the task instruction. '
               'Select only the requested destination, only in image 1. If that destination is not '
               'visible, return exactly ABSENT and no points.')
    elif role=='evidence':query=_EVIDENCE_PROMPT
    else:raise ValueError('unknown query role')
    text=('Image 1 is RGB. Image 2 is aligned depth '
          'for spatial context. Ground only in RGB image 1. '+query+'\nTask instruction: '+instruction)
    rgb=Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64,validate=True))).convert('RGB')
    depth=Image.open(io.BytesIO(base64.b64decode(observation.depth_png_base64(),validate=True))).convert('RGB')
    return [{'role':'user','content':[{'type':'text','text':text},
             {'type':'image','image':rgb},{'type':'image','image':depth}]}]

def _jsonable(value):
    if isinstance(value,dict):return {str(k):_jsonable(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [_jsonable(v) for v in value]
    if hasattr(value,'tolist'):return _jsonable(value.tolist())
    return value

def _digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def verify_sources(name,weights=False):
    metadata=json.loads((HERE/f'{name}-metadata-response.json').read_text())
    rows=[r for r in metadata['Data']['Files'] if r['Type']=='blob' and
          (weights or not r['Path'].endswith('.safetensors'))]
    for row in rows:
        file=HERE/'models'/name/row['Path']
        if not file.exists():raise FileNotFoundError('Pinned checkpoint is not ready: '+str(file))
        if file.stat().st_size!=row['Size'] or _digest(file)!=row['Sha256']:
            raise ValueError('pinned source integrity mismatch: '+str(file))
    return {'metadata_sha256':_digest(HERE/f'{name}-metadata-response.json'),
            'files_verified':len(rows),'weights_verified':weights,
            'model_source_hashes':{r['Path']:r['Sha256'] for r in rows if r['Path'].endswith('.py')}}

class NativeMolmo:
    def __init__(self,name,*,gpu_lease):
        require_gpu_lease(gpu_lease)
        self.name=name;self.source=verify_sources(name,weights=True)
        import torch
        from transformers import AutoProcessor,AutoModelForImageTextToText,BitsAndBytesConfig
        self.torch=torch
        path=str(HERE/'models'/name)
        self.processor=AutoProcessor.from_pretrained(path,trust_remote_code=True,local_files_only=True,
                                                     use_fast=False,padding_side='left')
        kwargs={'trust_remote_code':True,'local_files_only':True,'device_map':{'':0},
                'dtype':torch.bfloat16,'attn_implementation':'sdpa'}
        if name=='MolmoPoint-8B':
            kwargs['quantization_config']=BitsAndBytesConfig(load_in_8bit=True,llm_int8_threshold=6.0,
                                                            llm_int8_skip_modules=['lm_head'])
        started=time.perf_counter()
        self.model=AutoModelForImageTextToText.from_pretrained(path,**kwargs).eval()
        self.load_seconds=time.perf_counter()-started
        self.gpu_lease=gpu_lease
        self.precision='BF16' if name=='Molmo2-4B' else 'bitsandbytes INT8 linear + BF16 remaining'

    def call(self,instruction,observation,role,*,max_new_tokens=160,on_generated=None):
        torch=self.torch;messages=build_messages(instruction,observation,role)
        kwargs={'return_pointing_metadata':True} if self.name=='MolmoPoint-8B' else {}
        started=time.perf_counter()
        inputs=self.processor.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,
                  return_tensors='pt',return_dict=True,padding=True,**kwargs)
        metadata=inputs.pop('metadata',None)
        cpu_shapes={k:list(v.shape) for k,v in inputs.items()}
        inputs={k:v.to(self.model.device) for k,v in inputs.items()}
        gen_kwargs={'max_new_tokens':max_new_tokens,'do_sample':False,'num_beams':1,'use_cache':True}
        if self.name=='MolmoPoint-8B':
            gen_kwargs['logits_processor']=self.model.build_logit_processor_from_inputs(inputs)
        torch.cuda.synchronize();torch.cuda.reset_peak_memory_stats()
        infer_started=time.perf_counter()
        with torch.inference_mode(),torch.autocast('cuda',dtype=torch.bfloat16):
            output=self.model.generate(**inputs,**gen_kwargs)
        torch.cuda.synchronize()
        generated=output[:,inputs['input_ids'].shape[1]:]
        token_ids=generated[0].tolist()
        raw=self.processor.post_process_image_text_to_text(generated,skip_special_tokens=False,
                              clean_up_tokenization_spaces=False)[0]
        record={'role':role,'input_images':actual_image_evidence(messages,observation),'prompt_text':messages[0]['content'][0]['text'],
                'raw_text':raw,'raw_token_ids':token_ids,'input_token_count':inputs['input_ids'].shape[1],
                'output_token_count':len(token_ids),'processor_shapes':cpu_shapes,
                'latency_s':time.perf_counter()-started,'inference_s':time.perf_counter()-infer_started,
                'max_memory_allocated_bytes':torch.cuda.max_memory_allocated(),
                'max_memory_reserved_bytes':torch.cuda.max_memory_reserved(),
                'metadata':_jsonable(metadata),'generation':{'max_new_tokens':max_new_tokens,'do_sample':False,
                  'num_beams':1,'native_logits_processor':self.name=='MolmoPoint-8B'},
                'cloud_invoice_cny':0,'local_energy_cost_cny':None}
        if on_generated is not None:on_generated(record)
        if role=='evidence':
            # Free generation only. No JSON schema constraint interferes with grounding tokens.
            clean=raw.strip()
            for terminal in ('<|im_end|>','<|endoftext|>'):
                if clean.endswith(terminal):clean=clean[:-len(terminal)].strip()
            try:record['evidence']=json.loads(clean)
            except json.JSONDecodeError as exc:record['evidence_error']=str(exc)
        else:
            try:
                if self.name=='MolmoPoint-8B':
                    decoded=self.model.extract_image_points(raw,metadata['token_pooling'],
                                     metadata['subpatch_mapping'],metadata['image_sizes'])
                    record['native_decoded_pixels']=_jsonable(decoded)
                    points=convert_molmopoint(decoded,metadata['image_sizes'])
                else:points=parse_molmo2(raw,2)
                record['localization']=localization_result(raw,points,token_ids)
            except (NativeProtocolError,ValueError,IndexError) as exc:
                record['localization']={'status':'unavailable','point':None,'raw_text':raw,
                        'raw_token_ids':token_ids,'error':str(exc),'confidence':None}
        return record

    def screen(self,instruction,observation,*,full_contract=False,journal=None,case_key='single'):
        task_started=time.perf_counter()
        def invoke(role,max_new_tokens=160):
            key=case_key+'.'+role
            messages=build_messages(instruction,observation,role)
            started={'role':role,'input_images':actual_image_evidence(messages,observation),
                     'prompt_text':messages[0]['content'][0]['text'],'max_new_tokens':max_new_tokens}
            generated=(lambda record:journal.record(key,'generated',record)) if journal else None
            return run_recorded_call(lambda:self.call(instruction,observation,role,
                       max_new_tokens=max_new_tokens,on_generated=generated),journal,key,started)
        calls=[invoke(role) for role in ('target','destination')]
        output={'method':_METHOD,'model':self.name,'precision':self.precision,
                'source':self.source,'adapter_sha256':_digest(HERE/'native_adapter.py'),
                'bridge_sha256':_digest(HERE/'native_bridge.py'),'gpu_lease':self.gpu_lease,
                'load_seconds':self.load_seconds,'observation':observation.evidence(),
                'calls':calls,'call_count':2,'visual_decision':None,
                'execution_eligible':False,'ground_truth_used_online':False}
        if full_contract:
            evidence=invoke('evidence',256)
            calls.append(evidence);output['call_count']=3
            output['method']='molmo.native.rgbd.two_localization_plus_evidence.v1'
            try:
                decision=build_visual_decision(calls[0]['localization'],calls[1]['localization'],
                                              evidence.get('evidence'))
                from cloud_edge_robot_arm.vision.planner import VisualDecision
                output['visual_decision']=VisualDecision.model_validate(decision).model_dump(mode='json')
                output['execution_eligible']=bool(decision['skills'])
            except (NativeProtocolError,ValueError) as exc:output['contract_error']=str(exc)
        output['task_metrics']=task_metrics(calls,time.perf_counter()-task_started)
        output['vram_metric_scope']='Torch CUDA allocator only; driver/context allocations are not included'
        return output

def cpu_preflight(name,observation):
    os.environ['CUDA_VISIBLE_DEVICES']=''
    import torch,transformers,tokenizers
    from transformers import AutoConfig,AutoProcessor
    from transformers.dynamic_module_utils import get_class_from_dynamic_module
    source=verify_sources(name,weights=False);path=str(HERE/'models'/name)
    config=AutoConfig.from_pretrained(path,trust_remote_code=True,local_files_only=True)
    cls=get_class_from_dynamic_module(config.auto_map['AutoModelForImageTextToText'],path,local_files_only=True)
    processor=AutoProcessor.from_pretrained(path,trust_remote_code=True,local_files_only=True,use_fast=False)
    kwargs={'return_pointing_metadata':True} if name=='MolmoPoint-8B' else {}
    inputs=processor.apply_chat_template(build_messages('把图中的红色方块放到绿色方形目标区域。',observation,'target'),
            tokenize=True,add_generation_prompt=True,return_tensors='pt',return_dict=True,**kwargs)
    return {'status':'cpu_preflight_ok','model':name,'model_class':cls.__name__,
            'processor_class':type(processor).__name__,'torch':torch.__version__,
            'transformers':transformers.__version__,'tokenizers':tokenizers.__version__,
            'source':source,'processor_shapes':{k:list(v.shape) for k,v in inputs.items() if hasattr(v,'shape')},
            'metadata_keys':list(inputs.get('metadata',{})),
            'cuda_visible_devices':os.environ['CUDA_VISIBLE_DEVICES'],'cuda_allocated':False}

def actual_image_evidence(messages,observation):
    images=[part['image'] for message in messages for part in message['content'] if part['type']=='image']
    if len(images)!=2 or any(image.size!=(observation.width,observation.height) for image in images):
        raise ValueError('actual native input must be two registered RGB-D images')
    return {'image_count':2,'images':[{'index':i,'role':role,'size':list(image.size),
             'mode':image.mode,'decoded_rgb_pixel_sha256':hashlib.sha256(image.convert('RGB').tobytes()).hexdigest()}
             for i,(role,image) in enumerate(zip(('RGB','DEPTH'),images))],
            'observation_binding':{'frame_id':observation.frame_id,'observation_id':observation.observation_id,
                                   'checksum_sha256':observation.checksum_sha256}}

def select_cases(cases,requested):
    if not isinstance(cases,list) or not cases:raise ValueError('case allocation cannot be empty')
    ids=[c['case_id'] for c in cases]
    if any(not isinstance(case_id,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+',case_id) for case_id in ids):
        raise ValueError('unsafe case IDs')
    if len(set(ids))!=len(ids):raise ValueError('duplicate bank case IDs')
    if requested is None:return list(cases)
    if not requested:raise ValueError('requested case allocation cannot be empty')
    if len(set(requested))!=len(requested):raise ValueError('duplicate requested case IDs')
    unknown=set(requested)-set(ids)
    if unknown:raise ValueError('unknown requested case IDs: '+','.join(sorted(unknown)))
    by_id={case['case_id']:case for case in cases}
    return [by_id[case_id] for case_id in requested]

def write_exclusive_json(path,data):
    with path.open('x',encoding='utf-8') as stream:
        json.dump(_jsonable(data),stream,ensure_ascii=False,indent=2)
        stream.write('\n')

class AttemptJournal:
    """Exclusive audit files survive model/decoder failures; no synthetic token counts."""
    def __init__(self,directory,protocol_sha256):
        self.directory=directory;self.protocol_sha256=protocol_sha256
        directory.mkdir(parents=True,exist_ok=False)
    def record(self,key,phase,payload):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+',key) or phase not in ('started','generated','completed','failed'):
            raise ValueError('unsafe attempt journal key or phase')
        write_exclusive_json(self.directory/(key+'.'+phase+'.json'),{
            'protocol_sha256':self.protocol_sha256,'key':key,'phase':phase,'payload':payload})

def run_recorded_call(operation,journal,key,started_evidence):
    if journal is not None:journal.record(key,'started',started_evidence)
    started=time.perf_counter()
    try:result=operation()
    except Exception as exc:
        if journal is not None:journal.record(key,'failed',{'exception_type':type(exc).__name__,
            'error':str(exc),'traceback':traceback.format_exc(),'attempt_latency_s':time.perf_counter()-started})
        raise
    if journal is not None:journal.record(key,'completed',result)
    return result

def freeze_run_output(out,protocol,*,bank):
    if out.exists() or out.is_symlink():raise FileExistsError('output already exists: '+str(out))
    raw=json.dumps(protocol,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
    frozen={**protocol,'protocol_sha256':hashlib.sha256(raw).hexdigest()}
    if bank:
        out.mkdir(parents=True,exist_ok=False)
        protocol_path=out/'protocol.json'
    else:
        out.parent.mkdir(parents=True,exist_ok=True)
        protocol_path=out.with_name(out.name+'.protocol.json')
    write_exclusive_json(protocol_path,frozen)
    return frozen

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',choices=['Molmo2-4B','MolmoPoint-8B'],required=True)
    p.add_argument('--mode',choices=['cpu-preflight','screen'],required=True)
    p.add_argument('--observation',type=Path);p.add_argument('--instruction');p.add_argument('--bank',type=Path)
    p.add_argument('--cases',nargs='*');p.add_argument('--gpu-lease');p.add_argument('--full-contract',action='store_true')
    p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    if args.out.exists() or args.out.is_symlink():raise FileExistsError('output already exists: '+str(args.out))
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    bank=args.mode=='screen' and args.bank is not None
    manifest=None;allocation=[];bindings=[]
    if args.mode=='screen':require_gpu_lease(args.gpu_lease)
    if bank:
        manifest_bytes=(args.bank/'bank-manifest.json').read_bytes();manifest=json.loads(manifest_bytes)
        # All filter/allocation checks happen before any model class construction.
        cases=select_cases(manifest['cases'],args.cases)
        for case in cases:
            path=args.bank/'cases'/case['case_id']/'observation-transport.json'
            raw=path.read_bytes();obs=RGBDObservation.model_validate_json(raw)
            allocation.append((case['case_id'],case['instruction'],obs))
            bindings.append({'case_id':case['case_id'],'instruction':case['instruction'],
               'transport_sha256':hashlib.sha256(raw).hexdigest(),'observation':obs.evidence()})
    else:
        if args.cases is not None:raise ValueError('--cases requires bank screen mode')
        if args.observation is None:raise ValueError('single observation path is required')
        if args.mode=='screen' and not args.instruction:raise ValueError('single screen instruction is required')
        raw=args.observation.read_bytes();obs=RGBDObservation.model_validate_json(raw)
        instruction=args.instruction or '把图中的红色方块放到绿色方形目标区域。'
        allocation.append((None,instruction,obs))
        bindings.append({'case_id':None,'instruction':instruction,'transport_sha256':hashlib.sha256(raw).hexdigest(),
                         'observation':obs.evidence()})
    protocol={'mode':args.mode,'model':args.model,'method':_METHOD if not args.full_contract else
               'molmo.native.rgbd.two_localization_plus_evidence.v1',
              'precision':'BF16' if args.model=='Molmo2-4B' else 'bitsandbytes INT8 linear + BF16 remaining',
              'gpu_lease':args.gpu_lease,'planned_calls_per_task':0 if args.mode=='cpu-preflight' else 3 if args.full_contract else 2,
              'generation':{'localization_max_new_tokens':160,'evidence_max_new_tokens':256,'do_sample':False,
                            'num_beams':1,'use_cache':True,'native_logits_processor':args.model=='MolmoPoint-8B'},
              'allocation':bindings,'case_count':len(allocation),'ground_truth_used_online':False,
              'adapter_sha256':_digest(HERE/'native_adapter.py'),'bridge_sha256':_digest(HERE/'native_bridge.py'),
              'model_source_metadata_sha256':_digest(HERE/f'{args.model}-metadata-response.json'),
              'dependency_downloads_sha256':_digest(HERE/'dependency-downloads.json'),
              'environment_freeze_sha256':_digest(HERE/'environment-freeze.txt')}
    if bank:
        protocol['bank_manifest_sha256']=hashlib.sha256(manifest_bytes).hexdigest()
        protocol['source_snapshot_manifest_sha256']=manifest.get('source_snapshot_manifest_sha256')
    frozen=freeze_run_output(args.out,protocol,bank=bank)
    # Full allocation and input bindings are now immutable artifacts before inference.
    if args.mode=='cpu-preflight':
        result=cpu_preflight(args.model,allocation[0][2]);result['protocol_sha256']=frozen['protocol_sha256']
        write_exclusive_json(args.out,result);print(json.dumps(result))
    else:
        journal_directory=args.out/'attempts' if bank else args.out.with_name(args.out.name+'.attempts')
        journal=AttemptJournal(journal_directory,frozen['protocol_sha256'])
        holder={}
        def load():
            holder['model']=NativeMolmo(args.model,gpu_lease=args.gpu_lease)
            model=holder['model']
            return {'model':model.name,'source':model.source,'precision':model.precision,
                    'load_seconds':model.load_seconds,'gpu_lease':model.gpu_lease}
        run_recorded_call(load,journal,'model-load',{'model':args.model,'gpu_lease':args.gpu_lease})
        model=holder['model']
        for case_id,instruction,obs in allocation:
            result=model.screen(instruction,obs,full_contract=args.full_contract,journal=journal,case_key=case_id or 'single')
            result['protocol_sha256']=frozen['protocol_sha256']
            if bank:
                result['case_id']=case_id
                write_exclusive_json(args.out/(case_id+'.json'),result)
                print(json.dumps({'case_id':case_id,'target':result['calls'][0]['localization']['status'],
                      'destination':result['calls'][1]['localization']['status'],'execution_eligible':result['execution_eligible']}),flush=True)
            else:
                write_exclusive_json(args.out,result)
                print(json.dumps({'model':args.model,'call_count':result['call_count'],'execution_eligible':result['execution_eligible']}))

if __name__=='__main__':main()
