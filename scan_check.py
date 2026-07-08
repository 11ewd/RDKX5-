#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
import time
import math

class ScanCheck(Node):
    def __init__(self):
        super().__init__('scan_check_node')
        self.count = 0
        self.last = time.time()
        print("等待 /scan 数据...")
        self.sub = self.create_subscription(
            LaserScan,
            '/scan',
            self.cb,
            qos_profile_sensor_data
        )

    def cb(self, msg):
        self.count += 1
        now = time.time()
        dt = now - self.last
        if dt >= 2.0:
            valid = [r for r in msg.ranges if not math.isinf(r) and not math.isnan(r)]
            if valid:
                print(f"/scan 频率: {self.count / dt:.2f} Hz, 点数: {len(msg.ranges)}, 最近距离: {min(valid):.2f} m")
            else:
                print(f"/scan 频率: {self.count / dt:.2f} Hz, 点数: {len(msg.ranges)}, 距离全无效")
            self.count = 0
            self.last = now

rclpy.init()
node = ScanCheck()
rclpy.spin(node)
