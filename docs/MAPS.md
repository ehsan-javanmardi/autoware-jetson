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
| `lanelet2_map.osm` | 4,484 nodes, 636 ways, VMB `map_version` 29. The road network: lanes, stop lines, crosswalks, traffic light references. |
| `map_projector_info.yaml` | `projector_type: MGRS`, `mgrs_grid: 54SVE`, `vertical_datum: WGS84`. |

The projector file matters more than its size suggests. Without it Autoware derives the
projection from the lanelet2 map instead and logs a `DEPRECATED` warning; the grid designator is
the 100 km square taken from the map's `mgrs_code` tags, so `54SVE036734` gives `54SVE`.

## Using a map

The launch script defaults to `autoware_map/` and picks up whatever `.pcd` and `.osm` it finds
there:

```bash
./autoware_kashiwa_os1_128.sh                   # autoware_map/, next to the script
./autoware_kashiwa_os1_128.sh /path/to/map      # somewhere else
AUTOWARE_MAP_PATH=/path/to/map ./autoware_velodyne_kashiwa.sh
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
