# Copyright 2022 Open Source Robotics Foundation, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

""" A simple launch file for the nmea_tcpclient_driver node. """

import os
import sys

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription, LaunchIntrospector, LaunchService, substitutions
from launch_ros import actions
from launch.actions import DeclareLaunchArgument


def generate_launch_description():
    """Generate a launch description for a single tcpclient driver."""
    logger = substitutions.LaunchConfiguration("log_level")
    driver_node = actions.Node(
        package='nmea_navsat_driver',
        executable='nmea_tcpclient_driver',
        output='screen',
        parameters=[{
            "ip": "192.168.1.110",
            "port": 9904,
            "buffer_size": 4096,
            # The driver defaults to stamping the fix with frame_id "gps", which no URDF in
            # this workspace creates. gnss_poser then fails every lookupTransform with
            # '"gps" passed to lookupTransform argument target_frame does not exist' and
            # skips the antenna lever arm entirely, so the pose it publishes is the antenna
            # position rather than base_link, and correcting the antenna offset changes
            # nothing. gnss_link is the frame the sensor kit description actually builds.
            "frame_id": "gnss_link",

            # Estimated position error per GGA quality indicator [m]. The driver turns
            # these into the NavSatFix covariance as (HDOP * epe)^2, and gnss_poser passes
            # that straight into the pose the EKF weights its GNSS measurement by. The
            # upstream defaults claim 4.0 m for an RTK *float* solution, which is roughly
            # ten times too pessimistic and was making a live float fix report 2.2-3.2 m
            # of uncertainty. That is harmless while NDT carries the position, and it is
            # not harmless at all with pose_source:=gnss, where this number is the only
            # thing telling the EKF how much to trust its one source of position.
            # Integer upstream, unlike the rest; a float here fails the type check.
            "epe_quality0": 1000000,    # invalid / unknown
            "epe_quality1": 4.0,        # single point
            "epe_quality2": 1.0,        # DGPS; the 0.1 m default is optimistic for it
            "epe_quality4": 0.02,       # RTK fixed
            "epe_quality5": 0.4,        # RTK float, realistically decimetre level
            "epe_quality9": 3.0,        # WAAS
        }],
        arguments=['--ros-args', '--log-level', logger]
        )
    argument = DeclareLaunchArgument(
            "log_level",
            default_value=["error"],
            description="Logging level"
            )
    return LaunchDescription([argument, driver_node])


def main(argv):
    ld = generate_launch_description()

    print('Starting introspection of launch description...')
    print('')

    print(LaunchIntrospector().format_launch_description(ld))

    print('')
    print('Starting launch of launch description...')
    print('')

    ls = LaunchService()
    ls.include_launch_description(ld)
    return ls.run()


if __name__ == '__main__':
    main(sys.argv)
