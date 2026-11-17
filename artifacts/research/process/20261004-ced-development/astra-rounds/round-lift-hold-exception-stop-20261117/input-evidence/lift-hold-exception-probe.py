from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.simulation.mujoco.visual_servo import VisualServoSession
import json

backend = MuJoCoPhysicsBackend()
try:
    backend.initialize(SimulatorConfig(physics_dt_s=1/240, render_rgb=False, render_depth=False))
    backend.reset(PhysicalScenarioConfig.scenario('S01_NORMAL_STATIC', seed=31))
    robot = MuJoCoSkillRobot(backend)
    assert robot.approach('object', resolved_target=Pose(x=0.45,y=0,z=0.045)).success
    assert robot.grasp('object', timeout_ms=1000).success
    start = backend.get_tcp_pose()
    target = Pose(x=start.x,y=start.y,z=0.16)
    path = VerticalClearancePath('task','lift','LIFT',(start.x,start.y,start.z),(target.x,target.y,target.z),0.08)
    session = VisualServoSession(lambda value:value, vertical_clearance=path)
    fault_step = None
    def fail_in_hold(snapshot):
        global fault_step
        if session.terminal_reason == 'SUCCEEDED':
            fault_step = snapshot.physics_step
            raise RuntimeError('review_fault_first_lift_hold_step')
    try:
        with backend.observe_physics_steps(fail_in_hold), robot.visual_servo(session):
            robot.lift(resolved_target=target,timeout_ms=10000,tcp_velocity=0.15,acceleration=0.5)
    except RuntimeError as exc:
        assert str(exc)=='review_fault_first_lift_hold_step'
    else:
        raise AssertionError('fault did not trigger')
    result = {
        'scope':'isolated headless LIFT, identity visual callback; not full worker',
        'fault_step':fault_step,
        'last_command_type':backend.command_records[-1]['type'],
        'last_command_step':backend.command_records[-1]['physics_step'],
        'commands_at_or_after_fault':[r['type'] for r in backend.command_records if r['physics_step']>=fault_step],
        'estop_engaged':backend.estop_engaged,
        'session_terminal_reason':session.terminal_reason,
        'max_retained_target_minus_feedback_rad':float(abs(backend._target_positions-backend._data.qpos[:7]).max()),
    }
    print(json.dumps(result, indent=2))
finally:
    backend.shutdown()
