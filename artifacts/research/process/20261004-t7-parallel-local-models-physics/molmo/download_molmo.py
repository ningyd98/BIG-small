"""Pinned physical Molmo downloads: four independent shards, one range each.

Models are sequential, preserving Molmo2-first priority. Four total workers. An authorized bounded eight-worker trial showed no material throughput gain.
Small sources use per-blob frozen Revision, exact size and SHA256. Resumes
existing validated range pieces without replacing completed checkpoint files.
"""
from __future__ import annotations
import hashlib,importlib.util,json,sys
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import httpx
from cloud_edge_robot_arm.datasets.external.network import create_direct_transport
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[4]
POLICY={'mode':'direct','interface':'enp7s0','dns_servers':['223.5.5.5','223.6.6.6'],'allowed_hosts':['modelscope.cn','cdn-lfs-cn-1.modelscope.cn']}
spec=importlib.util.spec_from_file_location('validated_range',ROOT/'artifacts/research/process/20261004-t7-larger-vlm-candidates/range_download.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

def digest(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def model_download(name):
 repo='allenai/'+name;cache=HERE/'models'/name;cache.mkdir(parents=True,exist_ok=True)
 metadata=json.loads((HERE/f'{name}-metadata-response.json').read_text())
 rows=[r for r in metadata['Data']['Files'] if r['Type']=='blob'];records=[]
 def save(record,row):
  records.append({**record,'revision':row['Revision']})
  (HERE/f'{name}-downloads.json').write_text(json.dumps({'repo':repo,'network_policy':POLICY,
      'max_total_workers':4,'max_per_shard_range_workers':1,'files':records},indent=2)+'\n')
  print('DONE',name,row['Path'],flush=True)
 for row in [r for r in rows if not r['Path'].endswith('.safetensors')]:
  item={'name':row['Path'],'size':row['Size'],'sha256':row['Sha256']}
  url=f"https://modelscope.cn/models/{repo}/resolve/{row['Revision']}/{row['Path']}"
  dest=cache/item['name'];dest.parent.mkdir(parents=True,exist_ok=True)
  if not dest.exists():
   with httpx.Client(transport=create_direct_transport(POLICY),trust_env=False,timeout=60,follow_redirects=True) as c:
    r=c.get(url);r.raise_for_status()
    if len(r.content)!=item['size'] or hashlib.sha256(r.content).hexdigest()!=item['sha256']:raise ValueError('small file integrity failed '+url)
    dest.write_bytes(r.content)
  if dest.stat().st_size!=item['size'] or digest(dest)!=item['sha256']:raise ValueError('existing source integrity failed '+str(dest))
  save({**item,'path':str(dest),'source':url,'verified':True},row)
 weights=[r for r in rows if r['Path'].endswith('.safetensors')]
 with ThreadPoolExecutor(max_workers=4) as pool:
  futures={pool.submit(mod.download,{'name':r['Path'],'size':r['Size'],'sha256':r['Sha256']},
        cache=cache,repo=repo,revision=r['Revision'],policy=POLICY,workers=1):r for r in weights}
  for future in as_completed(futures):save(future.result(),futures[future])
 print('MODEL_VERIFIED',name,flush=True)

if __name__=='__main__':
 names=sys.argv[1:] or ['Molmo2-4B','MolmoPoint-8B']
 if any(n not in ['Molmo2-4B','MolmoPoint-8B'] for n in names):raise ValueError('unsupported model')
 for name in names:model_download(name)
