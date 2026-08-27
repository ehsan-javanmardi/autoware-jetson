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

#include <memory>
#include <string>

#include "gnss_pose_source/gnss_pose_source_node.hpp"

namespace gnss_pose_source
{
namespace
{
/// Diagonal indices of the 6x6 pose covariance for x and y.
constexpr std::size_t covariance_xx = 0;
constexpr std::size_t covariance_yy = 7;
constexpr int throttle_period_ms = 5000;
constexpr int queue_depth = 1;
}  // namespace

GnssPoseSourceNode::GnssPoseSourceNode(const rclcpp::NodeOptions & options)
: Node("gnss_pose_source", options)
{
  settings_.min_navsat_status = static_cast<int>(declare_parameter<int>("min_navsat_status", 2));
  settings_.max_position_stddev = declare_parameter<double>("max_position_stddev", 1.0);
  settings_.max_fix_age_sec = declare_parameter<double>("max_fix_age_sec", 0.5);
  settings_.require_ins_orientation = declare_parameter<bool>("require_ins_orientation", true);
  settings_.max_orientation_age_sec = declare_parameter<double>("max_orientation_age_sec", 0.5);

  pose_pub_ = create_publisher<geometry_msgs::msg::PoseWithCovarianceStamped>(
    "~/output/pose_with_covariance", rclcpp::QoS{queue_depth});

  pose_sub_ = create_subscription<geometry_msgs::msg::PoseWithCovarianceStamped>(
    "~/input/pose_with_covariance", rclcpp::QoS{queue_depth},
    std::bind(&GnssPoseSourceNode::on_pose, this, std::placeholders::_1));
  fix_sub_ = create_subscription<sensor_msgs::msg::NavSatFix>(
    "~/input/fix", rclcpp::QoS{queue_depth},
    std::bind(&GnssPoseSourceNode::on_fix, this, std::placeholders::_1));
  orientation_sub_ = create_subscription<autoware_sensing_msgs::msg::GnssInsOrientationStamped>(
    "~/input/gnss_ins_orientation", rclcpp::QoS{queue_depth},
    std::bind(&GnssPoseSourceNode::on_orientation, this, std::placeholders::_1));

  RCLCPP_INFO(
    get_logger(),
    "GNSS is the only pose source. Requiring NavSatStatus >= %d, position std dev <= %.2f m, "
    "INS orientation %s.",
    settings_.min_navsat_status, settings_.max_position_stddev,
    settings_.require_ins_orientation ? "required" : "not required");
}

void GnssPoseSourceNode::on_fix(const sensor_msgs::msg::NavSatFix::ConstSharedPtr msg)
{
  last_fix_status_ = msg->status.status;
  last_fix_time_ = msg->header.stamp;
  has_fix_ = true;
}

void GnssPoseSourceNode::on_orientation(
  const autoware_sensing_msgs::msg::GnssInsOrientationStamped::ConstSharedPtr msg)
{
  last_orientation_time_ = msg->header.stamp;
  has_orientation_ = true;
}

void GnssPoseSourceNode::on_pose(
  const geometry_msgs::msg::PoseWithCovarianceStamped::ConstSharedPtr msg)
{
  const auto stamp = rclcpp::Time(msg->header.stamp);

  SolutionState state;
  state.has_fix = has_fix_;
  state.navsat_status = last_fix_status_;
  state.fix_age_sec = has_fix_ ? (stamp - rclcpp::Time(last_fix_time_)).seconds() : 0.0;
  state.has_orientation = has_orientation_;
  state.orientation_age_sec =
    has_orientation_ ? (stamp - rclcpp::Time(last_orientation_time_)).seconds() : 0.0;
  // The covariance is passed through untouched, so the EKF weights the measurement by
  // what the receiver actually claims. The gate only decides whether to pass it at all.
  state.position_stddev = std::sqrt(
    std::max(msg->pose.covariance[covariance_xx], msg->pose.covariance[covariance_yy]));

  const auto verdict = judge(settings_, state);

  if (verdict != Verdict::Accepted) {
    // Dropping rather than publishing something degraded is deliberate: with no other
    // pose source the EKF has to coast on gyro and wheel odometry, its covariance grows,
    // and localization_error_monitor takes autonomous mode away. Feeding a bad pose
    // instead would keep the system confident while being wrong.
    RCLCPP_WARN_THROTTLE(
      get_logger(), *get_clock(), throttle_period_ms,
      "dropping GNSS pose: %s (status %d, %.2f m std dev). The EKF is dead reckoning.",
      describe(verdict), state.navsat_status, state.position_stddev);
    if (accepting_) {
      RCLCPP_WARN(get_logger(), "GNSS pose source stopped: %s", describe(verdict));
      accepting_ = false;
    }
    return;
  }

  if (!accepting_) {
    RCLCPP_INFO(
      get_logger(), "GNSS pose source accepted (status %d, %.3f m std dev)", state.navsat_status,
      state.position_stddev);
    accepting_ = true;
  }

  pose_pub_->publish(*msg);
}

}  // namespace gnss_pose_source

#include <rclcpp_components/register_node_macro.hpp>
RCLCPP_COMPONENTS_REGISTER_NODE(gnss_pose_source::GnssPoseSourceNode)
