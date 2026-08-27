// Copyright 2026 Ehsan Javanmardi
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#ifndef GNSS_POSE_SOURCE__GNSS_POSE_SOURCE_NODE_HPP_
#define GNSS_POSE_SOURCE__GNSS_POSE_SOURCE_NODE_HPP_

#include <algorithm>
#include <cmath>
#include <cstddef>

#include "gnss_pose_source/solution_gate.hpp"

#include <autoware_sensing_msgs/msg/gnss_ins_orientation_stamped.hpp>
#include <builtin_interfaces/msg/time.hpp>
#include <geometry_msgs/msg/pose_with_covariance_stamped.hpp>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/nav_sat_fix.hpp>

namespace gnss_pose_source
{

/// Makes RTK GNSS the vehicle's pose estimator, in place of a map matcher.
///
/// The EKF reads `/localization/pose_estimator/pose_with_covariance`, which is normally
/// written by NDT. This node writes it from the GNSS pose instead, but only while the
/// solution is good enough to be the *only* thing telling the vehicle where it is.
///
/// The covariance is relayed untouched. Whether a GNSS pose deserves to be trusted is a
/// question about the receiver's own accuracy estimate, and quietly substituting a
/// prettier number here would make the EKF confident for no reason. If that estimate is
/// wrong, the place to fix it is the driver that produces it — see the epe_quality
/// parameters of nmea_navsat_driver.
class GnssPoseSourceNode : public rclcpp::Node
{
public:
  explicit GnssPoseSourceNode(const rclcpp::NodeOptions & options);

private:
  void on_pose(const geometry_msgs::msg::PoseWithCovarianceStamped::ConstSharedPtr msg);
  void on_fix(const sensor_msgs::msg::NavSatFix::ConstSharedPtr msg);
  void on_orientation(
    const autoware_sensing_msgs::msg::GnssInsOrientationStamped::ConstSharedPtr msg);

  rclcpp::Subscription<geometry_msgs::msg::PoseWithCovarianceStamped>::SharedPtr pose_sub_;
  rclcpp::Subscription<sensor_msgs::msg::NavSatFix>::SharedPtr fix_sub_;
  rclcpp::Subscription<autoware_sensing_msgs::msg::GnssInsOrientationStamped>::SharedPtr
    orientation_sub_;
  rclcpp::Publisher<geometry_msgs::msg::PoseWithCovarianceStamped>::SharedPtr pose_pub_;

  GateSettings settings_;

  bool has_fix_{false};
  int last_fix_status_{-1};
  builtin_interfaces::msg::Time last_fix_time_;

  bool has_orientation_{false};
  builtin_interfaces::msg::Time last_orientation_time_;

  /// Whether poses are currently being passed on, so the transition can be logged once
  /// instead of on every message.
  bool accepting_{false};
};

}  // namespace gnss_pose_source

#endif  // GNSS_POSE_SOURCE__GNSS_POSE_SOURCE_NODE_HPP_
