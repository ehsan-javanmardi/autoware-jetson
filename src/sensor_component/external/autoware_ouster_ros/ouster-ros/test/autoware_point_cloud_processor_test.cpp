#include <gtest/gtest.h>

#include <sensor_msgs/point_cloud2_iterator.hpp>

#include <fstream>
#include <sstream>

// prevent clang-format from altering the location of "ouster_ros/os_ros.h", the
// header file needs to be the first include due to PCL_NO_PRECOMPILE flag
// clang-format off
#include "ouster_ros/os_ros.h"
// clang-format on
#include "ouster_ros/autoware_point_types.h"
#include "../src/point_cloud_processor_factory.h"

using namespace ouster_ros;

namespace {

constexpr int kBeamsUnderTest = 8;
constexpr int kColumnsUnderTest = 16;

ouster::sensor::sensor_info load_sensor_info() {
    std::ifstream file(std::string(TEST_METADATA_DIR) +
                       "/2_4_0_os-992146000760-128.json");
    std::stringstream buffer;
    buffer << file.rdbuf();
    return ouster::sensor::parse_metadata(buffer.str());
}

// a scan where every pixel has a return, so that no point is dropped and the
// mapping of each channel can be checked by index
ouster::LidarScan make_populated_scan(
    const ouster::sensor::sensor_info& info) {
    ouster::LidarScan ls(kColumnsUnderTest, kBeamsUnderTest,
                         info.format.udp_profile_lidar);

    auto range = ls.field<uint32_t>(ouster::sensor::ChanField::RANGE);
    auto signal = ls.field<uint16_t>(ouster::sensor::ChanField::SIGNAL);
    auto reflectivity =
        ls.field<uint16_t>(ouster::sensor::ChanField::REFLECTIVITY);
    auto near_ir = ls.field<uint16_t>(ouster::sensor::ChanField::NEAR_IR);

    for (int u = 0; u < kBeamsUnderTest; ++u) {
        for (int v = 0; v < kColumnsUnderTest; ++v) {
            range(u, v) = 3000 + 100 * u;   // millimeters
            signal(u, v) = 500;
            reflectivity(u, v) = static_cast<uint16_t>(100 + u);
            near_ir(u, v) = 20;
        }
    }

    auto timestamp = ls.timestamp();
    for (int v = 0; v < kColumnsUnderTest; ++v) {
        timestamp(v) = 1'000'000'000UL + static_cast<uint64_t>(v) * 100'000UL;
    }

    return ls;
}

}  // namespace

// end to end check of the path the driver actually takes: LidarScan ->
// PointCloudProcessor -> PointCloud2, with the sensor_info of a real sensor
class AutowarePointCloudProcessorTest : public ::testing::Test {
   protected:
    void SetUp() override {
        info = load_sensor_info();
        info.format.columns_per_frame = kColumnsUnderTest;
        info.format.pixels_per_column = kBeamsUnderTest;
        info.format.pixel_shift_by_row.assign(kBeamsUnderTest, 0);
        info.beam_azimuth_angles.resize(kBeamsUnderTest);
        info.beam_altitude_angles.resize(kBeamsUnderTest);
    }

    sensor_msgs::msg::PointCloud2 process(const point::TransformOpts& opts) {
        sensor_msgs::msg::PointCloud2 result;
        auto processor =
            PointCloudProcessorFactory::create_point_cloud_processor(
                "xyzircaedt", info, "os_lidar",
                /*apply_lidar_to_sensor_transform=*/false,
                /*organized=*/false, /*destagger=*/true, /*min_range=*/0,
                /*max_range=*/1'000'000, /*rows_step=*/1,
                [&result](PointCloudProcessor_OutputType msgs) {
                    result = *msgs[0];
                },
                opts);

        const auto ls = make_populated_scan(info);
        processor(ls, ls.timestamp()(0), rclcpp::Time(0, 0));
        return result;
    }

    ouster::sensor::sensor_info info;
};

TEST_F(AutowarePointCloudProcessorTest, PublishesTheAutowareLayout) {
    const auto msg = process(point::TransformOpts{});

    EXPECT_EQ(msg.point_step, 32U);
    ASSERT_EQ(msg.fields.size(), 10U);
    EXPECT_EQ(msg.fields[3].name, "intensity");
    EXPECT_EQ(msg.fields[9].name, "time_stamp");
    EXPECT_EQ(msg.width * msg.height,
              static_cast<uint32_t>(kBeamsUnderTest * kColumnsUnderTest));
    EXPECT_EQ(msg.data.size(), msg.width * msg.height * msg.point_step);
}

TEST_F(AutowarePointCloudProcessorTest, PopulatesEveryChannel) {
    const auto msg = process(point::TransformOpts{});

    sensor_msgs::PointCloud2ConstIterator<float> it_x(msg, "x");
    sensor_msgs::PointCloud2ConstIterator<uint8_t> it_i(msg, "intensity");
    sensor_msgs::PointCloud2ConstIterator<uint8_t> it_r(msg, "return_type");
    sensor_msgs::PointCloud2ConstIterator<uint16_t> it_c(msg, "channel");
    sensor_msgs::PointCloud2ConstIterator<float> it_a(msg, "azimuth");
    sensor_msgs::PointCloud2ConstIterator<float> it_d(msg, "distance");
    sensor_msgs::PointCloud2ConstIterator<uint32_t> it_t(msg, "time_stamp");

    bool saw_non_zero_timestamp = false;
    size_t count = 0;
    for (; it_x != it_x.end();
         ++it_x, ++it_i, ++it_r, ++it_c, ++it_a, ++it_d, ++it_t) {
        ASSERT_FALSE(std::isnan(*it_x)) << "invalid point at index " << count;
        // reflectivity was written as 100 + row, and channel is the row
        EXPECT_EQ(*it_i, static_cast<uint8_t>(100 + *it_c));
        EXPECT_EQ(*it_r, RETURN_TYPE_SINGLE_STRONGEST);
        EXPECT_LT(*it_c, kBeamsUnderTest);
        EXPECT_GE(*it_a, 0.0f);
        EXPECT_LT(*it_a, 2.0f * static_cast<float>(M_PI));
        // ranges were 3.0 m and up
        EXPECT_GT(*it_d, 2.9f);
        saw_non_zero_timestamp |= (*it_t != 0U);
        ++count;
    }

    EXPECT_EQ(count, static_cast<size_t>(kBeamsUnderTest * kColumnsUnderTest));
    EXPECT_TRUE(saw_non_zero_timestamp)
        << "per point timestamps are what makes distortion correction possible";
}

TEST_F(AutowarePointCloudProcessorTest, HonorsTheIntensitySource) {
    point::TransformOpts opts;
    opts.intensity_source = point::TransformOpts::IntensitySource::SIGNAL;
    opts.intensity_scale = 0.5f;   // signal was 500 for every pixel
    const auto msg = process(opts);

    sensor_msgs::PointCloud2ConstIterator<uint8_t> it_i(msg, "intensity");
    for (; it_i != it_i.end(); ++it_i) {
        EXPECT_EQ(*it_i, 250);
    }
}
