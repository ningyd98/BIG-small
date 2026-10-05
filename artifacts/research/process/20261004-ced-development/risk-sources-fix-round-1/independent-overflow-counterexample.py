from pathlib import Path
from dataclasses import replace
import json,tempfile,traceback
from tests.test_research_risk_sources import fixture_case,registered,hashes
root=Path(tempfile.mkdtemp(prefix='risk-fix1-overflow-probe-'));case,d=fixture_case(root)
p=d/'raw-actuators.jsonl';rows=[json.loads(x) for x in p.read_text().splitlines()];rows[5]['pre_gravity_bias_nm'][0]=10**500;p.write_text(''.join(json.dumps(x)+'\n' for x in rows));case=replace(case,original_file_hashes=hashes(d))
try:
 result=registered(root,case).audit('fixture',scope='RAW_EXECUTION');print('RETURN',result.status,dict(result.counts),result.reasons)
except Exception as error:
 print('UNCAUGHT',type(error).__name__,str(error));traceback.print_exc()
print('SOFTWARE_ONLY original bytes isolated, no renderer/data/step/model/network/action')
