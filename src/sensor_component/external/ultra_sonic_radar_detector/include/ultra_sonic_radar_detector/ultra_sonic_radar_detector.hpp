/**
 * @file ultra_sonic_radar_detector.hpp
 * @author Mark Jin (mark@pixmoving.net)
 * @brief header file of ultra sonic radar detector
 * @version 0.1
 * @date 2022-06-17
 *
 * @copyright Copyright (c) 2022, Pixmoving
 * Rebuild The City With Autonomous Mobility
 * https://www.pixmoving.com
 *
 */
#ifndef __ULTRA_SONIC_RADAR_DETECTOR__HPP__
#define __ULTRA_SONIC_RADAR_DETECTOR__HPP__

#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <pcl_ros/transforms.hpp>

#include <tf2/convert.h>
#include <tf2_ros/buffer.h>
#include <tf2_sensor_msgs/tf2_sensor_msgs.hpp>
#include <tf2_ros/transform_listener.h>

#include <pcl/point_cloud.h>
#include <pcl/point_types.h>
#include <pcl/io/pcd_io.h>
#include <pcl_conversions/pcl_conversions.h>

#include <sensor_msgs/msg/range.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>

#include "message_filters/subscriber.h"
#include "message_filters/sync_policies/approximate_time.h"
#include "message_filters/synchronizer.h"

namespace ultra_sonic_radar_detector
{
#define RS_ERROR   std::cout << "\033[1m\033[31m"  // bold red
#define RS_WARNING std::cout << "\033[1m\033[33m"  // bold yellow
#define RS_INFO    std::cout << "\033[1m\033[32m"  // bold green
#define RS_INFOL   std::cout << "\033[32m"         // green
#define RS_DEBUG   std::cout << "\033[1m\033[36m"  // bold cyan
#define RS_REND    "\033[0m" << std::endl

#define RS_TITLE   std::cout << "\033[1m\033[35m"  // bold magenta
#define RS_MSG     std::cout << "\033[1m\033[37m"  // bold white

typedef message_filters::sync_policies::ApproximateTime<
    sensor_msgs::msg::Range, sensor_msgs::msg::Range, sensor_msgs::msg::Range, sensor_msgs::msg::Range,
    sensor_msgs::msg::Range, sensor_msgs::msg::Range, sensor_msgs::msg::Range, sensor_msgs::msg::Range> SyncPolicy;
typedef message_filters::Synchronizer<SyncPolicy> Sync;


using std::placeholders::_1;
using std::placeholders::_2;
using std::placeholders::_3;
using std::placeholders::_4;

using std::placeholders::_5;
using std::placeholders::_6;
using std::placeholders::_7;
using std::placeholders::_8;

using std::placeholders::_9;
using std::placeholders::_10;
using std::placeholders::_11;
using std::placeholders::_12;

/**
 * @brief param for ultra_sonic_radar_detector_node
 * 
 */
struct Param
{
  std::string output_frame; // output frame of concat pointcloud
  float cloud_radius_m; // radius of sphere pointcloud in meters
  float cloud_resolution_m; // resolution of pointcloud in meters
};

/**
 * @brief convert radar range msg to a pointcloud in the shape of sphere
 * 
 * @param range_ptr radar range msg ptr
 * @param radius radius of sphere in meters
 * @param resolution resolution of pointcloud in meters
 * @return sensor_msgs::msg::PointCloud2 
 */
sensor_msgs::msg::PointCloud2 rangeToPointCloud(
  const sensor_msgs::msg::Range::ConstSharedPtr & range_ptr, const float & radius, const float & resolution);

class UltraSonicRadarDetector : public rclcpp::Node
{
private:
  Param param_;
  /**
   * @brief callback function of 8 radar topics
   * 
   * @param input_radar_0_msg 
   * @param input_radar_1_msg 
   * @param input_radar_2_msg 
   * @param input_radar_3_msg 
   * @param input_radar_4_msg 
   * @param input_radar_5_msg 
   * @param input_radar_6_msg 
   * @param input_radar_7_msg 
   */
  void radarsCallback_fr(
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_0_msg,
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_1_msg,
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_2_msg,
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_3_msg,

    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_4_msg,
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_5_msg,
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_6_msg,
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_7_msg);

  void radarsCallback_rl(
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_8_msg,
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_9_msg,
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_10_msg,
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_11_msg);

  // tf2
  tf2_ros::Buffer tf_buffer_;
  tf2_ros::TransformListener tf_listener_;

  // publisher
  rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr fr_merged_pointcloud_pub_;
  rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr lr_merged_pointcloud_pub_;

  // subscribers
  message_filters::Subscriber<sensor_msgs::msg::Range> radar_0_sub_;
  message_filters::Subscriber<sensor_msgs::msg::Range> radar_1_sub_;
  message_filters::Subscriber<sensor_msgs::msg::Range> radar_2_sub_;
  message_filters::Subscriber<sensor_msgs::msg::Range> radar_3_sub_;

  message_filters::Subscriber<sensor_msgs::msg::Range> radar_4_sub_;
  message_filters::Subscriber<sensor_msgs::msg::Range> radar_5_sub_;
  message_filters::Subscriber<sensor_msgs::msg::Range> radar_6_sub_;
  message_filters::Subscriber<sensor_msgs::msg::Range> radar_7_sub_;

  message_filters::Subscriber<sensor_msgs::msg::Range> radar_8_sub_;
  message_filters::Subscriber<sensor_msgs::msg::Range> radar_9_sub_;
  message_filters::Subscriber<sensor_msgs::msg::Range> radar_10_sub_;
  message_filters::Subscriber<sensor_msgs::msg::Range> radar_11_sub_;


  // synchronizer
  Sync sync_fr_;
  Sync sync_lr_;

public:
  /**
   * @brief Construct a new Ultra Sonic Radar Detector object
   * 
   */
  UltraSonicRadarDetector();
  /**
   * @brief Destroy the Ultra Sonic Radar Detector object
   * 
   */
  ~UltraSonicRadarDetector();
  /**
   * @brief transform pointcloud from its our frame to output_frame
   * 
   * @param in1 input pointcloud
   * @param out output/transformed pointcloud
   */
  void transformPointCloud(
    const sensor_msgs::msg::PointCloud2&  in, sensor_msgs::msg::PointCloud2& out);
  /**
   * @brief concatenate 2 pointclouds which share the same frame
   * 
   * @param in1 input pointcloud 1
   * @param in2 input pointcloud 2
   * @param out output/concatenated pointcloud
   */
  void combineClouds(
    const sensor_msgs::msg::PointCloud2& in1, const sensor_msgs::msg::PointCloud2& in2,
    sensor_msgs::msg::PointCloud2& out);
};

}  // namespace ultra_sonic_radar_detector

#endif  // __ULTRA_SONIC_RADAR_DETECTOR__HPP__