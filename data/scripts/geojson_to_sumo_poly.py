from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

import geopandas as gpd
import sumolib


def polygon_coords_to_shape(coords, net):
    points = []
    for lon, lat in coords:
        x, y = net.convertLonLat2XY(lon, lat)
        points.append(f"{x:.2f},{y:.2f}")
    return " ".join(points)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--net-file", required=True)
    parser.add_argument("--geojson-file", required=True)
    parser.add_argument("--id-column", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    net_file = Path(args.net_file)
    geojson_file = Path(args.geojson_file)
    output_file = Path(args.output)

    if not net_file.exists():
        raise FileNotFoundError(f"Network file not found: {net_file}")

    if not geojson_file.exists():
        raise FileNotFoundError(f"GeoJSON file not found: {geojson_file}")

    output_file.parent.mkdir(parents=True, exist_ok=True)

    net = sumolib.net.readNet(str(net_file), withInternal=False)
    zones = gpd.read_file(geojson_file)

    if args.id_column not in zones.columns:
        raise ValueError(
            f"Column '{args.id_column}' not found in GeoJSON. "
            f"Available columns: {list(zones.columns)}"
        )

    if zones.crs is None:
        zones = zones.set_crs("EPSG:4326")

    zones = zones.to_crs("EPSG:4326")

    root = ET.Element("additional")

    for _, row in zones.iterrows():
        zone_id = str(row[args.id_column])
        geom = row.geometry

        if geom is None or geom.is_empty:
            continue

        if geom.geom_type == "Polygon":
            polygons = [geom]
        elif geom.geom_type == "MultiPolygon":
            polygons = list(geom.geoms)
        else:
            continue

        for i, poly in enumerate(polygons):
            polygon_id = zone_id if len(polygons) == 1 else f"{zone_id}_{i}"
            exterior = list(poly.exterior.coords)

            shape = polygon_coords_to_shape(exterior, net)

            ET.SubElement(
                root,
                "poly",
                {
                    "id": polygon_id,
                    "type": "taz",
                    "color": "1,0,0,0.25",
                    "fill": "true",
                    "shape": shape,
                },
            )

    tree = ET.ElementTree(root)
    if hasattr(ET, "indent"):  # ET.indent was added in Python 3.9; skip on 3.8
        ET.indent(tree, space="  ")
    tree.write(output_file, encoding="utf-8", xml_declaration=True)

    print(f"Wrote SUMO polygon file: {output_file}")


if __name__ == "__main__":
    main()