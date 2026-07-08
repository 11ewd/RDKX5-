#!/usr/bin/env python3
# coding: utf-8

import time
import glob
import gpiod

lines = []
last = {}

print("[INFO] 开始扫描 /dev/gpiochip*")
print("[INFO] 运行后，依次按下你的按钮。哪个 gpiochip/line 变化，就记下来。")
print("[INFO] 按 Ctrl+C 退出\n")

for chip_path in sorted(glob.glob("/dev/gpiochip*")):
    try:
        chip = gpiod.Chip(chip_path)
    except Exception as e:
        print(f"[WARN] 打不开 {chip_path}: {e}")
        continue

    try:
        count = chip.num_lines()
    except TypeError:
        count = chip.num_lines
    except Exception as e:
        print(f"[WARN] 读取 {chip_path} line 数失败: {e}")
        continue

    print(f"[INFO] {chip_path}: {count} lines")

    for offset in range(count):
        try:
            line = chip.get_line(offset)

            flags = 0
            if hasattr(gpiod, "LINE_REQ_FLAG_BIAS_PULL_UP"):
                flags = gpiod.LINE_REQ_FLAG_BIAS_PULL_UP

            try:
                line.request(
                    consumer="scan_gpio_buttons",
                    type=gpiod.LINE_REQ_DIR_IN,
                    flags=flags
                )
            except Exception:
                continue

            v = line.get_value()
            key = f"{chip_path}:{offset}"
            last[key] = v
            lines.append((chip_path, offset, line))

        except Exception:
            continue

print(f"\n[OK] 已监听 {len(lines)} 个可用 GPIO line")
print("[操作] 现在按下按钮，终端会打印变化：")
print("      例如 /dev/gpiochip3 line 12: 1 -> 0")
print("      这个就是这个按钮对应的真实编号。\n")

try:
    while True:
        for chip_path, offset, line in lines:
            key = f"{chip_path}:{offset}"
            try:
                v = line.get_value()
            except Exception:
                continue

            if v != last[key]:
                print(f"[CHANGE] {chip_path} line {offset}: {last[key]} -> {v}")
                last[key] = v

        time.sleep(0.02)

except KeyboardInterrupt:
    print("\n[EXIT] 退出扫描")
