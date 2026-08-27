cmake_minimum_required(VERSION 3.14)
project(gnss_pose_source)

find_package(autoware_cmake REQUIRED)
autoware_package()

ament_auto_add_library(${PROJECT_NAME} SHARED
  src/gnss_pose_source_node.cpp
)

rclcpp_components_register_node(${PROJECT_NAME}
  PLUGIN "gnss_pose_source::GnssPoseSourceNode"
  EXECUTABLE "gnss_pose_source_node"
)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_auto_add_gtest(test_solution_gate
    test/test_solution_gate.cpp
  )
endif()

ament_auto_package(USE_SCOPED_HEADER_INSTALL_DIR INSTALL_TO_SHARE config launch)
