#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import time
import select
import termios
import tty
import argparse
import serial


# ============================================================
# 上位机键盘 -> STM32 串口命令
# ============================================================
#
# STM32 当前串口命令：
# 0 : 停止所有电机
# 1 : 小车前进
# 2 : 小车后退
# 7 : 小车左转
# 8 : 小车右转
#
# L / l : 舵机执行左动作
# R / r : 舵机执行右动作
# Z / z : 舵机复位
#
# p : 水泵1开关切换
# q : 水泵2开关切换
# P : 单独关闭水泵1
# Q : 单独关闭水泵2
# x : 两个水泵全部关闭
#
# k : 急停锁定
# U : 解除急停
# m : 电机使能
# n : 电机失能
# g : 打印状态
# h : 打印帮助
#
# 注意：
# q 是水泵2开关，所以退出程序不用 q。
# 本程序使用 ESC 退出，或者 Ctrl+C 退出。
# ============================================================


# =========================
# 键盘按键映射
# =========================
KEY_CMD_MAP = {
    # 小车运动，按住控制
    'w': '1',
    'W': '1',
    's': '2',
    'S': '2',
    'a': '7',
    'A': '7',
    'd': '8',
    'D': '8',

    # 停止
    ' ': '0',

    # 舵机动作
    'l': 'L',
    'L': 'L',
    'r': 'R',
    'R': 'R',
    'z': 'Z',
    'Z': 'Z',

    # 水泵控制
    'p': 'p',     # 水泵1 开/关切换
    'q': 'q',     # 水泵2 开/关切换
    'P': 'P',     # 关闭水泵1
    'Q': 'Q',     # 关闭水泵2
    'x': 'x',     # 两个水泵全关
    'X': 'x',

    # 安全与电机
    'k': 'k',     # 急停锁定
    'K': 'k',
    'u': 'U',     # 解除急停
    'U': 'U',
    'm': 'm',     # 电机使能
    'M': 'm',
    'n': 'n',     # 电机失能
    'N': 'n',

    # 查询
    'g': 'g',
    'G': 'g',
    'h': 'h',
    'H': 'h',
}


# =========================
# 参数调节区
# =========================

# 松开按键后，超过这个时间没有收到键盘重复输入，就自动停车
# 如果直走一卡一卡，调大，比如 0.70 / 0.80
KEY_RELEASE_TIMEOUT = 0.60

# 按住 W/S/A/D 时，每隔多久补发一次运动指令
# 0.06~0.12 都可以
RESEND_INTERVAL = 0.08

# 串口发送后的小延时，防止连续发送太快
SERIAL_SEND_DELAY = 0.005


def print_help():
    print("")
    print("===================================================")
    print("RDK 上位机键盘控制小车 + 舵机 + 水泵")
    print("---------------------------------------------------")
    print("【小车运动】")
    print("按住 W : 小车前进       -> 发送 1")
    print("按住 S : 小车后退       -> 发送 2")
    print("按住 A : 小车左转       -> 发送 7")
    print("按住 D : 小车右转       -> 发送 8")
    print("松开 W/S/A/D : 自动停车 -> 发送 0")
    print("空格 : 立即停车         -> 发送 0")
    print("")
    print("【舵机动作】")
    print("L : 舵机执行左动作      -> 发送 L")
    print("R : 舵机执行右动作      -> 发送 R")
    print("Z : 舵机复位            -> 发送 Z")
    print("")
    print("【水泵控制】")
    print("p : 水泵1 开/关切换     -> 发送 p")
    print("q : 水泵2 开/关切换     -> 发送 q")
    print("P : 单独关闭水泵1       -> 发送 P")
    print("Q : 单独关闭水泵2       -> 发送 Q")
    print("X : 两个水泵全部关闭    -> 发送 x")
    print("")
    print("【安全控制】")
    print("K : 急停锁定            -> 发送 k")
    print("U : 解除急停            -> 发送 U")
    print("M : 电机使能            -> 发送 m")
    print("N : 电机失能            -> 发送 n")
    print("")
    print("【查询】")
    print("G : 打印状态            -> 发送 g")
    print("H : 打印帮助            -> 发送 h")
    print("")
    print("【退出】")
    print("ESC : 退出程序")
    print("Ctrl+C : 退出程序")
    print("---------------------------------------------------")
    print("启动后自动发送：U、m、0、x")
    print("退出前自动发送：0、x")
    print("===================================================")
    print("")


def cmd_name(cmd):
    name_map = {
        '0': '停止所有电机',
        '1': '小车前进',
        '2': '小车后退',
        '7': '小车左转',
        '8': '小车右转',

        'L': '舵机执行左动作',
        'R': '舵机执行右动作',
        'Z': '舵机复位',

        'p': '水泵1开关切换',
        'q': '水泵2开关切换',
        'P': '单独关闭水泵1',
        'Q': '单独关闭水泵2',
        'x': '两个水泵全部关闭',

        'k': '急停锁定',
        'U': '解除急停',
        'm': '电机使能',
        'n': '电机失能',

        'g': '打印状态',
        'h': '打印帮助',
    }
    return name_map.get(cmd, '未知命令')


