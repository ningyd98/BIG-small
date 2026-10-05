import json,os,subprocess,time
from pathlib import Path
ROOT=Path('/home/ningyd/文档/ChatGPT/BIGsmall')
OUT=ROOT/'artifacts/research/process/20261004-ced-development/t9-risk-replay-module'
setup=json.loads((OUT/'frozen-overlay-setup.json').read_text())
env=dict(os.environ);env.update(setup['environment'])
results={}
for name,argv in setup['commands'].items():
    start=time.monotonic()
    with (OUT/(name+'.log')).open('wb') as log:
        process=subprocess.run(argv,cwd=setup['cwd'],env=env,stdout=log,stderr=subprocess.STDOUT)
    results[name]={'argv':argv,'exit_code':process.returncode,'elapsed_s':time.monotonic()-start,'log':name+'.log'}
    (OUT/'frozen-check-results.json').write_text(json.dumps(results,indent=2)+'\n')
    print(name,process.returncode,flush=True)
    if process.returncode:raise SystemExit(process.returncode)
