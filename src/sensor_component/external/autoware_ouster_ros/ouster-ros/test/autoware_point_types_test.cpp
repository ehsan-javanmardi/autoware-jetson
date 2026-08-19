#include <gtest/gtest.h>

#include <cmath>

// prevent clang-format from altering the location of "ouster_ros/os_ros.h", the
// header file needs to be the first include due to PCL_NO_PRECOMPILE flag
// clang-format off
#include "ouster_ros/os_ros.h"
// clang-format on
#include "ouster_ros/autoware_point_types.h"
#include "ouster_ros/sensor_point_types.h"
#include "../src/point_cloud_compose.h"

using namespace ouster_ros;
using namespace ouster_ros::point;

namespace {

// mirrors autoware::point_types::PointXYZIRCAEDT, Autoware compares the
// received fields against this layout name by name, offset by offset
struct ExpectedField {
    const char* name;
    uint32_t offset;
    uint8_t datatype;
};

constexpr ExpectedField expected_fields[] = {
    {"x", 0, sensor_msgs::msg::PointField::FLOAT32},
    {"y", 4, sensor_msgs::msg::PointField::FLOAT32},
    {"z", 8, sensor_msgs::msg::PointField::FLOAT32},
    {"intensity", 12, sensor_msgs::msg::PointField::UINT8},
    {"return_type", 13, sensor_msgs::msg::PointField::UINT8},
    {"channel", 14, sensor_msgs::msg::PointField::UINT16},
    {"azimuth", 16, sensor_msgs::msg::PointField::FLOAT32},
    {"elevation", 20, sensor_msgs::msg::PointField::FLOAT32},
    {"distance", 24, sensor_msgs::msg::PointField::FLOAT32},
    {"time_stamp", 28, sensor_msgs::msg::PointField::UINT32},
};

sensor_msgs::msg::PointCloud2 to_ros_msg(
    const ouster_ros::Cloud<PointXYZIRCAEDT>& pcl_cloud) {
    pcl::PCLPointCloud2 staging;
    pcl::toPCLPointCloud2(pcl_cloud, staging);
    sensor_msgs::msg::PointCloud2 msg;
    pcl_conversions::moveFromPCL(staging, msg);
    return msg;
}

}  // namespace

// the whole point of the type: a PointCloud2 that Autoware's
// is_data_layout_compatible_with_point_xyzircaedt accepts
TEST(AutowarePointTypesTest, PublishedLayoutMatchesAutoware) {
    ouster_ros::Cloud<PointXYZIRCAEDT> cloud(4, 1);
    const auto msg = to_ros_msg(cloud);

    EXPECT_EQ(msg.point_step, 32U);
    ASSERT_EQ(msg.fields.size(), 10U);
    for (size_t i = 0; i < msg.fields.size(); ++i) {
        EXPECT_EQ(msg.fields[i].name, expected_fields[i].name);
        EXPECT_EQ(msg.fields[i].offset, expected_fields[i].offset);
        EXPECT_EQ(msg.fields[i].datatype, expected_fields[i].datatype);
        EXPECT_EQ(msg.fields[i].count, 1U);
    }
}

TEST(AutowarePointTypesTest, TransformMapsSensorFields) {
    Point_RNG19_RFL8_SIG16_NIR16 src_pt;
    src_pt.x = 3.0f;
    src_pt.y = 4.0f;
    src_pt.z = 0.0f;
    src_pt.t = 123456U;
    src_pt.ring = 42;
    src_pt.range = 5000;
    src_pt.signal = 1000;
    src_pt.reflectivity = 200;
    src_pt.near_ir = 30;

    PointXYZIRCAEDT tgt_pt;
    TransformOpts opts;  // defaults to reflectivity, unity scale
    transform(tgt_pt, src_pt, opts);

    EXPECT_FLOAT_EQ(tgt_pt.x, 3.0f);
    EXPECT_FLOAT_EQ(tgt_pt.y, 4.0f);
    EXPECT_FLOAT_EQ(tgt_pt.z, 0.0f);
    EXPECT_EQ(tgt_pt.intensity, 200);
    EXPECT_EQ(tgt_pt.channel, 42);
    EXPECT_EQ(tgt_pt.time_stamp, 123456U);
    EXPECT_FLOAT_EQ(tgt_pt.distance, 5.0f);
    EXPECT_FLOAT_EQ(tgt_pt.azimuth, std::atan2(4.0f, 3.0f));
    EXPECT_FLOAT_EQ(tgt_pt.elevation, 0.0f);
}

TEST(AutowarePointTypesTest, AzimuthIsWrappedIntoZeroTwoPi) {
    Point_RNG19_RFL8_SIG16_NIR16 src_pt;
    src_pt.x = 0.0f;
    src_pt.y = -1.0f;
    src_pt.z = 1.0f;

    PointXYZIRCAEDT tgt_pt;
    transform(tgt_pt, src_pt, TransformOpts{});

    EXPECT_NEAR(tgt_pt.azimuth, 1.5f * static_cast<float>(M_PI), 1e-5);
    EXPECT_NEAR(tgt_pt.elevation, 0.25f * static_cast<float>(M_PI), 1e-5);
}

TEST(AutowarePointTypesTest, IntensitySourceIsSelectable) {
    Point_RNG19_RFL8_SIG16_NIR16 src_pt;
    src_pt.signal = 1000;
    src_pt.reflectivity = 200;
    src_pt.near_ir = 30;

    PointXYZIRCAEDT tgt_pt;

    TransformOpts opts;
    opts.intensity_source = intensity_source_of("signal");
    opts.intensity_scale = 0.1f;
    transform(tgt_pt, src_pt, opts);
    EXPECT_EQ(tgt_pt.intensity, 100);  // 1000 * 0.1

    // signal saturates the uint8 range instead of wrapping around
    opts.intensity_scale = 1.0f;
    transform(tgt_pt, src_pt, opts);
    EXPECT_EQ(tgt_pt.intensity, 255);

    opts.intensity_source = intensity_source_of("near_ir");
    transform(tgt_pt, src_pt, opts);
    EXPECT_EQ(tgt_pt.intensity, 30);

    EXPECT_THROW(intensity_source_of("ambient"), std::invalid_argument);
}

TEST(AutowarePointTypesTest, ReturnTypeIsAssignedOnlyWhenPresent) {
    PointXYZIRCAEDT aedt_pt;
    set_return_type(aedt_pt, RETURN_TYPE_DUAL_STRONGEST_FIRST);
    EXPECT_EQ(aedt_pt.return_type, RETURN_TYPE_DUAL_STRONGEST_FIRST);

    // types without the field are left untouched, this must compile
    ouster_ros::Point original_pt;
    set_return_type(original_pt, RETURN_TYPE_SINGLE_STRONGEST);
    SUCCEED();
}