def is_motion_cmd(cmd):
    return cmd in ['1', '2', '7', '8']


def send_cmd(ser, cmd, show=True):
    """
    向 STM32 发送一条命令。
    你的 STM32 当前按单字节解析，带不带换行都能处理。
    为了兼容你之前的程序，这里发送 cmd + '\\n'。
    """
    try:
        ser.write((cmd + "\n").encode("utf-8"))
        ser.flush()
        time.sleep(SERIAL_SEND_DELAY)

        if show:
            print("{} -> 发送 {}".format(cmd_name(cmd), repr(cmd + "\n")))

    except Exception as e:
        print("串口发送失败:", e)


def main():
    parser = argparse.ArgumentParser(description="RDK keyboard car pump control")

    parser.add_argument(
        "--port",
        default="/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0",
        help="STM32 串口，默认使用固定 by-id 路径"
    )

    parser.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="串口波特率，默认 115200"
    )

    args = parser.parse_args()

    print_help()

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.02)
        time.sleep(0.5)
        print("串口打开成功:", args.port, args.baud)
    except Exception as e:
        print("串口打开失败:", e)
        print("")
        print("可以先查看串口：")
        print("  ls /dev/serial/by-id/")
        print("  ls /dev/ttyUSB*")
        print("")
        print("如果是 /dev/ttyUSB0，则这样运行：")
        print("  python3 ~/agri_robot_ws/keyboard_car_pump_control.py --port /dev/ttyUSB0")
        return

    old_settings = termios.tcgetattr(sys.stdin)

    current_cmd = "0"
    moving = False
    last_key_time = time.time()
    last_send_time = 0.0

    try:
        tty.setcbreak(sys.stdin.fileno())

        # 启动初始化
        print("")
        print("正在初始化小车状态...")
        send_cmd(ser, "U", show=True)     # 解除急停
        time.sleep(0.1)
        send_cmd(ser, "m", show=True)     # 电机使能
        time.sleep(0.1)
        send_cmd(ser, "0", show=True)     # 停车
        time.sleep(0.1)
        send_cmd(ser, "x", show=True)     # 水泵全关
        print("初始化完成，可以开始控制。")
        print("")

        while True:
            now = time.time()

            readable, _, _ = select.select([sys.stdin], [], [], 0.02)

            if readable:
                key = sys.stdin.read(1)
                now = time.time()

                # ESC 退出
                if key == '\x1b':
                    print("")
                    print("收到 ESC，准备退出程序")
                    break

                if key not in KEY_CMD_MAP:
                    continue

                cmd = KEY_CMD_MAP[key]

                # 空格立即停车
                if cmd == '0':
                    send_cmd(ser, '0', show=True)
                    current_cmd = '0'
                    moving = False
                    continue

                # 运动指令：按住 W/S/A/D
                if is_motion_cmd(cmd):
                    last_key_time = now
                    moving = True

                    # 方向变化时立即发送
                    if cmd != current_cmd:
                        send_cmd(ser, cmd, show=True)
                        current_cmd = cmd
                        last_send_time = now

                    continue

                # 非运动命令执行前，不改变 current_cmd
                # 但如果是急停、电机失能、水泵全关等安全命令，强制停止运动状态
                send_cmd(ser, cmd, show=True)

                if cmd in ['k', 'n']:
                    current_cmd = '0'
                    moving = False

                # 如果用户按了水泵、舵机、状态查询，不影响小车继续按住运动
                # 但是实际操作时建议先停车再浇水/动舵机

            # 按住运动键期间，定期补发当前运动指令
            now = time.time()

            if moving and is_motion_cmd(current_cmd):
                if now - last_send_time >= RESEND_INTERVAL:
                    send_cmd(ser, current_cmd, show=False)
                    last_send_time = now

                # 如果超过一定时间没有收到键盘重复输入，认为松手，自动停车
                if now - last_key_time >= KEY_RELEASE_TIMEOUT:
                    send_cmd(ser, "0", show=True)
                    print("检测到松开按键，自动停车")
                    current_cmd = "0"
                    moving = False

    except KeyboardInterrupt:
        print("")
        print("收到 Ctrl+C，准备退出程序")

    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

        try:
            print("")
            print("退出前执行安全关闭...")
            send_cmd(ser, "0", show=True)     # 停车
            time.sleep(0.1)
            send_cmd(ser, "x", show=True)     # 两个水泵全关
            time.sleep(0.1)
            ser.close()
        except Exception:
            pass

        print("程序结束，已发送停车和水泵关闭指令。")


if __name__ == "__main__":
    main()