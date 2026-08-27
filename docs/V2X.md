# V2X objects in the perception pipeline

Autoware on this vehicle can accept vehicles reported over V2X — by another kart, or by a
roadside unit — and treat them as detected objects, so the planner reacts to something no
sensor on this vehicle ever saw.

The V2X stack itself is a **separate workspace**:
[`racing_kart_v2x`](https://github.com/ehsan-javanmardi/racing_kart_v2x), normally cloned
to `~/workspace/racing_kart_v2x` and built as an overlay on this one. Nothing in
`pix_autoware` depends on it; this page documents only the hook that lets it in.

## The hook: `use_v2x_objects`

```bash
./autoware_velodyne_kashiwa.sh use_v2x_objects:=true
```

**Off by default.** Nothing in a stock Autoware publishes the topic it subscribes to, so
leaving it off changes nothing, and turning it on with no V2X stack running just leaves an
idle subscription.

| Argument | Default | Meaning |
| --- | --- | --- |
| `use_v2x_objects` | `false` | Give the tracker an input channel for V2X reported objects |
| `v2x_objects_topic` | `/perception/object_recognition/detection/v2x/objects` | Where it listens |

It is a top-level argument of `autoware.launch.xml`, plumbed through
`tier4_perception_component.launch.xml` → `perception.launch.xml` →
`object_recognition/tracking/tracking.launch.xml`.

## Why it needs a dedicated topic

The obvious destination is the merged
`/perception/object_recognition/detection/objects`. On this vehicle that topic goes
nowhere.

`tracking.launch.xml` wires the tracker two ways. With
`use_multi_channel_tracker_merger:=false` the tracker reads the merged topic. With it
**true**, which is how this vehicle runs, the tracker subscribes to each detector's own
topic instead and the merged one has **no subscriber at all**:

```bash
ros2 topic info /perception/object_recognition/detection/objects
# Publisher count: 1     <- whatever you connected
# Subscription count: 0  <- nobody is listening
```

Anything published there is dropped silently, with no error to explain why. So the V2X
objects go to their own topic, and `use_v2x_objects:=true` binds that topic to the
tracker's first free input slot with the `detected_objects` channel.

**Slot 10, not 9.** In the multi-channel branch slots 01–09 are assigned, but only 01–08
are forwarded to the node — slot 09 is set to `camera_only` and then never passed on,
which looks like an upstream oversight. Slot 10 is the first genuinely free one.

## Checking it took effect

```bash
ros2 param get /perception/object_recognition/tracking/multi_object_tracker \
  input/detection10/channel
# String value is: detected_objects

ros2 topic info /perception/object_recognition/detection/v2x/objects
# Subscription count: 1
```

If the channel reads `none`, Autoware was started without the flag.

## Seeing the objects

Autoware's RViz config has **no display for the V2X topic** — it has one per individual
detector, plus the tracked and predicted outputs. So a V2X object appears only after the
tracker has taken it:

| RViz display | Topic |
| --- | --- |
| `TrackedObjects` | `/perception/object_recognition/tracking/objects` |
| `PredictedObjects` | `/perception/object_recognition/objects` |

To watch the raw input instead — which also works with the flag off — add a display by
hand: **Add → By topic → `/perception/object_recognition/detection/v2x/objects` →
`DetectedObjects`**.

## Verified end to end

With the `racing_kart_v2x` stack running against the live challenge broker, a kart
transmitting as `d8` arrived as a `CAR`-classified object at `(3864.6, 73774.1)` in the
`map` frame, through the tracker and into `/perception/object_recognition/objects`.

Positions on the wire are **absolute MGRS coordinates**, not bearings relative to us, so
Autoware has to be localized in the same map or the object lands far away rather than
slightly off.

## Two publishers on one topic

`racing_kart_v2x` has two producers that both default to this topic:
`v2x_autoware_bridge` (other karts' positions) and `v2x_perception_sharing` (a roadside
unit's whole perception result). Running both puts two publishers on one topic, and the
tracker then sees alternating frames. Tracks survive that — a tracker is built to tolerate
missed detections — but the two sources are not distinguishable downstream. Give one of
them its own `output_objects_topic` if you need them apart, and wire a second tracker slot
the same way slot 10 is wired here.

## See also

- [`racing_kart_v2x`](https://github.com/ehsan-javanmardi/racing_kart_v2x) — the V2X
  workspace: install, certificates, running, and the payload formats. **Private
  repository; it contains live TLS keys.**
- [`docs/components/PERCEPTION.md`](components/PERCEPTION.md) — the rest of the detection
  stack this feeds into.
