#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import cv2
import time
import threading
import argparse
import requests
import numpy as np
from flask import Flask, Response, render_template_string, jsonify

app = Flask(__name__)

latest_jpg = None
frame_lock = threading.Lock()

running = True
current_fps = 0

crop_status = {
    "status": "初始化",
    "green_ratio": 0.0,
    "yellow_ratio": 0.0,
    "brown_ratio": 0.0,
    "brightness": 0.0,
    "suggestion": "等待摄像头画面",
    "upload": "未上传"
}

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>RDK X5 小车作物复查画面</title>
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
        .main {
            width: 1120px;
            margin: 20px auto;
            display: flex;
            gap: 20px;
            justify-content: center;
            align-items: flex-start;
        }
        .video_box {
            width: 760px;
            background: white;
            padding: 18px;
            border-radius: 12px;
            box-shadow: 0 3px 12px rgba(0,0,0,0.15);
        }
        .status_box {
            width: 300px;
            background: white;
            padding: 18px;
            border-radius: 12px;
            box-shadow: 0 3px 12px rgba(0,0,0,0.15);
            text-align: left;
        }
        img {
            width: 720px;
            height: 540px;
            object-fit: contain;
            background: #111;
            border-radius: 8px;
        }
        h2 {
            color: #073b88;
            border-left: 6px solid #073b88;
            padding-left: 10px;
        }
        .item {
            font-size: 18px;
            margin: 14px 0;
        }
        .result {
            font-size: 26px;
            font-weight: bold;
            color: #d35400;
            margin: 18px 0;
        }
        .ok {
            color: #168a37;
        }
        .bad {
            color: #d35400;
        }
        .warn {
            color: #b9770e;
        }
    </style>
</head>
<body>
    <div class="header">
        RDK X5 小车作物近距离复查画面
        <div class="sub">实时视频 + 作物状态检测 + 异常报告自动上传</div>
    </div>

    <div class="main">
        <div class="video_box">
            <img src="/video_feed">
            <div class="item">实时推流 FPS：<span id="fps">--</span></div>
        </div>

        <div class="status_box">
            <h2>作物状态检测</h2>
            <div class="result" id="status">等待检测</div>
            <div class="item">绿色比例：<span id="green">--</span></div>
            <div class="item">黄色比例：<span id="yellow">--</span></div>
            <div class="item">褐色比例：<span id="brown">--</span></div>
            <div class="item">亮度：<span id="brightness">--</span></div>
            <h2>处理建议</h2>
            <div class="item" id="suggestion">等待画面</div>
            <h2>异常上传状态</h2>
            <div class="item" id="upload">未上传</div>
        </div>
    </div>

    <script>
        function updateStatus() {
            fetch('/status')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('fps').innerText = data.fps;
                    document.getElementById('status').innerText = data.crop.status;
                    document.getElementById('green').innerText = data.crop.green_ratio.toFixed(3);
                    document.getElementById('yellow').innerText = data.crop.yellow_ratio.toFixed(3);
                    document.getElementById('brown').innerText = data.crop.brown_ratio.toFixed(3);
                    document.getElementById('brightness').innerText = data.crop.brightness.toFixed(1);
                    document.getElementById('suggestion').innerText = data.crop.suggestion;
                    document.getElementById('upload').innerText = data.crop.upload;

                    let statusBox = document.getElementById('status');
                    statusBox.className = "result";

                    if (data.crop.status.includes("健康")) {
                        statusBox.classList.add("ok");
                    } else if (data.crop.status.includes("异常")) {
                        statusBox.classList.add("bad");
                    } else {
                        statusBox.classList.add("warn");
                    }
                })
                .catch(err => {});
        }

        setInterval(updateStatus, 500);
    </script>
