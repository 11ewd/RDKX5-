#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import cv2
import csv
import json
import time
from datetime import datetime


class AnomalyReportManager:
    def __init__(self,
                 image_dir="static/anomaly_images",
                 report_dir="report/report_data"):
        self.image_dir = image_dir
        self.report_dir = report_dir

        os.makedirs(self.image_dir, exist_ok=True)
        os.makedirs(self.report_dir, exist_ok=True)

    def get_severity(self, confidence):
        if confidence >= 0.80:
            return "严重"
        elif confidence >= 0.65:
            return "中等"
        else:
            return "轻微"

    def get_suggestion(self, anomaly_type, severity):
        if anomaly_type == "yellow_leaf":
            if severity == "轻微":
                return "记录观察，建议后续复查。"
            elif severity == "中等":
                return "建议地面小车前往复查，检查是否缺水或缺肥。"
            else:
                return "建议地面小车重点复查，可结合喷药或补肥处理。"

        elif anomaly_type == "dry_leaf":
            if severity == "轻微":
                return "发现轻微干枯，建议观察土壤湿度。"
            elif severity == "中等":
                return "建议地面小车补水，并记录作物状态。"
            else:
                return "干枯较严重，建议立即补水并人工检查。"

        elif anomaly_type == "bad_leaf":
            if severity == "轻微":
                return "疑似坏叶，建议复查。"
            elif severity == "中等":
                return "建议小车近距离复查，判断是否需要喷药。"
            else:
                return "坏叶严重，建议喷药并人工处理。"

        elif anomaly_type == "water_stress":
            return "疑似缺水，建议小车执行补水任务。"

        else:
            return "未知异常，建议人工复查。"

    def save_anomaly(self,
                     frame,
                     source="car",
                     anomaly_type="yellow_leaf",
                     confidence=0.0,
                     location="未知区域",
                     bbox=None):
        """
        frame: OpenCV 图像
        source: car / drone
        anomaly_type: yellow_leaf / dry_leaf / bad_leaf / water_stress
        confidence: 0~1
        location: 区域位置，例如 A区-第2垄-第5株
        bbox: [x1, y1, x2, y2]，可选
        """

        now = datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M:%S")
        date_str = now.strftime("%Y-%m-%d")
        file_time = now.strftime("%Y%m%d_%H%M%S")

        severity = self.get_severity(confidence)
        suggestion = self.get_suggestion(anomaly_type, severity)

        # 画框
        save_frame = frame.copy()
        if bbox is not None:
            x1, y1, x2, y2 = bbox
            cv2.rectangle(save_frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
            cv2.putText(save_frame,
                        f"{anomaly_type} {confidence:.2f}",
                        (x1, max(30, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 255),
                        2)

        image_name = f"{source}_{anomaly_type}_{file_time}.jpg"
        image_path = os.path.join(self.image_dir, image_name)
        cv2.imwrite(image_path, save_frame)

        record = {
            "time": time_str,
            "source": source,
            "anomaly_type": anomaly_type,
            "confidence": round(float(confidence), 3),
            "severity": severity,
            "location": location,
            "image_path": image_path,
            "suggestion": suggestion,
            "status": "未处理"
        }

        # 保存 JSONL
        jsonl_path = os.path.join(self.report_dir, f"anomaly_{date_str}.jsonl")
        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        # 保存 CSV
        csv_path = os.path.join(self.report_dir, f"anomaly_{date_str}.csv")
        file_exists = os.path.exists(csv_path)

        with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=record.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(record)

        return record

    def load_today_reports(self):
        date_str = datetime.now().strftime("%Y-%m-%d")
        jsonl_path = os.path.join(self.report_dir, f"anomaly_{date_str}.jsonl")

        reports = []
        if not os.path.exists(jsonl_path):
            return reports

        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    reports.append(json.loads(line.strip()))
                except Exception:
                    pass

        return reports
