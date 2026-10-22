"""R329: one finite read of retained files; no product imports, SQL or writes."""
import ast
import base64
import hashlib
import json
import stat
from pathlib import Path

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
B = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds'
D = B / 'round319-p6-session-constructor-observer-bookkeeping-20261023'
T = B / 'round325-p6-observer-final-poll-envelope-continuation-20261023/reviews/red-acceptance-continuation-actual.json'

def digest(b):
    return hashlib.sha256(b).hexdigest()
def canon(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
def pin(p):
    p = Path(p); b = p.read_bytes()
    return {'path': str(p), 'bytes': len(b), 'sha256': digest(b)}
def load(p):
    return json.loads(Path(p).read_bytes())
ALIASES = {}
def short(p):
    p = Path(p)
    try:
        relative=p.relative_to(B); first=relative.parts[0]
        if first.startswith('round'):
            alias=first.split('-',1)[0].replace('round','R',1); ALIASES[alias]=first
            return alias+'/'+str(Path(*relative.parts[1:]))
        return str(relative)
    except ValueError: return 'ROOT/'+str(p.relative_to(ROOT))

def build():
    refs = []; refids = {}; checked = []; errors = []; historical = []
    def ref(p):
        q = pin(p); key = q['path']
        if key not in refids:
            refids[key] = len(refs)
            refs.append([short(key), q['bytes'], q['sha256']])
        return refids[key]
    manifest = load(D/'before/manifest.json')
    after = load(D/'after/manifest.json')
    old = {x['source']['path']: x for x in manifest['files'] if Path(x['source']['path']).name in ('test_operational_runtime_closure.py','test_t2_observer_lifecycle.py')}
    new = {x['source']['path']: x for x in after['files']}
    assert len(old) == len(new) == 2
    def check(q):
        path = q['path']; actual = pin(path); origin = 'live'
        if (actual['bytes'],actual['sha256']) != (q['bytes'],q['sha256']):
            assert path in old and all(q[k] == old[path]['source'][k] for k in ('path','bytes','sha256')), path
            archived = base64.b64decode(old[path]['base64'], validate=True)
            assert (len(archived),digest(archived)) == (q['bytes'],q['sha256'])
            assert all(actual[k] == new[path]['source'][k] for k in ('path','bytes','sha256'))
            assert archived == Path(old[path]['archive']['path']).read_bytes()
            assert Path(path).read_bytes() == base64.b64decode(new[path]['base64'],validate=True)
            actual = {k:q[k] for k in ('path','bytes','sha256')}; origin = 'authorized_before_archive'
            row = [short(path),q['sha256'],new[path]['source']['sha256']]
            if row not in historical: historical.append(row)
        assert all(actual[k] == q[k] for k in ('path','bytes','sha256')),path
        checked.append([path,q['bytes'],q['sha256'],origin])
        return actual
    anchors = {'plan':ref(D/'plan.json'), 'before_manifest':ref(D/'before/manifest.json'), 'after_manifest':ref(D/'after/manifest.json'), 'generation':ref(D/'implementation/observer-generation-map.json'), 'template':ref(T), 'failure':ref(D/'reviews/fresh-observer-review/batch-03-receipt.json'), 'release':ref(D/'reviews/fresh-observer-review-release.json')}
    template = load(T)['invocation']['arguments']['cmd'].split("<<'PY'\n",1)[1].rsplit('\nPY',1)[0]
    # The known metadata validator's read-only prefix; all write definitions and
    # acceptance/ledger suffix are excluded. It imports only Python stdlib.
    assert template.count('\naccept={') == 1
    prefix = template.split('\naccept={',1)[0]
    replacements = [
        ("actual['initial']['kind']=='initial'", "actual['initial'].get('kind','initial')=='initial'"),
        ("poll['kind']=='poll'", "poll.get('kind','poll')=='poll'")]
    for a,b in replacements:
        assert prefix.count(a) == 1; prefix = prefix.replace(a,b)
    tree = ast.parse(prefix)
    tree.body = [n for n in tree.body if not(isinstance(n,ast.FunctionDef) and n.name in ('save','full','check'))]
    code = compile(tree,'<R329-read-only-frozen-validator>','exec')
    runs = []
    for key in ('session_init_red','session_init_green','observer_selective_green'):
        start = len(checked)
        try:
            # KEY is selected by an exact single literal mapping before compile.
            text = prefix.replace("KEY='session_init_red';NEXT=''", "KEY="+repr(key)+";NEXT=''")
            assert prefix.count("KEY='session_init_red';NEXT=''") == 1
            tr = ast.parse(text)
            tr.body = [n for n in tr.body if not(isinstance(n,ast.FunctionDef) and n.name in ('save','full','check'))]
            ns = {'check':check}
            exec(compile(tr,'<R329-read-only-'+key+'>','exec'),ns)
            r=ns['r']; a=ns['actual']; native=ns['native']; inv=ns['inv']; O=ns['O']
            # Explicit extra linkage/pins: original validator checks values, these
            # anchor complete containers without displaying their nested contents.
            artefacts = {n:ref(O/n) for n in ('actual-tool-return.json','result.json','invocation.json','junit.xml','source-before.json','source-after.json')}
            artefacts['gate']=ref(ns['gatepath'])
            for field in ('persistent_index','cases','resource_summary','micro_cases'):
                if field in r: artefacts[field]=ref(r[field]['path'])
            native_summary=json.loads(native['output'])
            assert native_summary['command_id']==key
            assert native_summary['capture_integrity_complete']==r['capture_integrity_complete']
            assert native_summary['behavior_candidate_pass']==r['behavior_candidate_pass']
            assert native_summary['errors']==r['errors']
            # Original semantics, source/gate, mode/inode, link text, byte hashes,
            # DB/archive and sidecar presence checks all completed in prefix.
            facts={'key':key,'refs':artefacts,'native':[a['initial']['actual_tool_return']['chunk_id'],native['chunk_id'],native['exit_code'],native_summary],
                'actual_args_sha':digest(canon(a['invocation'])),'child_args_sha':digest(canon(inv['child_argv'])),'child_env_sha':digest(canon(inv['child_env'])),
                'approved_args_env_exact':True,'attempts':a['attempts'],'retries':a['retries'],'polls':len(a['polls']),
                'sourcepins':len(ns['gate']['pins']),'source_before_after_gate_equal':True,'HEAD':ns['gate']['HEAD'],'JUnit':ns['expected'],
                'regular_files_checked':ns['regular'],'DB_archive_pairs':len(r['new_databases']),'all_checks_passed':True,'checked_pin_count':len(checked)-start,
                'cleanup':r['cleanup'],'errors':r['errors'],'unobserved':r['unobserved']}
            if ns['unit']:
                facts['unit']={'micro_cases':ns['j'](r['micro_cases']['path']),'polls':0,'DB':0,'resource_summary_present':False,'basetemp':r['persistent_basetemp']}
            else:
                c=ns['c'];cb=ns['cb'];s=ns['session'];w=ns['worker'];raw=ns['raw']
                facts['semantic']={'counts':{k:v for k,v in ns['counts'].items() if k in ('allocation_attempts','initialized','cleanup_observed','never_polled_workers') or k.startswith('kind:')},'session':[s['resource_id'],s['initialized'],s['initialization_error'],s.get('constructor_outcome'),s['cleanup_observed'],s['broker_alive']],
                    'worker':w['resource_id'],'normal_poll':[ns['call'][k] for k in ('poll_id','worker_resource_id','attempted','entered','returned_normally','return_value','exception','start_sequence','entry_sequence','end_sequence')],'checks':c['checks'],
                    'callback':{k:cb[k] for k in ('session_resource_id','worker_resource_id','actual_has_sealed','closed_during_callback','broker_alive_during_callback','constructor_is_original_during_callback','constructor_delegate_is_original')},
                    'after_cleanup':c['after_cleanup_session'],'test_exit_exception':c['test_exit_exception'],
                    'constructors_hooks_methods_restored':[c['constructor_restored'],c['hooks_restored'],raw['observations']['method_restoration']],
                    'resource_copy_and_case_match':True,'worker_session_threads_identity_unique':True,
                    'prerequisite':{k:ns['pr'][k] for k in ('pid','accepted_prerequisite','exception','same_sys_modules_object_after','profile_trace_before_after_equal')},
                    'prerequisite_pin':ref(r['prerequisite']['pin']['path']), 'raw_resource_pin':ref(ns['sr']['pin']['path']), 'case_pin':ref(ns['casepin']['path'])}
            runs.append(facts)
        except Exception as exc:
            errors.append({'scope':key,'type':type(exc).__name__,'message':str(exc)[:1000],'coverage':'incomplete from first failure'})
    overlay=load(D/'historical-session-initialization-overlay.json'); anchors['overlay']=ref(D/'historical-session-initialization-overlay.json')
    rows=[]; raw_by_path={}; totals={'attempts':0,'initialized':0,'cleanup':0}; unique=set(); histories=[]
    for i,row in enumerate(overlay['rows']):
        try:
            rp=row['resource_pin'];check(rp)
            if rp['path'] not in raw_by_path:
                rr=load(rp['path']); raw_by_path[rp['path']]=rr
                resources=rr['resources'];assert len(resources)==rr['allocation_attempts']==len({x['resource_id'] for x in resources})
                totals['attempts']+=len(resources);totals['initialized']+=sum(x['initialized'] is True for x in resources);totals['cleanup']+=sum(x['cleanup_observed'] is True for x in resources)
                histories.append({'ref':ref(rp['path']),'command':row['command'],'pid':rr['pid'],'attempts':len(resources),'initialized':sum(x['initialized'] is True for x in resources),'cleanup':sum(x['cleanup_observed'] is True for x in resources)})
            rr=raw_by_path[rp['path']];byid={x['resource_id']:x for x in rr['resources']};s=row['session'];w=row['worker'];p=row['normal_poll'];threads=row['owned_threads']
            assert rr['pid']==row['pid']==s['pid']==w['pid'] and rr['nodeid']==row['nodeid']
            assert s==byid[s['resource_id']] and w==byid[w['resource_id']]
            assert sum(x==p for x in rr['worker_lifecycles'])==1
            assert s['worker_resource_id']==w['resource_id']==p['worker_resource_id']
            assert w['session_resource_ids'].count(s['resource_id'])==1 and w['poll_ids'].count(p['poll_id'])==1
            assert sum(x['kind']=='lease_session' and x['worker_resource_id']==w['resource_id'] for x in rr['resources'])==1
            assert p['attempted'] and p['entered'] and p['returned_normally'] and p['return_value'] is True and p['exception'] is None
            assert p['start_sequence']<p['entry_sequence']<p['end_sequence']
            assert w['session_observed'] and w['heartbeat_observed'] and w['cleanup_observed'] and s['cleanup_observed'] and not s['broker_alive']
            assert s['initialized'] is False and s['initialization_error']=={'type':'IncompleteConstructor','message':'actual session constructor did not seal'}
            assert len(threads)==2 and {t['kind'] for t in threads}=={'broker_thread','heartbeat_thread'}
            for t in threads:
                assert t==byid[t['resource_id']] and t['session_resource_id']==s['resource_id'] and t['worker_resource_id']==w['resource_id'] and t['cleanup_observed'] and t['alive_after_join'] is False
                link='broker_resource_ids' if t['kind']=='broker_thread' else 'heartbeat_resource_ids';assert w[link].count(t['resource_id'])==1
            pair=(rp['path'],s['resource_id']);assert pair not in unique;unique.add(pair)
            check(row['source_before']);check(row['source_after']);sb=load(row['source_before']['path']);sa=load(row['source_after']['path']);assert sb==sa
            for name,q in row['source_generation'].items():
                check(q);assert sum(x==q for x in sb['pins'])==1
            assert row['original_explicit_normal_constructor_return_trace'] is False
            rows.append([i,row['command'],ref(rp['path']),row['pid'],s['resource_id'],w['resource_id'],p['poll_id'],[t['resource_id'] for t in threads],s['initialized'],s['cleanup_observed'],s['broker_alive'],p['returned_normally'],p['return_value'],p['exception'],True,ref(row['source_before']['path']),ref(row['source_after']['path']),False])
        except Exception as exc:
            errors.append({'scope':'overlay/'+str(i),'type':type(exc).__name__,'message':str(exc)[:1000],'coverage':'incomplete'})
    assert len(overlay['rows'])==15
    if totals!={'attempts':5708,'initialized':5693,'cleanup':5708}:
        errors.append({'scope':'old_denominators','actual':totals})
    expected_facts={'allocation_attempts':5708,'recorded_initialized_true':5693,'recorded_initialized_false':15,'cleanup_observed_true':5708}
    if overlay['original_facts']!=expected_facts or overlay['historical_raw_totals']!={'attempts':5708,'recorded_initialized':5693,'cleanup_observed':5708}:
        errors.append({'scope':'overlay_original_totals','mismatch':True})
    if len(raw_by_path)!=7 or len(unique)!=15:errors.append({'scope':'overlay_uniqueness','raws':len(raw_by_path),'sessions':len(unique)})
    sections=[]; nlines=0
    for name,ranges in [('operational_lease.py',[(416,460),(913,948)]),('worker.py',[(146,180),(235,240)])]:
        path=ROOT/'src/cloud_edge_robot_arm/simulation_runtime'/name
        for row in overlay['rows']:
            assert row['source_generation'][name]==pin(path)
        source_ref=ref(path);ls=path.read_text().splitlines()
        for a,z in ranges:
            selected=ls[a-1:z]
            if name=='operational_lease.py' and a==913 and z==948 and selected[-1]=='': selected=selected[:-1]
            nlines+=len(selected)
            sections.append('SOURCE ref='+str(source_ref)+' '+name+' '+str(a)+'-'+str(a+len(selected)-1)+'\n'+'\n'.join(str(a+i)+': '+s for i,s in enumerate(selected)))
    # Do not serialize original invocation/prerequisite/resource containers.
    payload={'kind':'R319 final original read attempt4 via R329','anchors':anchors,'path_aliases':dict(sorted(ALIASES.items())),'alias_base':str(B),'ROOT':str(ROOT),'blank_line_948_omitted':True,'refs_columns':['relative_path','bytes','sha256'],'refs':refs,'runs':runs,
        'historical_RED_bindings_columns':['path','before_sha','after_sha'],'historical_RED_bindings':historical,
        'checked_pin_table_rows':len(checked),'checked_pin_table_sha256':digest(canon(checked)),
        'normal_poll_columns':['poll_id','worker_resource_id','attempted','entered','returned_normally','return_value','exception','start_sequence','entry_sequence','end_sequence'],'old7_raw_totals':histories,'old_totals':totals,
        'overlay_columns':['row','command','rawref','pid','session_id','worker_id','poll_id','thread_ids','original_initialized','cleanup','broker_alive','normal_return','return_value','exception','all_identity_copy_source_checks','source_before_ref','source_after_ref','original_explicit_return_trace'],
        'overlay15':rows,'overlay_status':overlay['status'],'inference':{'source_control_flow_only':True,'proposed_sessions':overlay['proposed_inferred_successful_sessions'],'proposed_total':overlay['proposed_interpretive_initialized_total'],'accepted_interpretation_in_original':overlay['accepted_interpretation'],'raw_changed':overlay['raw_records_changed'],'counts_overwritten':overlay['original_initialized_counts_overwritten'],'missing_old_artifacts_repaired':overlay['historical_missing_35_DB_90_sidecars_repaired'],'SIGSEGV_cause_proven':overlay['original_SIGSEGV_cause_proven'],'formal':overlay['native_or_formal_accepted']},
        'errors':errors,'coverage':'3 frozen runtime evidence and all15 overlay/7raw; full programmatic checks; original121 product source lines; no product execution. Independent verdict still required.'}
    body=json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n'+'\n\n'.join(sections)+'\n'
    header='R329 FINAL READ source_lines='+str(nlines)+' body_utf8='+str(len(body.encode()))+'\n'
    return header+body,{'source_lines':nlines,'formatted_utf8':len((header+body).encode()),'errors':errors,'refs':len(refs),'runs':len(runs),'overlay_rows':len(rows),'checked_pins':len(checked)}

if __name__=='__main__':
    text,measured=build()
    assert measured['source_lines']<=600 and measured['formatted_utf8']<=28000,measured
    print(text,end='')
