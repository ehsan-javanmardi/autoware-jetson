/**
 * Copyright (c) 2018-2023, Ouster, Inc.
 * All rights reserved.
 *
 * @file point_transform.h
 * @brief Implements the main transform_point method used to convert point from
 * a source pcl point format usually sensor native point representation to other
 * pcl point formats such as Velodyne XYZIR or pcl::XYZ, pcl::XYZI, ... 
 */

#pragma once

#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <string>

#include "ouster_ros/autoware_point_types.h"

#include "point_meta_helpers.h"

namespace ouster_ros {
namespace point {

DEFINE_MEMBER_CHECKER(x);
DEFINE_MEMBER_CHECKER(y);
DEFINE_MEMBER_CHECKER(z);
DEFINE_MEMBER_CHECKER(t);
DEFINE_MEMBER_CHECKER(ring);
DEFINE_MEMBER_CHECKER(intensity);
DEFINE_MEMBER_CHECKER(ambient);
DEFINE_MEMBER_CHECKER(range);
DEFINE_MEMBER_CHECKER(signal);
DEFINE_MEMBER_CHECKER(reflectivity);
DEFINE_MEMBER_CHECKER(near_ir);
DEFINE_MEMBER_CHECKER(return_type);

template <typename PointTGT, typename PointSRC>
void transform(PointTGT& tgt_pt, const PointSRC& src_pt) {
    // NOTE: for now we assume all points have xyz component
    tgt_pt.x = src_pt.x; tgt_pt.y = src_pt.y; tgt_pt.z = src_pt.z;

    // t: timestamp
    CondBinaryOp<has_t_v<PointTGT> && has_t_v<PointSRC>>::run(
        tgt_pt, src_pt, [](auto& tgt_pt, const auto& src_pt) { tgt_pt.t = src_pt.t; }
    );

    CondBinaryOp<has_t_v<PointTGT> && !has_t_v<PointSRC>>::run(
        tgt_pt, src_pt, [](auto& tgt_pt, const auto&) { tgt_pt.t = 0U; }
    );

    // ring
    CondBinaryOp<has_ring_v<PointTGT> && has_ring_v<PointSRC>>::run(
        tgt_pt, src_pt, [](auto& tgt_pt, const auto& src_pt) { tgt_pt.ring = src_pt.ring; }
    );

    CondBinaryOp<has_ring_v<PointTGT> && !has_ring_v<PointSRC>>::run(
        tgt_pt, src_pt, [](auto& tgt_pt, const auto&) {
            tgt_pt.ring = static_cast<decltype(tgt_pt.ring)>(0);
        }
    );

    // range
    CondBinaryOp<has_range_v<PointTGT> && has_range_v<PointSRC>>::run(
        tgt_pt, src_pt, [](auto& tgt_pt, const auto& src_pt) { tgt_pt.range = src_pt.range; }
    );

    CondBinaryOp<has_range_v<PointTGT> && !has_range_v<PointSRC>>::run(
        tgt_pt, src_pt, [](auto& tgt_pt, const auto&) { tgt_pt.range = 0U; }
    );

    // signal
    CondBinaryOp<has_signal_v<PointTGT> && has_signal_v<PointSRC>>::run(
        tgt_pt, src_pt, [](auto& tgt_pt, const auto& src_pt) { tgt_pt.signal = src_pt.signal; }
    );

    CondBinaryOp<has_signal_v<PointTGT> && !has_signal_v<PointSRC>>::run(
        tgt_pt, src_pt, [](auto& tgt_pt, const auto&) {
            tgt_pt.signal = static_cast<decltype(tgt_pt.signal)>(0);
        }
    );

    // intensity <- signal
    // PointTGT should not have signal and intensity at the same time [normally]
    CondBinaryOp<has_intensity_v<PointTGT> && has_signal_v<PointSRC>>::run(
        tgt_pt, src_pt, [](auto& tgt_pt, const auto& src_pt) {
            tgt_pt.intensity = static_cast<decltype(tgt_pt.intensity)>(src_pt.signal);
        }
    );

    CondBinaryOp<has_intensity_v<PointTGT> && !has_signal_v<PointSRC>>::run(
        tgt_pt, src_pt, [](auto& tgt_pt, const auto&) {
            tgt_pt.intensity = static_cast<decltype(tgt_pt.intensity)>(0);
        }
    );

    // reflectivity
    CondBinaryOp<has_reflectivity_v<PointTGT> && has_reflectivity_v<PointSRC>>::run(
        tgt_pt, src_pt, [](auto& tgt_pt, const auto& src_pt) {
            tgt_pt.reflectivity = src_pt.reflectivity;
        }
    );

    CondBinaryOp<has_reflectivity_v<PointTGT> && !has_reflectivity_v<PointSRC>>::run(
        tgt_pt, src_pt, [](auto& tgt_pt, const auto&) {
            tgt_pt.reflectivity = static_cast<decltype(tgt_pt.reflectivity)>(0);
        }
    );

    // near_ir
    CondBinaryOp<has_near_ir_v<PointTGT> && has_near_ir_v<PointSRC>>::run(
        tgt_pt, src_pt, [](auto& tgt_pt, const auto& src_pt) { tgt_pt.near_ir = src_pt.near_ir; }
    );

    CondBinaryOp<has_near_ir_v<PointTGT> && !has_near_ir_v<PointSRC>>::run(
        tgt_pt, src_pt, [](auto& tgt_pt, const auto&) {
            tgt_pt.near_ir = static_cast<decltype(tgt_pt.near_ir)>(0); }
    );

    // ambient <- near_ir
    CondBinaryOp<has_ambient_v<PointTGT> && has_near_ir_v<PointSRC>>::run(tgt_pt, src_pt,
        [](auto& tgt_pt, const auto& src_pt) {
            tgt_pt.ambient = static_cast<decltype(tgt_pt.ambient)>(src_pt.near_ir);
        }
    );

    CondBinaryOp<has_ambient_v<PointTGT> && !has_near_ir_v<PointSRC>>::run(tgt_pt, src_pt,
        [](auto& tgt_pt, const auto&) {
            tgt_pt.ambient = static_cast<decltype(tgt_pt.ambient)>(0);
        }
    );
}

/**
 * @brief options that influence how the sensor native fields are mapped onto a
 * target point type. Only consulted by point types that need a runtime choice,
 * at the moment that is PointXYZIRCAEDT alone.
 */
struct TransformOpts {
    enum class IntensitySource { REFLECTIVITY, SIGNAL, NEAR_IR };

