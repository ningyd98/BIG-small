from dataclasses import replace
from datetime import timedelta
import json
from tests.test_visual_owner_registration import api, values
data=values()
module=api()
original=data['original']
checks={}
for name,changes in [('negative_generation',{'state_generation':-1}),('nan_duration',{'required_duration_s':float('nan')}),('string_generation',{'state_generation':'2'})]:
    try:
        module.bind_step_grounding(**{**data,**changes})
        checks[name]='UNEXPECTED_ACCEPT'
    except ValueError:
        checks[name]='REJECTED'
bindings=[]
for x in (.2,.201):
    inputs=replace(data['grounding_inputs'],grasp_tcp={'x':x,'y':.1,'z':.06})
    grounded=data['grounded_step'].model_copy(update={'parameters':{**data['grounded_step'].parameters,'target_pose':{'x':x,'y':.1,'z':.16}}},deep=True)
    result=module.bind_step_grounding(**{**data,'grounding_inputs':inputs,'grounded_step':grounded})
    bindings.append(result.binding_hash)
checks['different_full_grounding_inputs_change_binding']=bindings[0]!=bindings[1]
stored=module.bind_step_grounding(**data)
fresh=stored.grounded_step
fresh.parameters['target_pose']['x']=9
checks['returned_nested_step_detached']=stored.grounded_step.parameters['target_pose']['x']==.2
checks['scope']=stored.binding_scope
checks['no_method_field']=not hasattr(stored,'method_admitted')
checks['no_execution_field']=not hasattr(stored,'execution_admitted')
print(json.dumps(checks,indent=2))
assert all(checks[k]=='REJECTED' for k in ['negative_generation','nan_duration','string_generation'])
assert checks['different_full_grounding_inputs_change_binding'] and checks['returned_nested_step_detached']
assert checks['scope']=='SOURCE_BINDING_ONLY' and checks['no_method_field'] and checks['no_execution_field']
