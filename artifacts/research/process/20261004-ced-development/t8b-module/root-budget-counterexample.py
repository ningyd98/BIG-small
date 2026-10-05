"""Isolate the budget gate with MOCK accepted prior inputs; no physics/protocol publication."""
import json,tempfile
from pathlib import Path
from unittest.mock import patch
from cloud_edge_robot_arm.research import freeze_evidence as mod
from cloud_edge_robot_arm.research.protocol import build_scene_pools
pools=build_scene_pools(981301,set(),protocol_version="ced.research.v2")
root=Path(tempfile.mkdtemp(prefix="t8-budget-guard-",dir="/tmp"))
(root/"selection-evidence").mkdir();d=root/"protocol-evidence";d.mkdir()
for name,value in {"evidence-pools.json":pools,"opportunities.json":[],"recovery-faults.json":[]}.items():
    (d/name).write_text(json.dumps(value))
base={"available":True,"pools":pools,"role_bundle_hash":"a"*64,"selected_period_s":2.,"evidence_hash":"b"*64}
foundation={**base,"cases":[{"stratum_id":r["stratum_id"],"success":True,"safety_violation":False,"wall_duration_s":20.} for r in pools["foundation"]]}
def audit(path,stage):return foundation if stage=="foundation" else base
with patch.object(mod,"audit_ced_pilot_stage",audit),patch("cloud_edge_robot_arm.research.protocol_evidence.verify_protocol_evidence",return_value={"valid":True}):
    spec=mod._initial_v2_spec(root)
print(json.dumps({"scope":"SOFTWARE_ONLY_GATE_PROBE","prior_gates":"MOCK","physical_actions":0,"protocol_written":False,"resource_evidence_files":[],"spec_issued_without_resource_acceptance":True,"spec_version":spec.schema_version,"tcap_s":spec.tcap_s}))
