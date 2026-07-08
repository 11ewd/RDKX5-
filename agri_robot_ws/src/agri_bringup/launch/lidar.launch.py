from launch import LaunchDescription
from launch_ros.actions import Node
import os

def generate_launch_description():
    param_file = os.path.expanduser(
        '~/agri_robot_ws/src/LSLIDAR_X_ROS2-20240228/src/lslidar_driver/params/lidar_uart_ros2/lsn10.yaml'
    )

    return LaunchDescription([
        Node(
            package='lslidar_driver',
            executable='lslidar_driver_node',
            name='lslidar_driver_node',
            output='screen',
            parameters=[param_file],
        )
    ])
