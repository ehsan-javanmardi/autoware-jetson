# Maps

Autoware needs two maps to localize and plan: a point cloud map it matches lidar scans
against, and a lanelet2 map describing the road network. Both live in
[`autoware_map/`](../autoware_map) and are committed to this repository.

## Layout

```text
autoware_map/
├── pointcloud_map.pcd          the point cloud, shared by every variant
├── lanelet2_map.osm            the road network Autoware loads
├── map_projector_info.yaml     projection, shared by every variant
└── other_maps/                 the lanelet2 variants, none of them loaded directly
    ├── Kashiwa_campus.osm
    ├── Kashiwa_campus_no-traffic-light.osm
    └── Kashiwa_campus_garage-front-added.osm
```

Only the three files at the top level are ever loaded. `other_maps/` is a shelf: to switch
road networks, copy one over `lanelet2_map.osm`, or pass it explicitly with
`lanelet2_map_file:=`.

Everything here is Kashiwanoha Campus, Kashiwa, Chiba, in MGRS grid `54SVE`. There is one
point cloud and one projection; the variants differ only in the lanelet2 layer.

| File | What it is |
| ---- | ---------- |
| `pointcloud_map.pcd` | 20 MB, `binary_compressed`, fields `rgb x y z`. Used by the NDT scan matcher. Not used at all with `pose_source:=gnss`. |
| `lanelet2_map.osm` | The road network Autoware loads. Currently a copy of `Kashiwa_campus_no-traffic-light.osm`. |
| `map_projector_info.yaml` | `projector_type: MGRS`, `mgrs_grid: 54SVE`, `vertical_datum: EGM2008`. |

The projector file matters more than its size suggests. Without it Autoware derives the
projection from the lanelet2 map and logs a `DEPRECATED` warning. The grid designator is the
100 km square from the map's `mgrs_code` tags, so `54SVE036734` gives `54SVE`.

## The lanelet2 variants

Same campus, three different road networks. Measured, not assumed — the counts below come
from parsing each file and loading it through lanelet2.

| File | Lanelets | Traffic light regulatory elements | Lanelets bound to one | Stop lines | Stop signs | Loads with |
| ---- | -------- | --------------------------------- | --------------------- | ---------- | ---------- | ---------- |
| `Kashiwa_campus.osm` | 195 | 18 | 33 | 89 | 8 | 7 errors |
| `Kashiwa_campus_garage-front-added.osm` | 197 | 18 | 33 | 89 | 8 | 7 errors |
| `Kashiwa_campus_no-traffic-light.osm` | 195 | **0** | **0** | **0** | **0** | **0 errors** |

### `Kashiwa_campus.osm` — the original

The map as delivered. Untouched reference copy; keep it that way, and branch from it rather
than editing it.

The 7 load errors are in the delivered file, not something we introduced. Three are
`No regulatory element found that implements rule road_marking` — lanelet2 has no handler
for that subtype, so those three elements are dropped at load time whichever map you use.

### `Kashiwa_campus_garage-front-added.osm` — original plus the garage approach

The original with the area in front of the garage added: **2 extra lanelets** (197 vs 195),
drawn in Vector Map Builder.

> [!WARNING]
> The added path is rough and **needs revision before it is driven**. It was drawn to make
> the garage reachable at all, not to a standard you would plan against. Treat it as a
> sketch.

It still carries all 18 traffic light regulatory elements, so it has the same problem
described below as the original.

### `Kashiwa_campus_no-traffic-light.osm` — what is loaded today

The original with everything that makes the vehicle stop for a signal or a painted line
removed. This is the only variant that loads with **zero** errors.

**Why this variant exists.** The Pixkit has no camera, so nothing ever publishes a traffic
signal state. Autoware treats an unknown signal as red and holds at the stop line
indefinitely, which makes every signalised intersection a dead end. With no traffic light
bound to any lane, that stop is never planned.

**What was removed**, relative to the original:

| | count |
| --- | --- |
| `traffic_light` regulatory elements, and the 33 lanelet references to them | 18 |
| `traffic_light` ways (the light geometry) | 50 |
| `light_bulbs` ways | 42 |
| `stop_line` ways | 89 |
| `traffic_sign` ways of subtype `stop_sign` | 8 |
| regulatory elements referring to any of the above (6 stop sign, 3 road marking) | 9 |
| nodes left referenced by nothing | 231 |

All 195 lanelets survive, and there are zero dangling references.

**What was kept.** The 9 `traffic_sign` ways of subtype `unknown` and their 8 regulatory
elements. They are physical signposts with a height and no `ref_line`; they stop nothing.

**The vehicle no longer stops at stop lines either.** The earlier version of this map
unbound the traffic lights but left the stop line geometry and the stop signs, so the stop
line module still held at painted stop lines. That is gone now. If you want stop signs back
without traffic lights, that is a different edit from the original — not this file.

