#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import csv
import json
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory, render_template_string

app = Flask(__name__)

# =========================
# 普通图片/视频接收目录
# =========================

RECEIVED_DIR = os.path.expanduser("~/agri_robot_ws/received")
IMAGE_DIR = os.path.join(RECEIVED_DIR, "images")
VIDEO_DIR = os.path.join(RECEIVED_DIR, "videos")

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)

# =========================
# 异常报告目录
# =========================

GROUND_STATION_DIR = os.path.dirname(os.path.abspath(__file__))
ANOMALY_IMAGE_DIR = os.path.join(GROUND_STATION_DIR, "static", "anomaly_images")
ANOMALY_REPORT_DIR = os.path.join(GROUND_STATION_DIR, "report_data")

os.makedirs(ANOMALY_IMAGE_DIR, exist_ok=True)
os.makedirs(ANOMALY_REPORT_DIR, exist_ok=True)


def list_files(folder, exts, limit=30):
    files = []
    if not os.path.exists(folder):
        return files

    for name in os.listdir(folder):
        lower = name.lower()
        if any(lower.endswith(ext) for ext in exts):
            path = os.path.join(folder, name)
            files.append((name, os.path.getmtime(path)))

    files.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in files[:limit]]


def get_severity_by_confidence(confidence):
    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0.0

    if confidence >= 0.80:
        return "严重"
    elif confidence >= 0.65:
        return "中等"
    else:
        return "轻微"


def get_anomaly_chinese_name(anomaly_type):
    names = {
        "yellow_leaf": "黄叶",
        "dry_leaf": "干枯叶",
        "bad_leaf": "坏叶/病叶",
        "water_stress": "疑似缺水",
        "unknown": "未知异常"
    }
    return names.get(anomaly_type, anomaly_type)


def get_suggestion(anomaly_type, severity):
    if anomaly_type == "yellow_leaf":
        if severity == "轻微":
            return "发现轻微黄叶，建议记录观察，后续复查。"
        elif severity == "中等":
            return "发现中等黄叶，建议地面小车前往复查，检查是否缺水、缺肥或病害。"
        else:
            return "黄叶较严重，建议地面小车重点复查，可结合补水、补肥或喷药处理。"

    elif anomaly_type == "dry_leaf":
        if severity == "轻微":
            return "发现轻微干枯，建议观察土壤湿度。"
        elif severity == "中等":
            return "建议地面小车执行补水，并记录处理结果。"
        else:
            return "干枯较严重，建议立即补水并人工检查。"

    elif anomaly_type == "bad_leaf":
        if severity == "轻微":
            return "疑似坏叶，建议近距离复查。"
        elif severity == "中等":
            return "建议小车近距离复查，判断是否需要喷药。"
        else:
            return "坏叶较严重，建议喷药并人工处理。"

    elif anomaly_type == "water_stress":
        return "疑似缺水，建议地面小车执行补水任务。"

    return "未知异常，建议人工复查。"


def load_anomaly_reports(date_str):
    jsonl_path = os.path.join(ANOMALY_REPORT_DIR, f"anomaly_{date_str}.jsonl")

    reports = []
    if os.path.exists(jsonl_path):
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    reports.append(json.loads(line.strip()))
                except Exception:
                    pass

    return list(reversed(reports))


HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>RDK X5 地面站</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body {
            font-family: Arial, "Microsoft YaHei", sans-serif;
            background: #f2f5fa;
            margin: 0;
            padding: 0;
        }
        .header {
            background: #073b88;
            color: white;
            padding: 20px;
            text-align: center;
            font-size: 28px;
            font-weight: bold;
        }
        .sub {
            font-size: 16px;
            margin-top: 8px;
            color: #dce8ff;
        }
        .container {
            width: 92%;
            margin: 20px auto;
        }
        .card {
            background: white;
            border-radius: 12px;
            padding: 18px;
            margin-bottom: 22px;
            box-shadow: 0 3px 12px rgba(0,0,0,0.12);
        }
        h2 {
            color: #073b88;
            border-left: 6px solid #073b88;
            padding-left: 12px;
        }
        .nav a {
            display: inline-block;
            background: #073b88;
            color: white;
            padding: 10px 16px;
            border-radius: 8px;
            text-decoration: none;
            margin-right: 12px;
            margin-bottom: 10px;
        }
        .grid {
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
        }
        .imgbox {
            width: 220px;
            background: #fafafa;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 8px;
            text-align: center;
        }
        .imgbox img {
            width: 200px;
            height: 150px;
            object-fit: cover;
            border-radius: 6px;
            background: #111;
        }
        .name {
            margin-top: 6px;
            font-size: 13px;
            word-break: break-all;
            color: #333;
        }
        .video-item {
            padding: 10px;
            border-bottom: 1px solid #eee;
            font-size: 16px;
        }
        a {
            color: #0b63c7;
            text-decoration: none;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="header">
        RDK X5 地面站接收页面
        <div class="sub">接收小车上传的图片、视频、黄叶异常报告</div>
    </div>

    <div class="container">

        <div class="card">
            <h2>功能入口</h2>
            <div class="nav">
                <a href="/anomaly_report">查看作物异常报告</a>
                <a href="/api/anomaly/list">查看异常 JSON 数据</a>
                <a href="/status">查看服务器状态</a>
            </div>
        </div>

        <div class="card">
            <h2>最新图片</h2>
            <div class="grid">
                {% for img in images %}
                <div class="imgbox">
                    <a href="/files/images/{{ img }}" target="_blank">
                        <img src="/files/images/{{ img }}">
                    </a>
                    <div class="name">{{ img }}</div>
                </div>
                {% endfor %}
            </div>
        </div>

        <div class="card">
            <h2>视频文件</h2>
            {% for video in videos %}
            <div class="video-item">
                <a href="/files/videos/{{ video }}" target="_blank">{{ video }}</a>
            </div>
            {% endfor %}
        </div>

    </div>
</body>
</html>
"""


@app.route("/")
def index():
    images = list_files(IMAGE_DIR, [".jpg", ".jpeg", ".png"], limit=30)
    videos = list_files(VIDEO_DIR, [".avi", ".mp4", ".mkv"], limit=30)
    return render_template_string(HTML_PAGE, images=images, videos=videos)


@app.route("/upload/image", methods=["POST"])
def upload_image():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "no file"}), 400

    file = request.files["file"]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"car_image_{ts}.jpg"
    save_path = os.path.join(IMAGE_DIR, filename)
    file.save(save_path)

    print("收到图片:", save_path)
    return jsonify({"ok": True, "type": "image", "filename": filename})


@app.route("/upload/video", methods=["POST"])
def upload_video():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "no file"}), 400

    file = request.files["file"]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"car_video_{ts}.avi"
    save_path = os.path.join(VIDEO_DIR, filename)
    file.save(save_path)

    print("收到视频:", save_path)
    return jsonify({"ok": True, "type": "video", "filename": filename})


@app.route("/files/images/<filename>")
def get_image(filename):
    return send_from_directory(IMAGE_DIR, filename)


@app.route("/files/videos/<filename>")
def get_video(filename):
    return send_from_directory(VIDEO_DIR, filename)


@app.route("/api/anomaly/upload", methods=["POST"])
def upload_anomaly():
    now = datetime.now()
    time_str = now.strftime("%Y-%m-%d %H:%M:%S")
    date_str = now.strftime("%Y-%m-%d")
    file_time = now.strftime("%Y%m%d_%H%M%S_%f")

    source = request.form.get("source", "car")
    anomaly_type = request.form.get("anomaly_type", "yellow_leaf")
    confidence = request.form.get("confidence", "0")
    location = request.form.get("location", "未知区域")
    bbox = request.form.get("bbox", "")

    try:
        confidence_float = float(confidence)
    except Exception:
        confidence_float = 0.0

    severity = request.form.get("severity", "")
    if not severity:
        severity = get_severity_by_confidence(confidence_float)

    suggestion = request.form.get("suggestion", "")
    if not suggestion:
        suggestion = get_suggestion(anomaly_type, severity)

    image_file = request.files.get("image")
    image_name = ""
    image_url = ""

    if image_file is not None:
        image_name = f"{source}_{anomaly_type}_{file_time}.jpg"
        image_path = os.path.join(ANOMALY_IMAGE_DIR, image_name)
        image_file.save(image_path)
        image_url = f"/anomaly_images/{image_name}"

    record = {
        "time": time_str,
        "source": source,
        "anomaly_type": anomaly_type,
        "anomaly_name": get_anomaly_chinese_name(anomaly_type),
        "confidence": round(confidence_float, 3),
        "severity": severity,
        "location": location,
        "bbox": bbox,
        "image_name": image_name,
        "image_url": image_url,
        "suggestion": suggestion,
        "status": "未处理"
    }

    jsonl_path = os.path.join(ANOMALY_REPORT_DIR, f"anomaly_{date_str}.jsonl")
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    csv_path = os.path.join(ANOMALY_REPORT_DIR, f"anomaly_{date_str}.csv")
    file_exists = os.path.exists(csv_path)

    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=record.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(record)

    print("[ANOMALY] 收到异常报告:", record)

    return jsonify({
        "ok": True,
        "msg": "anomaly saved",
        "record": record
    })


@app.route("/api/anomaly/list", methods=["GET"])
def list_anomaly():
    date_str = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    reports = load_anomaly_reports(date_str)

    return jsonify({
        "ok": True,
        "date": date_str,
        "count": len(reports),
        "reports": reports
    })


@app.route("/anomaly_images/<filename>")
def anomaly_images(filename):
    return send_from_directory(ANOMALY_IMAGE_DIR, filename)


@app.route("/anomaly_report")
def anomaly_report_page():
    date_str = datetime.now().strftime("%Y-%m-%d")
    reports = load_anomaly_reports(date_str)

    html = """
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>作物异常报告</title>
        <meta http-equiv="refresh" content="5">
        <style>
            body {
                font-family: Arial, "Microsoft YaHei", sans-serif;
                background: #f2f5fa;
                margin: 20px;
            }
            h1 {
                color: #073b88;
            }
            .summary {
                background: white;
                padding: 15px;
                border-radius: 10px;
                margin-bottom: 20px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.12);
            }
            .card {
                background: white;
                padding: 15px;
                border-radius: 10px;
                margin-bottom: 15px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.12);
                display: flex;
                gap: 15px;
            }
            .card img {
                width: 260px;
                height: 190px;
                object-fit: contain;
                background: #111;
                border-radius: 8px;
                border: 1px solid #ddd;
            }
            .info {
                flex: 1;
            }
            .tag {
                display: inline-block;
                padding: 4px 10px;
                border-radius: 20px;
                font-size: 14px;
                color: white;
            }
            .light {
                background: #16a34a;
            }
            .medium {
                background: #f59e0b;
            }
            .serious {
                background: #dc2626;
            }
            .empty {
                background: white;
                padding: 30px;
                border-radius: 10px;
                color: #666;
            }
            a {
                color: #073b88;
                text-decoration: none;
                font-weight: bold;
            }
        </style>
    </head>
    <body>
        <h1>作物异常报告</h1>

        <div class="summary">
            <b>今日日期：</b>{{ date_str }}　
            <b>异常总数：</b>{{ reports|length }}　
            <b>页面自动刷新：</b>5 秒
            <br><br>
            <a href="/">返回地面站主页</a>　
            <a href="/api/anomaly/list">查看 JSON 数据</a>
        </div>

        {% if reports|length == 0 %}
            <div class="empty">今日暂时没有异常报告。</div>
        {% endif %}

        {% for r in reports %}
        <div class="card">
            {% if r.image_url %}
                <img src="{{ r.image_url }}">
            {% else %}
                <div style="width:260px;height:190px;background:#eee;border-radius:8px;text-align:center;line-height:190px;">
                    无图片
                </div>
            {% endif %}

            <div class="info">
                <h2>
                    {{ r.anomaly_name }}
                    {% if r.severity == "严重" %}
                        <span class="tag serious">严重</span>
                    {% elif r.severity == "中等" %}
                        <span class="tag medium">中等</span>
                    {% else %}
                        <span class="tag light">轻微</span>
                    {% endif %}
                </h2>

                <p><b>时间：</b>{{ r.time }}</p>
                <p><b>来源：</b>{{ r.source }}</p>
                <p><b>位置：</b>{{ r.location }}</p>
                <p><b>置信度：</b>{{ r.confidence }}</p>
                <p><b>检测框：</b>{{ r.bbox }}</p>
                <p><b>状态：</b>{{ r.status }}</p>
                <p><b>建议：</b>{{ r.suggestion }}</p>
            </div>
        </div>
        {% endfor %}
    </body>
    </html>
    """

    return render_template_string(html, date_str=date_str, reports=reports)


@app.route("/status")
def status():
    date_str = datetime.now().strftime("%Y-%m-%d")
    reports = load_anomaly_reports(date_str)

    return jsonify({
        "ok": True,
        "images": len(os.listdir(IMAGE_DIR)),
        "videos": len(os.listdir(VIDEO_DIR)),
        "anomalies": len(reports)
    })


if __name__ == "__main__":
    print("RDK X5 地面站接收服务器启动")
    print("浏览器访问: http://本机IP:8090")
    print("异常报告页面: http://本机IP:8090/anomaly_report")
    print("异常上传接口: http://本机IP:8090/api/anomaly/upload")
    print(app.url_map)

    app.run(host="0.0.0.0", port=8090, debug=False, threaded=True)