    IntensitySource intensity_source = IntensitySource::REFLECTIVITY;
    float intensity_scale = 1.0f;
};

/**
 * @brief parses the string representation of an intensity source.
 * @throw std::invalid_argument if the value isn't recognized.
 */
inline TransformOpts::IntensitySource intensity_source_of(
    const std::string& value) {
    if (value == "reflectivity")
        return TransformOpts::IntensitySource::REFLECTIVITY;
    if (value == "signal") return TransformOpts::IntensitySource::SIGNAL;
    if (value == "near_ir") return TransformOpts::IntensitySource::NEAR_IR;
    throw std::invalid_argument("un-supported intensity_source used: " + value);
}

/**
 * @brief reads the channel selected by opts from a sensor native point,
 * yielding 0 when the active udp profile doesn't carry that channel.
 */
template <typename PointSRC>
inline float intensity_source_value(const PointSRC& src_pt,
                                    TransformOpts::IntensitySource source) {
    if (source == TransformOpts::IntensitySource::SIGNAL) {
        if constexpr (has_signal_v<PointSRC>)
            return static_cast<float>(src_pt.signal);
    } else if (source == TransformOpts::IntensitySource::NEAR_IR) {
        if constexpr (has_near_ir_v<PointSRC>)
            return static_cast<float>(src_pt.near_ir);
    } else {
        if constexpr (has_reflectivity_v<PointSRC>)
            return static_cast<float>(src_pt.reflectivity);
    }
    unused_variable(src_pt);
    return 0.0f;
}

/**
 * @brief saturating cast into the uint8 intensity that Autoware expects, NaN
 * and negative values map to 0.
 */
inline std::uint8_t clamp_to_uint8(float value) {
    if (!(value > 0.0f)) return 0;  // also catches NaN
    if (value >= 255.0f) return 255;
    return static_cast<std::uint8_t>(value + 0.5f);
}

/**
 * @brief assigns the return type when the target point has such a field, the
 * value can't be derived from the source point since the sensor native point
 * types have no notion of which return they belong to.
 */
template <typename PointT>
inline void set_return_type(PointT& pt, std::uint8_t return_type) {
    if constexpr (has_return_type_v<PointT>) {
        pt.return_type = return_type;
    } else {
        unused_variable(pt);
        unused_variable(return_type);
    }
}

/**
 * @brief the 3 argument form used by scan_to_cloud_f, forwards to the generic
 * transform for every point type that doesn't need the extra options.
 */
template <typename PointTGT, typename PointSRC>
void transform(PointTGT& tgt_pt, const PointSRC& src_pt, const TransformOpts&) {
    transform(tgt_pt, src_pt);
}

/**
 * @brief maps a sensor native point onto Autoware's PointXYZIRCAEDT.
 * @remark azimuth, elevation and distance are derived from the cartesian
 * coordinates rather than from the RANGE channel so that they remain
 * consistent with the frame the point cloud is published in (which may have
 * the lidar to sensor transform applied to it).
 * @remark azimuth is reported as atan2(y, x) wrapped to [0, 2pi) which is the
 * convention Autoware's distortion corrector auto-detects with a unit sign and
 * a zero offset.
 */
template <typename PointSRC>
void transform(PointXYZIRCAEDT& tgt_pt, const PointSRC& src_pt,
               const TransformOpts& opts) {
    tgt_pt.x = src_pt.x; tgt_pt.y = src_pt.y; tgt_pt.z = src_pt.z;

    tgt_pt.intensity = clamp_to_uint8(
        opts.intensity_scale *
        intensity_source_value(src_pt, opts.intensity_source));

    if constexpr (has_ring_v<PointSRC>) {
        tgt_pt.channel = static_cast<std::uint16_t>(src_pt.ring);
    } else {
        tgt_pt.channel = 0;
    }

    if constexpr (has_t_v<PointSRC>) {
        tgt_pt.time_stamp = static_cast<std::uint32_t>(src_pt.t);
    } else {
        tgt_pt.time_stamp = 0U;
    }

    const float azimuth = std::atan2(tgt_pt.y, tgt_pt.x);
    tgt_pt.azimuth =
        azimuth < 0.0f ? azimuth + 2.0f * static_cast<float>(M_PI) : azimuth;
    tgt_pt.elevation = std::atan2(tgt_pt.z, std::hypot(tgt_pt.x, tgt_pt.y));
    tgt_pt.distance = std::sqrt(tgt_pt.x * tgt_pt.x + tgt_pt.y * tgt_pt.y +
                                tgt_pt.z * tgt_pt.z);
}

}   // point
}   // ouster_ros