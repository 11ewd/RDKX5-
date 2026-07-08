#!/usr/bin/env python3
import serial
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
import struct
import time

READ_CMD = bytes([0xA4, 0x03, 0x08, 0x12, 0xC1])

class IMU(Node):
    def __init__(self):
        super().__init__('imu_node')

        self.declare_parameter('port', '/dev/ttyUSB0')
        self.declare_parameter('baud', 115200)

        port = self.get_parameter('port').value
        baud = self.get_parameter('baud').value

        self.ser = serial.Serial(port, baud, timeout=0.1)
        time.sleep(0.2)

        self.pub = self.create_publisher(Float32, '/imu/yaw', 10)
        self.timer = self.create_timer(0.05, self.loop)

    def read(self):
        try:
            self.ser.reset_input_buffer()
            self.ser.write(READ_CMD)
            time.sleep(0.02)
            buf = self.ser.read(80)

            for i in range(len(buf)-20):
                if buf[i]==0xA4 and buf[i+1]==0x03:
                    data = buf[i+4:i+22]
                    yaw = struct.unpack(">h", data[16:18])[0] / 100.0
                    return yaw
        except:
            return None

    def loop(self):
        yaw = self.read()
        if yaw is not None:
            msg = Float32()
            msg.data = yaw
            self.pub.publish(msg)

def main():
    rclpy.init()
    node = IMU()
    rclpy.spin(node)

if __name__ == '__main__':
    main()
