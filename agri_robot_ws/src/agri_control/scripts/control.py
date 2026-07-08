import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, String

class CTRL(Node):
    def __init__(self):
        super().__init__('ctrl')

        self.yaw = None
        self.start = None

        self.pub = self.create_publisher(String,'/cmd_car',10)

        self.create_subscription(Float32,'/imu/yaw',self.cb,10)

    def cb(self,msg):
        self.yaw = msg.data

    def turn_left_90(self):
        self.start = self.yaw
        self.pub.publish(String(data='7'))

        while True:
            if self.yaw is None:
                continue
            if abs(self.yaw - self.start) > 85:
                break

        self.pub.publish(String(data='0'))

def main():
    rclpy.init()
    node = CTRL()
    node.turn_left_90()

if __name__=='__main__':
    main()

