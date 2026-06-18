# CMake 说明：安装仿真桥接 Python 节点入口，不包含真实硬件写操作。
cmake_minimum_required(VERSION 3.20)
project(bigsmall_sim_bridge)
find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)

ament_python_install_package(${PROJECT_NAME})

install(PROGRAMS
  scripts/bigsmall_sim_bridge_node
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