**Crosswalks changed behaviour rather than losing it.** Four crosswalk lanelets referenced a
pedestrian signal. Without it the crosswalk module falls back to its unsignalised path:
yield to detected pedestrians rather than obey a light. Crosswalk safety now rests entirely
on lidar perception.

## Choosing a map

> [!IMPORTANT]
> The launch scripts pick a map with `ls -1 *.osm | head -n1`, which returns whatever sorts
> first in the current locale. With one `.osm` at the top level that is `lanelet2_map.osm`,
> which is what you want — but add a second file there and the choice silently changes.
> Passing `lanelet2_map_file:=` is the only way to be certain.

```bash
./autoware_kashiwa_os1_128.sh                                          # lanelet2_map.osm
./autoware_kashiwa_os1_128.sh lanelet2_map_file:=lanelet2_map.osm      # the same, explicitly
```

The script echoes `lanelet2  : <file>` in its first four lines. Read it before driving.

To drive a different variant, copy it into place:

```bash
cd autoware_map
cp other_maps/Kashiwa_campus_garage-front-added.osm lanelet2_map.osm
```

`other_maps/` is not on the search path, so a file left there can never be picked up by
accident.

## Using a map directory

```bash
./autoware_kashiwa_os1_128.sh                   # autoware_map/, next to the script
./autoware_kashiwa_os1_128.sh /path/to/map      # somewhere else
AUTOWARE_MAP_PATH=/path/to/map ./autoware_kashiwa.sh
```

Launching Autoware directly takes the same directory as `map_path`:

```bash
ros2 launch autoware_launch autoware.launch.xml \
    vehicle_model:=pixkit \
    sensor_model:=pixkit_sensor_kit \
    map_path:=$PWD/autoware_map \
    pointcloud_map_file:=pointcloud_map.pcd \
    lanelet2_map_file:=lanelet2_map.osm
```

`pointcloud_map_file` and `lanelet2_map_file` default to `pointcloud_map.pcd` and
`lanelet2_map.osm`, which is why the top level files carry those names.

## Verifying a map after editing it

Load it through the same library Autoware uses rather than trusting the XML. Vector Map
Builder will re-export a map silently dropping relations it does not understand, so run this
after every round trip through it.

```bash
source install/setup.bash
python3 - <<'EOF'
import lanelet2
from lanelet2.projection import UtmProjector
# the projector only affects coordinates, not topology, so any origin works for a load test
proj = UtmProjector(lanelet2.io.Origin(35.9035, 139.9345))
m, errs = lanelet2.io.loadRobust('autoware_map/lanelet2_map.osm', proj)
print('lanelets:', len(m.laneletLayer), ' load errors:', len(errs))
for ll in m.laneletLayer:
    for r in ll.regulatoryElements:
        if 'TrafficLight' in type(r).__name__:
            print('still bound to a traffic light:', ll.id)
EOF
```

`loadRobust` reports what was dropped instead of throwing, which is what you want here —
plain `load()` hides the `road_marking` failures.

A separate check worth running after any edit is that nothing references a deleted element:

```bash
python3 - <<'EOF'
import xml.etree.ElementTree as ET
root = ET.parse('autoware_map/lanelet2_map.osm').getroot()
pool = {k: {e.get('id') for e in root.findall(k)} for k in ('node', 'way', 'relation')}
bad = [(p.tag, p.get('id'), m.get('type'), m.get('ref'))
       for p in root.findall('relation') for m in p.findall('member')
       if m.get('ref') not in pool[m.get('type')]]
bad += [('way', w.get('id'), 'node', nd.get('ref'))
        for w in root.findall('way') for nd in w.findall('nd')
        if nd.get('ref') not in pool['node']]
print('dangling references:', len(bad), bad[:5])
EOF
```

## Adding another map

Give each map its own directory containing the three top level files, then pass that
directory to the launch script. Once a second location exists, move Kashiwanoha into
`autoware_map/kashiwanoha/` alongside it and update the default in the scripts, rather than
leaving one map at the top level and the rest nested.

Things to check before committing a new map:

- **Size.** GitHub rejects any file over 100 MB and warns at 50 MB. A city scale point cloud
  will exceed that; keep those out of the repository and note where they live instead.
- **`map_projector_info.yaml` is present.** Three lines, and it removes a deprecation path.
- **The projection matches the lanelet2 map.** A mismatch between the MGRS grid here and the
  `mgrs_code` tags in the `.osm` puts the vehicle in the wrong 100 km square, which shows up
  as localization that never converges rather than as an error.
- **The point cloud and the lanelet2 map are in the same frame.** They are authored
  separately and nothing at runtime checks that they agree.
