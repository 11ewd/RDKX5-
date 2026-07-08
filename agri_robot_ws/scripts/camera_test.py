#!/usr/bin/env python3
import cv2
import time
import os
import argparse
from datetime import datetime

def open_camera(device, width, height, fps):
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)

    if not cap.isOpened():
        print(f"无法打开摄像头: /dev/video{device}")
        return None

    # 优先使用 MJPG，很多 USB 摄像头这样更流畅
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)

    real_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    real_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    real_fps = cap.get(cv2.CAP_PROP_FPS)

    print("摄像头打开成功")
    print(f"设备: /dev/video{device}")
    print(f"分辨率: {real_w} x {real_h}")
    print(f"FPS: {real_fps}")

    return cap

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", type=int, default=0, help="摄像头编号，例如 /dev/video0 就填 0")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--show", action="store_true", help="显示实时画面，有屏幕时使用")
    parser.add_argument("--save", action="store_true", help="自动保存截图")
    parser.add_argument("--save_dir", type=str, default=os.path.expanduser("~/agri_robot_ws/images"))
    args = parser.parse_args()

    os.makedirs(args.save_dir, exist_ok=True)

    cap = open_camera(args.device, args.width, args.height, args.fps)
    if cap is None:
        return

    frame_count = 0
    last_time = time.time()
    last_save_time = time.time()

    print("开始采集画面")
    print("按 Ctrl+C 退出")
    if args.show:
        print("显示模式：按 q 也可以退出")
    if args.save:
        print("保存模式：每 3 秒保存一张图片")

    try:
        while True:
            ret, frame = cap.read()

            if not ret or frame is None:
                print("读取画面失败")
                time.sleep(0.1)
                continue

            frame_count += 1
            now = time.time()

            # 每秒打印一次实际帧率
            if now - last_time >= 1.0:
                print(f"当前采集 FPS: {frame_count}")
                frame_count = 0
                last_time = now

            # 显示画面
            if args.show:
                cv2.imshow("RDK X5 Camera", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break

            # 自动保存截图
            if args.save and now - last_save_time >= 3.0:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = os.path.join(args.save_dir, f"camera_{ts}.jpg")
                cv2.imwrite(filename, frame)
                print("已保存截图:", filename)
                last_save_time = now

    except KeyboardInterrupt:
        print("\n退出摄像头采集")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("摄像头已关闭")

if __name__ == "__main__":
    main()
