cmake_minimum_required(VERSION 3.20)
project(bigsmall_interfaces)
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(trajectory_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/CommandHeader.msg"
  "msg/Contact.msg"
  "msg/ContactArray.msg"
  "msg/FaultEvent.msg"
  "msg/RobotState.msg"
  "msg/SafetyEvent.msg"
  "msg/SceneSummary.msg"
  "msg/SimulationStatus.msg"
  "srv/EmergencyStop.srv"
  "srv/GripperCommand.srv"
  "srv/Home.srv"
  "srv/InjectFault.srv"
  "srv/LoadScenario.srv"
  "srv/ResetWorld.srv"
  "srv/Stop.srv"
  "action/FollowJointTrajectory.action"
  "action/MoveToPose.action"
  DEPENDENCIES builtin_interfaces geometry_msgs sensor_msgs std_msgs trajectory_msgs
)

ament_package()
