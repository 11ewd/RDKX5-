#!/usr/bin/env python3
import cv2
import time
import threading
import argparse
import numpy as np
import serial
from flask import Flask, Response, render_template_string, jsonify

app = Flask(__name__)

latest_jpg = None
frame_lock = threading.Lock()

running = True
current_fps = 0

serial_obj = None
serial_lock = threading.Lock()

action_lock = threading.Lock()
working = False
last_water_time = 0
last_spray_time = 0

crop_status = {
    "status": "初始化",
    "label": "INIT",
    "green_ratio": 0.0,
    "yellow_ratio": 0.0,
    "brown_ratio": 0.0,
    "brightness": 0.0,
    "suggestion": "等待摄像头画面",
    "working": False,
    "work_type": "无",
    "last_action": "暂无"
}

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>RDK X5 作物检测与水肥药联动</title>
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
        .ok { color: #168a37; }
        .bad { color: #d35400; }
        .warn { color: #b9770e; }
        .work { color: #0b63c7; font-weight: bold; }
    </style>
</head>
<body>
    <div class="header">
        RDK X5 小车作物检测与精准作业系统
        <div class="sub">实时视频 + 作物状态判断 + STM32 水泵 / 药泵联动</div>
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
            <div class="item">黄色/坏叶比例：<span id="yellow">--</span></div>
            <div class="item">褐色/干枯比例：<span id="brown">--</span></div>
            <div class="item">亮度：<span id="brightness">--</span></div>

            <h2>自动作业状态</h2>
            <div class="item">作业状态：<span class="work" id="working">--</span></div>
            <div class="item">作业类型：<span class="work" id="work_type">--</span></div>
            <div class="item">最近动作：<span id="last_action">--</span></div>

            <h2>处理建议</h2>
            <div class="item" id="suggestion">等待画面</div>
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
                    document.getElementById('working').innerText = data.crop.working ? "作业中" : "空闲";
                    document.getElementById('work_type').innerText = data.crop.work_type;
                    document.getElementById('last_action').innerText = data.crop.last_action;

                    let statusBox = document.getElementById('status');
                    statusBox.className = "result";

                    if (data.crop.status.includes("健康")) {
                        statusBox.classList.add("ok");
                    } else if (data.crop.status.includes("干枯") || data.crop.status.includes("坏叶") || data.crop.status.includes("异常")) {
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

def open_stm32_serial(port, baudrate):
    global serial_obj

    try:
        serial_obj = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.2
        )
        time.sleep(1)
        print("STM32 串口打开成功:", port)
        return True
    except Exception as e:
        print("STM32 串口打开失败:", e)
        serial_obj = None
        return False

def send_stm32_cmd(cmd):
    global serial_obj

    if serial_obj is None:
        print("串口未打开，无法发送:", cmd)
        return False

    try:
        with serial_lock:
            serial_obj.write(cmd.encode("utf-8"))
            serial_obj.flush()
            time.sleep(0.05)

            reply = serial_obj.read_all().decode("utf-8", errors="ignore")
            print("RDK -> STM32:", cmd)
            if reply:
                print("STM32 -> RDK:", reply.strip())

        return True

    except Exception as e:
        print("串口发送失败:", e)
        return False

def close_all_pumps():
    send_stm32_cmd("P")
    time.sleep(0.05)
    send_stm32_cmd("Q")
    time.sleep(0.05)
    send_stm32_cmd("x")

def water_once(duration):
    """
    干枯时：只打开 p 水泵。
    p: 水泵1
    P: 关闭水泵1
    """
    global working, last_water_time, crop_status

    with action_lock:
        if working:
            print("当前已有作业，忽略浇水触发")
            return

        working = True
        crop_status["working"] = True
        crop_status["work_type"] = "单独浇水"
        crop_status["last_action"] = "检测到疑似干枯，开始 p 水泵浇水"

    print("========== 自动浇水开始 ==========")

    close_all_pumps()
    time.sleep(0.2)

    send_stm32_cmd("p")

    start = time.time()
    while time.time() - start < duration and running:
        time.sleep(0.1)

    send_stm32_cmd("P")
    time.sleep(0.1)
    send_stm32_cmd("x")

    with action_lock:
        working = False
        last_water_time = time.time()
        crop_status["working"] = False
        crop_status["work_type"] = "无"
        crop_status["last_action"] = f"已完成单独浇水，p 水泵持续 {duration:.1f} 秒"

    print("========== 自动浇水结束 ==========")

def spray_mix_once(water_duration, pesticide_duration):
    """
    坏叶/病害时：同时打开 p 水泵和 q 药泵。
    p: 水泵1，水
    q: 水泵2，药液/农药
    P: 关闭水泵1
    Q: 关闭水泵2

    逻辑：
    1. 先全部关闭
    2. p 和 q 同时打开
    3. q 持续时间较短，先关闭
    4. p 继续持续到 water_duration
    5. 最后全部关闭
    """
    global working, last_spray_time, crop_status

    if pesticide_duration >= water_duration:
        pesticide_duration = water_duration * 0.3

    with action_lock:
        if working:
            print("当前已有作业，忽略喷药触发")
            return

        working = True
        crop_status["working"] = True
        crop_status["work_type"] = "水药混合作业"
        crop_status["last_action"] = "检测到疑似坏叶，开始 p 水泵 + q 药泵联动"

    print("========== 水药混合作业开始 ==========")
    print(f"p 水泵持续: {water_duration:.1f} 秒")
    print(f"q 药泵持续: {pesticide_duration:.1f} 秒")

    close_all_pumps()
    time.sleep(0.2)

    # 同时启动 p 和 q
    send_stm32_cmd("p")
    time.sleep(0.1)
    send_stm32_cmd("q")

    start = time.time()
    q_closed = False

    while time.time() - start < water_duration and running:
        elapsed = time.time() - start

        if not q_closed and elapsed >= pesticide_duration:
            send_stm32_cmd("Q")
            q_closed = True
            crop_status["last_action"] = f"q 药泵已关闭，p 水泵继续稀释/冲洗"

        time.sleep(0.05)

    # 兜底关闭
    send_stm32_cmd("Q")
    time.sleep(0.1)
    send_stm32_cmd("P")
    time.sleep(0.1)
    send_stm32_cmd("x")

    with action_lock:
        working = False
        last_spray_time = time.time()
        crop_status["working"] = False
        crop_status["work_type"] = "无"
        crop_status["last_action"] = (
            f"水药混合作业完成：p={water_duration:.1f}s，q={pesticide_duration:.1f}s"
        )

    print("========== 水药混合作业结束 ==========")

def analyze_crop(frame):
    global crop_status

    h, w = frame.shape[:2]
    roi = frame[int(h * 0.15):int(h * 0.90), int(w * 0.10):int(w * 0.90)]

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    brightness = float(np.mean(gray))

    green_lower = np.array([35, 40, 40])
    green_upper = np.array([85, 255, 255])
    green_mask = cv2.inRange(hsv, green_lower, green_upper)

    # 黄色/坏叶区域
    yellow_lower = np.array([18, 50, 50])
    yellow_upper = np.array([34, 255, 255])
    yellow_mask = cv2.inRange(hsv, yellow_lower, yellow_upper)

    # 褐色/干枯区域
    brown_lower = np.array([5, 40, 30])
    brown_upper = np.array([20, 255, 180])
    brown_mask = cv2.inRange(hsv, brown_lower, brown_upper)

    area = roi.shape[0] * roi.shape[1]

    green_ratio = float(cv2.countNonZero(green_mask)) / area
    yellow_ratio = float(cv2.countNonZero(yellow_mask)) / area
    brown_ratio = float(cv2.countNonZero(brown_mask)) / area

    if brightness < 45:
        label = "LOW_LIGHT"
        status = "图像偏暗"
        suggestion = "补光或靠近作物后再检测"
    elif green_ratio < 0.03 and yellow_ratio < 0.03 and brown_ratio < 0.08:
        label = "NO_CROP"
        status = "未检测到明显作物"
        suggestion = "小车需要靠近作物或调整摄像头角度"
    elif brown_ratio > 0.18 and green_ratio < 0.12:
        label = "DRY"
        status = "疑似干枯"
        suggestion = "建议执行单独浇水任务：只启动 p 水泵"
    elif yellow_ratio > 0.08:
        label = "BAD_LEAF"
        status = "疑似坏叶/黄叶异常"
        suggestion = "建议执行水药混合作业：p 水泵 + q 药泵，q 时间更短"
    else:
        label = "HEALTHY"
        status = "作物健康"
        suggestion = "作物状态正常，可继续巡检"

    crop_status["status"] = status
    crop_status["label"] = label
    crop_status["green_ratio"] = green_ratio
    crop_status["yellow_ratio"] = yellow_ratio
    crop_status["brown_ratio"] = brown_ratio
    crop_status["brightness"] = brightness
    crop_status["suggestion"] = suggestion

    return label, green_ratio, yellow_ratio, brown_ratio, brightness

def draw_overlay(frame, label, green_ratio, yellow_ratio, brown_ratio, brightness, auto_water, auto_spray):
    if label == "HEALTHY":
        color = (0, 255, 0)
    elif label in ["BAD_LEAF", "DRY"]:
        color = (0, 165, 255)
    else:
        color = (0, 0, 255)

    mode_text = f"AUTO WATER:{'ON' if auto_water else 'OFF'}  AUTO SPRAY:{'ON' if auto_spray else 'OFF'}"

    cv2.rectangle(frame, (10, 10), (620, 190), (0, 0, 0), -1)
    cv2.putText(frame, f"Crop Status: {label}", (25, 45),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
    cv2.putText(frame, f"Green: {green_ratio:.3f}", (25, 78),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(frame, f"Yellow/Bad Leaf: {yellow_ratio:.3f}", (25, 110),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    cv2.putText(frame, f"Brown/Dry: {brown_ratio:.3f}  Light: {brightness:.1f}", (25, 142),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(frame, mode_text, (25, 174),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 200, 0), 2)

    return frame

def camera_loop(
    device,
    width,
    height,
    fps,
    detect_interval,
    auto_water,
    water_duration,
    water_cooldown,
    dry_trigger_count,
    auto_spray,
    spray_water_duration,
    spray_pesticide_duration,
    spray_cooldown,
    bad_leaf_trigger_count
):
    global latest_jpg, running, current_fps, last_water_time, last_spray_time

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
    detect_count = 0
    dry_count = 0
    bad_leaf_count = 0
    last_time = time.time()

    last_label = "INIT"
    last_green = 0.0
    last_yellow = 0.0
    last_brown = 0.0
    last_brightness = 0.0

    while running:
        ret, frame = cap.read()

        if not ret or frame is None:
            print("读取摄像头失败")
            time.sleep(0.05)
            continue

        frame_count += 1
        detect_count += 1

        if detect_count >= detect_interval:
            detect_count = 0
            label, green_ratio, yellow_ratio, brown_ratio, brightness = analyze_crop(frame)

            last_label = label
            last_green = green_ratio
            last_yellow = yellow_ratio
            last_brown = brown_ratio
            last_brightness = brightness

            if label == "DRY":
                dry_count += 1
            else:
                dry_count = 0

            if label == "BAD_LEAF":
                bad_leaf_count += 1
            else:
                bad_leaf_count = 0

            now = time.time()

            if auto_spray:
                can_spray = (
                    bad_leaf_count >= bad_leaf_trigger_count
                    and not working
                    and (now - last_spray_time) >= spray_cooldown
                )

                if can_spray:
                    print("连续检测到疑似坏叶，触发水药混合作业")
                    t = threading.Thread(
                        target=spray_mix_once,
                        args=(spray_water_duration, spray_pesticide_duration),
                        daemon=True
                    )
                    t.start()
                    bad_leaf_count = 0

            if auto_water:
                can_water = (
                    dry_count >= dry_trigger_count
                    and not working
                    and (now - last_water_time) >= water_cooldown
                )

                if can_water:
                    print("连续检测到疑似干枯，触发单独浇水")
                    t = threading.Thread(
                        target=water_once,
                        args=(water_duration,),
                        daemon=True
                    )
                    t.start()
                    dry_count = 0

        frame = draw_overlay(
            frame,
            last_label,
            last_green,
            last_yellow,
            last_brown,
            last_brightness,
            auto_water,
            auto_spray
        )

        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            with frame_lock:
                latest_jpg = jpg.tobytes()

        now = time.time()
        if now - last_time >= 1.0:
            current_fps = frame_count
            print("当前推流 FPS:", current_fps,
                  "状态:", crop_status["status"],
                  "作业:", crop_status["work_type"])
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

@app.route("/manual_water")
def manual_water():
    t = threading.Thread(target=water_once, args=(3.0,), daemon=True)
    t.start()
    return jsonify({"ok": True, "action": "manual_water"})

@app.route("/manual_spray")
def manual_spray():
    t = threading.Thread(target=spray_mix_once, args=(5.0, 1.0), daemon=True)
    t.start()
    return jsonify({"ok": True, "action": "manual_spray", "p_water_sec": 5.0, "q_pesticide_sec": 1.0})

def main():
    global running

    parser = argparse.ArgumentParser()
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--port", type=int, default=8083)
    parser.add_argument("--detect_interval", type=int, default=5)

    parser.add_argument("--serial_port", type=str, default="/dev/ttyUSB0")
    parser.add_argument("--baudrate", type=int, default=115200)

    parser.add_argument("--auto_water", action="store_true")
    parser.add_argument("--water_duration", type=float, default=3.0)
    parser.add_argument("--water_cooldown", type=float, default=20.0)
    parser.add_argument("--dry_trigger_count", type=int, default=3)

    parser.add_argument("--auto_spray", action="store_true")
    parser.add_argument("--spray_water_duration", type=float, default=5.0)
    parser.add_argument("--spray_pesticide_duration", type=float, default=1.0)
    parser.add_argument("--spray_cooldown", type=float, default=30.0)
    parser.add_argument("--bad_leaf_trigger_count", type=int, default=3)

    args = parser.parse_args()

    if args.auto_water or args.auto_spray:
        ok = open_stm32_serial(args.serial_port, args.baudrate)
        if not ok:
            print("已开启自动作业，但 STM32 串口打开失败，程序退出")
            return

        close_all_pumps()
    else:
        print("自动作业未开启，只进行检测和显示")

    t = threading.Thread(
        target=camera_loop,
        args=(
            args.device,
            args.width,
            args.height,
            args.fps,
            args.detect_interval,
            args.auto_water,
            args.water_duration,
            args.water_cooldown,
            args.dry_trigger_count,
            args.auto_spray,
            args.spray_water_duration,
            args.spray_pesticide_duration,
            args.spray_cooldown,
            args.bad_leaf_trigger_count
        ),
        daemon=True
    )
    t.start()

    time.sleep(1)

    print("作物检测 + STM32 水泵/药泵联动服务启动")
    print(f"本机访问: http://127.0.0.1:{args.port}")
    print(f"显示屏 RDK 访问: http://小车RDK_IP:{args.port}")
    print(f"手动浇水接口: http://小车RDK_IP:{args.port}/manual_water")
    print(f"手动水药混合接口: http://小车RDK_IP:{args.port}/manual_spray")
    print("按 Ctrl+C 退出")

    try:
        app.run(host="0.0.0.0", port=args.port, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("退出服务")
    finally:
        running = False
        print("安全关闭所有水泵")
        close_all_pumps()
        if serial_obj is not None:
            serial_obj.close()
        time.sleep(0.5)

if __name__ == "__main__":
    main()
