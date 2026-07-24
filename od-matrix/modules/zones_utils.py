import geopandas as gpd
import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.io import MemoryFile
from rasterstats import zonal_stats
from shapely.geometry import box
from scipy.spatial import cKDTree


def create_zones(city_gdf, cell_size, pop_raster_path):
    """
    Creates zones over a city polygon, computes population per zone,
    and returns zones and their population array.
    Handles raster reprojection, masking, and missing data safely.
    """
    city_gdf = city_gdf.copy()
    city_gdf["geometry"] = city_gdf.geometry.buffer(0)  # fix invalid geometries
    city_gdf = city_gdf.to_crs(epsg=3857)

    xmin, ymin, xmax, ymax = city_gdf.total_bounds
    nx_cells = max(int((xmax - xmin) / cell_size), 1)
    ny_cells = max(int((ymax - ymin) / cell_size), 1)

    grid = [box(xmin + i*cell_size, ymin + j*cell_size,
                xmin + (i+1)*cell_size, ymin + (j+1)*cell_size)
            for i in range(nx_cells) for j in range(ny_cells)]
    zones = gpd.GeoDataFrame({"geometry": grid}, crs=city_gdf.crs)

    zones = gpd.overlay(zones, city_gdf, how="intersection")
    if len(zones) == 0:
        raise ValueError("No zones intersect city polygon! Check cell_size or city geometry.")

    with rasterio.open(pop_raster_path) as src:

        if src.crs.to_string() != "EPSG:3857":
            print(f"Reprojecting raster: {src.crs} → EPSG:3857")
            transform, width, height = calculate_default_transform(
                src.crs, "EPSG:3857", src.width, src.height, *src.bounds
            )
            kwargs = src.meta.copy()
            kwargs.update({
                "crs": "EPSG:3857",
                "transform": transform,
                "width": width,
                "height": height
            })

            dst_array = np.zeros((src.count, height, width), dtype=src.meta['dtype'])
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=dst_array[i-1],
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs="EPSG:3857",
                    resampling=Resampling.nearest
                )

            memfile = MemoryFile()
            with memfile.open(**kwargs) as dst:
                dst.write(dst_array)
                try:
                    clipped, clipped_transform = mask(dst, city_gdf.geometry, crop=True)
                except ValueError:
                    raise ValueError("City polygon does not overlap reprojected raster!")

        else:
            try:
                clipped, clipped_transform = mask(src, city_gdf.geometry, crop=True)
            except ValueError:
                raise ValueError("City polygon does not overlap raster!")

        # Use first band; robustly clean nodata / sentinels / impossible values.
        # Population rasters carry NoData over sea/rivers/forest; if it leaks in
        # it inflates a zone's pop and (via pop[i]*pop[j]) dominates the OD matrix.
        clipped = clipped[0].astype("float64")
        if src.nodata is not None:
            clipped[clipped == src.nodata] = 0.0
        clipped[~np.isfinite(clipped)] = 0.0   # NaN / +-inf (reprojection, float fill)
        clipped[clipped < 0] = 0.0             # -9999 / -200 / -3.4e38 sentinels
        clipped[clipped > 1e6] = 0.0           # no single pixel holds >1e6 people

    stats = zonal_stats(
        zones,
        clipped,
        affine=clipped_transform,
        stats=["sum"],
        nodata=0
    )

    zones["pop"] = np.array([
        max(int(s["sum"]) if s is not None and s["sum"] is not None else 0, 1)
        for s in stats
    ])
    pop = zones["pop"].values

    print(f"Zones created: {len(zones)} | Total population: {pop.sum():,.0f}")

    return zones, pop


def snap_zones_to_nodes(zones_gdf, nodes_gdf, max_snap_dist=None):
    """
    Robust snapping of zones to nearest graph nodes.

    - ALWAYS returns all zones (no loss)
    - Uses KDTree for fast nearest search
    - Optional max_snap_dist only triggers warning (not filtering)

    Returns:
        zones_gdf (unchanged, reindexed)
        nodes_sel (list of node IDs aligned with zones)
    """
    print("Snapping zones to nodes (robust)...")

    if not zones_gdf.geometry.iloc[0].geom_type == "Point":
        centroids = zones_gdf.geometry.centroid
    else:
        centroids = zones_gdf.geometry

    node_coords = np.array([(geom.x, geom.y) for geom in nodes_gdf.geometry])
    tree = cKDTree(node_coords)

    zone_coords = np.array([(geom.x, geom.y) for geom in centroids])
    distances, indices = tree.query(zone_coords, k=1)

    node_ids = nodes_gdf.index.astype(str).tolist()
    nodes_sel = [node_ids[i] for i in indices]

    if max_snap_dist is not None:
        too_far = distances > max_snap_dist
        n_far = np.sum(too_far)
        if n_far > 0:
            print(f"{n_far} zones farther than max_snap_dist ({max_snap_dist})")

    zones_gdf = zones_gdf.copy().reset_index(drop=True)

    print(f"Snapped ALL zones: {len(zones_gdf)}")
    print(f"   Avg distance: {distances.mean():.2f}")
    print(f"   Max distance: {distances.max():.2f}")

    return zones_gdf, nodes_sel
