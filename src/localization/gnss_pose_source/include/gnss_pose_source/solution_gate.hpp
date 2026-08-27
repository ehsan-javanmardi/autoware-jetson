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

#ifndef GNSS_POSE_SOURCE__SOLUTION_GATE_HPP_
#define GNSS_POSE_SOURCE__SOLUTION_GATE_HPP_

#include <cmath>
#include <string>

namespace gnss_pose_source
{

/// Why a GNSS pose was refused, or Accepted.
enum class Verdict
{
  Accepted,
  NoFixSeen,
  FixTooOld,
  FixQualityTooLow,
  PositionTooUncertain,
  NoOrientationSeen,
  OrientationTooOld,
};

inline const char * describe(Verdict verdict)
{
  switch (verdict) {
    case Verdict::Accepted:
      return "accepted";
    case Verdict::NoFixSeen:
      return "no NavSatFix received yet";
    case Verdict::FixTooOld:
      return "the NavSatFix is stale";
    case Verdict::FixQualityTooLow:
      return "the fix type is below the required quality";
    case Verdict::PositionTooUncertain:
      return "the reported position uncertainty is too large";
    case Verdict::NoOrientationSeen:
      return "no GNSS/INS orientation received yet";
    case Verdict::OrientationTooOld:
      return "the GNSS/INS orientation is stale";
  }
  return "unknown";
}

/// Thresholds a GNSS solution has to clear before it may drive the EKF.
struct GateSettings
{
  /// Minimum sensor_msgs::NavSatStatus::status. 2 (GBAS_FIX) is what an RTK solution
  /// reports; 0 (FIX) is plain single-point positioning, metres out.
  int min_navsat_status{2};
  /// Largest horizontal standard deviation [m] that may still be used.
  double max_position_stddev{1.0};
  /// How old the supporting NavSatFix may be [s].
  double max_fix_age_sec{0.5};
  /// Whether a dual-antenna heading is required. Without one the pose's yaw comes from
  /// the direction of travel, which is meaningless at a standstill and would let the EKF
  /// pull the heading around while parked.
  bool require_ins_orientation{true};
  /// How old the GNSS/INS orientation may be [s].
  double max_orientation_age_sec{0.5};
};

/// What is currently known about the GNSS solution.
struct SolutionState
{
  bool has_fix{false};
  int navsat_status{-1};
  double fix_age_sec{0.0};

  bool has_orientation{false};
  double orientation_age_sec{0.0};

  /// Horizontal standard deviation of the pose being judged [m].
  double position_stddev{0.0};
};

/// Decides whether one GNSS pose is fit to be the vehicle's only position source.
///
/// Kept separate from the node and free of ROS types so the thresholds can be tested
/// directly. The order matters only for the message the operator sees: the most
/// fundamental problem is reported first, so "no fix at all" is not reported as
/// "uncertainty too large".
inline Verdict judge(const GateSettings & settings, const SolutionState & state)
{
  if (!state.has_fix) {
    return Verdict::NoFixSeen;
  }
  if (state.fix_age_sec > settings.max_fix_age_sec) {
    return Verdict::FixTooOld;
  }
  if (state.navsat_status < settings.min_navsat_status) {
    return Verdict::FixQualityTooLow;
  }
  if (!std::isfinite(state.position_stddev) ||
    state.position_stddev > settings.max_position_stddev)
  {
    return Verdict::PositionTooUncertain;
  }
  if (settings.require_ins_orientation) {
    if (!state.has_orientation) {
      return Verdict::NoOrientationSeen;
    }
    if (state.orientation_age_sec > settings.max_orientation_age_sec) {
      return Verdict::OrientationTooOld;
    }
  }
  return Verdict::Accepted;
}

}  // namespace gnss_pose_source

#endif  // GNSS_POSE_SOURCE__SOLUTION_GATE_HPP_
