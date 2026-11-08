"""Bounded, metadata-only deployment of already verified persistence software."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pwd
import select
import signal
import sqlite3
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

WORK = Path(__file__).parent
REPO = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
DRAFT = WORK/'round493-persistent-key-live-transition-20261108'
PLAN = json.loads((DRAFT/'plan.json').read_text())
OUT = REPO/PLAN['canonical_directory']
EXECUTION = OUT/'execution'
EXPECTED = set(PLAN['expected_profile_ids'])
ACTIVE = PLAN['active_profile_id']
DB = REPO/'data/model_control.db'
MODULE = 'cloud_edge_robot_arm.cloud.api.dev_dashboard_app:app'
PROFILE_FIELDS = ('profile_id','display_name','provider_kind','base_url','chat_completions_path',
    'model_name','temperature','max_tokens','timeout_seconds','max_retries','json_mode','enabled',
    'active','endpoint_hash','config_version','created_at','updated_at','secret_updated_at')
RUNTIME_FIELDS = ('active_profile_id','active_provider','active_model','endpoint_hash','config_version')

class Stop(Exception):
    pass

def require(condition, code):
    if not condition:
        raise Stop(code)

def save(name, value):
    path = EXECUTION/name
    with path.open('x') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2)
        stream.write('\n')

def verify_pins():
    for pin in PLAN['input_pins']:
        require(hashlib.sha256((REPO/pin['path']).read_bytes()).hexdigest() == pin['sha256'], 'source_pin_drift')
    review = json.loads((REPO/'artifacts/research/process/20261004-ced-development/astra-rounds/round492-persistent-key-service-transition-20261108/review/source-pins.json').read_text())
    for pin in review['files']:
        require(hashlib.sha256((REPO/pin['path']).read_bytes()).hexdigest() == pin['sha256'],'review_pin_drift')

def identity(pid, ticks=None, frontend=False):
    root = Path('/proc')/str(pid)
    fields = (root/'stat').read_text().rsplit(')',1)[1].split()
    start = int(fields[19])
    require(fields[0] != 'Z','process_is_zombie')
    require(root.stat().st_uid == os.geteuid() == 1000,'process_owner_mismatch')
    require(ticks is None or start == ticks,'process_starttime_mismatch')
    require(Path(os.readlink(root/'cwd')) == (REPO/'dashboard' if frontend else REPO),'process_cwd_mismatch')
    with (root/'cmdline').open('rb') as stream:
        raw = stream.read(4097)
    require(len(raw) <= 4096,'argv_outside_known_contract')
    args = raw.rstrip(b'\0').decode().split('\0')
    if frontend:
        require(Path(os.readlink(root/'exe')).name == 'node' and any('vite' in item for item in args[1:3]),'frontend_identity_mismatch')
    else:
        require(len(args) in (8,10) and args[1:4] == ['-m','uvicorn',MODULE], 'backend_module_mismatch')
        require(args[4:8] == ['--host','127.0.0.1','--port','8000'],'backend_bind_mismatch')
        # The executable is argv[0]; command may have a log-level option or a
        # final uvicorn flag. Reject anything not already known and nonsecret.
        tail = args[8:]
        require(tail in ([],['--log-level','info']),'backend_extra_args')
    return {'pid':pid,'starttime_ticks':start,'uid':os.geteuid(),'cwd':str(REPO/'dashboard' if frontend else REPO), 'kind':'Vite' if frontend else MODULE}

def listeners(port):
    found=[]
    for table in ('tcp','tcp6'):
        for line in (Path('/proc/net')/table).read_text().splitlines()[1:]:
            row=line.split()
            address, rawport = row[1].split(':')
            if int(rawport,16)==port and row[3]=='0A':
                found.append((table,address,row[9]))
    return found

def require_listener(pid,port):
    bound=listeners(port)
    require(len(bound)==1 and bound[0][0]=='tcp' and bound[0][1]=='0100007F','listener_bind_mismatch')
    inodes=set()
    for fd in (Path('/proc')/str(pid)/'fd').iterdir():
        try:
            target=os.readlink(fd)
        except FileNotFoundError:
            continue
        if target.startswith('socket:['):
            inodes.add(target[8:-1])
    require(bound[0][2] in inodes,'listener_owner_mismatch')

def get_json(path,timeout=5):
    with urllib.request.urlopen('http://127.0.0.1:8000'+path,timeout=timeout) as response:
        require(response.status==200,'endpoint_status_mismatch')
        data=response.read(1024*1024+1)
    require(len(data)<=1024*1024,'endpoint_oversize')
    return json.loads(data)

def snapshot(*,known_healthy=False):
    health={'status':'ok'} if known_healthy else get_json('/health')
    require(health.get('status')=='ok','health_not_ok')
    profiles=get_json('/api/v1/model-control/profiles')
    runtime=get_json('/api/v1/model-control/runtime')
    capabilities=get_json('/api/v1/model-control/capabilities')
    require({p['profile_id'] for p in profiles}==EXPECTED and len(profiles)==3,'profile_id_mismatch')
    require(runtime['active_profile_id']==ACTIVE,'active_profile_mismatch')
    safe=[]
    for profile in profiles:
        require(profile.get('api_key') is None,'write_only_invariant_failed')
        item={key:profile.get(key) for key in PROFILE_FIELDS}
        url=profile.get('base_url','')
        parsed=urllib.parse.urlsplit(url)
        item['base_url_sha256']=hashlib.sha256(url.encode()).hexdigest()
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            host=parsed.hostname or ''
            if parsed.port: host+=':'+str(parsed.port)
            item['base_url']=urllib.parse.urlunsplit((parsed.scheme,host,parsed.path,'',''))
        item['secret_present']=profile['secret_present']
        item['secret_store_kind']=profile['secret_store_kind']
        safe.append(item)
    return {'health':{'status':health['status']},'profiles':sorted(safe,key=lambda p:p['profile_id']),
        'runtime':{key:runtime.get(key) for key in RUNTIME_FIELDS},
        'secret_store_modes':capabilities.get('secret_store_modes',[])}

def configuration(state):
    return {'profiles':[{k:v for k,v in p.items() if k not in {'secret_present','secret_store_kind'}} for p in state['profiles']], 'runtime':state['runtime']}

def launch_environment():
    account_home=Path(pwd.getpwuid(os.geteuid()).pw_dir)
    require(account_home==Path('/home/ningyd') and Path(os.environ.get('HOME',''))==account_home,'account_home_mismatch')
    xdg=os.environ.get('XDG_DATA_HOME','')
    base=Path(xdg) if xdg else account_home/'.local/share'
    require(base.is_absolute() and not str(base).startswith(('/tmp/','/var/tmp/')),'unstable_user_data_base')
    namespace=hashlib.sha256(os.path.abspath(os.fspath(DB)).encode()).hexdigest()
    require(namespace==PLAN['launch']['default_namespace'],'namespace_mismatch')
    directory=base/'BIGsmall/model-control-secrets'/namespace
    current=Path('/')
    for part in directory.parts[1:]:
        current=current/part
        try: info=current.lstat()
        except FileNotFoundError: break
        require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),'unsafe_user_data_component')
        require(info.st_uid in {0,os.geteuid()} and not stat.S_IMODE(info.st_mode)&0o022,'unsafe_user_data_permissions')
        require(current!=directory,'unexpected_existing_vault_metadata')
    names=('HOME','PATH','LANG','LC_ALL','LC_CTYPE','TZ')
    environment={name:os.environ[name] for name in names if name in os.environ}
    environment.update({key:value for key,value in PLAN['launch']['environment'].items() if key!='HOME'})
    if xdg: environment['XDG_DATA_HOME']=xdg
    contract={'argv':PLAN['launch']['argv'],'cwd':str(REPO),
        'environment':{name:environment[name] for name in PLAN['launch']['environment']},
        'xdg_data_home':xdg or None,'selected_data_base':str(base),'namespace':namespace,
        'secret_directory_override':False,'paid_calls':False}
    return environment,contract

def metadata_db():
    info=DB.lstat()
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),'database_not_regular')
    with sqlite3.connect(DB.as_uri()+'?mode=ro',uri=True) as connection:
        connection.execute('PRAGMA query_only=ON')
        ids={row[0] for row in connection.execute('SELECT profile_id FROM model_provider_profiles')}
        row=connection.execute("SELECT value FROM model_runtime_state WHERE key='active_profile_id'").fetchone()
    require(ids==EXPECTED and row is not None and row[0]==ACTIVE,'database_identity_mismatch')
    return {'path':str(DB),'profile_ids':sorted(ids),'active_profile_id':row[0],'scope':'read-only IDs only'}

def stop_process(state):
    pid=state['pid']
    descriptor=os.pidfd_open(pid)
    try:
        identity(pid,state['starttime_ticks'])
        signal.pidfd_send_signal(descriptor,signal.SIGTERM)
        require(bool(select.select([descriptor],[],[],30)[0]),'backend_did_not_exit_after_sigterm')
    finally:
        os.close(descriptor)

def preflight():
    verify_pins()
    OUT.mkdir(parents=True,exist_ok=True)
    EXECUTION.mkdir(exist_ok=True)
    for name in ('plan.md','plan.json'):
        target=OUT/name
        require(not target.exists() or target.read_bytes()==(DRAFT/name).read_bytes(),'canonical_plan_differs')
        target.write_bytes((DRAFT/name).read_bytes())
    backend=identity(300100,8283996)
    frontend=identity(159968,8153269,True)
    require_listener(backend['pid'],8000)
    require_listener(frontend['pid'],5173)
    _,contract=launch_environment()
    before=snapshot()
    db=metadata_db()
    save('preflight.json',{'backend':backend,'frontend':frontend,'db':db,'contract':contract,'before':before,'pins_verified':len(PLAN['input_pins'])})
    (EXECUTION/'operational-runner.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({'preflight_verified':True,'profile_count':3,'old_backend_pid':300100,'frontend_preserved':True,'paid_calls':False}))

def transition():
    verify_pins()
    original=json.loads((EXECUTION/'preflight.json').read_text())
    environment,contract=launch_environment()
    require(contract==original['contract'],'launch_contract_drift')
    frontend=identity(159968,8153269,True)
    require_listener(frontend['pid'],5173)
    old=identity(300100,8283996)
    require_listener(old['pid'],8000)
    require(not (EXECUTION/'new-backend-stdout.log').exists(),'transition_already_attempted')
    output_fd=os.open(EXECUTION/'new-backend-stdout.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    error_fd=os.open(EXECUTION/'new-backend-stderr.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    new=None
    started=time.monotonic()
    try:
        stop_process(old)
        require(not listeners(8000),'unexpected_listener_after_stop')
        child=subprocess.Popen(PLAN['launch']['argv'],cwd=REPO,env=environment,
            start_new_session=True,stdin=subprocess.DEVNULL,stdout=output_fd,stderr=error_fd)
        new=identity(child.pid)
        save('launched-process.json',{'backend':new,'contract':contract})
        deadline=time.monotonic()+30
        healthy=False
        for attempt in range(10):
            if time.monotonic()>=deadline or child.poll() is not None: break
            try:
                healthy=get_json('/health',timeout=2).get('status')=='ok'
            except (urllib.error.URLError,TimeoutError,ConnectionError):
                pass
            if healthy: break
            time.sleep(min(1,max(0,deadline-time.monotonic())))
        require(healthy,'new_backend_health_failed')
        require_listener(new['pid'],8000)
        after=snapshot(known_healthy=True)
        require(configuration(after)==configuration(original['before']),'nonsecret_configuration_changed')
        require(set(after['secret_store_modes'])=={'ENCRYPTED_FILE','SESSION_ONLY'},'encrypted_capability_missing')
        require(all(p['secret_store_kind']=='ENCRYPTED_FILE' and not p['secret_present'] for p in after['profiles']),'unexpected_post_transition_secret_state')
        identity(159968,8153269,True)
        require_listener(159968,5173)
        with urllib.request.urlopen('http://127.0.0.1:5173/models',timeout=5) as response:
            require(response.status==200,'frontend_unavailable')
            body=response.read(1024*1024)
            frontend_receipt={'status':response.status,'bytes':len(body),'html_sha256':hashlib.sha256(body).hexdigest()}
        save('after-state.json',after)
        result={'state':'ready_for_one_time_key_entry','software_tests_passed':108,
            'live_deployed':True,'user_key_persisted':False,'persisted_key_survives_restart':False,
            'memory_key_migrated':False,'paid_calls':False,'profile_count':3,'active_profile_id':ACTIVE,
            'backend':new,'frontend':frontend,'frontend_http':frontend_receipt,
            'elapsed_seconds':round(time.monotonic()-started,3)}
        save('transition-result.json',result)
        print(json.dumps(result,ensure_ascii=False))
    except Exception as error:
        stopped=False
        if new is not None:
            try:
                stop_process(new)
                stopped=True
            except Exception:
                pass
        save('transition-failure.json',{'error_class':type(error).__name__,'safe_code':str(error) if isinstance(error,Stop) else 'operational_failure','new_backend_stopped':stopped,'old_memory_key_unrecoverable_after_stop':True})
        raise
    finally:
        os.close(output_fd)
        os.close(error_fd)

if __name__=='__main__':
    try:
        {'preflight':preflight,'transition':transition}[sys.argv[1]]()
    except Exception as error:
        print(json.dumps({'operation_failed':True,'error_class':type(error).__name__,
            'safe_code':str(error) if isinstance(error,Stop) else 'operational_failure'}))
        raise SystemExit(1) from None
