#!/usr/bin/env python3
# coding: utf-8

import argparse
import json
import time
import urllib.request
import urllib.error

try:
    import serial
except ImportError:
    print("[ERROR] 没有安装 python3-serial")
    print("请执行：sudo apt install -y python3-serial")
    raise


VALID_CMDS = {
    "START_AUTO",
    "STOP_TASK",
    "ESTOP",
    "TEST_WATER_L",
    "TEST_WATER_R",
    "TEST_SPRAY_L",
    "TEST_SPRAY_R",
    "CLEAR_REPORT",
    "MOCK_UAV_ABNORMAL",
}


def now_str():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def post_json(url, data, timeout=1.5):
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        resp_body = resp.read().decode("utf-8", errors="ignore")
        return resp.status, resp_body


class GroundStationButtonBridge:
    def __init__(self, port, baud, car_url, dry_run=False, forward_clear=False, ack=False):
        self.port = port
        self.baud = baud
        self.car_url = car_url
        self.dry_run = dry_run
        self.forward_clear = forward_clear
        self.ack = ack

        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.1
        )

        print("[OK] 地面站按钮串口桥接程序启动")
        print(f"[OK] 串口: {self.port}, baud={self.baud}")
        print(f"[OK] 小车RDK接口: {self.car_url}")
        print(f"[OK] dry_run={self.dry_run}")
        print("等待 STM32 按钮命令...\n")

    def build_payload(self, cmd):
        t = now_str()

        if cmd == "MOCK_UAV_ABNORMAL":
            return {
                "cmd": "UAV_ABNORMAL_TASK",
                "source": "stm32_button_panel",
                "time": t,
                "target": {
                    "id": 1,
                    "type": "bad_leaf",
                    "side": "left",
                    "x": 2.0,
                    "y": 1.0,
                    "action": "spray"
                }
            }

        return {
            "cmd": cmd,
            "source": "stm32_button_panel",
            "time": t
        }

    def handle_clear_report(self):
        print("[GROUND] 清空地面站异常报告")

        try:
            report_file = "/home/sunrise/agri_ground_station/abnormal_report.json"
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            print(f"[OK] 已清空: {report_file}")
        except Exception as e:
            print(f"[WARN] 清空本地异常报告文件失败: {e}")

    def send_to_car(self, cmd):
        if cmd == "CLEAR_REPORT" and not self.forward_clear:
            self.handle_clear_report()
            return True

        payload = self.build_payload(cmd)

        if self.dry_run:
            print("[DRY-RUN] 不发送网络，只打印数据:")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return True

        try:
            status, resp = post_json(self.car_url, payload)
            if status == 200:
                print(f"[OK] 已发送给小车 RDK: {payload['cmd']}")
                return True
            else:
                print(f"[ERROR] 小车 RDK 返回异常: HTTP {status}, {resp}")
                return False

        except urllib.error.URLError as e:
            print(f"[ERROR] 发送失败，检查小车RDK IP、端口、服务是否启动: {e}")
            return False
        except Exception as e:
            print(f"[ERROR] 发送失败: {e}")
            return False

    def send_ack_to_stm32(self, ok=True):
        if not self.ack:
            return

        try:
            msg = "OK\r\n" if ok else "ERR\r\n"
            self.ser.write(msg.encode("utf-8"))
            self.ser.flush()
        except Exception as e:
            print(f"[WARN] 回传ACK失败: {e}")

    def loop(self):
        while True:
            try:
                raw = self.ser.readline()
                if not raw:
                    continue

                line = raw.decode("utf-8", errors="ignore").strip()
                line = line.replace("\x00", "")

                if not line:
                    continue

                print(f"[STM32] 收到按钮命令: {line}")

                if line not in VALID_CMDS:
                    print(f"[WARN] 未知命令，已忽略: {line}")
                    self.send_ack_to_stm32(False)
                    continue

                ok = self.send_to_car(line)
                self.send_ack_to_stm32(ok)

            except KeyboardInterrupt:
                print("\n[EXIT] 退出")
                break

            except Exception as e:
                print(f"[ERROR] 主循环异常: {e}")
                time.sleep(0.5)


def main():
    parser = argparse.ArgumentParser(description="STM32按钮面板 -> 地面站RDK -> 小车RDKX5")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="STM32连接到地面站RDK的串口")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--car-url", default="http://192.168.1.120:8000/api/cmd", help="小车RDKX5接收命令的HTTP接口")
    parser.add_argument("--dry-run", action="store_true", help="只测试串口，不发送给小车RDK")
    parser.add_argument("--forward-clear", action="store_true", help="CLEAR_REPORT也转发给小车RDK")
    parser.add_argument("--ack", action="store_true", help="收到命令后给STM32回传OK/ERR")
    args = parser.parse_args()

    bridge = GroundStationButtonBridge(
        port=args.port,
        baud=args.baud,
        car_url=args.car_url,
        dry_run=args.dry_run,
        forward_clear=args.forward_clear,
        ack=args.ack
    )

    bridge.loop()


if __name__ == "__main__":
    main()
