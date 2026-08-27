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

#include <gtest/gtest.h>

#include <cmath>
#include <limits>

#include "gnss_pose_source/solution_gate.hpp"

namespace
{

using gnss_pose_source::GateSettings;
using gnss_pose_source::judge;
using gnss_pose_source::SolutionState;
using gnss_pose_source::Verdict;

/// An RTK solution good enough to drive on.
SolutionState good()
{
  SolutionState state;
  state.has_fix = true;
  state.navsat_status = 2;  // GBAS
  state.fix_age_sec = 0.05;
  state.has_orientation = true;
  state.orientation_age_sec = 0.05;
  state.position_stddev = 0.03;
  return state;
}

}  // namespace

TEST(SolutionGate, accepts_a_healthy_rtk_solution)
{
  EXPECT_EQ(judge(GateSettings{}, good()), Verdict::Accepted);
}

TEST(SolutionGate, refuses_before_any_fix_has_arrived)
{
  auto state = good();
  state.has_fix = false;
  EXPECT_EQ(judge(GateSettings{}, state), Verdict::NoFixSeen);
}

TEST(SolutionGate, refuses_a_single_point_fix)
{
  // Status 0 is plain GPS, metres out. As the only pose source that is not drivable,
  // however small the reported covariance happens to be.
  auto state = good();
  state.navsat_status = 0;
  EXPECT_EQ(judge(GateSettings{}, state), Verdict::FixQualityTooLow);
}

TEST(SolutionGate, refuses_a_fix_that_has_stopped_updating)
{
  auto state = good();
  state.fix_age_sec = 2.0;
  EXPECT_EQ(judge(GateSettings{}, state), Verdict::FixTooOld);
}

TEST(SolutionGate, refuses_a_position_it_is_not_sure_enough_about)
{
  // What this vehicle's receiver actually reported while in RTK float with the upstream
  // epe table: GBAS status, but 3 m of claimed uncertainty.
  auto state = good();
  state.position_stddev = 3.16;
  EXPECT_EQ(judge(GateSettings{}, state), Verdict::PositionTooUncertain);
}

TEST(SolutionGate, refuses_a_non_finite_uncertainty)
{
  auto state = good();
  state.position_stddev = std::numeric_limits<double>::quiet_NaN();
  EXPECT_EQ(judge(GateSettings{}, state), Verdict::PositionTooUncertain);

  state.position_stddev = std::numeric_limits<double>::infinity();
  EXPECT_EQ(judge(GateSettings{}, state), Verdict::PositionTooUncertain);
}

TEST(SolutionGate, refuses_when_the_dual_antenna_heading_is_missing_or_stale)
{
  auto state = good();
  state.has_orientation = false;
  EXPECT_EQ(judge(GateSettings{}, state), Verdict::NoOrientationSeen);

  state = good();
  state.orientation_age_sec = 3.0;
  EXPECT_EQ(judge(GateSettings{}, state), Verdict::OrientationTooOld);
}

TEST(SolutionGate, ignores_orientation_when_it_is_not_required)
{
  GateSettings settings;
  settings.require_ins_orientation = false;

  auto state = good();
  state.has_orientation = false;
  state.orientation_age_sec = 100.0;
  EXPECT_EQ(judge(settings, state), Verdict::Accepted);
}

TEST(SolutionGate, reports_the_most_fundamental_problem_first)
{
  // Everything is wrong at once. "No fix at all" is the useful thing to tell an operator,
  // not "uncertainty too large", which would suggest the receiver is merely struggling.
  SolutionState state;
  state.has_fix = false;
  state.navsat_status = -1;
  state.position_stddev = 500.0;
  state.has_orientation = false;
  EXPECT_EQ(judge(GateSettings{}, state), Verdict::NoFixSeen);
}

TEST(SolutionGate, thresholds_are_boundaries_not_strict_limits)
{
  GateSettings settings;
  auto state = good();

  state.position_stddev = settings.max_position_stddev;
  EXPECT_EQ(judge(settings, state), Verdict::Accepted);

  state.position_stddev = std::nextafter(settings.max_position_stddev, 1e9);
  EXPECT_EQ(judge(settings, state), Verdict::PositionTooUncertain);
}

TEST(SolutionGate, a_tightened_threshold_rejects_a_float_grade_solution)
{
  // The intended way to move from bring-up to lane keeping: leave the fix type alone and
  // tighten the uncertainty a solution has to prove.
  GateSettings settings;
  settings.max_position_stddev = 0.1;

  auto state = good();
  state.position_stddev = 0.4;  // typical RTK float with a corrected epe table
  EXPECT_EQ(judge(settings, state), Verdict::PositionTooUncertain);

  state.position_stddev = 0.02;  // RTK fixed
  EXPECT_EQ(judge(settings, state), Verdict::Accepted);
}
