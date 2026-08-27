# Maps

Autoware needs two maps to localize and plan: a point cloud map it matches lidar
scans against, and a lanelet2 map describing the road network. Both live in
[`autoware_map/`](../autoware_map) and are committed to this repository.

## Available maps

| Map | Location | Projection | Size |
| --- | -------- | ---------- | ---- |
| Kashiwanoha | [`autoware_map/`](../autoware_map) | MGRS `54SVE`, WGS84 | 22 MB |

### Kashiwanoha

Kashiwanoha Campus, Kashiwa, Chiba. This is the map the
[`autoware_velodyne_kashiwa.sh`](../autoware_velodyne_kashiwa.sh) script loads by default.

| File | What it is |
| ---- | ---------- |
| `pointcloud_map.pcd` | 1,757,841 points, `binary_compressed`, fields `rgb x y z`. Used by the NDT scan matcher. |
| `lanelet2_map.osm` | The map Autoware is meant to load. 4,530 nodes, 639 ways, 197 lanelets, VMB `map_version` 30. Same road network as the original plus the garage area. |
| `map_projector_info.yaml` | `projector_type: MGRS`, `mgrs_grid: 54SVE`, `vertical_datum: EGM2008`. |

The projector file matters more than its size suggests. Without it Autoware derives the
projection from the lanelet2 map instead and logs a `DEPRECATED` warning; the grid designator is
the 100 km square taken from the map's `mgrs_code` tags, so `54SVE036734` gives `54SVE`.

#### The lanelet2 variants

Four `.osm` files sit in the directory. They are the same road network at different stages of
editing, kept side by side so an edit can be undone by picking a different file rather than by
reverting a 1 MB diff.

| File | Version | Lanelets | Traffic lights bound to a lane | Notes |
| ---- | ------- | -------- | ------------------------------ | ----- |
| `lanelet2_map_original.osm` | v29 | 195 | 33 | The map as delivered in 2022. Untouched reference copy. |
| `lanelet2_map_garage added.osm` | v30 | 197 | 33 | v29 with the garage area added (2 lanelets, 3 linestrings), edited in Vector Map Builder. |
| `lanelet2_map.osm` | v30 | 197 | 33 | Byte-identical to `lanelet2_map_garage added.osm`. Carries the filename Autoware defaults to. |
| `lanelet2_map_no_traffic_light.osm` | v29 | 195 | **0** | v29 with every traffic light unbound from the lanes. See below. |

"Traffic lights bound to a lane" is the number that decides whether the vehicle stops: the
`traffic_light` behavior velocity module only looks at traffic lights reachable through a lane's
regulatory elements, so a map where that count is 0 never plans a traffic light stop.

### Driving without traffic light recognition

The Pixkit has no camera, so nothing ever publishes a traffic signal state. Autoware treats an
unknown signal as red and holds the vehicle at the stop line indefinitely, which makes every
signalised intersection on the Kashiwanoha map a dead end.
`lanelet2_map_no_traffic_light.osm` is the map to use until a camera is fitted:

```bash
./autoware_velodyne_kashiwa.sh lanelet2_map_file:=lanelet2_map_no_traffic_light.osm
```

The argument is required. The launch scripts pick a map with `ls -1 *.osm | head -n1`, which
returns whatever sorts first in the current locale - today `lanelet2_map_garage added.osm` - not
the file named `lanelet2_map.osm`. Passing `lanelet2_map_file:=` explicitly is the only way to be
sure which map is loaded. `echo "lanelet2  : $LANELET_FILE"` in the script output reports what it
settled on; read it before driving.

**What was removed.** All 18 `regulatory_element` relations of subtype `traffic_light`, and the 33
references to them from lanelets (29 road lanelets, 4 crosswalk lanelets). Nothing else changed -
the diff against `lanelet2_map_original.osm` is 193 deleted lines and zero added ones, and node,
way and linestring counts are unchanged at 4,484 / 636 / 635.

