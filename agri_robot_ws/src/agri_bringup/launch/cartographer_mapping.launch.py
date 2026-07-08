from launch import LaunchDescription
from launch_ros.actions import Node
import os


def generate_launch_description():
    config_dir = os.path.expanduser('~/agri_robot_ws/src/agri_bringup/config')

    return LaunchDescription([
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='base_to_laser_tf',
            arguments=[
                '--x', '0.15',
                '--y', '0',
                '--z', '0.20',
                '--roll', '0',
                '--pitch', '0',
                '--yaw', '0',
                '--frame-id', 'base_link',
                '--child-frame-id', 'laser'
            ],
            output='screen'
        ),

        Node(
            package='cartographer_ros',
            executable='cartographer_node',
            name='cartographer_node',
            output='screen',
            parameters=[
                {'use_sim_time': False}
            ],
            arguments=[
                '-configuration_directory', config_dir,
                '-configuration_basename', 'agri_2d.lua'
            ],
            remappings=[
                ('scan', '/scan')
            ]
        ),

        Node(
            package='cartographer_ros',
            executable='cartographer_occupancy_grid_node',
            name='cartographer_occupancy_grid_node',
            output='screen',
            parameters=[
                {'use_sim_time': False}
            ],
            arguments=[
                '-resolution', '0.05',
                '-publish_period_sec', '1.0'
            ]
        ),
    ])
