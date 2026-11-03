"""R415 derivative: resource parents and collision-free tail identity only."""
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
        child['id']=f"{spec['id']}-r415-tail-{index:04}"
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
        for name in spec.get('resource_dirs',[]):(Path(new)/name).mkdir(parents=True,exist_ok=True)
        run_one(child)
