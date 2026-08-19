#include "ultra_sonic_radar_detector/ultra_sonic_radar_detector.hpp"

namespace ultra_sonic_radar_detector
{

sensor_msgs::msg::PointCloud2 rangeToPointCloud(
  const sensor_msgs::msg::Range::ConstSharedPtr & range_ptr, const float & radius, const float & resolution)
{
  sensor_msgs::msg::PointCloud2 output_pointcloud;

  pcl::PointCloud<pcl::PointXYZ>::Ptr cloud_ptr(new pcl::PointCloud<pcl::PointXYZ>);
  cloud_ptr->width = 1000;
  cloud_ptr->height = 1000;
  cloud_ptr->is_dense = false;
  cloud_ptr->points.reserve(cloud_ptr->width * cloud_ptr->height);
  
  if (range_ptr->range > range_ptr->max_range || range_ptr->range < range_ptr->min_range ||
      radius == 0.0) {
    cloud_ptr->resize(cloud_ptr->points.size());
    pcl::toROSMsg(*cloud_ptr, output_pointcloud);
    output_pointcloud.header = range_ptr->header;

    return output_pointcloud;
  }
  for (float y = -radius; y <= radius; y += resolution) {
    for (float x = -radius; x <= radius; x += resolution) {
      for (float z = -radius; z <= radius; z += resolution) {
        if (x * x + y * y + z * z <= radius * radius) {
          pcl::PointXYZ point;
          point.x = x+range_ptr->range;
          point.y = y;
          point.z = z;
          cloud_ptr->points.push_back(point);
        }
      }
    }
  }
  cloud_ptr->resize(cloud_ptr->points.size());
  pcl::toROSMsg(*cloud_ptr, output_pointcloud);
  output_pointcloud.header = range_ptr->header;
  return output_pointcloud;
}

void UltraSonicRadarDetector::transformPointCloud(
  const sensor_msgs::msg::PointCloud2&  in, sensor_msgs::msg::PointCloud2& out)
{
  if (param_.output_frame != in.header.frame_id) {
    try {
      geometry_msgs::msg::TransformStamped transformStamped =
        tf_buffer_.lookupTransform(param_.output_frame, in.header.frame_id, rclcpp::Time());
      // RS_INFO <<  "transformStamped" << RS_REND;
      tf2::doTransform(in, out, transformStamped);
    } catch (tf2::TransformException & ex) {
      RCLCPP_WARN(this->get_logger(),
        "[UltraSonicRadarDetector::transformPointCloud] Error converting from %s to %s, %s",
        in.header.frame_id.c_str(), param_.output_frame.c_str(), ex.what());
      return;
    }
  } else {
    out = in;
  }
}

void UltraSonicRadarDetector::combineClouds(
    const sensor_msgs::msg::PointCloud2& in1, const sensor_msgs::msg::PointCloud2& in2,
    sensor_msgs::msg::PointCloud2& out)
{
  pcl::concatenatePointCloud(in1, in2, out);

  rclcpp::Time time1(in1.header.stamp.sec, in1.header.stamp.nanosec);
  rclcpp::Time time2(in2.header.stamp.sec, in2.header.stamp.nanosec);
  if (time1 < time2) {
    out.header.stamp = in1.header.stamp;
  } else if (time1 >= time2) {
    out.header.stamp = in2.header.stamp;
  } 
}

UltraSonicRadarDetector::UltraSonicRadarDetector():Node("ultra_sonic_radar_detector_node"),
  tf_buffer_(this->get_clock()), tf_listener_(tf_buffer_),
  radar_0_sub_(this, "input/radar_0", rclcpp::QoS{1}.get_rmw_qos_profile()),
  radar_1_sub_(this, "input/radar_1", rclcpp::QoS{1}.get_rmw_qos_profile()),
  radar_2_sub_(this, "input/radar_2", rclcpp::QoS{1}.get_rmw_qos_profile()),
  radar_3_sub_(this, "input/radar_3", rclcpp::QoS{1}.get_rmw_qos_profile()),

  radar_4_sub_(this, "input/radar_4", rclcpp::QoS{1}.get_rmw_qos_profile()),
  radar_5_sub_(this, "input/radar_5", rclcpp::QoS{1}.get_rmw_qos_profile()),
  radar_6_sub_(this, "input/radar_6", rclcpp::QoS{1}.get_rmw_qos_profile()),
  radar_7_sub_(this, "input/radar_7", rclcpp::QoS{1}.get_rmw_qos_profile()),

