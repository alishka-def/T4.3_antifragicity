"""
Usage
-----
    python data/scripts/build_grid_taz_zones.py \
        --city-shp OD-matrix-main/data/city_boundaries/Larissa/Larissa-v1.geojson \
        --cell-size 3000 \
        --output data/zones/larissa_grid_zones.geojson
"""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box


def build_zones(city_gdf: gpd.GeoDataFrame, cell_size: float) -> gpd.GeoDataFrame:
    """Replicate create_zones() grid + clip, preserving row order exactly."""

    # --- prepare boundary (same as create_zones) ---
    city_gdf = city_gdf.copy()
    city_gdf["geometry"] = city_gdf.geometry.buffer(0)  # fix invalid geometries
    city_gdf = city_gdf.to_crs(epsg=3857)

    # --- regular square grid over the bounding box ---
    xmin, ymin, xmax, ymax = city_gdf.total_bounds
    nx_cells = max(int((xmax - xmin) / cell_size), 1)
    ny_cells = max(int((ymax - ymin) / cell_size), 1)

    # NOTE: i (x) outer, j (y) inner -- this order defines the Z-numbering.
    grid = [
        box(
            xmin + i * cell_size,
            ymin + j * cell_size,
            xmin + (i + 1) * cell_size,
            ymin + (j + 1) * cell_size,
        )
        for i in range(nx_cells)
        for j in range(ny_cells)
    ]
    zones = gpd.GeoDataFrame({"geometry": grid}, crs=city_gdf.crs)

    # --- clip grid to the administrative boundary ---
    zones = gpd.overlay(zones, city_gdf, how="intersection")
    if len(zones) == 0:
        raise ValueError(
            "No zones intersect the city polygon! Check --cell-size or geometry."
        )

    # Ids assigned by row order, exactly like od_utils.save_hourly_od_xlsx_matrix
    # (zone_ids = [f"Z{i}" for i in range(n)]).
    zones = zones.reset_index(drop=True)
    zones = zones[["geometry"]].copy()
    zones["zone_id"] = [f"Z{i}" for i in range(len(zones))]

    return zones


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--city-shp",
        required=True,
        help="City boundary file (the same one used in multi-config.json).",
    )
    parser.add_argument(
        "--cell-size",
        type=float,
        default=3000.0,
        help="Grid cell size in meters (must match cell_size in multi-config.json).",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output GeoJSON path (multi-zone, one feature per grid cell).",
    )
    args = parser.parse_args()

    city_path = Path(args.city_shp)
    if not city_path.exists():
        raise FileNotFoundError(f"City boundary file not found: {city_path}")

    city_gdf = gpd.read_file(city_path)
    zones = build_zones(city_gdf, args.cell_size)

    # Write a standard lon/lat GeoJSON (RFC 7946) so geojson_to_sumo_poly.py
    # reprojects it correctly.
    zones_4326 = zones.to_crs(epsg=4326)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()  # GeoJSON driver appends otherwise
    zones_4326.to_file(out, driver="GeoJSON")

    ids = zones_4326["zone_id"].tolist()
    print(f"Wrote {len(ids)} TAZ grid zones -> {out}")
    print(f"Zone IDs: {', '.join(ids[:5])} ... {ids[-1]}")
    print(
        "Check this count matches the number of zones (Z0..Zn-1) in "
        "hourly_od_<City>.xlsx -> sheet 'zones_coords'."
    )


if __name__ == "__main__":
    main()