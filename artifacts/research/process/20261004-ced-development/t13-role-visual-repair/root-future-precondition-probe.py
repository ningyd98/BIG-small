"""Software-only integration limit: a future LIFT requires a preceding GRASP effect."""
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from pytest import MonkeyPatch

from cloud_edge_robot_arm.cloud.replanning.role_visual_repair import RoleVisualRepairSource
from cloud_edge_robot_arm.cloud.replanning.visual_dependencies import StepDependency
from cloud_edge_robot_arm.contracts.models import SkillName
from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec, evaluate_conditions
from tests.test_role_visual_repair import NOW, setup

with TemporaryDirectory(prefix='bigsmall-future-condition-') as name:
    with MonkeyPatch.context() as patch:
        adapter, wire, planner, binding, source, request, window, observation, ledger = setup(Path(name), patch, full_remaining=True)
        context = source.context
        future = context.active_contract.steps[2].model_copy(update={
            'skill': SkillName.LIFT, 'preconditions': ['gripper_holding'],
            'success_conditions': ['object_held'],
        })
        contract = context.active_contract.model_copy(update={
            'steps': [*context.active_contract.steps[:2], future],
        }, deep=True)
        robot = context.online_evidence.robot_state.model_copy(update={
            'gripper_open': True, 'holding_object_id': None,
        })
        context = replace(context, active_contract=contract,
                          online_evidence=replace(context.online_evidence, robot_state=robot),
                          dependencies=(*context.dependencies[:2], StepDependency('telemetry', ('grasp',), ('grasp-effect',), 'lift-effect', False)))
        proofs = dict(source.action_evidence)
        proofs['telemetry'] = replace(proofs['telemetry'], preconditions=(ConditionSpec('gripper_holding', 'obj-1'),))
        source = RoleVisualRepairSource(context, proofs, 'SOFTWARE_ONLY')
        adapter.source_provider = lambda *_: source
        result = adapter.replan(request)
        print('scope=SOFTWARE_ONLY live_calls=0 controller_commands=0')
        print('future_precondition=', evaluate_conditions(proofs['telemetry'].preconditions, context.online_evidence, now=NOW + timedelta(seconds=0.2))[0].status)
        print('outcome=', result.outcome, 'mock_attempts=', len(wire.requests), 'steps=', len(result.new_steps))
        assert result.outcome == 'MORE_OBSERVATION_REQUIRED' and not wire.requests
