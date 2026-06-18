# ROS 消息说明：该消息只承载状态、事件或感知数据，不表达运动授权。
builtin_interfaces/Time stamp
string frame_id
string scenario_id
string[] object_ids
geometry_msgs/Pose[] object_poses
string[] obstacle_ids
geometry_msgs/Pose[] obstacle_poses
float64 confidence
bool ground_truth_used_for_control
