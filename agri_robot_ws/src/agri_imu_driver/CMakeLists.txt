cmake_minimum_required(VERSION 3.5)
project(agri_imu_driver)

find_package(ament_cmake REQUIRED)

install(PROGRAMS
  scripts/imu_node.py
  DESTINATION lib/${PROJECT_NAME}
)

install(PROGRAMS
  scripts/gy95t_node.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()

