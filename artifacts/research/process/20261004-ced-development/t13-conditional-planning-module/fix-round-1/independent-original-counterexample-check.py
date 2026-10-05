import json
from dataclasses import replace
from tests.test_conditional_repair_intent import inputs,build,payload,api
from cloud_edge_robot_arm.cloud.replanning.conditional_intent import ConditionalReplacement
from cloud_edge_robot_arm.cloud.replanning.visual_dependencies import StepDependency
from cloud_edge_robot_arm.contracts import SkillName
from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
from cloud_edge_robot_arm.edge.recovery.lifecycle import checkpoint_digest
from cloud_edge_robot_arm.vision.owner_registration import OriginalActionRequirements,freeze_original_visual_plan

result=build();closed=0
class MutableReplacement:
 def __init__(self):self.payload={'arbitrary':[]}
 def to_payload(self):return self.payload
cases=[('binding_hash','not-a-sha'),('original_plan_hash',None),('source_checkpoint_hash',''),('observation_id',''),('replacements',[MutableReplacement()]),('_preserved_steps_json','{"duplicate":1,"duplicate":2,"nonfinite":NaN}')]
preserved=inputs()['original'].contract.steps[0].model_dump(mode='json');preserved['step_id']='unrelated';preserved['retry_limit']=True
cases.append(('_preserved_steps_json',json.dumps({'unrelated':preserved})))
for name,value in cases:
 try:replace(result,**{name:value})
 except (TypeError,ValueError):closed+=1;print(name,'REJECTED')
 else:raise AssertionError((name,'still accepted'))
class MutableSubclass(ConditionalReplacement):
 def to_payload(self):return self.alias
r=result.replacements[0];subclass=MutableSubclass(r.step_id,r.target_pixel,r.destination_pixel,r.original_requirements,r.current_preconditions);object.__setattr__(subclass,'alias',{'fake':[]})
cloned=replace(result,replacements=[subclass,*result.replacements[1:]]);before=cloned.digest();subclass.alias['fake'].append('changed');assert cloned.digest()==before and type(cloned.replacements[0]) is ConditionalReplacement;print('inherited_override','CLONED_CONCRETE_IMMUTABLE')
rows=[[r.current_preconditions[0][0],r.current_preconditions[0][1],r.current_preconditions[0][2],['reason']]]
replacement=replace(r,current_preconditions=rows);cloned=replace(result,replacements=[replacement,*result.replacements[1:]]);before=cloned.digest();rows[0][3].append('later');assert cloned.digest()==before;print('nested_diagnostics_alias','DETACHED')
data=inputs();original=data['original'];contract=original.contract;extra=contract.steps[0].model_copy(update={'step_id':'unrelated','skill':SkillName.RELEASE,'preconditions':['gripper_closed'],'success_conditions':['gripper_released']},deep=True);requirements=dict(original.requirements);requirements['unrelated']=OriginalActionRequirements(extra,(ConditionSpec('gripper_closed',contract.task_target.object_id),),(ConditionSpec('gripper_released',contract.task_target.object_id),),.01,('rgbd',),5.,max(extra.timeout_ms,extra.expected_duration_ms)/1000,original.source_hashes)
data['original']=freeze_original_visual_plan(**{**original.freeze_inputs(),'contract':contract.model_copy(update={'steps':[*contract.steps,extra]}),'requirements':requirements,'dependencies':(*original.dependencies,StepDependency('unrelated',(),('other',),'other-effect',False))})
cp=data['source_checkpoint'].model_copy(update={'pending_step_ids':['grasp','lift','unrelated']},deep=True);cp=cp.model_copy(update={'checkpoint_hash':checkpoint_digest(cp)});data['source_checkpoint']=cp;data['online']=replace(data['online'],context_hash=cp.checkpoint_hash);new=build(data,payload(data));assert new.preserved_original_steps['unrelated']==extra.model_dump(mode='json');assert new.replacements[1].current_preconditions[0][1]=='FAIL';print('unrelated_step','PRESERVED_EXACT','future_holding','FAIL')
assert result.scope=='PLANNING_ONLY' and result.method_admitted is False and result.execution_admitted is False
print('PASS',closed,'original negatives; subclass/diagnostics/unrelated positives; no actual authority or action.')
