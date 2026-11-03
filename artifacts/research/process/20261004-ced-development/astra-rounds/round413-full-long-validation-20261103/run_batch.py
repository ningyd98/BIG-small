"""Execute immutable R413 stage assignments once, continuing only unstarted tails."""
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROUND=Path(__file__).resolve().parent
ROOT=Path('/home/ningyd/文档/ChatGPT/BIGsmall')
PYTHON=str(ROOT/'.venv/bin/python')

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')

def event(value):
    value['at_utc']=datetime.now(UTC).isoformat()
    with (ROUND/'progress.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(value,ensure_ascii=False)+'\n')
    print(json.dumps(value,ensure_ascii=False),flush=True)

def events(directory):
    path=directory/'pytest-events.jsonl'
    if not path.exists():return []
    return [json.loads(line) for line in path.read_text().splitlines()]

def run_one(spec):
    directory=Path(spec['directory'])
    spec_path=ROUND/'specs'/f"{spec['id']}.json"
    if not spec_path.exists():save(spec_path,spec)
    else:
        assert json.loads(spec_path.read_text())==spec
    if (directory/'invocation.json').exists() or (directory/'result.json').exists():
        raise RuntimeError('Refusing repeat: '+spec['id'])
    event({'event':'stage_start','stage_id':spec['id'],'nodes':len(spec.get('nodes',[]))})
    completed=subprocess.run([PYTHON,str(ROUND/'bounded_stage.py'),str(spec_path)],stdin=subprocess.DEVNULL)
    result_path=directory/'result.json'
    if not result_path.exists():
        event({'event':'stage_driver_unclosed','stage_id':spec['id'],'driver_returncode':completed.returncode})
        raise RuntimeError('Driver did not close terminal record; do not silently retry')
    result=json.loads(result_path.read_text())
    event({'event':'stage_end','stage_id':spec['id'],'driver_returncode':completed.returncode,
        **{k:result.get(k) for k in ['state','returncode','elapsed_s','reaped','source_drift','remaining_live']}})
    if result.get('source_drift') or result.get('remaining_live') or result.get('errors'):
        raise RuntimeError('Source/cleanup/driver error; dependent execution paused')
    return result

def execute(spec):
    if spec.get('precondition_software_only') is False:
        save(Path(spec['directory'])/'result.json',{'stage_id':spec['id'],'state':'NOT_RUN_EXTERNAL_RUNTIME',
            'launched':False,'reason':'Original external-runtime prerequisite did not establish software-only execution'})
        event({'event':'stage_not_run_external_runtime','stage_id':spec['id']})
        return
    if spec.get('requires_success'):
        parent=ROUND/'implementation'/spec['requires_success']/'result.json'
        prior=json.loads(parent.read_text()) if parent.exists() else None
        ready=bool(prior and prior.get('state')=='FINISHED' and prior.get('returncode')==0 and prior.get('reaped'))
        if spec.get('requires_files'):
            ready=ready and all(Path(p).is_file() and Path(p).stat().st_size>0 for p in spec['requires_files'])
        if not ready:
            save(Path(spec['directory'])/'result.json',{'stage_id':spec['id'],'state':'NOT_RUN_DEPENDENCY',
                'launched':False,'upstream':spec['requires_success'],'upstream_result':prior})
            event({'event':'stage_not_run_dependency','stage_id':spec['id'],'upstream':spec['requires_success']})
            return
    result=run_one(spec)
    nodes=spec.get('nodes',[])
    if not nodes or not spec.get('continue_unstarted',False):return
    try:
        recorded=events(Path(spec['directory']))
    except (OSError,json.JSONDecodeError) as error:
        event({'event':'indeterminate_events_no_continuation','stage_id':spec['id'],'error':str(error)})
        return
    if not recorded or not any(r.get('event')=='collection_finished' for r in recorded):
        event({'event':'indeterminate_collection_no_continuation','stage_id':spec['id']})
        return
    started={r['nodeid'] for r in recorded if r['event']=='started'}
    finished=any(r['event']=='finished' for r in recorded)
    if finished:return
    # No reruns: continuation includes only nodes lacking any runtest start.
    pending=[node for node in nodes if node not in started]
    save(ROUND/'continuations'/f"{spec['id']}.json",{'parent':spec['id'],'started':sorted(started),'unstarted':pending,
        'parent_result':result,'policy':'Only never-started nodes; started nodes remain final even if incomplete'})
    for index,node in enumerate(pending,1):
        child=json.loads(json.dumps(spec))
        child['id']=f"{spec['id']}-tail-{index:04}"
        child['parent_stage']=spec['id']
        child['nodes']=[node]
        child['continue_unstarted']=False
        child['timeout_s']=spec['tail_timeout_s']
        old=spec['directory'];new=str(ROUND/'implementation'/child['id'])
        child['directory']=new
        child['argv']=[arg.replace(old,new) for arg in spec['argv'] if arg not in nodes]+[node]
        child['argv']=[f"--basetemp=/tmp/bigsmall-r413-{child['id']}" if arg.startswith('--basetemp=') else arg for arg in child['argv']]
        child['env']={k:v.replace(old,new) for k,v in spec['env'].items()}
        Path(new).mkdir(parents=True,exist_ok=False)
        for name in spec.get('resource_dirs',[]):(Path(new)/name).mkdir()
        run_one(child)

if __name__=='__main__':
    lane=sys.argv[1] if len(sys.argv)>1 else 'main'
    preparation=json.loads((ROUND/'preflight/prepared.json').read_text())
    assert preparation['ready']
    assert hashlib.sha256((ROUND/'plan.json').read_bytes()).hexdigest()==preparation['plan_sha256']
    stages=json.loads((ROUND/'stages.json').read_text())
    selected=[s for s in stages if s.get('lane','main')==lane]
    assert selected
    event({'event':'batch_start','lane':lane,'stages':len(selected),'tested_commit':preparation['source_commit']})
    for spec in selected:execute(spec)
    event({'event':'batch_end','lane':lane,'stages':len(selected)})
