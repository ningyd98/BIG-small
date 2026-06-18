# CMake 说明：声明 Franka MoveIt 配置包的构建入口，仅用于仿真/干运行配置打包。
cmake_minimum_required(VERSION 3.20)
project(bigsmall_franka_moveit_config)
find_package(ament_cmake REQUIRED)
ament_package()
