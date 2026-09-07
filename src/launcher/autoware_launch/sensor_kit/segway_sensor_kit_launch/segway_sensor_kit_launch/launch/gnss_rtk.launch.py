"""u-blox ZED-F9R with working RTK against a VRS caster.

Replaces ublox_dgnss's own rover launch for two reasons, both of which have to hold at
once or RTK cannot work at all.

1. The NavSatFix publisher must be RELIABLE.

   ublox_nav_sat_fix_hp publishes best_effort by default. The NTRIP client that can
   actually uplink a position subscribes RELIABLE, and ROS 2 will not connect a
   best_effort publisher to a RELIABLE subscriber - it logs an incompatible-QoS warning
   and delivers nothing. QoS is fixed when the publisher is created, so this cannot be
   set with ros2 param afterwards; it has to be a launch parameter, and ublox's own
   launch file offers no way to pass one.

2. The NTRIP client must be the one that sends NMEA GGA.

   ichimill's mount points are VRS: the caster generates corrections for the receiver's
   own location and sends nothing until told where that is. ublox_dgnss's ntrip_client
   subscribes to nothing at all, so it can never say. It logs in, the caster replies OK,
   and both sit waiting - visible as a socket frozen at 179 bytes sent, 14 received.

   ntrip_client (the MicroStrain one) subscribes to a NavSatFix and builds the GGA from
   it, which is what closes the loop.

The RTCM path back into the receiver is /ntrip_client/rtcm, an absolute topic compiled
into ublox_dgnss_node, so the remap target here is absolute on purpose.

Credentials come from NTRIP_USERNAME and NTRIP_PASSWORD in the environment. This
repository is public; they live in ~/.ichimill.env.
"""
import os

import launch
from launch.actions import DeclareLaunchArgument
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, TextSubstitution
from launch_ros.actions import ComposableNodeContainer, Node
from launch_ros.descriptions import ComposableNode

RTCM_TOPIC = "/ntrip_client/rtcm"


def generate_launch_description():
    args = [
        DeclareLaunchArgument("log_level", default_value=TextSubstitution(text="INFO")),
        DeclareLaunchArgument("device_family", default_value=TextSubstitution(text="F9R")),
        DeclareLaunchArgument("frame_id", default_value=TextSubstitution(text="gnss_link")),
        DeclareLaunchArgument("host", default_value=TextSubstitution(text="ntrip.ales-corp.co.jp")),
        DeclareLaunchArgument("port", default_value=TextSubstitution(text="2101")),
        DeclareLaunchArgument("mountpoint", default_value=TextSubstitution(text="RTCM32M7S")),
        DeclareLaunchArgument("fix_topic", default_value=TextSubstitution(text="fix")),
    ]
    log_level = LaunchConfiguration("log_level")

    receiver_params = [{
        "DEVICE_FAMILY": LaunchConfiguration("device_family"),
        "FRAME_ID": LaunchConfiguration("frame_id"),
        "CFG_USBOUTPROT_NMEA": False,
        "CFG_RATE_MEAS": 10,
        "CFG_RATE_NAV": 100,
        "CFG_MSGOUT_UBX_NAV_HPPOSLLH_USB": 1,
        "CFG_MSGOUT_UBX_NAV_STATUS_USB": 5,
        "CFG_MSGOUT_UBX_NAV_COV_USB": 1,
        "CFG_MSGOUT_UBX_NAV_PVT_USB": 1,
        # Makes correction arrival visible at the receiver, which is the only way to
        # tell corrections reaching the chip from corrections reaching the client.
        "CFG_MSGOUT_UBX_RXM_RTCM_USB": 1,
    }]

    driver = ComposableNodeContainer(
        name="ublox_dgnss_container", namespace="",
        package="rclcpp_components", executable="component_container_mt",
        arguments=["--ros-args", "--log-level", log_level],
        composable_node_descriptions=[
            ComposableNode(
                package="ublox_dgnss_node",
                plugin="ublox_dgnss::UbloxDGNSSNode",
                name="ublox_dgnss",
                parameters=receiver_params,
            )
        ],
    )

    navsatfix = ComposableNodeContainer(
        name="ublox_nav_sat_fix_hp_container", namespace="",
        package="rclcpp_components", executable="component_container_mt",
        arguments=["--ros-args", "--log-level", log_level],
        composable_node_descriptions=[
            ComposableNode(
                package="ublox_nav_sat_fix_hp_node",
                plugin="ublox_nav_sat_fix_hp::UbloxNavSatHpFixNode",
                name="ublox_nav_sat_fix_hp",
                # The whole reason this file exists. Without it the NTRIP client below
                # never receives a fix, never sends a GGA, and the caster never streams.
                parameters=[{
                    "qos_overrides./sensing/gnss/fix.publisher.reliability": "reliable",
                }],
            )
        ],
    )

    ntrip = Node(
        package="ntrip_client", executable="ntrip_ros.py", name="ntrip_client",
        output="screen",
        parameters=[{
            "host": LaunchConfiguration("host"),
            "port": LaunchConfiguration("port"),
            "mountpoint": LaunchConfiguration("mountpoint"),
            "authenticate": True,
            "username": EnvironmentVariable("NTRIP_USERNAME", default_value=""),
            "password": EnvironmentVariable("NTRIP_PASSWORD", default_value=""),
            "ssl": False,
            # Defaults to mavros_msgs, which is not installed and is not what
            # ublox_dgnss_node subscribes to.
            "rtcm_message_package": "rtcm_msgs",
        }],
        remappings=[
            ("fix", LaunchConfiguration("fix_topic")),
            ("rtcm", RTCM_TOPIC),
        ],
    )

    return launch.LaunchDescription(args + [driver, navsatfix, ntrip])
