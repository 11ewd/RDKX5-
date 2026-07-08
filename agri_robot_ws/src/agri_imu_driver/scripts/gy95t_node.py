#!/usr/bin/env python3
# coding: utf-8

import math
import serial

import rclpy
from rclpy.node import Node

from sensor_msgs.msg import Imu, Temperature
from geometry_msgs.msg import Vector3Stamped
from std_msgs.msg import Float32


FRAME_HEAD = bytes([0xA4, 0x03, 0x08, 0x1B])
FRAME_LEN = 32
G = 9.80665


def int16_le(data, offset):
    return int.from_bytes(data[offset:offset + 2], byteorder='little', signed=True)


def norm_deg(a):
    while a > 180.0:
        a -= 360.0
    while a < -180.0:
        a += 360.0
    return a


def euler_to_quaternion(roll, pitch, yaw):
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)

    qx = sr * cp * cy - cr * sp * sy
    qy = cr * sp * cy + sr * cp * sy
    qz = cr * cp * sy - sr * sp * cy
    qw = cr * cp * cy + sr * sp * sy
    return qx, qy, qz, qw


class GY95TNode(Node):
    def __init__(self):
        super().__init__('gy95t_node')

        self.declare_parameter('port', '/dev/ttyUSB0')
        self.declare_parameter('baud', 115200)
        self.declare_parameter('frame_id', 'imu_link')

        # 角度修正参数。装反、方向不对时改这些，不要先改代码。
        self.declare_parameter('yaw_offset_deg', 0.0)
        self.declare_parameter('invert_roll', False)
        self.declare_parameter('invert_pitch', False)
        self.declare_parameter('invert_yaw', False)

        # GY95T 说明书中角度是 /100，准确。
        # 加速度和陀螺仪说明书称为“原始数据”，这里给默认换算参数，后续可根据实际标定改。
        # 常见配置：加速度 2048 LSB/g，陀螺仪 16.4 LSB/(deg/s)
        self.declare_parameter('accel_lsb_per_g', 2048.0)
        self.declare_parameter('gyro_lsb_per_dps', 16.4)

        self.port = self.get_parameter('port').value
        self.baud = int(self.get_parameter('baud').value)
        self.frame_id = self.get_parameter('frame_id').value

        self.yaw_offset_deg = float(self.get_parameter('yaw_offset_deg').value)
        self.invert_roll = bool(self.get_parameter('invert_roll').value)
        self.invert_pitch = bool(self.get_parameter('invert_pitch').value)
        self.invert_yaw = bool(self.get_parameter('invert_yaw').value)

        self.accel_lsb_per_g = float(self.get_parameter('accel_lsb_per_g').value)
        self.gyro_lsb_per_dps = float(self.get_parameter('gyro_lsb_per_dps').value)

        self.imu_pub = self.create_publisher(Imu, '/imu/data', 20)
        self.euler_pub = self.create_publisher(Vector3Stamped, '/imu/euler_deg', 20)
        self.yaw_pub = self.create_publisher(Float32, '/imu/yaw_deg', 20)
        self.temp_pub = self.create_publisher(Temperature, '/imu/temp', 10)
        self.mag_pub = self.create_publisher(Vector3Stamped, '/imu/mag_raw', 10)

        self.buf = bytearray()
        self.frame_count = 0
        self.bad_count = 0

        try:
            self.ser = serial.Serial(
                self.port,
                self.baud,
                timeout=0.0,
                rtscts=False,
                dsrdtr=False
            )
        except Exception as e:
            self.get_logger().error(f'Open serial failed: {self.port}, {e}')
            raise

        self.get_logger().info(f'GY95T started: port={self.port}, baud={self.baud}')

        # 200Hz 模块也能读，定时器 2ms 轮询串口。
        self.timer = self.create_timer(0.002, self.poll_serial)

    def checksum_ok(self, frame):
        return (sum(frame[:-1]) & 0xFF) == frame[-1]

    def poll_serial(self):
        try:
            n = self.ser.in_waiting
            data = self.ser.read(n if n > 0 else 1)
        except Exception as e:
            self.get_logger().error(f'Serial read error: {e}')
            return

        if data:
            self.buf.extend(data)

        self.parse_frames()

    def parse_frames(self):
        while True:
            idx = self.buf.find(FRAME_HEAD)

            if idx < 0:
                # 保留最后 3 字节，防止帧头被切开。
                if len(self.buf) > 3:
                    del self.buf[:-3]
                return

            if idx > 0:
                del self.buf[:idx]

            if len(self.buf) < FRAME_LEN:
                return

            frame = bytes(self.buf[:FRAME_LEN])

            if not self.checksum_ok(frame):
                self.bad_count += 1
                del self.buf[0]
                if self.bad_count % 50 == 0:
                    self.get_logger().warn(f'Bad checksum count={self.bad_count}')
                continue

            del self.buf[:FRAME_LEN]
            self.handle_frame(frame)

    def handle_frame(self, frame):
        now = self.get_clock().now().to_msg()

        # frame 格式：
        # A4 03 08 1B + 27字节寄存器数据 + checksum
        d = frame[4:31]

        acc_x_raw = int16_le(d, 0)
        acc_y_raw = int16_le(d, 2)
        acc_z_raw = int16_le(d, 4)

        gyro_x_raw = int16_le(d, 6)
        gyro_y_raw = int16_le(d, 8)
        gyro_z_raw = int16_le(d, 10)

        roll_deg = int16_le(d, 12) / 100.0
        pitch_deg = int16_le(d, 14) / 100.0
        yaw_deg = int16_le(d, 16) / 100.0

        level = d[18]
        temp_c = int16_le(d, 19) / 100.0

        mag_x_raw = int16_le(d, 21)
        mag_y_raw = int16_le(d, 23)
        mag_z_raw = int16_le(d, 25)

        if self.invert_roll:
            roll_deg = -roll_deg
        if self.invert_pitch:
            pitch_deg = -pitch_deg
        if self.invert_yaw:
            yaw_deg = -yaw_deg

        yaw_deg = norm_deg(yaw_deg + self.yaw_offset_deg)

        roll = math.radians(roll_deg)
        pitch = math.radians(pitch_deg)
        yaw = math.radians(yaw_deg)

        qx, qy, qz, qw = euler_to_quaternion(roll, pitch, yaw)

        imu = Imu()
        imu.header.stamp = now
        imu.header.frame_id = self.frame_id

        imu.orientation.x = qx
        imu.orientation.y = qy
        imu.orientation.z = qz
        imu.orientation.w = qw

        imu.angular_velocity.x = (gyro_x_raw / self.gyro_lsb_per_dps) * math.pi / 180.0
        imu.angular_velocity.y = (gyro_y_raw / self.gyro_lsb_per_dps) * math.pi / 180.0
        imu.angular_velocity.z = (gyro_z_raw / self.gyro_lsb_per_dps) * math.pi / 180.0

        imu.linear_acceleration.x = (acc_x_raw / self.accel_lsb_per_g) * G
        imu.linear_acceleration.y = (acc_y_raw / self.accel_lsb_per_g) * G
        imu.linear_acceleration.z = (acc_z_raw / self.accel_lsb_per_g) * G

        imu.orientation_covariance = [
            0.05, 0.0, 0.0,
            0.0, 0.05, 0.0,
            0.0, 0.0, 0.10
        ]
        imu.angular_velocity_covariance = [
            0.10, 0.0, 0.0,
            0.0, 0.10, 0.0,
            0.0, 0.0, 0.10
        ]
        imu.linear_acceleration_covariance = [
            0.20, 0.0, 0.0,
            0.0, 0.20, 0.0,
            0.0, 0.0, 0.20
        ]

        self.imu_pub.publish(imu)

        euler = Vector3Stamped()
        euler.header.stamp = now
        euler.header.frame_id = self.frame_id
        euler.vector.x = roll_deg
        euler.vector.y = pitch_deg
        euler.vector.z = yaw_deg
        self.euler_pub.publish(euler)

        yaw_msg = Float32()
        yaw_msg.data = float(yaw_deg)
        self.yaw_pub.publish(yaw_msg)

        temp = Temperature()
        temp.header.stamp = now
        temp.header.frame_id = self.frame_id
        temp.temperature = temp_c
        temp.variance = 0.0
        self.temp_pub.publish(temp)

        mag = Vector3Stamped()
        mag.header.stamp = now
        mag.header.frame_id = self.frame_id
        mag.vector.x = float(mag_x_raw)
        mag.vector.y = float(mag_y_raw)
        mag.vector.z = float(mag_z_raw)
        self.mag_pub.publish(mag)

        self.frame_count += 1
        if self.frame_count % 100 == 0:
            self.get_logger().info(
                f'roll={roll_deg:.2f}, pitch={pitch_deg:.2f}, yaw={yaw_deg:.2f}, '
                f'temp={temp_c:.2f}, level={level}, bad={self.bad_count}'
            )


def main(args=None):
    rclpy.init(args=args)
    node = GY95TNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            node.ser.close()
        except Exception:
            pass

        try:
            node.destroy_node()
        except Exception:
            pass

        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass


if __name__ == '__main__':
    main()
