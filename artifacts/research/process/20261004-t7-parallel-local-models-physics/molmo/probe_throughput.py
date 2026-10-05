"""Bounded observational throughput probe; no network requests or GPU calls."""
import argparse,json,time
from pathlib import Path
HERE=Path(__file__).resolve().parent

def snapshot(model):
 rows=[r for r in json.loads((HERE/f'{model}-metadata-response.json').read_text())['Data']['Files'] if r['Path'].endswith('.safetensors')]
 shards={}
 for row in rows:
  file=HERE/'models'/model/row['Path']
  received=file.stat().st_size if file.exists() else sum(p.stat().st_size for p in file.parent.glob(file.name+'.range-*'))
  shards[row['Path']]={'received_bytes':received,'expected_bytes':row['Size'],'assembled':file.exists()}
 return {'time':time.time(),'monotonic':time.monotonic(),'interface_rx_bytes':int(Path('/sys/class/net/enp7s0/statistics/rx_bytes').read_text()),'shards':shards,'model_received_bytes':sum(r['received_bytes'] for r in shards.values())}

p=argparse.ArgumentParser();p.add_argument('--model',default='Molmo2-4B');p.add_argument('--seconds',type=int,default=60);p.add_argument('--range-workers-per-shard',type=int,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if not 1<=a.seconds<=120:raise ValueError('probe must be bounded to120s')
before=snapshot(a.model)
for _ in range(a.seconds):time.sleep(1)
after=snapshot(a.model);seconds=after['monotonic']-before['monotonic']
result={'model':a.model,'range_workers_per_shard':a.range_workers_per_shard,'max_shard_workers':4,'max_total_workers':4*a.range_workers_per_shard,'interval_s':seconds,'before':before,'after':after,'model_MiB_s':(after['model_received_bytes']-before['model_received_bytes'])/seconds/2**20,'interface_MiB_s':(after['interface_rx_bytes']-before['interface_rx_bytes'])/seconds/2**20,'no_other_bulk_downloads':'root reported other candidates complete before this probe; interface total may still contain other traffic'}
a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['before','after']}),flush=True)
