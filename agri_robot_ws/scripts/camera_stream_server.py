#!/usr/bin/env python3
import cv2
import time
import threading
import argparse
from flask import Flask, Response, render_template_string, jsonify

app = Flask(__name__)

latest_jpg = None
frame_lock = threading.Lock()
running = True
current_fps = 0

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>RDK X5 小车实时画面</title>
    <style>
        body {
            margin: 0;
            background: #f3f6fb;
            font-family: Arial, "Microsoft YaHei", sans-serif;
            text-align: center;
        }
        .header {
            background: #073b88;
            color: white;
            padding: 18px;
            font-size: 28px;
            font-weight: bold;
        }
        .sub {
            margin-top: 6px;
            font-size: 16px;
            color: #dce8ff;
        }
        .box {
            margin: 25px auto;
            width: 760px;
            background: white;
            padding: 18px;
            border-radius: 12px;
            box-shadow: 0 3px 12px rgba(0,0,0,0.15);
        }
        img {
            width: 720px;
            height: 540px;
            object-fit: contain;
            background: #111;
            border-radius: 8px;
        }
        .status {
            margin-top: 15px;
            font-size: 18px;
        }
    </style>
</head>
<body>
    <div class="header">
        RDK X5 小车摄像头实时画面
        <div class="sub">智慧农业陆空协同系统 · 小车近距离复查画面</div>
    </div>

    <div class="box">
        <img src="/video_feed">
        <div class="status">
            摄像头状态：运行中　
            <span id="fps">FPS: --</span>
        </div>
    </div>

    <script>
        setInterval(() => {
            fetch('/status')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('fps').innerText = "FPS: " + data.fps;
                })
                .catch(err => {});
        }, 1000);
    </script>
</body>
</html>
"""

def camera_loop(device, width, height, fps):
    global latest_jpg, running, current_fps

    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)

    if not cap.isOpened():
        print(f"无法打开摄像头 /dev/video{device}")
        running = False
        return

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

    frame_count = 0
    last_time = time.time()

    while running:
        ret, frame = cap.read()

        if not ret or frame is None:
            print("读取摄像头失败")
            time.sleep(0.05)
            continue

        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            with frame_lock:
                latest_jpg = jpg.tobytes()

        frame_count += 1
        now = time.time()

        if now - last_time >= 1.0:
            current_fps = frame_count
            print("当前推流 FPS:", current_fps)
            frame_count = 0
            last_time = now

    cap.release()

def generate_mjpeg():
    while True:
        with frame_lock:
            frame = latest_jpg

        if frame is None:
            time.sleep(0.05)
            continue

        yield b"--frame\r\n"
        yield b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"

        time.sleep(0.03)

@app.route("/")
def index():
    return render_template_string(HTML_PAGE)

@app.route("/video_feed")
def video_feed():
    return Response(
        generate_mjpeg(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

@app.route("/status")
def status():
    return jsonify({
        "camera": "running" if running else "stopped",
        "fps": current_fps
    })

def main():
    global running

    parser = argparse.ArgumentParser()
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--port", type=int, default=8081)
    args = parser.parse_args()

    t = threading.Thread(
        target=camera_loop,
        args=(args.device, args.width, args.height, args.fps),
        daemon=True
    )
    t.start()

    time.sleep(1)

    print("视频流服务启动")
    print(f"本机访问: http://127.0.0.1:{args.port}")
    print(f"其他设备访问: http://小车RDK_IP:{args.port}")
    print("按 Ctrl+C 退出")

    try:
        app.run(host="0.0.0.0", port=args.port, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("退出服务")
    finally:
        running = False
        time.sleep(0.5)

if __name__ == "__main__":
    main()
