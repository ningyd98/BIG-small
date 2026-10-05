from __future__ import annotations
import json, tempfile
from pathlib import Path
from dataclasses import replace
from cloud_edge_robot_arm.research.risk_supervision import RiskSupervisionAuditor, RiskObservationAllocation, RiskComponentHistory, RiskDiagnosticMeasurements
from tests.test_research_risk_supervision import registered_fixture
from tests.test_research_risk_sources import hashes, json_file

results=[]
def fixture():
 return registered_fixture(Path(tempfile.mkdtemp(prefix='root-risk-extra-probe-')))
def audit(registration):
 return RiskSupervisionAuditor({'source':registration}).audit('source')
def assert_rejected(name, make):
 try: make()
 except (TypeError,ValueError) as error:
  results.append({'probe':name,'result':'PASS','reason':str(error)});return
 raise AssertionError(name+' accepted')
registration,_,_,_=fixture()
class PretendAllocation(RiskObservationAllocation): pass
allocation=registration.allocations[0]
assert_rejected('allocation_subclass',lambda:replace(registration,allocations=(PretendAllocation(allocation.sample_id,allocation.case_id,allocation.observation_id,allocation.split),*registration.allocations[1:])))
class PretendHistory(RiskComponentHistory): pass
history=registration.histories[0]
assert_rejected('history_subclass',lambda:replace(registration,histories=(PretendHistory(history.group_id,history.used_purposes),)))
class PretendMeasurement(RiskDiagnosticMeasurements): pass
measured=registration.diagnostic_measurements
assert_rejected('measurement_subclass',lambda:replace(registration,diagnostic_measurements=PretendMeasurement(measured.artifact_root,measured.original_file_hashes,measured.clock_path,measured.calibration_path)))
for name in ['clock_path','calibration_path']:
 registration,_,_,_=fixture()
 source=replace(registration,diagnostic_measurements=replace(registration.diagnostic_measurements,**{name:None}))
 result=audit(source)
 assert result.status==result.actual_source_status==result.diagnostic_status=='UNKNOWN', result.reasons
 assert result.counts['allocated_observations']==result.counts['task_labels']==2
 assert result.counts['feature_rows']==0 and all(row['online_features'] is None for row in result.rows)
 results.append({'probe':'missing_'+name,'result':'PASS','allocated':2,'features':0,'task_labels':2})
registration,_,measurements,_=fixture()
payload=json.loads((measurements/'calibration.json').read_bytes())
payload['pairs_m'][0]={'estimate':[1e308,1e308,1e308],'reference':[-1e308,-1e308,-1e308]}
json_file(measurements/'calibration.json',payload)
source=replace(registration,diagnostic_measurements=replace(registration.diagnostic_measurements,original_file_hashes=hashes(measurements)))
result=audit(source)
assert result.diagnostic_status==result.status=='INVALID' and result.counts['missing_observations']==2
results.append({'probe':'finite_components_overflow_norm','result':'PASS','reasons':list(result.reasons)})
registration,_,measurements,_=fixture()
payload=json.loads((measurements/'clock.json').read_bytes())
payload['cases'][registration.raw_registration.cases[0].case_id][121]['utc']='2026-10-05T00:00:30.251000+00:00'
json_file(measurements/'clock.json',payload)
source=replace(registration,diagnostic_measurements=replace(registration.diagnostic_measurements,original_file_hashes=hashes(measurements)))
result=audit(source)
assert result.diagnostic_status==result.status=='INVALID'
results.append({'probe':'UTC_monotonic_interval_incoherence','result':'PASS','reasons':list(result.reasons)})
registration,_,_,_=fixture()
owner=RiskSupervisionAuditor({'source':registration})
criteria=registration.raw_registration.criteria
object.__setattr__(criteria,'workspace_max_m',(0.85,0.85,0.001))
result=owner.audit('source')
assert result.diagnostic_status=='VALID' and len(result.rows)==2
results.append({'probe':'immutable_tuple_criteria_scalar_reassignment_is_isolated','result':'PASS'})
print(json.dumps({'passed':len(results),'probes':results},indent=2))
