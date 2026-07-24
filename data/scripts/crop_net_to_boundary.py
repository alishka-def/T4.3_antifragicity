"""
Usage
-----
    python data/scripts/crop_net_to_boundary.py \
        --net-file data/larissa/net/larissa_full.net.xml \
        --geojson-file od-matrix/data/city_boundaries/Larissa/Larissa-v1.geojson \
        --output data/larissa/net/keep_edges.txt

Then crop with netconvert (see the printed command at the end).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import sumolib
from shapely.geometry import shape, Point, LineString
from shapely.ops import unary_union
from shapely.prepared import prep


def load_boundary(geojson_path: Path):
    """Union all features of a GeoJSON into one (multi)polygon in lon/lat."""
    with open(geojson_path, encoding="utf-8") as f:
        gj = json.load(f)

    if gj.get("type") == "FeatureCollection":
        geoms = [shape(ft["geometry"]) for ft in gj["features"]]
    elif gj.get("type") == "Feature":
        geoms = [shape(gj["geometry"])]
    else:  # bare geometry
        geoms = [shape(gj)]

    # buffer(0) repairs self-intersections / invalid rings
    return unary_union([g.buffer(0) for g in geoms])


def edge_centre_lonlat(edge, net):
    """Centroid of an edge's shape, converted from network XY to lon/lat."""
    shape_xy = edge.getShape()
    if len(shape_xy) == 1:
        cx, cy = shape_xy[0]
    else:
        c = LineString(shape_xy).centroid
        cx, cy = c.x, c.y
    lon, lat = net.convertXY2LonLat(cx, cy)
    return lon, lat


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--net-file", required=True, help="Input (large) SUMO net.")
    parser.add_argument("--geojson-file", required=True, help="Boundary GeoJSON (lon/lat).")
    parser.add_argument("--output", required=True, help="Edge keep-list (txt).")
    parser.add_argument("--buffer-m", type=float, default=0.0,
                        help="Buffer the boundary by this many metres before testing "
                             "edge centres. Use a positive value (e.g. 1500) for cities "
                             "split by a river, so the bridges (whose centres lie over "
                             "the water, outside the boundary) are kept and both banks "
                             "stay in one connected component.")
    args = parser.parse_args()

    net_file = Path(args.net_file)
    geojson_file = Path(args.geojson_file)
    output_file = Path(args.output)

    if not net_file.exists():
        raise FileNotFoundError(f"Network file not found: {net_file}")
    if not geojson_file.exists():
        raise FileNotFoundError(f"GeoJSON file not found: {geojson_file}")

    print("Loading network...")
    net = sumolib.net.readNet(str(net_file), withInternal=False)

    print("Loading boundary...")
    boundary = load_boundary(geojson_file)
    if args.buffer_m > 0:
        import geopandas as gpd
        boundary = (gpd.GeoSeries([boundary], crs=4326)
                    .to_crs(3857).buffer(args.buffer_m).to_crs(4326).iloc[0])
        print(f"  buffered boundary by {args.buffer_m:.0f} m (to keep river bridges)")
    boundary_prep = prep(boundary)  # fast repeated contains() tests

    edges = net.getEdges()
    keep = []
    for edge in edges:
        if edge.getID().startswith(":"):  # internal edge, skip
            continue
        lon, lat = edge_centre_lonlat(edge, net)
        if boundary_prep.contains(Point(lon, lat)):
            keep.append(edge.getID())

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("\n".join(keep) + "\n", encoding="utf-8")

    total = sum(1 for e in edges if not e.getID().startswith(":"))
    print(f"Edges inside boundary: {len(keep)} / {total} kept "
          f"({100.0 * len(keep) / max(total, 1):.1f}%)")
    print(f"Wrote keep-list -> {output_file}")
    print()
    print("Now crop the network with netconvert:")
    out_net = net_file.name.replace("_full", "")  # <city>_full.net.xml -> <city>.net.xml
    print(
        f"  netconvert -s {net_file} \\\n"
        f"      --keep-edges.input-file {output_file} \\\n"
        f"      --keep-edges.components 1 \\\n"
        f"      -o {net_file.with_name(out_net)}"
    )


if __name__ == "__main__":
    main()