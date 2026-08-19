/**
 * Copyright (c) 2018-2023, Ouster, Inc.
 * All rights reserved.
 *
 * @file autoware_point_types.h
 * @brief PCL point datatype that matches the point representation expected by
 * Autoware (autoware::point_types::PointXYZIRCAEDT).
 *
 * Autoware compares the incoming PointCloud2 field names, datatypes AND byte
 * offsets against its own struct, so the layout below has to stay byte exact:
 *
 *   x           float32   @ 0
 *   y           float32   @ 4
 *   z           float32   @ 8
 *   intensity   uint8     @ 12
 *   return_type uint8     @ 13
 *   channel     uint16    @ 14
 *   azimuth     float32   @ 16
 *   elevation   float32   @ 20
 *   distance    float32   @ 24
 *   time_stamp  uint32    @ 28
 *
 * Note that PCL_ADD_POINT4D is deliberately not used here: it pads x/y/z to 16
 * bytes, which would push intensity to offset 16 and make Autoware reject the
 * cloud. The struct is plain and tightly packed instead, which is fine because
 * the driver never performs Eigen operations on the point itself.
 */

#pragma once

#include <pcl/point_types.h>

#include <cstddef>
#include <cstdint>
#include <tuple>

namespace ouster_ros {

/**
 * @brief mirrors autoware::point_types::ReturnType. Kept as a local definition
 * so that the driver does not need to depend on an Autoware package.
 */
enum AutowareReturnType : std::uint8_t {
    RETURN_TYPE_INVALID = 0,
    RETURN_TYPE_SINGLE_STRONGEST = 1,
    RETURN_TYPE_SINGLE_LAST = 2,
    RETURN_TYPE_DUAL_STRONGEST_FIRST = 3,
    RETURN_TYPE_DUAL_STRONGEST_LAST = 4,
    RETURN_TYPE_DUAL_WEAK_FIRST = 5,
    RETURN_TYPE_DUAL_WEAK_LAST = 6,
    RETURN_TYPE_DUAL_ONLY = 7,
};

struct PointXYZIRCAEDT {
    float x;
    float y;
    float z;
    std::uint8_t intensity;     // reflectivity, signal or near_ir, see intensity_source
    std::uint8_t return_type;   // one of AutowareReturnType
    std::uint16_t channel;      // equivalent to ring
    float azimuth;              // [rad] atan2(y, x) wrapped to [0, 2pi)
    float elevation;            // [rad] atan2(z, hypot(x, y))
    float distance;             // [m] range from the origin of the point cloud frame
    std::uint32_t time_stamp;   // [ns] relative to the point cloud message stamp

    inline PointXYZIRCAEDT()
        : x(0.0f),
          y(0.0f),
          z(0.0f),
          intensity(0),
          return_type(RETURN_TYPE_INVALID),
          channel(0),
          azimuth(0.0f),
          elevation(0.0f),
          distance(0.0f),
          time_stamp(0) {}

    inline const auto as_tuple() const {
        return std::tie(x, y, z, intensity, return_type, channel, azimuth,
                        elevation, distance, time_stamp);
    }

    inline auto as_tuple() {
        return std::tie(x, y, z, intensity, return_type, channel, azimuth,
                        elevation, distance, time_stamp);
    }

    template <size_t I>
    inline auto& get() {
        return std::get<I>(as_tuple());
    }
};

// Autoware performs a byte exact layout check on the received point cloud, any
// deviation here makes it silently fall back to an xyz only representation.
static_assert(sizeof(PointXYZIRCAEDT) == 32,
              "PointXYZIRCAEDT must be 32 bytes to match Autoware's layout");
static_assert(offsetof(PointXYZIRCAEDT, x) == 0, "unexpected x offset");
static_assert(offsetof(PointXYZIRCAEDT, y) == 4, "unexpected y offset");
static_assert(offsetof(PointXYZIRCAEDT, z) == 8, "unexpected z offset");
static_assert(offsetof(PointXYZIRCAEDT, intensity) == 12,
              "unexpected intensity offset");
static_assert(offsetof(PointXYZIRCAEDT, return_type) == 13,
              "unexpected return_type offset");
static_assert(offsetof(PointXYZIRCAEDT, channel) == 14,
              "unexpected channel offset");
static_assert(offsetof(PointXYZIRCAEDT, azimuth) == 16,
              "unexpected azimuth offset");
static_assert(offsetof(PointXYZIRCAEDT, elevation) == 20,
              "unexpected elevation offset");
static_assert(offsetof(PointXYZIRCAEDT, distance) == 24,
              "unexpected distance offset");
static_assert(offsetof(PointXYZIRCAEDT, time_stamp) == 28,
              "unexpected time_stamp offset");

}   // namespace ouster_ros

// clang-format off

POINT_CLOUD_REGISTER_POINT_STRUCT(ouster_ros::PointXYZIRCAEDT,
    (float, x, x)
    (float, y, y)
    (float, z, z)
    (std::uint8_t, intensity, intensity)
    (std::uint8_t, return_type, return_type)
    (std::uint16_t, channel, channel)
    (float, azimuth, azimuth)
    (float, elevation, elevation)
    (float, distance, distance)
    (std::uint32_t, time_stamp, time_stamp)
)

// clang-format on
