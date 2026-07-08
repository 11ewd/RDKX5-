#!/usr/bin/env python3
# coding: utf-8

import sys
import time
import math
import select
import termios
import tty

import serial

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32


def angle_diff_deg(a, b):
    """
    返回 a - b 的最短角度差，范围 -180 ~ 180
    """
    diff = a - b
    while diff > 180.0:
        diff -= 360.0
    while diff < -180.0:
        diff += 360.0
    return diff


class ImuCarControl(Node):
    def __init__(self):
        super().__init__('imu_car_control')

        # ========== ROS 参数 ==========
        self.declare_parameter('yaw_topic', '/imu/yaw_deg')

        # 这里改成你 STM32 的串口
        # 如果 STM32 是 USB-TTL，可能是 /dev/ttyUSB1
        # 如果你建了软链接，可以用 /dev/carserial
        self.declare_parameter('car_port', '/dev/carserial')
        self.declare_parameter('car_baud', 115200)

        # 下位机命令
        self.declare_parameter('cmd_stop', '0')
        self.declare_parameter('cmd_forward', '1')
        self.declare_parameter('cmd_backward', '2')
        self.declare_parameter('cmd_left', '7')
        self.declare_parameter('cmd_right', '8')

        # 是否每条命令后面加换行
        # 你的 STM32 如果是按单字符解析，保持 False
        self.declare_parameter('send_newline', False)

        # 没接 STM32 时可以 dry_run 测试，只打印不真正发串口
        self.declare_parameter('dry_run', False)

        # 直行纠偏参数
        self.declare_parameter('forward_deadband_deg', 3.0)     # 偏差小于 3° 不修正
        self.declare_parameter('correction_pulse_sec', 0.08)    # 每次修正转向脉冲时间
        self.declare_parameter('forward_cmd_period_sec', 0.25)  # 正常前进命令刷新周期

        # 90 度转弯参数
        self.declare_parameter('turn_angle_deg', 90.0)
        self.declare_parameter('turn_tolerance_deg', 3.0)
        self.declare_parameter('turn_cmd_period_sec', 0.08)

        self.yaw_topic = self.get_parameter('yaw_topic').value
        self.car_port = self.get_parameter('car_port').value
        self.car_baud = int(self.get_parameter('car_baud').value)

        self.cmd_stop = self.get_parameter('cmd_stop').value
        self.cmd_forward = self.get_parameter('cmd_forward').value
        self.cmd_backward = self.get_parameter('cmd_backward').value
        self.cmd_left = self.get_parameter('cmd_left').value
        self.cmd_right = self.get_parameter('cmd_right').value

        self.send_newline = bool(self.get_parameter('send_newline').value)
        self.dry_run = bool(self.get_parameter('dry_run').value)

        self.forward_deadband_deg = float(self.get_parameter('forward_deadband_deg').value)
        self.correction_pulse_sec = float(self.get_parameter('correction_pulse_sec').value)
        self.forward_cmd_period_sec = float(self.get_parameter('forward_cmd_period_sec').value)

        self.turn_angle_deg = float(self.get_parameter('turn_angle_deg').value)
        self.turn_tolerance_deg = float(self.get_parameter('turn_tolerance_deg').value)
        self.turn_cmd_period_sec = float(self.get_parameter('turn_cmd_period_sec').value)

        # ========== 状态变量 ==========
        self.current_yaw = None
        self.target_yaw = None

        self.mode = 'IDLE'
        self.last_cmd_time = 0.0
        self.next_forward_time = 0.0

        self.correction_active = False
        self.correction_end_time = 0.0

        self.last_log_time = 0.0

        # ========== 串口 ==========
        self.ser = None
        if not self.dry_run:
            try:
                self.ser = serial.Serial(
                    self.car_port,
                    self.car_baud,
                    timeout=0.1,
                    rtscts=False,
                    dsrdtr=False
                )
                self.get_logger().info(
                    f'Car serial opened: port={self.car_port}, baud={self.car_baud}'
                )
            except Exception as e:
                self.get_logger().error(f'Open car serial failed: {self.car_port}, {e}')
                self.get_logger().error('可以先加 -p dry_run:=true 测试键盘和 yaw 逻辑')
                raise
        else:
            self.get_logger().warn('DRY RUN MODE: 不会真正发送串口命令，只打印命令')

        # ========== ROS 订阅 ==========
        self.yaw_sub = self.create_subscription(
            Float32,
            self.yaw_topic,
            self.yaw_callback,
            20
        )

        # ========== 键盘 ==========
        self.old_termios = None
        if sys.stdin.isatty():
            self.old_termios = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())

        self.print_help()

        # 50Hz 控制循环
        self.timer = self.create_timer(0.02, self.control_loop)

    def print_help(self):
        self.get_logger().info('')
        self.get_logger().info('========== IMU 小车控制节点 ==========')
        self.get_logger().info('w : IMU 辅助直行，记录当前 yaw 为目标角')
        self.get_logger().info('a : 左转 90 度')
        self.get_logger().info('d : 右转 90 度')
        self.get_logger().info('s / 空格 / 0 : 停止')
        self.get_logger().info('x : 后退')
        self.get_logger().info('1 : 直接前进，不进行 IMU 纠偏')
        self.get_logger().info('7 : 直接左转')
        self.get_logger().info('8 : 直接右转')
        self.get_logger().info('g : 打印当前 yaw')
        self.get_logger().info('q : 退出')
        self.get_logger().info('=====================================')
        self.get_logger().info('')

    def yaw_callback(self, msg):
        self.current_yaw = float(msg.data)

    def send_cmd(self, cmd, reason=''):
        if not cmd:
            return

        data = cmd.encode('utf-8')
        if self.send_newline:
            data += b'\n'

        now = time.monotonic()

        if self.dry_run:
            self.get_logger().info(f'[DRY] send {cmd} {reason}')
        else:
            try:
                self.ser.write(data)
                self.ser.flush()
            except Exception as e:
                self.get_logger().error(f'Serial write failed: {e}')
                return

        self.last_cmd_time = now

        if reason:
            self.get_logger().info(f'send {cmd} : {reason}')

    def get_key(self):
        if not sys.stdin.isatty():
            return None

        dr, _, _ = select.select([sys.stdin], [], [], 0.0)
        if dr:
            return sys.stdin.read(1)
        return None

    def start_forward_hold(self):
        if self.current_yaw is None:
            self.get_logger().warn('还没有收到 /imu/yaw_deg，不能开始 IMU 直行')
            return

        self.mode = 'FORWARD_HOLD'
        self.target_yaw = self.current_yaw
        self.correction_active = False
        self.next_forward_time = 0.0

        self.send_cmd(self.cmd_forward, f'IMU直行开始 target_yaw={self.target_yaw:.2f}')

    def start_turn(self, direction):
        if self.current_yaw is None:
            self.get_logger().warn('还没有收到 /imu/yaw_deg，不能开始转弯')
            return

        start_yaw = self.current_yaw

        if direction == 'LEFT':
            self.target_yaw = self.normalize_deg(start_yaw + self.turn_angle_deg)
            self.mode = 'TURN_LEFT'
            self.send_cmd(
                self.cmd_left,
                f'左转{self.turn_angle_deg:.1f}度 start={start_yaw:.2f}, target={self.target_yaw:.2f}'
            )

        elif direction == 'RIGHT':
            self.target_yaw = self.normalize_deg(start_yaw - self.turn_angle_deg)
            self.mode = 'TURN_RIGHT'
            self.send_cmd(
                self.cmd_right,
                f'右转{self.turn_angle_deg:.1f}度 start={start_yaw:.2f}, target={self.target_yaw:.2f}'
            )

    def stop_car(self, reason='停止'):
        self.mode = 'IDLE'
        self.target_yaw = None
        self.correction_active = False
        self.send_cmd(self.cmd_stop, reason)

    def normalize_deg(self, a):
        while a > 180.0:
            a -= 360.0
        while a < -180.0:
            a += 360.0
        return a

    def handle_key(self, key):
        if key is None:
            return

        if key == 'w':
            self.start_forward_hold()

        elif key == 'a':
            self.start_turn('LEFT')

        elif key == 'd':
            self.start_turn('RIGHT')

        elif key == 's' or key == ' ' or key == '0':
            self.stop_car('键盘停止')

        elif key == 'x':
            self.mode = 'IDLE'
            self.send_cmd(self.cmd_backward, '直接后退')

        elif key == '1':
            self.mode = 'IDLE'
            self.send_cmd(self.cmd_forward, '直接前进，无IMU纠偏')

        elif key == '7':
            self.mode = 'IDLE'
            self.send_cmd(self.cmd_left, '直接左转')

        elif key == '8':
            self.mode = 'IDLE'
            self.send_cmd(self.cmd_right, '直接右转')

        elif key == 'g':
            if self.current_yaw is None:
                self.get_logger().info('current_yaw=None')
            else:
                self.get_logger().info(f'current_yaw={self.current_yaw:.2f}')

        elif key == 'h':
            self.print_help()

        elif key == 'q':
            self.stop_car('退出前停止')
            raise KeyboardInterrupt

    def control_loop(self):
        key = self.get_key()
        if key is not None:
            self.handle_key(key)

        if self.current_yaw is None:
            return

        now = time.monotonic()

        if self.mode == 'FORWARD_HOLD':
            self.forward_hold_loop(now)

        elif self.mode == 'TURN_LEFT' or self.mode == 'TURN_RIGHT':
            self.turn_loop(now)

    def forward_hold_loop(self, now):
        if self.target_yaw is None:
            return

        # 修正脉冲结束后，恢复前进
        if self.correction_active:
            if now >= self.correction_end_time:
                self.correction_active = False
                self.send_cmd(self.cmd_forward, '修正结束，恢复前进')
                self.next_forward_time = now + self.forward_cmd_period_sec
            return

        if now < self.next_forward_time:
            return

        error = angle_diff_deg(self.current_yaw, self.target_yaw)

        # error > 0：当前 yaw 比目标大，说明偏左，需要右修正
        if error > self.forward_deadband_deg:
            self.send_cmd(
                self.cmd_right,
                f'直行右修正 error={error:.2f}, yaw={self.current_yaw:.2f}, target={self.target_yaw:.2f}'
            )
            self.correction_active = True
            self.correction_end_time = now + self.correction_pulse_sec

        # error < 0：当前 yaw 比目标小，说明偏右，需要左修正
        elif error < -self.forward_deadband_deg:
            self.send_cmd(
                self.cmd_left,
                f'直行左修正 error={error:.2f}, yaw={self.current_yaw:.2f}, target={self.target_yaw:.2f}'
            )
            self.correction_active = True
            self.correction_end_time = now + self.correction_pulse_sec

        else:
            self.send_cmd(
                self.cmd_forward,
                f'直行保持 error={error:.2f}, yaw={self.current_yaw:.2f}'
            )
            self.next_forward_time = now + self.forward_cmd_period_sec

    def turn_loop(self, now):
        if self.target_yaw is None:
            return

        if now - self.last_cmd_time < self.turn_cmd_period_sec:
            return

        # target - current
        remain = angle_diff_deg(self.target_yaw, self.current_yaw)

        if abs(remain) <= self.turn_tolerance_deg:
            self.stop_car(
                f'转弯完成 yaw={self.current_yaw:.2f}, target={self.target_yaw:.2f}, remain={remain:.2f}'
            )
            return

        # remain > 0：目标角在当前角左侧，需要左转
        # remain < 0：目标角在当前角右侧，需要右转
        if remain > 0:
            self.send_cmd(
                self.cmd_left,
                f'继续左转 remain={remain:.2f}, yaw={self.current_yaw:.2f}, target={self.target_yaw:.2f}'
            )
        else:
            self.send_cmd(
                self.cmd_right,
                f'继续右转 remain={remain:.2f}, yaw={self.current_yaw:.2f}, target={self.target_yaw:.2f}'
            )

    def destroy_node(self):
        try:
            self.stop_car('节点退出停止')
        except Exception:
            pass

        try:
            if self.ser is not None:
                self.ser.close()
        except Exception:
            pass

        if self.old_termios is not None:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_termios)
            except Exception:
                pass

        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = ImuCarControl()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
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
