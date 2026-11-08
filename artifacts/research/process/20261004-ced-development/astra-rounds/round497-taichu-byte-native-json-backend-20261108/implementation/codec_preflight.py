"""Exercise actual pre-generation config evidence without loading model weights."""
import json,sys,hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent.parent;ROOT=HERE.parents[5];OLD=HERE.parent/'round486-taichu-no-think-best-profile-20261108'
sys.path.insert(0,str(OLD/'implementation'))
from experiment_r489 import CACHE,base_versions,kernel_bindings
from evidence_codec_r488 import write_evidence,normalize
from r478_adapter import prepare
from transformers import CompressedTensorsConfig,GenerationConfig
import torch,importlib,importlib.metadata as md
model_class=None
try:
 config,model_class,original,adapter=prepare()
 quantization=CompressedTensorsConfig.from_dict(config.quantization_config,use_optimized_inference=True,dequantize=False)
 generation=GenerationConfig.from_pretrained(str(CACHE),local_files_only=True)
 data={'auto_config':config.to_dict(),'compressed_tensors_config':quantization.to_dict(),'generation_config':generation.to_dict(),'torch_version':torch.__version__,'adapter':adapter,'ignore_patterns':model_class._keys_to_ignore_on_load_unexpected,'historical_loading_info':json.loads((CACHE/'actual/round486/run-fla-r489/loading-info.json').read_text()),'schema':json.loads((HERE.parent/'round491-taichu-constrained-json-20261108/diagnostic/visual-decision-schema.json').read_text()),'state':{'kernel_counts':{},'requests':[],'model_loads':0,'generation_calls':0}}
 write_evidence(HERE/'codec-config-dry-run.json',data)
 failures=[]
 for name,value in [('unknown',object()),('nonfinite',float('nan'))]:
  try:json.dumps(normalize(value),allow_nan=False)
  except (TypeError,ValueError):failures.append(name)
 assert failures==['unknown','nonfinite']
 cycle=[];cycle.append(cycle)
 try:normalize(cycle)
 except ValueError:failures.append('cycle')
 assert len(failures)==3
 modules={}
 for name in ['torch','transformers','compressed_tensors','fla','llguidance']:
  m=importlib.import_module(name);f=Path(m.__file__).resolve();modules[name]={'file':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
 result={'status':'PASS','actual_configs_recorded':True,'rejects_unknown_nonfinite_cycle':failures,'base68':base_versions(),'modules':modules,'kernel_bindings':kernel_bindings()[1],'scope':'NO_MODEL_LOAD_NO_GENERATION','versions':{n:md.version(n) for n in ['torch','transformers','compressed-tensors','flash-linear-attention','fla-core','llguidance']}}
 write_evidence(HERE/'codec-preflight.json',result);print('CODEC_PREFLIGHT_PASS',flush=True)
finally:
 if model_class is not None:model_class._keys_to_ignore_on_load_unexpected=original
