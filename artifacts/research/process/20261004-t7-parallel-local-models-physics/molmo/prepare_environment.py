"""Download exact official PyPI wheels with physical-interface TLS and SHA256."""
import hashlib,json
from pathlib import Path
import httpx
from cloud_edge_robot_arm.datasets.external.network import create_direct_transport
HERE=Path(__file__).resolve().parent
POLICY={'mode':'direct','interface':'enp7s0','dns_servers':['223.5.5.5','223.6.6.6'],'allowed_hosts':['pypi.org','files.pythonhosted.org']}
wheelhouse=HERE/'wheelhouse';wheelhouse.mkdir(exist_ok=True)
records=[]
with httpx.Client(transport=create_direct_transport(POLICY),trust_env=False,timeout=60,follow_redirects=True) as c:
 for package,version in [('transformers','4.57.1'),('tokenizers','0.22.1')]:
  resp=c.get(f'https://pypi.org/pypi/{package}/{version}/json');resp.raise_for_status();metadata=resp.json()
  (HERE/f'{package}-{version}-pypi.json').write_text(json.dumps(metadata,indent=2)+'\n')
  candidates=[f for f in metadata['urls'] if f['filename'].endswith('py3-none-any.whl') or ('manylinux' in f['filename'] and 'x86_64' in f['filename'] and 'cp39-abi3' in f['filename'])]
  if len(candidates)!=1:raise ValueError([f['filename'] for f in candidates])
  item=candidates[0];path=wheelhouse/item['filename'];expected=item['digests']['sha256']
  if not path.exists():
   resp=c.get(item['url']);resp.raise_for_status()
   if len(resp.content)!=item['size'] or hashlib.sha256(resp.content).hexdigest()!=expected:raise ValueError('wheel integrity failure')
   path.write_bytes(resp.content)
  if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('wheel integrity failure')
  records.append({'package':package,'version':version,'filename':item['filename'],'size':item['size'],'sha256':expected,'url':item['url'],'verified':True})
  print('VERIFIED_WHEEL',item['filename'],expected,flush=True)
(HERE/'dependency-downloads.json').write_text(json.dumps({'network_policy':POLICY,'wheels':records},indent=2)+'\n')