  radar_8_sub_(this, "input/radar_8", rclcpp::QoS{1}.get_rmw_qos_profile()),
  radar_9_sub_(this, "input/radar_9", rclcpp::QoS{1}.get_rmw_qos_profile()),
  radar_10_sub_(this, "input/radar_10", rclcpp::QoS{1}.get_rmw_qos_profile()),
  radar_11_sub_(this, "input/radar_11", rclcpp::QoS{1}.get_rmw_qos_profile()),
  sync_fr_(SyncPolicy(5), 
    radar_0_sub_, radar_1_sub_, radar_2_sub_, radar_3_sub_, 
    radar_4_sub_, radar_5_sub_, radar_6_sub_, radar_7_sub_),
  sync_lr_(SyncPolicy(10), 
    radar_8_sub_, radar_9_sub_, radar_10_sub_, radar_11_sub_)
{
  param_.output_frame = this->declare_parameter("output_frame", "base_link");
  param_.cloud_radius_m = this->declare_parameter("cloud_radius_m", 0.2);
  param_.cloud_resolution_m = this->declare_parameter("cloud_resolution_m", 0.01);

  sync_fr_.registerCallback(
    std::bind(&UltraSonicRadarDetector::radarsCallback_fr, this, _1, _2, _3, _4, _5, _6, _7, _8));

  sync_lr_.registerCallback(
    std::bind(&UltraSonicRadarDetector::radarsCallback_rl, this, _1, _2, _3, _4));

  fr_merged_pointcloud_pub_ = 
    this->create_publisher<sensor_msgs::msg::PointCloud2>("output/front_rear/pointcloud", rclcpp::SensorDataQoS());
  
  lr_merged_pointcloud_pub_ = 
    this->create_publisher<sensor_msgs::msg::PointCloud2>("output/left_right/pointcloud", rclcpp::SensorDataQoS());
}

UltraSonicRadarDetector::~UltraSonicRadarDetector()
{
  
} 
void UltraSonicRadarDetector::radarsCallback_rl(
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_8_msg,
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_9_msg,
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_10_msg,
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_11_msg)
{
  std::cout << "input_radar_8_msg: " << input_radar_8_msg->range << std::endl;
  // Create 4 point clouds
  sensor_msgs::msg::PointCloud2 cloud_0 =
    rangeToPointCloud(input_radar_8_msg, param_.cloud_radius_m, param_.cloud_resolution_m);
  sensor_msgs::msg::PointCloud2 cloud_1 =
    rangeToPointCloud(input_radar_9_msg, param_.cloud_radius_m, param_.cloud_resolution_m);
  sensor_msgs::msg::PointCloud2 cloud_2 =
    rangeToPointCloud(input_radar_10_msg, param_.cloud_radius_m, param_.cloud_resolution_m);
  sensor_msgs::msg::PointCloud2 cloud_3 =
    rangeToPointCloud(input_radar_11_msg, param_.cloud_radius_m, param_.cloud_resolution_m);
  
  sensor_msgs::msg::PointCloud2 cloud_tranformed_0;
  sensor_msgs::msg::PointCloud2 cloud_tranformed_1;
  sensor_msgs::msg::PointCloud2 cloud_tranformed_2;
  sensor_msgs::msg::PointCloud2 cloud_tranformed_3;
 
  transformPointCloud(cloud_0, cloud_tranformed_0);
  transformPointCloud(cloud_1, cloud_tranformed_1);
  transformPointCloud(cloud_2, cloud_tranformed_2);
  transformPointCloud(cloud_3, cloud_tranformed_3);

  // concatenate pointclouds
  sensor_msgs::msg::PointCloud2 output_clouds_0;
  sensor_msgs::msg::PointCloud2 output_clouds_1;
  sensor_msgs::msg::PointCloud2 output_clouds_2;
  
  combineClouds(cloud_tranformed_0, cloud_tranformed_1, output_clouds_0);
  combineClouds(output_clouds_0, cloud_tranformed_2, output_clouds_1);
  combineClouds(output_clouds_1, cloud_tranformed_3, output_clouds_2);
  output_clouds_2.header.frame_id = param_.output_frame;
  output_clouds_2.header.stamp = rclcpp::Time();
  fr_merged_pointcloud_pub_->publish(output_clouds_2);
}

void UltraSonicRadarDetector::radarsCallback_fr(
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_0_msg,
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_1_msg,
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_2_msg,
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_3_msg,

    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_4_msg,
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_5_msg,
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_6_msg,
    const sensor_msgs::msg::Range::ConstSharedPtr & input_radar_7_msg)
{
  // Create 8 point clouds
  sensor_msgs::msg::PointCloud2 cloud_0 =
    rangeToPointCloud(input_radar_0_msg, param_.cloud_radius_m, param_.cloud_resolution_m);
  sensor_msgs::msg::PointCloud2 cloud_1 =
    rangeToPointCloud(input_radar_1_msg, param_.cloud_radius_m, param_.cloud_resolution_m);
  sensor_msgs::msg::PointCloud2 cloud_2 =
    rangeToPointCloud(input_radar_2_msg, param_.cloud_radius_m, param_.cloud_resolution_m);
  sensor_msgs::msg::PointCloud2 cloud_3 =
    rangeToPointCloud(input_radar_3_msg, param_.cloud_radius_m, param_.cloud_resolution_m);
  
  sensor_msgs::msg::PointCloud2 cloud_4 =
    rangeToPointCloud(input_radar_4_msg, param_.cloud_radius_m, param_.cloud_resolution_m);
  sensor_msgs::msg::PointCloud2 cloud_5 =
    rangeToPointCloud(input_radar_5_msg, param_.cloud_radius_m, param_.cloud_resolution_m);
  sensor_msgs::msg::PointCloud2 cloud_6 =
    rangeToPointCloud(input_radar_6_msg, param_.cloud_radius_m, param_.cloud_resolution_m);
  sensor_msgs::msg::PointCloud2 cloud_7 =
    rangeToPointCloud(input_radar_7_msg, param_.cloud_radius_m, param_.cloud_resolution_m);

  sensor_msgs::msg::PointCloud2 cloud_tranformed_0;
  sensor_msgs::msg::PointCloud2 cloud_tranformed_1;
  sensor_msgs::msg::PointCloud2 cloud_tranformed_2;
  sensor_msgs::msg::PointCloud2 cloud_tranformed_3;
  sensor_msgs::msg::PointCloud2 cloud_tranformed_4;
  sensor_msgs::msg::PointCloud2 cloud_tranformed_5;
  sensor_msgs::msg::PointCloud2 cloud_tranformed_6;
  sensor_msgs::msg::PointCloud2 cloud_tranformed_7;

  transformPointCloud(cloud_0, cloud_tranformed_0);
  transformPointCloud(cloud_1, cloud_tranformed_1);
  transformPointCloud(cloud_2, cloud_tranformed_2);
  transformPointCloud(cloud_3, cloud_tranformed_3);
  transformPointCloud(cloud_4, cloud_tranformed_4);
  transformPointCloud(cloud_5, cloud_tranformed_5);
  transformPointCloud(cloud_6, cloud_tranformed_6);
  transformPointCloud(cloud_7, cloud_tranformed_7);

  // concatenate pointclouds
  sensor_msgs::msg::PointCloud2 output_clouds_0;
  sensor_msgs::msg::PointCloud2 output_clouds_1;
  sensor_msgs::msg::PointCloud2 output_clouds_2;
  sensor_msgs::msg::PointCloud2 output_clouds_3;
  sensor_msgs::msg::PointCloud2 output_clouds_4;
  sensor_msgs::msg::PointCloud2 output_clouds_5;
  sensor_msgs::msg::PointCloud2 output_clouds_6;
  combineClouds(cloud_tranformed_0, cloud_tranformed_1, output_clouds_0);
  combineClouds(output_clouds_0, cloud_tranformed_2, output_clouds_1);
  combineClouds(output_clouds_1, cloud_tranformed_3, output_clouds_2);
  combineClouds(output_clouds_2, cloud_tranformed_4, output_clouds_3);
  combineClouds(output_clouds_3, cloud_tranformed_5, output_clouds_4);
  combineClouds(output_clouds_4, cloud_tranformed_6, output_clouds_5);
  combineClouds(output_clouds_5, cloud_tranformed_7, output_clouds_6);
  output_clouds_6.header.frame_id = param_.output_frame;
  output_clouds_6.header.stamp = this->now();
  fr_merged_pointcloud_pub_->publish(output_clouds_6);
}

}  // namespace ultra_sonic_radar_detector
