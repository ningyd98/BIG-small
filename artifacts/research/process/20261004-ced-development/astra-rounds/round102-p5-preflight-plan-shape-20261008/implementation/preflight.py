import hashlib,json,sys
from datetime import UTC,datetime
from pathlib import Path
r=Path(__file__).resolve().parent
b=r.parent.parent
p101=b/"round101-p5-age-deadline-boundary-20261008"
start=datetime.now(UTC).isoformat()
checks=[]
def require(value,reason):
 if not value:raise ValueError(reason)
def check_pins(items,count):
 require(type(items) is list and len(items)==count,"wrong finite pin list")
 for item in items:
  require(type(item) is dict and type(item.get("path")) is str and type(item.get("bytes")) is int and type(item.get("sha256")) is str,"wrong pin shape")
  q=Path(item["path"]);data=q.read_bytes();actual={"path":item["path"],"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
  actual["match"]=actual["bytes"]==item["bytes"] and actual["sha256"]==item["sha256"]
  checks.append(actual);require(actual["match"],"changed pin: "+item["path"])
try:
 p=json.loads((p101/"plan.json").read_text())
 require(type(p) is dict and type(p.get("schema_version")) is int and p["schema_version"]==1,"R101 schema must be exact integer1")
 require(p.get("round")=="round101-p5-age-deadline-boundary-20261008","wrong round")
 require(type(p.get("scope")) is dict,"scope must be mapping")
 owned=p["scope"].get("owned_paths")
 approved=["src/cloud_edge_robot_arm/vision/operational_windows.py","src/cloud_edge_robot_arm/vision/worker_runtime.py","src/cloud_edge_robot_arm/vision/supervision.py","src/cloud_edge_robot_arm/vision/marker_association.py","src/cloud_edge_robot_arm/repositories/event_autonomy/visual_bootstrap.py","src/cloud_edge_robot_arm/repositories/event_autonomy/visual_supervision.py","src/cloud_edge_robot_arm/edge/evidence/models.py","src/cloud_edge_robot_arm/edge/evidence/conditions.py","src/cloud_edge_robot_arm/simulation_runtime/worker.py","tests/test_operational_windows.py"]
 require(type(owned) is list and owned==approved and len(set(owned))==10,"owned paths differ from ten literal approved paths")
 require(type(p.get("budget")) is dict and type(p.get("commands")) is list and len(p["commands"])==3,"budget/commands shape")
 for name in ["GREEN","ruff_check","format_check_new_two"]:
  entry=p["budget"].get(name);require(type(entry) is dict and entry.get("used")==0 and entry.get("remaining")==1 and entry.get("maximum_total")==1,"wrong remaining budget: "+name)
 require(p["budget"].get("RED",{}).get("remaining")==0,"RED exhausted")
 for command in p["commands"]:
  require(type(command) is dict and command.get("name") in ["ruff","format_check","green"] and type(command.get("argv")) is list and all(type(a) is str for a in command["argv"]) and command.get("maximum_invocations")==1,"wrong command shape")
 check_pins(p.get("input_pins"),40)
 p102=json.loads((r.parent/"plan.json").read_text());check_pins(p102.get("input_pins"),12)
 frozen=json.loads((p101/"implementation/source-freeze.json").read_text())["owned"]
 require(type(frozen) is list and len(frozen)==10,"wrong source freeze")
 states=[]
 for name,expected in zip(owned,frozen,strict=True):
  require(expected.get("path")==name,"frozen path mismatch")
  q=Path(name)
  if name=="src/cloud_edge_robot_arm/vision/operational_windows.py":
   require(not q.exists() and expected.get("absent") is True,"NEW module must remain absent");states.append({"path":name,"absent":True})
  else:
   data=q.read_bytes();state={"path":name,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()};require(state["bytes"]==expected["bytes"] and state["sha256"]==expected["sha256"],"frozen source changed");states.append(state)
 require(not (p101/"implementation/green").exists(),"original GREEN leaf already exists")
 require(not Path("/tmp/bigsmall-p5-r101-green").exists(),"original basetemp already exists")
 require(not (r/"source-before").exists() and not (r/"input-check.json").exists() and not (r/"progress.md").exists(),"recovery output already exists")
 (r/"source-before").mkdir()
 for state in states:
  if state.get("absent"):continue
  q=Path(state["path"]);dst=r/"source-before"/state["path"];dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(q.read_bytes())
 result={"status":"METADATA_RECOVERED","start_utc":start,"end_utc":datetime.now(UTC).isoformat(),"exit_code":0,"checks":checks,"source_states":states,"nine_source_before_saved":True,"module_absence_saved":True,"original_GREEN_leaf_and_basetemp_absent":True,"R101_stop_originals_unchanged":True}
 (r/"input-check.json").write_text(json.dumps(result,indent=2)+"\n")
 (r/"progress.md").write_text("# R102 continued P5\n\nMETADATA_RECOVERED: R10140+R10212 pins MATCH; ten source states match, nine source-before saved and NEW module absent. Original R101 GREEN leaf/basetemp absent; original stop and R100 RED preserved. Continuing approved32 tests and R100/R101 software.\n\nRED exhausted; proof0; Ruff/formatcheck/GREEN0/1; formatter/mypy/actual/Git0.\n")
except Exception as error:
 result={"status":"NEEDS_ASTRA_METADATA_STOP","start_utc":start,"end_utc":datetime.now(UTC).isoformat(),"exit_code":1,"exception":type(error).__name__,"reason":str(error),"completed_checks":checks}
(r/"preflight-result.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps({k:v for k,v in result.items() if k not in ["checks","source_states"]},indent=2))
sys.exit(result["exit_code"])
