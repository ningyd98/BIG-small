# ROS 消息说明：该消息只承载状态、事件或感知数据，不表达运动授权。
builtin_interfaces/Time stamp
string state
bool emergency_stopped
bool motion_active
float64 sim_time_s
float64 ros_time_s
float64 wall_time_s
uint64 command_seq
uint64 plan_version
