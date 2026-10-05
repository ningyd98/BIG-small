"""Exclusive research-run logs and nvidia driver telemetry; never terminates foreign clients."""
import argparse,json,subprocess,time,threading
from pathlib import Path
from datetime import datetime,UTC

def query(fields,kind='gpu'):
 result=subprocess.run(['nvidia-smi','--query-'+kind+'='+fields,'--format=csv,noheader,nounits'],capture_output=True,text=True)
 if result.returncode:raise RuntimeError(result.stderr)
 return [[item.strip() for item in line.split(',')] for line in result.stdout.splitlines() if line.strip()]

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--telemetry',type=Path,required=True);parser.add_argument('--log',type=Path,required=True);parser.add_argument('command',nargs=argparse.REMAINDER);args=parser.parse_args()
 command=args.command[1:] if args.command[:1]==['--'] else args.command
 if not command:raise ValueError('missing subprocess command')
 if args.telemetry.exists() or args.log.exists():raise FileExistsError('exclusive monitor output already exists')
 initial=query('pid,process_name,used_memory','compute-apps')
 if initial:raise RuntimeError('GPU is not empty before owned model launch: '+repr(initial))
 samples=[];foreign=[];errors=[];started=time.perf_counter();stop=threading.Event()
 with args.log.open('x',encoding='utf-8') as log:
  process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
  def monitor():
   while not stop.is_set():
    try:
     apps=query('pid,process_name,used_memory','compute-apps')
     sample={'elapsed_s':time.perf_counter()-started,'gpu':query('memory.used,memory.total,utilization.gpu'),'compute_apps':apps}
     samples.append(sample)
     for app in apps:
      if int(app[0])!=process.pid:foreign.append({'elapsed_s':sample['elapsed_s'],'pid':int(app[0]),'name':app[1],'memory_MiB':app[2]})
    except Exception as exc:errors.append({'elapsed_s':time.perf_counter()-started,'error':str(exc)})
    stop.wait(.5)
  worker=threading.Thread(target=monitor);worker.start();exit_code=process.wait();stop.set();worker.join()
 final_apps=query('pid,process_name,used_memory','compute-apps')
 report={'timestamp_utc':datetime.now(UTC).isoformat(),'command':command,'owned_pid':process.pid,'exit_code':exit_code,'startup_and_full_screen_wall_s':time.perf_counter()-started,
         'driver_wide_peak_memory_MiB':max((float(s['gpu'][0][0]) for s in samples),default=None),'driver_memory_scope':'whole GPU including context, display and all clients; sampled every0.5s',
         'foreign_compute_clients':foreign,'monitor_errors':errors,'initial_compute_apps':initial,'final_compute_apps':final_apps,'samples':samples}
 with args.telemetry.open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2);stream.write('\n')
 print(json.dumps({k:v for k,v in report.items() if k!='samples'}),flush=True)
 raise SystemExit(exit_code)
if __name__=='__main__':main()
