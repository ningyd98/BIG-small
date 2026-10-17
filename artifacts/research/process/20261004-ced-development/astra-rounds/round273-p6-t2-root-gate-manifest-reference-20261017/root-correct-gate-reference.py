"""R273 exact ROOT metadata source correction and complete before preservation."""
from pathlib import Path
import base64,difflib,hashlib,json,os,stat
D=Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round273-p6-t2-root-gate-manifest-reference-20261017")
def pin(path,raw):
 return {"path":str(path),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
def checked(record):
 path=Path(record["path"]); info=path.lstat()
 assert stat.S_ISREG(info.st_mode)
 raw=path.read_bytes()
 assert len(raw)==record["bytes"] and hashlib.sha256(raw).hexdigest()==record["sha256"]
 return raw
def save(path,raw,mode=None):
 path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("xb") as handle:
  assert handle.write(raw)==len(raw); handle.flush(); os.fsync(handle.fileno())
 if mode is not None: os.chmod(path,stat.S_IMODE(mode))
 assert path.read_bytes()==raw
 return pin(path,raw)
plan_pin={"path":str(D/"plan.json"),"bytes":9822,"sha256":"2002ee559baa9a1623eb3e751df29a3bf5a835b1771926715c524d06f93fd430"}
p=json.loads(checked(plan_pin))
checked(p["observation"])
for item in p["inputs"]: checked(item)
path=Path(p["exact_change"]["path"]); raw=path.read_bytes(); mode=path.lstat().st_mode
assert mode==33204 and stat.S_ISREG(mode)
old=p["exact_change"]["old"].encode(); new=p["exact_change"]["new"].encode()
assert raw.count(old)==1
expected=raw.replace(old,new,1)
assert len(expected)==p["exact_change"]["expected_after"]["bytes"] and hashlib.sha256(expected).hexdigest()==p["exact_change"]["expected_after"]["sha256"]
original=pin(path,raw)
archive=save(p["before_preservation"]["physical"],raw,mode)
manifest={"round":"R273","original":original,"archive":archive,"mode":mode,"base64":base64.b64encode(raw).decode("ascii")}
manifest_pin=save(p["before_preservation"]["manifest"],(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n").encode())
candidate=save(D/"implementation/prepared-root-final-source-input-argv-gate.txt",expected,mode)
temporary=path.with_name(path.name+".r273-next")
save(temporary,expected,mode)
assert path.read_bytes()==raw and path.lstat().st_mode==mode
os.replace(temporary,path)
assert path.read_bytes()==expected and path.lstat().st_mode==mode
diff="".join(difflib.unified_diff(raw.decode().splitlines(True),expected.decode().splitlines(True),fromfile=original["path"],tofile=str(path)+" (R273)"))
diff_pin=save(D/"implementation/limited.diff",diff.encode())
report={"round":"R273","status":"EXACT_REFERENCE_CORRECTED_GATE_NOT_EXECUTED","plan":plan_pin,"all11_inputs_verified_before_change":True,"before":manifest,"before_manifest":manifest_pin,"candidate":candidate,"after":pin(path,expected),"diff":diff_pin,"all_other_bytes_preserved":True,"gate_executed":False,"runtime_executed":False,"role_mutations":0,"independent_stdout":None,"independent_stderr":None}
report_pin=save(D/"root-correction-result.json",(json.dumps(report,ensure_ascii=False,indent=2)+"\n").encode())
print(json.dumps({"all11_inputs_verified_before_change":True,"before_manifest":manifest_pin,"after":pin(path,expected),"report":report_pin,"gate_executed":False},ensure_ascii=False))
