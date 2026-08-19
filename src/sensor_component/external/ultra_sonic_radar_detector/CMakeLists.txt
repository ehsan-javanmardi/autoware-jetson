cmake_minimum_required(VERSION 3.8)
project(ultra_sonic_radar_detector)

# find dependencies
find_package(ament_cmake_auto REQUIRED)
ament_auto_find_build_dependencies()

# Default to C++14
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 14)
  set(CMAKE_CXX_STANDARD_REQUIRED ON)
  set(CMAKE_CXX_EXTENSIONS OFF)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

include_directories(
  include
  ${CMAKE_CURRENT_SOURCE_DIR}
)

ament_auto_add_executable(ultra_sonic_radar_detector_node
  src/ultra_sonic_radar_detector_node.cpp
  src/ultra_sonic_radar_detector.cpp
)


# install
ament_auto_package(
  INSTALL_TO_SHARE
  launch
)
