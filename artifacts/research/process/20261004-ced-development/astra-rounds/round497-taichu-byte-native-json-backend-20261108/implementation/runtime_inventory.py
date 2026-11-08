"""Observe the actual interpreter; no CUDA work or model load."""
import hashlib,importlib.metadata as md,importlib.util,json,sys
from pathlib import Path
from packaging.utils import canonicalize_name
records=[]
for d in md.distributions():
 metadata=d.read_text('METADATA')
 records.append({'name':canonicalize_name(d.metadata['Name']),'version':d.version,'location':str(Path(d.locate_file('')).resolve()),'metadata_sha256':hashlib.sha256(metadata.encode()).hexdigest()})
assert len({r['name'] for r in records})==len(records), 'duplicate canonical distribution'
modules={}
for name in ['torch','transformers','compressed_tensors','fla','llguidance','pip']:
 spec=importlib.util.find_spec(name)
 if spec is not None:
  p=Path(spec.origin).resolve()
  modules[name]={'origin':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
print(json.dumps({'executable':sys.executable,'prefix':sys.prefix,'sys_path':sys.path,'distributions':sorted(records,key=lambda r:r['name']),'modules':modules}))
