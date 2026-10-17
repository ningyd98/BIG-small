import hashlib,json,os,subprocess,sys,tempfile
from datetime import UTC,datetime
from pathlib import Path
r=Path(__file__).resolve().parent
name=sys.argv[1]
plan=json.loads((r.parent/"plan.json").read_text())
cmds={"red":[".venv/bin/python","-m","pytest","-q","tests/test_operational_windows.py"],"green":[".venv/bin/python","-m","pytest","-q","tests/test_operational_windows.py","tests/test_operational_time_v1.py"],"ruff":[".venv/bin/python","-m","ruff","check",*plan["owned_paths"]],"format_check":[".venv/bin/python","-m","ruff","format","--check",*plan["new_paths"]]}
q=r/name;q.mkdir(exist_ok=False)
argv=cmds[name]
if name in {"red","green"}:
 temp=tempfile.mkdtemp(prefix="p5-r100-"+name+"-")
 argv += ["--basetemp",temp,"--junitxml",str(q/"junit.xml")]
else:temp=None
start={"name":name,"argv":argv,"cwd":str(Path.cwd()),"start_utc":datetime.now(UTC).isoformat(),"temp":temp,"env":{"PYTHONDONTWRITEBYTECODE":"1"}}
(q/"command-start.json").write_text(json.dumps(start,indent=2)+"\n")
with (q/"stdout.txt").open("wb") as out,(q/"stderr.txt").open("wb") as err:
 child=subprocess.Popen(argv,stdout=out,stderr=err,env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"})
 code=child.wait()
result={**start,"end_utc":datetime.now(UTC).isoformat(),"exit_code":code}
for f in [q/"stdout.txt",q/"stderr.txt"]:result[f.name]={"bytes":f.stat().st_size,"sha256":hashlib.sha256(f.read_bytes()).hexdigest()}
(q/"command-result.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result,indent=2))
sys.exit(code)
