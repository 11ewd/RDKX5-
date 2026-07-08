from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():

    return LaunchDescription([

        Node(
            package='agri_imu_driver',
            executable='imu_node.py'
        ),

        Node(
            package='agri_car_driver',
            executable='car_node.py'
        ),

        Node(
            package='agri_control',
            executable='control.py'
        ),
    ])

