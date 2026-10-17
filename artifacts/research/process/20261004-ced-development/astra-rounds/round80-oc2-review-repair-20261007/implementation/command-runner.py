from pathlib import Path
import datetime,json,os,subprocess,sys,time
root=Path(__file__).parent
plan=json.loads((root.parent/'plan.json').read_text())
name=sys.argv[1]
spec=plan['verification'][name]
env_delta=plan['verification']['env']
receipt={'argv':spec['argv'],'cwd':str(Path.cwd()),'env':env_delta,'author':'/root/sol_t12_p1','requested_model':'gpt-6.1-sol','round':80,'runs':1,'started_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
with (root/(name+'.command-start.json')).open('x') as f:json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
t=time.monotonic()
with (root/(name+'.stdout.txt')).open('xb') as out,(root/(name+'.stderr.txt')).open('xb') as err:
 result=subprocess.run(spec['argv'],env={**os.environ,**env_delta},stdout=out,stderr=err)
receipt.update(exit_code=result.returncode,ended_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),wall_s=time.monotonic()-t)
with (root/(name+'.command-result.json')).open('x') as f:json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps(receipt,ensure_ascii=False))