</body>
</html>
"""


last_anomaly_upload_time = 0.0


def analyze_crop(frame):
    """
    简单 OpenCV 作物状态判断：
    绿色多：健康
    黄色多：疑似黄叶/缺肥/病害
    褐色多：疑似干枯/土壤裸露
    亮度低：光照不足

    返回：
    label, status, green_ratio, yellow_ratio, brown_ratio, brightness, confidence, bbox
    """
    global crop_status

    h, w = frame.shape[:2]

    # 只分析中间区域，避免边缘干扰
    y0 = int(h * 0.15)
    y1 = int(h * 0.90)
    x0 = int(w * 0.10)
    x1 = int(w * 0.90)

    roi = frame[y0:y1, x0:x1]

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    brightness = float(np.mean(gray))

    # 绿色叶片范围
    green_lower = np.array([35, 40, 40])
    green_upper = np.array([85, 255, 255])
    green_mask = cv2.inRange(hsv, green_lower, green_upper)

    # 黄色叶片范围
    yellow_lower = np.array([18, 50, 50])
    yellow_upper = np.array([34, 255, 255])
    yellow_mask = cv2.inRange(hsv, yellow_lower, yellow_upper)

    # 褐色/干枯/土壤色范围
    brown_lower = np.array([5, 40, 30])
    brown_upper = np.array([20, 255, 180])
    brown_mask = cv2.inRange(hsv, brown_lower, brown_upper)

    # 去噪，减少误检
    kernel = np.ones((5, 5), np.uint8)
    yellow_mask = cv2.morphologyEx(yellow_mask, cv2.MORPH_OPEN, kernel)
    yellow_mask = cv2.morphologyEx(yellow_mask, cv2.MORPH_CLOSE, kernel)

    area = roi.shape[0] * roi.shape[1]

    green_ratio = float(cv2.countNonZero(green_mask)) / area
    yellow_ratio = float(cv2.countNonZero(yellow_mask)) / area
    brown_ratio = float(cv2.countNonZero(brown_mask)) / area

    label = "INIT"
    status = "初始化"
    suggestion = "等待检测"
    confidence = 0.0
    bbox = None

    if brightness < 45:
        status = "图像偏暗"
        suggestion = "补光或靠近作物后再检测"
        label = "LOW_LIGHT"

    elif green_ratio < 0.03 and yellow_ratio < 0.03:
        status = "未检测到明显作物"
        suggestion = "小车需要靠近作物或调整摄像头角度"
        label = "NO_CROP"

    elif yellow_ratio > 0.08:
        status = "疑似异常"
        suggestion = "疑似黄叶、缺肥或病害，建议小车执行近距离复查"
        label = "ABNORMAL"

        # 根据黄色面积比例估算一个置信度
        # yellow_ratio = 0.08 时约 0.56，越大越接近 0.99
        confidence = min(0.99, max(0.50, yellow_ratio * 7.0))

        # 找最大黄色区域，用来画框和上传 bbox
        contours, _ = cv2.findContours(
            yellow_mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        if contours:
            max_contour = max(contours, key=cv2.contourArea)
            max_area = cv2.contourArea(max_contour)

            if max_area > 800:
                bx, by, bw, bh = cv2.boundingRect(max_contour)

                # ROI 坐标转成整张图坐标
                bbox = [
                    x0 + bx,
                    y0 + by,
                    x0 + bx + bw,
                    y0 + by + bh
                ]

    elif brown_ratio > 0.18 and green_ratio < 0.12:
        status = "疑似干枯"
        suggestion = "疑似缺水或干枯，建议执行浇水任务"
        label = "DRY"

    else:
        status = "作物健康"
        suggestion = "作物状态正常，可继续巡检"
        label = "HEALTHY"

    # 保留原来的网页状态栏信息
    old_upload = crop_status.get("upload", "未上传")

    crop_status = {
        "status": status,
        "green_ratio": green_ratio,
        "yellow_ratio": yellow_ratio,
        "brown_ratio": brown_ratio,
        "brightness": brightness,
        "suggestion": suggestion,
        "upload": old_upload
    }

    return label, status, green_ratio, yellow_ratio, brown_ratio, brightness, confidence, bbox


def draw_overlay(frame, label, green_ratio, yellow_ratio, brown_ratio, brightness, bbox=None, confidence=0.0):
    # OpenCV 默认字体不支持中文，所以视频画面上用英文，网页状态栏显示中文
    if label == "HEALTHY":
        color = (0, 255, 0)
    elif label in ["ABNORMAL", "DRY"]:
        color = (0, 165, 255)
    else:
        color = (0, 0, 255)

    # 如果检测到黄叶区域，画检测框
    if bbox is not None:
        x1, y1, x2, y2 = bbox
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
        cv2.putText(
            frame,
            "yellow_leaf %.2f" % confidence,
            (x1, max(30, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2
        )

    cv2.rectangle(frame, (10, 10), (500, 155), (0, 0, 0), -1)
    cv2.putText(frame, f"Crop Status: {label}", (25, 45),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
    cv2.putText(frame, f"Green: {green_ratio:.3f}", (25, 75),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(frame, f"Yellow: {yellow_ratio:.3f}", (25, 105),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    cv2.putText(frame, f"Brown: {brown_ratio:.3f}  Light: {brightness:.1f}", (25, 135),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    return frame


def upload_anomaly_to_station(frame,
                              station_url,
                              source="car",
                              anomaly_type="yellow_leaf",
                              confidence=0.0,
                              location="小车实时巡检区域",
                              bbox=None):
    """
    把检测到的黄叶截图和信息上传到地面站 8090
    """

    global crop_status

    if frame is None:
        print("[UPLOAD] frame is None, skip")
        crop_status["upload"] = "上传失败：空图像"
        return False

    try:
        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            print("[UPLOAD] jpg encode failed")
            crop_status["upload"] = "上传失败：图像编码失败"
            return False

        files = {
            "image": ("anomaly.jpg", jpg.tobytes(), "image/jpeg")
        }

        if bbox is None:
            bbox_str = ""
        else:
            bbox_str = ",".join([str(int(v)) for v in bbox])

        data = {
            "source": source,
            "anomaly_type": anomaly_type,
            "confidence": str(float(confidence)),
            "location": location,
            "bbox": bbox_str
        }

        url = station_url.rstrip("/") + "/api/anomaly/upload"

        resp = requests.post(
            url,
            data=data,
            files=files,
            timeout=3
        )

        if resp.status_code == 200:
            ret = resp.json()
            if ret.get("ok"):
                report_time = ret.get("record", {}).get("time", "")
                print("[UPLOAD] 异常报告上传成功:", report_time)
                crop_status["upload"] = "上传成功：" + report_time
                return True

        print("[UPLOAD] 上传失败:", resp.status_code, resp.text[:200])
        crop_status["upload"] = "上传失败：" + str(resp.status_code)
        return False

    except Exception as e:
        print("[UPLOAD] 上传异常:", e)
        crop_status["upload"] = "上传异常：" + str(e)
        return False


def camera_loop(device,
                width,
                height,
                fps,
                detect_interval,
                station_url,
                upload_interval,
                upload_conf):
    global latest_jpg, running, current_fps
    global last_anomaly_upload_time

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
    print(f"地面站地址: {station_url}")
    print(f"异常上传间隔: {upload_interval} 秒")
    print(f"上传最低置信度: {upload_conf}")

    frame_count = 0
    detect_count = 0
    last_time = time.time()

    last_label = "INIT"
    last_green = 0.0
    last_yellow = 0.0
    last_brown = 0.0
    last_brightness = 0.0
    last_confidence = 0.0
    last_bbox = None

    while running:
        ret, frame = cap.read()

        if not ret or frame is None:
            print("读取摄像头失败")
            time.sleep(0.05)
            continue

        frame_count += 1
        detect_count += 1

        # 每隔 detect_interval 帧检测一次
        if detect_count >= detect_interval:
            detect_count = 0

            label, status, green_ratio, yellow_ratio, brown_ratio, brightness, confidence, bbox = analyze_crop(frame)

            last_label = label
            last_green = green_ratio
            last_yellow = yellow_ratio
            last_brown = brown_ratio
            last_brightness = brightness
            last_confidence = confidence
            last_bbox = bbox

            # ==============================
            # 关键新增部分：
            # 检测到黄叶 ABNORMAL 后，自动上传到 8090 地面站
            # ==============================
            if label == "ABNORMAL" and confidence >= upload_conf:
                now = time.time()

                if now - last_anomaly_upload_time >= upload_interval:
                    upload_frame = frame.copy()

                    upload_frame = draw_overlay(
                        upload_frame,
                        last_label,
                        last_green,
                        last_yellow,
                        last_brown,
                        last_brightness,
                        bbox=last_bbox,
                        confidence=last_confidence
                    )

                    ok_upload = upload_anomaly_to_station(
                        frame=upload_frame,
                        station_url=station_url,
                        source="car",
                        anomaly_type="yellow_leaf",
                        confidence=confidence,
                        location="小车实时巡检区域",
                        bbox=bbox
                    )

                    if ok_upload:
                        last_anomaly_upload_time = now

        # 给网页视频流画状态信息
        show_frame = frame.copy()

        show_frame = draw_overlay(
            show_frame,
            last_label,
            last_green,
            last_yellow,
            last_brown,
            last_brightness,
            bbox=last_bbox,
            confidence=last_confidence
        )

        ok, jpg = cv2.imencode(".jpg", show_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            with frame_lock:
                latest_jpg = jpg.tobytes()

        now = time.time()
        if now - last_time >= 1.0:
            current_fps = frame_count
            print(
                "当前推流 FPS:",
                current_fps,
                "状态:",
                crop_status["status"],
                "黄叶比例:",
                "%.3f" % crop_status["yellow_ratio"],
                "上传:",
                crop_status.get("upload", "未上传")
            )
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
        "fps": current_fps,
        "crop": crop_status
    })


def main():
    global running

    parser = argparse.ArgumentParser()
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--port", type=int, default=8082)
    parser.add_argument("--detect_interval", type=int, default=5, help="每隔多少帧检测一次")

    parser.add_argument(
        "--station",
        type=str,
        default="http://192.168.43.132:8090",
        help="地面站接收服务器地址"
    )

    parser.add_argument(
        "--upload_interval",
        type=float,
        default=8.0,
        help="异常报告最小上传间隔，单位秒，防止重复刷屏"
    )

    parser.add_argument(
        "--upload_conf",
        type=float,
        default=0.50,
        help="上传异常报告的最低置信度"
    )

    args = parser.parse_args()

    t = threading.Thread(
        target=camera_loop,
        args=(
            args.device,
            args.width,
            args.height,
            args.fps,
            args.detect_interval,
            args.station,
            args.upload_interval,
            args.upload_conf
        ),
        daemon=True
    )
    t.start()

    time.sleep(1)

    print("作物状态检测视频流服务启动")
    print(f"本机访问: http://127.0.0.1:{args.port}")
    print(f"显示屏 RDK 访问: http://小车RDK_IP:{args.port}")
    print(f"地面站上传地址: {args.station}/api/anomaly/upload")
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