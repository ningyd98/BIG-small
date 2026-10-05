from __future__ import annotations
import json, tempfile
from pathlib import Path
from dataclasses import replace
from tests.test_research_risk_supervision import registered_fixture, audit
from tests.test_research_risk_sources import hashes, json_file
from cloud_edge_robot_arm.research.risk_sources import RiskSourceAuditor
from cloud_edge_robot_arm.research.risk_supervision import RiskSupervisionAuditor

work=Path(tempfile.mkdtemp(prefix='root-risk-criteria-probe-'))
registration, directory, _, _ = registered_fixture(work)
minimum=[-0.85,-0.85,0.0]; maximum=[0.85,0.85,1.2]
criteria=replace(registration.raw_registration.criteria,workspace_min_m=minimum,workspace_max_m=maximum)
raw=replace(registration.raw_registration,criteria=criteria)
base=RiskSourceAuditor({'raw':raw}).audit('raw',scope='RAW_EXECUTION')
assert base.status=='VALID',base.reasons
json_file(directory/'summary.json', {'outcome':dict(base.case_results[0]['physical_outcome'])})
case=replace(raw.cases[0],original_file_hashes=hashes(directory))
registration=replace(registration,raw_registration=replace(raw,cases=(case,)))
owner=RiskSupervisionAuditor({'source':registration})
before=owner.audit('source')
assert before.diagnostic_status=='VALID',before.reasons
source_hashes_before=hashes(directory)
maximum[2]=0.001
assert hashes(directory)==source_hashes_before
after=owner.audit('source')
print(json.dumps({'work':str(work),'mutation':'original caller workspace_max_m[2] = 0.001','all_original_files_unchanged':True,'before':{'actual_status':before.status,'diagnostic_status':before.diagnostic_status,'rows':len(before.rows)},'after':{'actual_status':after.status,'diagnostic_status':after.diagnostic_status,'rows':len(after.rows),'reasons':after.reasons}},indent=2))
assert after.diagnostic_status==before.diagnostic_status, 'COPY ISOLATION FAILED: caller-owned criteria list alters registered immutable audit'
