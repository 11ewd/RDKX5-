# Air-Ground Collaborative Smart Agriculture Inspection and Precision Operation System Based on RDK X5

## Project Introduction

This project is designed for smart agriculture scenarios such as greenhouses, orchards, and small intelligent farms. Based on RDK X5, the system builds an air-ground collaborative agricultural robot platform that integrates UAV inspection, ground robot rechecking, crop anomaly recognition, precision watering and spraying, abnormal data recording, and visual management.

The overall idea of the project is “aerial global inspection + ground close-range rechecking + precision water/fertilizer/pesticide operation + visual management through a ground station”. The UAV is responsible for wide-area inspection and preliminary anomaly detection. The ground robot performs close-range rechecking and precise operation. The RDK ground station displays real-time images, records abnormal information, manages tasks, and stores historical data.

## Keywords

- RDK X5 Intelligent Hub
- RDK Edge Perception and Decision-Making
- Air-Ground Collaborative Ground Station

## Application Scenarios

This project can be used in:

- Greenhouse crop inspection
- Orchard crop anomaly detection
- Smart farm automation
- Yellow leaf, dry leaf, water shortage, and disease pre-screening
- Precision watering, fertilization, and pesticide spraying
- Agricultural robot education and competition demonstration

## System Composition

The system consists of three main parts:

### 1. UAV Inspection Terminal

The UAV performs large-area aerial inspection, captures crop images, and detects suspected abnormal areas. When an abnormal area is detected, the UAV sends the image, anomaly type, confidence, and location information to the ground station.

### 2. Ground Robot Operation Terminal

The ground robot uses RDK X5 as the upper-level controller. It is responsible for image acquisition, object recognition, task scheduling, LiDAR/IMU data processing, and communication forwarding. STM32F407VET6 is used as the lower-level controller to control chassis movement, servo gimbal, dual water pumps, and emergency stop protection.

### 3. RDK Ground Station

The ground station displays UAV and ground robot images, receives abnormal reports, shows anomaly type, confidence, data source, location, and images, and saves historical records for traceable agricultural management.

## Main Functions

### 1. Aerial Global Inspection

The UAV quickly inspects greenhouse or orchard areas and detects suspected abnormal crop regions, improving inspection coverage and efficiency.

### 2. Ground Close-Range Rechecking

After receiving an abnormal task, the ground robot moves to the target area for close-range image capture and rechecking, improving the accuracy of anomaly judgment.

### 3. Crop Anomaly Recognition

The system can identify abnormal crop states such as yellow leaves, dry leaves, water shortage, and possible diseases, and output anomaly type, confidence, and image evidence.

### 4. Precision Watering and Spraying

The ground robot is equipped with a dual-pump system. The clean water pump and liquid fertilizer/pesticide pump are controlled separately. According to the anomaly type, the robot can perform short pulse spraying for precision operation.

### 5. Ground Station Visualization

The ground station displays inspection images, abnormal reports, task status, and historical records in real time, helping operators manage agricultural tasks more efficiently.

### 6. Safety Protection

The system includes emergency stop, communication timeout stop, default pump-off protection, single-pump shutdown, and action timeout protection to reduce the risk of misoperation.

## Hardware Components

| Module | Hardware | Function |
|---|---|---|
| Upper Controller | RDK X5 | Image processing, ROS2, task scheduling, communication forwarding |
| Lower Controller | STM32F407VET6 | Motor, servo, water pump, and emergency stop control |
| Perception Module | USB camera, LiDAR, IMU | Image acquisition, environmental perception, attitude detection |
| Actuator Module | Motor driver, dual water pumps, relay, servo gimbal | Chassis motion and precision spraying |
| Ground Station | RDK/display/network module | Video display, abnormal record, task management |
| UAV Terminal | Flight controller, Jetson NX, D435i/camera | Aerial inspection and anomaly pre-screening |

## Software Architecture

The software system mainly includes:

- ROS2 Humble nodes
- Camera acquisition program
- Crop anomaly recognition program
- Serial communication bridge
- STM32 lower-level control program
- Flask Web service for the ground station
- HTTP anomaly upload interface
- Task state machine control logic

## Workflow

1. The UAV performs aerial inspection;
2. The camera captures crop images;
3. The system detects suspected yellow leaves, dry leaves, water shortage, or diseases;
4. Abnormal information is uploaded to the RDK ground station;
5. The ground robot receives the abnormal task;
6. The robot moves to the target area for close-range rechecking;
7. RDK X5 generates operation commands according to the recognition result;
8. STM32F407VET6 controls the chassis, gimbal, and water pumps;
9. The robot completes precision watering, fertilization, or spraying;
10. The ground station saves abnormal reports and operation records.

## Repository Structure

```text
RDKX5-
├── CAR/                    # STM32F407 lower-level control code
├── agri_ground_station/    # Ground station service and web interface
├── agri_robot_ws/          # RDK X5 ground robot ROS2 workspace
├── agri_robot_ws_ground/   # Ground station or communication-related workspace
├── keyboard_car_control.py # Keyboard control script for the robot
├── scan_check.py           # LiDAR scan checking script
├── scan_check_reliable.py  # Reliable LiDAR scan checking script
└── scan_gpio_buttons.py    # GPIO button scanning script
```

## Role of RDK X5 in This Project

RDK X5 is the intelligent hub of the ground robot. It mainly performs the following tasks:

- Running Ubuntu 22.04 and ROS2 Humble;
- Connecting cameras, LiDAR, and IMU;
- Capturing crop images and performing anomaly recognition;
- Receiving abnormal tasks from the ground station or UAV terminal;
- Sending control commands to STM32F407VET6 through serial communication;
- Managing robot movement, rechecking, spraying, and status feedback;
- Supporting future deployment of lightweight AI large models for smarter task understanding and decision-making.

## Innovations

1. An air-ground collaborative agricultural robot workflow is proposed, combining aerial global inspection, ground close-range rechecking, and precision operation;
2. RDK X5 is used to build edge-side intelligent perception and task scheduling;
3. A layered architecture of RDK X5 + STM32F407VET6 is adopted for reliable upper-level and lower-level control;
4. A dual-pump spraying strategy is designed to separately control clean water and liquid fertilizer/pesticide;
5. A ground station abnormal report system is built for visualization and data traceability;
6. The system has a modular structure, making it easy to expand autonomous navigation, AI large models, and multi-robot collaboration.

## Future Work

In the future, lightweight AI large models or multimodal models can be deployed on the RDK X5 of the ground robot. This will enable stronger natural language understanding, anomaly cause analysis, intelligent operation recommendations, and automatic report generation. Operators can issue tasks through voice or text, while the system combines camera, LiDAR, IMU, environmental data, and historical records to determine crop anomaly causes and recommend watering, fertilization, or spraying strategies. This will help the robot evolve from “automatic execution” to “intelligent decision-making”.

## Demonstration

The project demonstration video can be published on Bilibili, and the embedded code can be submitted to NodeHub.

Suggested video contents:

- Project background
- Overall system composition
- UAV inspection process
- Ground robot rechecking process
- Ground station abnormal information display
- Precision watering and spraying
- Future outlook of RDK X5 with AI large models

## License

This project is mainly used for embedded system competitions, learning, and smart agriculture robot demonstration. The open-source license can be selected according to the actual competition requirements.
