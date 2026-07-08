#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import re
import serial

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry

from tf2_ros import TransformBroadcaster


def norm_angle(a):
    while a > math.pi:
        a -= 2.0 * math.pi
    while a < -math.pi:
        a += 2.0 * math.pi
    return a


class CarSerialOdomNode(Node):
    def __init__(self):
        super().__init__("car_serial_odom_node")

        # 串口参数
        self.declare_parameter("port", "/dev/car_stm32")
        self.declare_parameter("baud", 115200)

        # 坐标系
        self.declare_parameter("odom_frame", "odom")
        self.declare_parameter("base_frame", "base_link")
        self.declare_parameter("publish_tf", True)

        # 车体参数，需要后面实测标定
        self.declare_parameter("track_width", 0.36)

        # 编码器标定参数：
        # 先给默认值，后面让小车直走 1m，再根据 total 变化来改
        self.declare_parameter("ticks_per_meter_left", 10000.0)
        self.declare_parameter("ticks_per_meter_right", 10000.0)

        # 编码器方向修正
        self.declare_parameter("m1_sign", 1.0)
        self.declare_parameter("m2_sign", 1.0)
        self.declare_parameter("m3_sign", 1.0)
        self.declare_parameter("m4_sign", 1.0)

        # 状态查询频率
        self.declare_parameter("query_hz", 10.0)

        # cmd_vel 超时停车
        self.declare_parameter("cmd_timeout", 0.5)

        self.port = self.get_parameter("port").value
        self.baud = int(self.get_parameter("baud").value)

        self.odom_frame = self.get_parameter("odom_frame").value
        self.base_frame = self.get_parameter("base_frame").value
        self.publish_tf = bool(self.get_parameter("publish_tf").value)

        self.track_width = float(self.get_parameter("track_width").value)
        self.ticks_per_meter_left = float(self.get_parameter("ticks_per_meter_left").value)
        self.ticks_per_meter_right = float(self.get_parameter("ticks_per_meter_right").value)

        self.m_sign = [
            float(self.get_parameter("m1_sign").value),
            float(self.get_parameter("m2_sign").value),
            float(self.get_parameter("m3_sign").value),
            float(self.get_parameter("m4_sign").value),
        ]

        self.query_hz = float(self.get_parameter("query_hz").value)
        self.cmd_timeout = float(self.get_parameter("cmd_timeout").value)

        self.ser = serial.Serial(self.port, self.baud, timeout=0.02)

        self.get_logger().info(f"serial opened: {self.port}, baud={self.baud}")

        # 启动时解除急停、电机使能、停止
        self.send_serial_cmd("u")
        self.send_serial_cmd("m")
        self.send_serial_cmd("0")

        self.rx_buf = b""

        self.total_now = [None, None, None, None]
        self.total_last = None

        self.x = 0.0
        self.y = 0.0
        self.th = 0.0
        self.last_odom_time = None

        self.current_serial_cmd = "0"
        self.last_cmd_time = self.get_clock().now()

        self.odom_pub = self.create_publisher(Odometry, "/odom", 20)
        self.tf_broadcaster = TransformBroadcaster(self)

        self.cmd_sub = self.create_subscription(
            Twist,
            "/cmd_vel",
            self.cmd_vel_callback,
            10
        )

        self.read_timer = self.create_timer(0.02, self.read_serial_timer)
        self.query_timer = self.create_timer(1.0 / self.query_hz, self.query_status_timer)
        self.cmd_timer = self.create_timer(0.05, self.cmd_timeout_timer)

        self.get_logger().info("car_serial_odom_node started.")
        self.get_logger().info("subscribe: /cmd_vel")
        self.get_logger().info("publish: /odom and odom->base_link tf")

    def send_serial_cmd(self, cmd):
        try:
            data = (cmd + "\n").encode("utf-8")
            self.ser.write(data)
            self.ser.flush()
        except Exception as e:
            self.get_logger().error(f"serial send failed: {e}")

    def query_status_timer(self):
        # STM32 里 g 是打印状态，会包含 M1/M2/M3/M4 total
        self.send_serial_cmd("g")

    def cmd_vel_callback(self, msg):
        linear_x = msg.linear.x
        angular_z = msg.angular.z

        # 先处理转向，后处理直行
        if angular_z > 0.05:
            cmd = "7"      # 左转
        elif angular_z < -0.05:
            cmd = "8"      # 右转
        elif linear_x > 0.05:
            cmd = "1"      # 前进
        elif linear_x < -0.05:
            cmd = "2"      # 后退
        else:
            cmd = "0"      # 停止

        self.last_cmd_time = self.get_clock().now()

        if cmd != self.current_serial_cmd:
            self.send_serial_cmd(cmd)
            self.current_serial_cmd = cmd
            self.get_logger().info(f"cmd_vel -> serial cmd: {cmd}")

    def cmd_timeout_timer(self):
        now = self.get_clock().now()
        dt = (now - self.last_cmd_time).nanoseconds / 1e9

        if dt > self.cmd_timeout and self.current_serial_cmd != "0":
            self.send_serial_cmd("0")
            self.current_serial_cmd = "0"
            self.get_logger().warn("cmd_vel timeout, send stop 0")

    def read_serial_timer(self):
        try:
            data = self.ser.read(self.ser.in_waiting or 1)
        except Exception as e:
            self.get_logger().error(f"serial read failed: {e}")
            return

        if not data:
            return

        self.rx_buf += data

        while b"\n" in self.rx_buf:
            line, self.rx_buf = self.rx_buf.split(b"\n", 1)
            text = line.decode(errors="ignore").strip()
            if text:
                self.parse_line(text)

    def parse_line(self, text):
        # 兼容 STM32 当前输出：
        # M1 pwm=0 d10=0 total=123
        m = re.search(r"M([1-4])\s+pwm=(-?\d+)\s+d10=(-?\d+)\s+total=(-?\d+)", text)
        if not m:
            return

        motor_id = int(m.group(1))
        total = int(m.group(4))

        self.total_now[motor_id - 1] = total

        # STM32 状态顺序是 M1 M2 M3 M4，收到 M4 后更新一次里程计
        if motor_id == 4 and all(v is not None for v in self.total_now):
            self.update_odom(self.total_now[:])

    def update_odom(self, total):
        now = self.get_clock().now()

        if self.total_last is None:
            self.total_last = total
            self.last_odom_time = now
            return

        dt = (now - self.last_odom_time).nanoseconds / 1e9
        if dt <= 0.001:
            return

        d = [
            total[0] - self.total_last[0],
            total[1] - self.total_last[1],
            total[2] - self.total_last[2],
            total[3] - self.total_last[3],
        ]

        self.total_last = total
        self.last_odom_time = now

        # 左侧：M1 左前，M2 左后
        # 右侧：M3 右后，M4 右前
        left_ticks = (self.m_sign[0] * d[0] + self.m_sign[1] * d[1]) / 2.0
        right_ticks = (self.m_sign[2] * d[2] + self.m_sign[3] * d[3]) / 2.0

        dl = left_ticks / self.ticks_per_meter_left
        dr = right_ticks / self.ticks_per_meter_right

        ds = (dl + dr) / 2.0
        dth = (dr - dl) / self.track_width

        mid_th = self.th + dth / 2.0

        self.x += ds * math.cos(mid_th)
        self.y += ds * math.sin(mid_th)
        self.th = norm_angle(self.th + dth)

        v = ds / dt
        w = dth / dt

        self.publish_odom(now, v, w)

    def publish_odom(self, stamp, v, w):
        qz = math.sin(self.th / 2.0)
        qw = math.cos(self.th / 2.0)

        odom = Odometry()
        odom.header.stamp = stamp.to_msg()
        odom.header.frame_id = self.odom_frame
        odom.child_frame_id = self.base_frame

        odom.pose.pose.position.x = self.x
        odom.pose.pose.position.y = self.y
        odom.pose.pose.position.z = 0.0

        odom.pose.pose.orientation.x = 0.0
        odom.pose.pose.orientation.y = 0.0
        odom.pose.pose.orientation.z = qz
        odom.pose.pose.orientation.w = qw

        odom.twist.twist.linear.x = v
        odom.twist.twist.angular.z = w

        # 简单协方差，后面可以再调
        odom.pose.covariance[0] = 0.05
        odom.pose.covariance[7] = 0.05
        odom.pose.covariance[35] = 0.10

        odom.twist.covariance[0] = 0.10
        odom.twist.covariance[35] = 0.20

        self.odom_pub.publish(odom)

        if self.publish_tf:
            tf = TransformStamped()
            tf.header.stamp = stamp.to_msg()
            tf.header.frame_id = self.odom_frame
            tf.child_frame_id = self.base_frame

            tf.transform.translation.x = self.x
            tf.transform.translation.y = self.y
            tf.transform.translation.z = 0.0

            tf.transform.rotation.x = 0.0
            tf.transform.rotation.y = 0.0
            tf.transform.rotation.z = qz
            tf.transform.rotation.w = qw

            self.tf_broadcaster.sendTransform(tf)

    def destroy_node(self):
        try:
            self.send_serial_cmd("0")
            self.ser.close()
        except Exception:
            pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = CarSerialOdomNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.get_logger().info("stopping car, closing serial.")
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
