#!/usr/bin/env python3
import serial
import time
import sys
import os

PORT = "/dev/ttyUSB0"
BAUD = 115200

if len(sys.argv) >= 2:
    PORT = sys.argv[1]

HELP_TEXT = """
================ RDK X5 -> STM32 串口控制指令 ================

【小车运动】
0 : 停止所有电机
1 : 小车前进
2 : 小车后退
7 : 小车左转
8 : 小车右转

【喷头 / 执行机构舵机，原来的 PCA9685 舵机】
L / l : 喷头 / 执行机构转左
R / r : 喷头 / 执行机构转右
Z / z : 喷头 / 执行机构复位

【摄像头二自由度云台，新加两个舵机】
a / A : 摄像头云台看左边
d / D : 摄像头云台看右边
c / C : 摄像头云台回中
w / W : 摄像头抬头
s / S : 摄像头低头
v / V : 摄像头俯仰回默认角度

【水泵】
p : 水泵1开关切换，清水泵
q : 水泵2开关切换，药泵 / 施肥泵
P : 单独关闭水泵1
Q : 单独关闭水泵2
x : 两个水泵全部关闭

【安全】
k : 急停锁定
u / U : 解除急停
m : 电机使能
n : 电机失能

【调试】
g : 打印状态
h : 打印帮助

exit / q! : 退出本程序
============================================================
"""

VALID_CMDS = {
    "0", "1", "2", "7", "8",

    "L", "l", "R", "r", "Z", "z",

    "a", "A", "d", "D", "c", "C",
    "w", "W", "s", "S", "v", "V",

    "p", "q", "P", "Q", "x",

    "k", "u", "U", "m", "n",

    "g", "h"
}

def open_serial(port):
    print("正在打开串口:", port)

    if not os.path.exists(port):
        print("串口不存在:", port)
        print("请执行：")
        print("ls -l /dev/ttyUSB* /dev/ttyACM* /dev/ttyS*")
        sys.exit(1)

    try:
        ser = serial.Serial(
            port=port,
            baudrate=BAUD,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.2
        )

        time.sleep(1)
        print("串口打开成功:", port)
        return ser

    except Exception as e:
        print("串口打开失败:", e)
        print("可以尝试：")
        print("sudo chmod 666", port)
        sys.exit(1)

def read_reply(ser):
    time.sleep(0.1)

    try:
        data = ser.read_all()
        if data:
            text = data.decode("utf-8", errors="ignore")
            print("STM32 -> RDK:")
            print(text.strip())
        else:
            print("STM32 -> RDK: 无返回")

    except Exception as e:
        print("读取返回失败:", e)

def send_cmd(ser, cmd):
    """
    注意：
    STM32 现在是单字符指令，所以这里发送单个字母/数字即可。
    不需要加 \\n。
    """
    try:
        ser.write(cmd.encode("utf-8"))
        ser.flush()
        print("RDK -> STM32:", cmd)
        read_reply(ser)

    except Exception as e:
        print("发送失败:", e)

def main():
    ser = open_serial(PORT)

    print(HELP_TEXT)

    try:
        while True:
            cmd = input("请输入指令: ").strip()

            if cmd in ["exit", "q!"]:
                print("退出程序，发送停止和关闭水泵")
                send_cmd(ser, "0")
                send_cmd(ser, "x")
                send_cmd(ser, "c")
                send_cmd(ser, "v")
                break

            if cmd == "":
                continue

            if cmd not in VALID_CMDS:
                print("无效指令，请输入 h 查看 STM32 帮助")
                continue

            send_cmd(ser, cmd)

    except KeyboardInterrupt:
        print("\n检测到 Ctrl+C，发送安全关闭指令")
        send_cmd(ser, "0")
        send_cmd(ser, "x")
        send_cmd(ser, "c")
        send_cmd(ser, "v")

    finally:
        ser.close()
        print("串口已关闭")

if __name__ == "__main__":
    main()