**What was deliberately kept.** The `traffic_light`, `light_bulbs` and `stop_line` ways are still
in the file, now referenced by nothing. Autoware ignores an unreferenced linestring, so they cost
nothing at runtime, and keeping them means the traffic lights can be switched back on by restoring
the 18 relations instead of redrawing the geometry. Regenerate the file from the original with:

```bash
python3 - <<'EOF'
import re
s = open('autoware_map/lanelet2_map_original.osm').read()
tl = {m.group(1) for m in re.finditer(
    r'<relation id="(\d+)">(?:(?!</relation>)[\s\S])*?'
    r'k="subtype" v="traffic_light"[\s\S]*?</relation>', s)}
s = re.sub(r' *<member type="relation" role="regulatory_element" ref="(?:%s)"/>\n'
           % '|'.join(tl), '', s)
s = re.sub(r' *<relation id="(?:%s)">[\s\S]*?</relation>\n' % '|'.join(tl), '', s)
open('autoware_map/lanelet2_map_no_traffic_light.osm', 'w').write(s)
EOF
```

**The vehicle still stops for stop signs.** Five `traffic_sign` regulatory elements of type
`stop_sign` keep a `ref_line`, so the stop line module still holds at those five stop lines. That
is correct - a painted stop line needs no camera - and it is a useful sign that stop line handling
is alive at all. The other 9 `traffic_sign` elements and all 3 `road_marking` elements have no
`ref_line` and stop nothing.

**Crosswalks change behaviour rather than losing it.** Four crosswalk lanelets referenced a
pedestrian signal. Without it the crosswalk module falls back to its unsignalised path: yield to
detected pedestrians instead of obeying a light. That is the intended behaviour here, but it means
crosswalk safety now rests entirely on lidar perception.

**Verifying a map after editing it.** Load it through the same library Autoware uses rather than
trusting the XML:

```bash
source install/setup.bash
python3 -c "
from autoware_lanelet2_extension_python.projection import MGRSProjector
import lanelet2
m = lanelet2.io.load('autoware_map/lanelet2_map_no_traffic_light.osm',
                     MGRSProjector(lanelet2.io.Origin(0, 0)))
sub = lambda r: r.attributes['subtype'] if 'subtype' in r.attributes else '?'
print('lanelets:', len(list(m.laneletLayer)))
print('bound to a traffic light:', sum(1 for l in m.laneletLayer
      if any(sub(r) == 'traffic_light' for r in l.regulatoryElements)))
"
```

A map that loads without throwing and reports 0 lanelets bound to a traffic light is good. Vector
Map Builder will also re-export a map silently dropping relations it does not understand, so run
this after every round trip through it.

## Using a map

The launch script defaults to `autoware_map/` and picks up whatever `.pcd` and `.osm` it finds
there:

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
`lanelet2_map.osm`, which is why the files here carry those names. The script passes them
explicitly after detecting whatever is present, so a map that uses different filenames still
works through the script.

## Adding another map

Give each map its own directory containing the three files above, then pass that directory to the
launch script. Once a second map exists, move Kashiwanoha into `autoware_map/kashiwanoha/`
alongside it and update the default in the script rather than leaving one map at the top level and
the rest nested.

Things to check before committing a new map:

- **Size.** GitHub rejects any file over 100 MB and starts warning at 50 MB. A city scale point
  cloud map will exceed that; keep those out of the repository and distribute them separately,
  with a note in the table above saying where they live.
- **`map_projector_info.yaml` is present.** It is three lines and it removes a deprecation path.
- **The projection matches the lanelet2 map.** A mismatch between the MGRS grid here and the
  `mgrs_code` tags in the `.osm` puts the vehicle in the wrong 100 km square, which shows up as
  localization that never converges rather than as an error message.
- **The point cloud and the lanelet2 map are in the same frame.** They are authored separately and
  nothing at runtime verifies that they agree.
