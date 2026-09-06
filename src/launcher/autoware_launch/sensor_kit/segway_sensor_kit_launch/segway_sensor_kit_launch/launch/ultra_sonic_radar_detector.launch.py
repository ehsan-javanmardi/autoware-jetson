import os

from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    # input_ultra_sonic_radar_topic='/sensing/ultrasonic_radar/ultra_sonic_radar'
    input_ultra_sonic_radar_topic='/ultrasonic_radar/ultra_sonic_radar'
    
    output_frame = DeclareLaunchArgument(
        'output_frame',
        default_value='base_link'
    )

    output_cloud_fr = DeclareLaunchArgument(
        'output_cloud_fr',
        default_value='/sensing/ultra_sonic_radar/front_rear/pointcloud'
    )
    output_cloud_rl = DeclareLaunchArgument(
        'output_cloud_lr',
        default_value='/sensing/ultra_sonic_radar/leaf_right/pointcloud'
    )

    cloud_radius_m = DeclareLaunchArgument(
        'cloud_radius_m',
        default_value='0.2'
    )

    cloud_resolution_m = DeclareLaunchArgument(
        'cloud_resolution_m',
        default_value='0.01'
    )

    ultra_sonic_radar_detector_node = Node(
        package='ultra_sonic_radar_detector',
        executable='ultra_sonic_radar_detector_node',
        name='ultra_sonic_radar_detector_node',
        remappings=[
                ('input/radar_0', input_ultra_sonic_radar_topic + '_0'),
                ('input/radar_1', input_ultra_sonic_radar_topic + '_1'),
                ('input/radar_2', input_ultra_sonic_radar_topic + '_2'),
                ('input/radar_3', input_ultra_sonic_radar_topic + '_3'),
                ('input/radar_4', input_ultra_sonic_radar_topic + '_4'),
                ('input/radar_5', input_ultra_sonic_radar_topic + '_5'),
                ('input/radar_6', input_ultra_sonic_radar_topic + '_6'),
                ('input/radar_7', input_ultra_sonic_radar_topic + '_7'),

                ('input/radar_8', input_ultra_sonic_radar_topic + '_8'),
                ('input/radar_9', input_ultra_sonic_radar_topic + '_9'),
                ('input/radar_10', input_ultra_sonic_radar_topic + '_10'),
                ('input/radar_11', input_ultra_sonic_radar_topic + '_11'),
                ('output/front_rear/pointcloud', LaunchConfiguration("output_cloud_fr")),
                ('output/left_right/pointcloud', LaunchConfiguration("output_cloud_lr"))
            ],
        parameters=[
            {'output_frame': LaunchConfiguration("output_frame")},
            {'cloud_radius_m': LaunchConfiguration('cloud_radius_m')},
            {'cloud_resolution_m': LaunchConfiguration('cloud_resolution_m')}
        ],
        output='screen')

    return LaunchDescription([
        output_frame,
        output_cloud_fr,
        output_cloud_rl,
        cloud_radius_m,
        cloud_resolution_m,
        ultra_sonic_radar_detector_node
    ])
