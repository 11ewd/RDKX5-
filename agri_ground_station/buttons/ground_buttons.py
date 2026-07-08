#!/usr/bin/env python3
# coding: utf-8

import time
import glob
import argparse
import requests
from dataclasses import dataclass

import gpiod


# 改成你小车 RDK 的 IP
CAR_RDK_URL = "http://192.168.1.120:8000/api/cmd"


@dataclass
class ButtonCfg:
    name: str
    pin: int
    line_names: list
    cmd: str
    desc: str


BUTTONS = [
    ButtonCfg("BTN_START_AUTO", 11, ["LSIO_UART7_TX_3V3", "LSIO_UART7_TX"], "START_AUTO", "开始自动任务"),
    ButtonCfg("BTN_STOP_TASK", 13, ["LSIO_UART7_RX_3V3", "LSIO_UART7_RX"], "STOP_TASK", "停止任务"),
    ButtonCfg("BTN_ESTOP", 15, ["LSIO_UART2_TX_3V3", "LSIO_UART2_TX"], "ESTOP", "急停"),

    ButtonCfg("BTN_WATER_LEFT", 16, ["LSIO_UART6_TX_3V3", "LSIO_UART6_TX"], "TEST_WATER_L", "左侧浇水测试"),
    ButtonCfg("BTN_WATER_RIGHT", 18, ["LSIO_SPI2_MOSI_PWM3_3V3", "LSIO_SPI2_MOSI_PWM3"], "TEST_WATER_R", "右侧浇水测试"),

    ButtonCfg("BTN_SPRAY_LEFT", 22, ["LSIO_UART2_RX_3V3", "LSIO_UART2_RX"], "TEST_SPRAY_L", "左侧喷药测试"),
    ButtonCfg("BTN_SPRAY_RIGHT", 24, ["LSIO_SPI1_CS1_3V3", "LSIO_SPI1_CS1"], "TEST_SPRAY_R", "右侧喷药测试"),

    ButtonCfg("BTN_CLEAR_REPORT", 26, ["LSIO_SPI1_CS0_3V3", "LSIO_SPI1_CS0"], "CLEAR_REPORT", "清空异常报告"),
    ButtonCfg("BTN_MOCK_UAV_ABNORMAL", 32, ["LSIO_PWM6_SCL1_3V3", "LSIO_PWM6_SCL1"], "MOCK_UAV_ABNORMAL", "生成无人机异常任务"),
]


def get_chip_line_count(chip):
    if hasattr(chip, "num_lines"):
        n = chip.num_lines
        if callable(n):
            return n()
        return n
    raise RuntimeError("当前 python3-libgpiod 不支持 num_lines")


def get_line_name(line):
    try:
        n = line.name
        if callable(n):
            return n()
        return n
    except Exception:
        return ""


def find_gpio_line(line_names):
    chip_paths = sorted(glob.glob("/dev/gpiochip*"))

    for chip_path in chip_paths:
        try:
            chip = gpiod.Chip(chip_path)
            count = get_chip_line_count(chip)
        except Exception:
            continue

        for offset in range(count):
            try:
                line = chip.get_line(offset)
                name = get_line_name(line) or ""

                for target in line_names:
                    if name == target or target in name:
                        return chip, line, chip_path, offset, name

            except Exception:
                continue

    return None, None, None, None, None


def print_useful_gpioinfo():
    print("\n[INFO] 没找到对应 GPIO line。请执行下面命令查看 RDK 暴露出来的 GPIO 名字：")
    print("gpioinfo | grep -E \"LSIO_UART7|LSIO_UART2|LSIO_UART6|SPI1_CS|SPI2_MOSI|PWM6\"")
    print("\n如果 grep 没有输出，就直接执行：")
    print("gpioinfo")
    print("\n然后把输出发我，我给你改成精确 chip/line。")


class GroundButtonPanel:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.lines = []
        self.last_level = {}
        self.last_time = {}
        self.debounce_s = 0.25

        for cfg in BUTTONS:
            chip, line, chip_path, offset, real_name = find_gpio_line(cfg.line_names)

            if line is None:
                print(f"[ERROR] 找不到 {cfg.desc}：Pin {cfg.pin}, 目标名字 {cfg.line_names}")
                print_useful_gpioinfo()
                raise SystemExit(1)

            flags = 0
            if hasattr(gpiod, "LINE_REQ_FLAG_BIAS_PULL_UP"):
                flags = gpiod.LINE_REQ_FLAG_BIAS_PULL_UP

            try:
                line.request(
                    consumer="ground_station_buttons",
                    type=gpiod.LINE_REQ_DIR_IN,
                    flags=flags
                )
            except Exception as e:
                print(f"[WARN] {cfg.desc} 内部上拉申请失败，改用普通输入：{e}")
                print("       建议每个按钮外接 10k 上拉电阻到 3.3V。")
                line.request(
                    consumer="ground_station_buttons",
                    type=gpiod.LINE_REQ_DIR_IN
                )

            self.lines.append((cfg, line))
            self.last_level[cfg.name] = 1
            self.last_time[cfg.name] = 0

            print(f"[OK] {cfg.desc:12s} Pin {cfg.pin:<2d} -> {chip_path} line {offset:<3d} name={real_name}")

        print("\n[OK] 地面站 9 个实体按钮初始化完成")
        print("[RUN] 按 Ctrl+C 退出\n")

    def send_cmd_to_car(self, cfg):
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[BUTTON] {cfg.desc} -> {cfg.cmd}")

        if cfg.cmd == "CLEAR_REPORT":
            print("[GROUND] 清空地面站异常报告")
            return

        if cfg.cmd == "MOCK_UAV_ABNORMAL":
            data = {
                "cmd": "UAV_ABNORMAL_TASK",
                "source": "ground_station_button",
                "target": {
                    "id": 1,
                    "type": "bad_leaf",
                    "side": "left",
                    "x": 2.0,
                    "y": 1.0,
                    "action": "spray"
                },
                "time": now
            }
        else:
            data = {
                "cmd": cfg.cmd,
                "source": "ground_station_button",
                "time": now
            }

        if self.dry_run:
            print(f"[DRY-RUN] 不发送网络，只打印命令：{data}")
            return

        try:
            r = requests.post(CAR_RDK_URL, json=data, timeout=1.0)
            if r.status_code == 200:
                print(f"[OK] 已发送给小车 RDK：{cfg.cmd}")
            else:
                print(f"[ERROR] 小车 RDK 返回异常：HTTP {r.status_code}")
        except Exception as e:
            print(f"[ERROR] 发送失败，请检查小车 RDK IP 或网络：{e}")

    def loop(self):
        while True:
            for cfg, line in self.lines:
                try:
                    level = line.get_value()
                except Exception as e:
                    print(f"[ERROR] 读取 {cfg.desc} 失败：{e}")
                    continue

                old = self.last_level[cfg.name]
                now = time.time()

                # 按钮接 GPIO-GND：松开=1，按下=0
                if old == 1 and level == 0:
                    if now - self.last_time[cfg.name] >= self.debounce_s:
                        self.send_cmd_to_car(cfg)
                        self.last_time[cfg.name] = now

                self.last_level[cfg.name] = level

            time.sleep(0.02)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只测试按钮，不发送给小车 RDK")
    args = parser.parse_args()

    panel = GroundButtonPanel(dry_run=args.dry_run)
    panel.loop()


if __name__ == "__main__":
    main()
