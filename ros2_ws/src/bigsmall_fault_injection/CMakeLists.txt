# CMake 说明：声明故障注入 ROS 2 包的构建入口，不连接真实控制器或触发硬件动作。
cmake_minimum_required(VERSION 3.20)
project(bigsmall_fault_injection)
find_package(ament_cmake REQUIRED)
ament_package()
