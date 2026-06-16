from __future__ import annotations

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description() -> LaunchDescription:
    db_arg = DeclareLaunchArgument("db", default_value="False", description="Database flag")
    ros2_control_hardware_type = DeclareLaunchArgument(
        "ros2_control_hardware_type",
        default_value="mock_components",
        description="ROS 2 control hardware interface type to use for the launch file",
    )

    moveit_config = (
        MoveItConfigsBuilder("moveit_resources_panda")
        .robot_description(
            file_path="config/panda.urdf.xacro",
            mappings={
                "ros2_control_hardware_type": LaunchConfiguration("ros2_control_hardware_type")
            },
        )
        .robot_description_semantic(file_path="config/panda.srdf")
        .planning_scene_monitor(
            publish_robot_description=True,
            publish_robot_description_semantic=True,
        )
        .trajectory_execution(file_path="config/gripper_moveit_controllers.yaml")
        .planning_pipelines(pipelines=["ompl", "chomp", "pilz_industrial_motion_planner", "stomp"])
        .to_moveit_configs()
    )

    ros2_controllers_path = os.path.join(
        get_package_share_directory("moveit_resources_panda_moveit_config"),
        "config",
        "ros2_controllers.yaml",
    )
    db_config = LaunchConfiguration("db")

    return LaunchDescription(
        [
            db_arg,
            ros2_control_hardware_type,
            Node(
                package="tf2_ros",
                executable="static_transform_publisher",
                name="static_transform_publisher",
                output="log",
                arguments=[
                    "0.0",
                    "0.0",
                    "0.0",
                    "0.0",
                    "0.0",
                    "0.0",
                    "world",
                    "panda_link0",
                ],
            ),
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                name="robot_state_publisher",
                output="both",
                parameters=[moveit_config.robot_description],
            ),
            Node(
                package="moveit_ros_move_group",
                executable="move_group",
                output="screen",
                parameters=[moveit_config.to_dict()],
                arguments=["--ros-args", "--log-level", "info"],
            ),
            Node(
                package="controller_manager",
                executable="ros2_control_node",
                parameters=[ros2_controllers_path],
                remappings=[
                    ("/controller_manager/robot_description", "/robot_description"),
                ],
                output="screen",
            ),
            Node(
                package="controller_manager",
                executable="spawner",
                arguments=[
                    "joint_state_broadcaster",
                    "--controller-manager",
                    "/controller_manager",
                ],
            ),
            Node(
                package="controller_manager",
                executable="spawner",
                arguments=["panda_arm_controller", "-c", "/controller_manager"],
            ),
            Node(
                package="controller_manager",
                executable="spawner",
                arguments=["panda_hand_controller", "-c", "/controller_manager"],
            ),
            Node(
                package="warehouse_ros_mongo",
                executable="mongo_wrapper_ros.py",
                parameters=[
                    {"warehouse_port": 33829},
                    {"warehouse_host": "localhost"},
                    {"warehouse_plugin": "warehouse_ros_mongo::MongoDatabaseConnection"},
                ],
                output="screen",
                condition=IfCondition(db_config),
            ),
        ]
    )
