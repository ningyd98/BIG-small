from dataclasses import replace
from tests.test_conditional_repair_intent import build

result=build()
for name,value in [('binding_hash','not-a-sha'),('original_plan_hash',None),('source_checkpoint_hash',''),('observation_id','')]:
 changed=replace(result,**{name:value})
 print(name,'accepted',getattr(changed,name),'scope',changed.scope,'method',changed.method_admitted,'execution',changed.execution_admitted)

class MutableReplacement:
 def __init__(self):self.payload={'step_id':'arbitrary','current_preconditions':[['gripper_holding','PASS','fake',[]]]}
 def to_payload(self):return self.payload
replacement=MutableReplacement()
changed=replace(result,replacements=[replacement]);before=changed.digest()
replacement.payload['current_preconditions'][0][1]='FAIL'
print('mutable_non_typed_replacement accepted',before!=changed.digest(),'hash_changed_without_carrier_assignment','scope',changed.scope,'method',changed.method_admitted,'execution',changed.execution_admitted)

malformed=replace(result,_preserved_steps_json='{"duplicate":1,"duplicate":2,"nonfinite":NaN}')
print('duplicate_nan_preserved_json accepted',malformed.preserved_original_steps)
print('Factory scope remains PLANNING_ONLY; no actual submission/admission authority or model/action.')
