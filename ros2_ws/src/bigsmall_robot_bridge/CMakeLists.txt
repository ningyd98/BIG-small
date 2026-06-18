# CMake 说明：安装机器人边界 Python 节点入口，不在构建阶段连接 MoveIt 或真实机械臂。
cmake_minimum_required(VERSION 3.20)
project(bigsmall_robot_bridge)
find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)

ament_python_install_package(${PROJECT_NAME})

install(PROGRAMS
  scripts/bigsmall_moveit_boundary_node
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
