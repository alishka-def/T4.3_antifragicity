import geopandas as gpd
import numpy as np
import rasterio
from rasterio.mask import mask
from shapely.geometry import box
from scipy.spatial import cKDTree
import networkx as nx
import osmnx as ox

def compute_distance_matrix(node_ids, G):

    node_ids = [str(n) for n in node_ids]

    n = len(node_ids)
    D = np.zeros((n, n))

    for i, s in enumerate(node_ids):

        if s not in G:
            continue

        lengths = nx.single_source_dijkstra_path_length(G, s, weight="length")

        for j, t in enumerate(node_ids):
            D[i, j] = lengths.get(t, np.inf)

    return D

def create_zones(city_gdf, cell_size, pop_raster_path):
    """
    Creates zones over a city polygon, computes population per zone,
    and returns zones and their population array.
    Handles raster reprojection, masking, and missing data safely.
    """

    import geopandas as gpd
    import numpy as np
    from shapely.geometry import box
    import rasterio
    from rasterio.mask import mask
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    from rasterstats import zonal_stats
    from rasterio.io import MemoryFile

    # -----------------------------
    # Prepare city polygon
    # -----------------------------
    city_gdf = city_gdf.copy()
    city_gdf["geometry"] = city_gdf.geometry.buffer(0)  # fix invalid geometries
    city_gdf = city_gdf.to_crs(epsg=3857)

    # -----------------------------
    # Generate grid zones
    # -----------------------------
    xmin, ymin, xmax, ymax = city_gdf.total_bounds
    nx_cells = max(int((xmax - xmin) / cell_size), 1)
    ny_cells = max(int((ymax - ymin) / cell_size), 1)

    grid = [box(xmin + i*cell_size, ymin + j*cell_size,
                xmin + (i+1)*cell_size, ymin + (j+1)*cell_size)
            for i in range(nx_cells) for j in range(ny_cells)]
    zones = gpd.GeoDataFrame({"geometry": grid}, crs=city_gdf.crs)

    # Clip zones to city polygon
    zones = gpd.overlay(zones, city_gdf, how="intersection")
    if len(zones) == 0:
        raise ValueError("No zones intersect city polygon! Check cell_size or city geometry.")

    # -----------------------------
    # Open population raster
    # -----------------------------
    with rasterio.open(pop_raster_path) as src:

        # Reproject raster to EPSG:3857 if needed
        if src.crs.to_string() != "EPSG:3857":
            print(f"⚠️ Reprojecting raster: {src.crs} → EPSG:3857")
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

            # Reproject raster into memory
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

            # Write to in-memory raster
            memfile = MemoryFile()
            with memfile.open(**kwargs) as dst:
                dst.write(dst_array)
                try:
                    clipped, clipped_transform = mask(dst, city_gdf.geometry, crop=True)
                except ValueError:
                    raise ValueError("City polygon does not overlap reprojected raster!")

        else:
            # Raster already in EPSG:3857
            try:
                clipped, clipped_transform = mask(src, city_gdf.geometry, crop=True)
            except ValueError:
                raise ValueError("City polygon does not overlap raster!")

        # Use first band and set nodata to 0
        clipped = clipped[0]
        if src.nodata is not None:
            clipped[clipped == src.nodata] = 0

    # -----------------------------
    # Compute zonal population
    # -----------------------------
    stats = zonal_stats(
        zones,
        clipped,
        affine=clipped_transform,
        stats=["sum"],
        nodata=0
    )

    # Handle None or missing sums safely
    zones["pop"] = np.array([
        max(int(s["sum"]) if s is not None and s["sum"] is not None else 0, 1)
        for s in stats
    ])
    pop = zones["pop"].values

    print(f"🔹 Zones created: {len(zones)} | Total population: {pop.sum():,.0f}")

    return zones, pop


import numpy as np
import geopandas as gpd
from scipy.spatial import cKDTree


import numpy as np
from scipy.spatial import cKDTree


import numpy as np
from scipy.spatial import cKDTree


import numpy as np
from scipy.spatial import cKDTree

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

    print("🔹 Snapping zones to nodes (robust)...")

    # -----------------------------
    # ENSURE POINT GEOMETRY
    # -----------------------------
    if not zones_gdf.geometry.iloc[0].geom_type == "Point":
        centroids = zones_gdf.geometry.centroid
    else:
        centroids = zones_gdf.geometry

    # -----------------------------
    # BUILD NODE COORD ARRAY
    # -----------------------------
    node_coords = np.array([
        (geom.x, geom.y) for geom in nodes_gdf.geometry
    ])

    # KDTree for fast nearest neighbor
    tree = cKDTree(node_coords)

    # -----------------------------
    # SNAP EACH ZONE
    # -----------------------------
    zone_coords = np.array([
        (geom.x, geom.y) for geom in centroids
    ])

    distances, indices = tree.query(zone_coords, k=1)

    # -----------------------------
    # MAP TO NODE IDS
    # -----------------------------
    node_ids = nodes_gdf.index.astype(str).tolist()
    nodes_sel = [node_ids[i] for i in indices]

    # -----------------------------
    # OPTIONAL DISTANCE CHECK
    # -----------------------------
    if max_snap_dist is not None:
        too_far = distances > max_snap_dist
        n_far = np.sum(too_far)

        if n_far > 0:
            print(f"⚠️ {n_far} zones farther than max_snap_dist ({max_snap_dist})")

    # -----------------------------
    # CLEAN OUTPUT
    # -----------------------------
    zones_gdf = zones_gdf.copy().reset_index(drop=True)

    print(f"✅ Snapped ALL zones: {len(zones_gdf)}")
    print(f"   Avg distance: {distances.mean():.2f}")
    print(f"   Max distance: {distances.max():.2f}")

    return zones_gdf, nodes_sel