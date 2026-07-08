#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from sensor_msgs.msg import LaserScan
import time
import math

class ScanCheck(Node):
    def __init__(self):
        super().__init__('scan_check_reliable_node')

        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )

        self.count = 0
        self.last = time.time()

        print("等待 /scan 数据，使用 RELIABLE QoS...")

        self.sub = self.create_subscription(
            LaserScan,
            '/scan',
            self.cb,
            qos
        )

    def cb(self, msg):
        self.count += 1
        now = time.time()
        dt = now - self.last

        if self.count == 1:
            print("收到第一帧 /scan")
            print("frame_id:", msg.header.frame_id)
            print("点数:", len(msg.ranges))
            print("angle_min:", msg.angle_min)
            print("angle_max:", msg.angle_max)

        if dt >= 2.0:
            valid = [
                r for r in msg.ranges
                if not math.isinf(r) and not math.isnan(r)
            ]

            if valid:
                print(f"/scan 频率: {self.count / dt:.2f} Hz, 点数: {len(msg.ranges)}, 最近距离: {min(valid):.2f} m")
            else:
                print(f"/scan 频率: {self.count / dt:.2f} Hz, 点数: {len(msg.ranges)}, 但距离全无效")

            self.count = 0
            self.last = now

def main():
    rclpy.init()
    node = ScanCheck()
    rclpy.spin(node)

if __name__ == '__main__':
    main()
