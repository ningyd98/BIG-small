from pathlib import Path
import hashlib,json
d=Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round226-p6-t2-patch-signed-line-alignment-20261015")
for name,n,h in [('source-gate.json',24701,'832cc3906327001954c8b51acfa195ef2d3378df50b77d98de3d905e1cfd785b'),('proposed-unit-preserving-preparer.py',16690,'6bc5d17b51d685a6d62bc70df9d2eef8b832d132003b26782ddf52cfb5c2347f')]:
 b=(d/name).read_bytes()
 assert len(b)==n and hashlib.sha256(b).hexdigest()==h,name
g=json.loads((d/'source-gate.json').read_bytes())
print(json.dumps({'source_and_gate_exact':True,'metadata_generation':{k:g['metadata_generation'][k] for k in ('state','used','remaining')},'transport_argv':g['metadata_generation']['transport_argv']},ensure_ascii=False))
