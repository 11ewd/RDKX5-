#!/usr/bin/env python3
import cv2
import time
import os
import argparse
import requests
from datetime import datetime

def upload_file(url, filepath):
    if not os.path.exists(filepath):
        print("文件不存在，无法上传:", filepath)
        return False

    try:
        with open(filepath, "rb") as f:
            files = {"file": (os.path.basename(filepath), f)}
            r = requests.post(url, files=files, timeout=20)

        if r.status_code == 200:
            print("上传成功:", filepath)
            print("服务器返回:", r.text)
            return True
        else:
            print("上传失败:", filepath)
            print("状态码:", r.status_code)
            print("返回:", r.text)
            return False

    except Exception as e:
        print("上传异常:", e)
        return False

def new_video_writer(video_dir, width, height, fps):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    video_path = os.path.join(video_dir, f"car_video_{ts}.avi")

    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(video_path, fourcc, fps, (width, height))

    if not writer.isOpened():
        print("视频写入器打开失败:", video_path)
        return None, None

    print("开始录制新视频:", video_path)
    return writer, video_path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--station", type=str, required=True, help="显示屏RDK地址，例如 http://192.168.1.100:8090")
    parser.add_argument("--image_interval", type=float, default=3.0, help="每隔几秒上传一张图片")
    parser.add_argument("--video_seconds", type=float, default=10.0, help="每段视频录制多少秒后上传")
    args = parser.parse_args()

    image_dir = os.path.expanduser("~/agri_robot_ws/local_capture/images")
    video_dir = os.path.expanduser("~/agri_robot_ws/local_capture/videos")
    os.makedirs(image_dir, exist_ok=True)
    os.makedirs(video_dir, exist_ok=True)

    image_upload_url = args.station.rstrip("/") + "/upload/image"
    video_upload_url = args.station.rstrip("/") + "/upload/video"

    print("图片上传地址:", image_upload_url)
    print("视频上传地址:", video_upload_url)

    cap = cv2.VideoCapture(args.device, cv2.CAP_V4L2)

    if not cap.isOpened():
        print(f"无法打开摄像头 /dev/video{args.device}")
        return

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)

    real_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    real_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    real_fps = cap.get(cv2.CAP_PROP_FPS)

    print("摄像头打开成功")
    print(f"设备: /dev/video{args.device}")
    print(f"分辨率: {real_w} x {real_h}")
    print(f"FPS: {real_fps}")

    writer, video_path = new_video_writer(video_dir, real_w, real_h, args.fps)
    video_start_time = time.time()
    last_image_time = time.time()
    last_fps_time = time.time()
    frame_count = 0

    try:
        while True:
            ret, frame = cap.read()

            if not ret or frame is None:
                print("读取摄像头失败")
                time.sleep(0.05)
                continue

            now = time.time()
            frame_count += 1

            if writer is not None:
                writer.write(frame)

            if now - last_fps_time >= 1.0:
                print("当前采集 FPS:", frame_count)
                frame_count = 0
                last_fps_time = now

            if now - last_image_time >= args.image_interval:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                img_path = os.path.join(image_dir, f"car_image_{ts}.jpg")
                cv2.imwrite(img_path, frame)
                print("保存图片:", img_path)
                upload_file(image_upload_url, img_path)
                last_image_time = now

            if now - video_start_time >= args.video_seconds:
                if writer is not None:
                    writer.release()
                    print("视频录制完成:", video_path)
                    upload_file(video_upload_url, video_path)

                writer, video_path = new_video_writer(video_dir, real_w, real_h, args.fps)
                video_start_time = now

    except KeyboardInterrupt:
        print("\n退出采集上传程序")

    finally:
        if writer is not None:
            writer.release()
            if video_path is not None:
                print("上传最后一段视频:", video_path)
                upload_file(video_upload_url, video_path)

        cap.release()
        print("摄像头已关闭")

if __name__ == "__main__":
    main()
