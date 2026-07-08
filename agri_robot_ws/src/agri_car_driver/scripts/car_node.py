#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import serial

class CAR(Node):
    def __init__(self):
        super().__init__('car_node')

        self.declare_parameter('port', '/dev/ttyUSB0')
        self.ser = serial.Serial(self.get_parameter('port').value,115200)

        self.sub = self.create_subscription(
            String,
            '/cmd_car',
            self.cb,
            10)

    def cb(self, msg):
        cmd = msg.data
        self.ser.write(cmd.encode())

def main():
    rclpy.init()
    node = CAR()
    rclpy.spin(node)

if __name__ == '__main__':
    main()

