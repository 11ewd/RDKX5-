
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist, TransformStamped
from nav_msgs.msg import Odometry
from tf2_ros import TransformBroadcaster


def yaw_to_quat(yaw):
    qz = math.sin(yaw * 0.5)
    qw = math.cos(yaw * 0.5)
    return 0.0, 0.0, qz, qw


class FakeOdomNode(Node):
    def __init__(self):
        super().__init__('fake_odom_node')

        self.x = 0.0
        self.y = 0.0
        self.yaw = 0.0

        self.vx = 0.0
        self.vth = 0.0

        self.last_time = self.get_clock().now()

        self.odom_pub = self.create_publisher(Odometry, '/odom', 10)
        self.tf_broadcaster = TransformBroadcaster(self)

        self.cmd_sub = self.create_subscription(
            Twist,
            '/cmd_vel',
            self.cmd_vel_callback,
            10
        )

        self.timer = self.create_timer(0.02, self.update)

        self.get_logger().info('fake odom started: publish /odom and odom -> base_link')

    def cmd_vel_callback(self, msg):
        self.vx = msg.linear.x
        self.vth = msg.angular.z

    def update(self):
        now = self.get_clock().now()
        dt = (now - self.last_time).nanoseconds / 1e9
        self.last_time = now

        if dt <= 0.0 or dt > 1.0:
            return

        dx = self.vx * math.cos(self.yaw) * dt
        dy = self.vx * math.sin(self.yaw) * dt
        dyaw = self.vth * dt

        self.x += dx
        self.y += dy
        self.yaw += dyaw

        qx, qy, qz, qw = yaw_to_quat(self.yaw)

        t = TransformStamped()
        t.header.stamp = now.to_msg()
        t.header.frame_id = 'odom'
        t.child_frame_id = 'base_link'
        t.transform.translation.x = self.x
        t.transform.translation.y = self.y
        t.transform.translation.z = 0.0
        t.transform.rotation.x = qx
        t.transform.rotation.y = qy
        t.transform.rotation.z = qz
        t.transform.rotation.w = qw
        self.tf_broadcaster.sendTransform(t)

        odom = Odometry()
        odom.header.stamp = now.to_msg()
        odom.header.frame_id = 'odom'
        odom.child_frame_id = 'base_link'

        odom.pose.pose.position.x = self.x
        odom.pose.pose.position.y = self.y
        odom.pose.pose.position.z = 0.0
        odom.pose.pose.orientation.x = qx
        odom.pose.pose.orientation.y = qy
        odom.pose.pose.orientation.z = qz
        odom.pose.pose.orientation.w = qw

        odom.twist.twist.linear.x = self.vx
        odom.twist.twist.angular.z = self.vth

        self.odom_pub.publish(odom)


def main():
    rclpy.init()
    node = FakeOdomNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
