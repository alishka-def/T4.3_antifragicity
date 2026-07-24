"""Build a SUMO TAZ file for Visum zones on an (unrelated) SUMO network.

Reads the $ZONE / $NODE / $CONNECTOR tables of a PTV Visum .net export, anchors
each zone at its connector nodes (fallback: zone centroid), transforms the
coordinates from the Visum CRS into the SUMO network's coordinates, and snaps
each anchor to the nearest car-routable edges. Zones whose anchors lie outside
the network (external / cordon zones) are snapped to the nearest *major* edge
so their demand enters on a real corridor at the network fringe.

The TAZ ids are the Visum zone numbers, so the resulting file can be fed to
od2trips together with the Visum OD matrices ($V / $O format).
"""

from __future__ import annotations

import argparse
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pyproj
import sumolib


def parse_visum_tables(path: Path, wanted: set[str]) -> dict[str, tuple[list[str], list[list[str]]]]:
    """Return {table_name: (column_names, rows)} for the wanted $-tables."""
    tables: dict[str, tuple[list[str], list[list[str]]]] = {}
    current = None
    with open(path, encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.rstrip("\n").rstrip("\r")
            if line.startswith("$"):
                name, _, header = line[1:].partition(":")
                if name in wanted:
                    tables[name] = (header.split(";"), [])
                    current = name
                else:
                    current = None
                continue
            if current is None or not line.strip() or line.startswith("*"):
                continue
            tables[current][1].append(line.split(";"))
    missing = wanted - tables.keys()
    if missing:
        raise ValueError(f"Tables not found in {path}: {sorted(missing)}")
    return tables


def read_matrix_zone_ids(path: Path) -> list[str]:
    """Return the zone numbers listed in a $V-format matrix file."""
    with open(path, encoding="utf-8-sig") as handle:
        lines = handle.read().splitlines()
    for i, line in enumerate(lines):
        if "Number of network objects" in line:
            count = int(lines[i + 1].strip())
        if "Network object numbers" in line:
            zone_ids: list[str] = []
            for row in lines[i + 1:]:
                zone_ids.extend(row.split())
                if len(zone_ids) >= count:
                    return zone_ids[:count]
    raise ValueError(f"Could not find zone list in matrix file {path}")


def largest_scc_edges(net) -> set:
    """Largest strongly connected component of passenger-allowed edges.

    Iterative Kosaraju on the edge graph (edge -> outgoing edges); keeps demand
    from being assigned to edges that cannot reach / be reached from the rest
    of the network.
    """
    edges = [e for e in net.getEdges() if e.allows("passenger")]
    allowed = set(edges)

    def out_neighbours(edge):
        return [e for e in edge.getOutgoing() if e in allowed]

    def in_neighbours(edge):
        return [e for e in edge.getIncoming() if e in allowed]

    order, seen = [], set()
    for start in edges:
        if start in seen:
            continue
        stack = [(start, iter(out_neighbours(start)))]
        seen.add(start)
        while stack:
            node, it = stack[-1]
            advanced = False
            for nxt in it:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append((nxt, iter(out_neighbours(nxt))))
                    advanced = True
                    break
            if not advanced:
                order.append(node)
                stack.pop()

    assigned, best = set(), set()
    for start in reversed(order):
        if start in assigned:
            continue
        component, stack = set(), [start]
        assigned.add(start)
        while stack:
            node = stack.pop()
            component.add(node)
            for nxt in in_neighbours(node):
                if nxt not in assigned:
                    assigned.add(nxt)
                    stack.append(nxt)
        if len(component) > len(best):
            best = component
    return best


def point_to_edge_distance(x: float, y: float, edge) -> float:
    shape = edge.getShape()
    best = math.inf
    for (x1, y1), (x2, y2) in zip(shape, shape[1:]):
        dx, dy = x2 - x1, y2 - y1
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            dist = math.hypot(x - x1, y - y1)
        else:
            t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length_sq))
            dist = math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))
        best = min(best, dist)
    return best


def snap_anchor(net, candidates: set, x: float, y: float, radii, k: int):
    """Nearest candidate edges around (x, y): list of (edge, dist), max k."""
    for radius in radii:
        hits = [(e, d) for e, d in net.getNeighboringEdges(x, y, radius) if e in candidates]
        if hits:
            hits.sort(key=lambda item: item[1])
            return hits[:k]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visum-net", required=True, help="Visum .net export ($ZONE/$NODE/$CONNECTOR)")
    parser.add_argument("--net-file", required=True, help="SUMO network to snap the zones onto")
    parser.add_argument("--crs", default="EPSG:5514", help="CRS of the Visum coordinates")
    parser.add_argument("--mtx", action="append", default=[],
                        help="$V matrix file(s); every zone id used there must end up in the TAZ")
    parser.add_argument("--max-snap-dist", type=float, default=2000.0,
                        help="max anchor-to-edge distance [m] before the major-road fallback kicks in")
    parser.add_argument("--edges-per-anchor", type=int, default=3)
    parser.add_argument("--major-speed", type=float, default=16.6,
                        help="edges at/above this speed [m/s] are fallback candidates for external zones")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    visum_net = Path(args.visum_net)
    net_file = Path(args.net_file)
    output_file = Path(args.output)
    for path in (visum_net, net_file):
        if not path.exists():
            raise FileNotFoundError(path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    tables = parse_visum_tables(visum_net, {"ZONE", "NODE", "CONNECTOR"})

    def columns(table, *names):
        header, rows = tables[table]
        idx = [header.index(n) for n in names]
        return [[row[i] for i in idx] for row in rows]

    zones = {no: (name, float(x), float(y))
             for no, name, x, y in columns("ZONE", "NO", "NAME", "XCOORD", "YCOORD")}
    nodes = {no: (float(x), float(y)) for no, x, y in columns("NODE", "NO", "XCOORD", "YCOORD")}
    connectors: dict[str, list[str]] = {}
    for zone_no, node_no in columns("CONNECTOR", "ZONENO", "NODENO"):
        connectors.setdefault(zone_no, [])
        if node_no not in connectors[zone_no]:
            connectors[zone_no].append(node_no)

    net = sumolib.net.readNet(str(net_file), withInternal=False)
    to_lonlat = pyproj.Transformer.from_crs(args.crs, "EPSG:4326", always_xy=True)

    def to_net_xy(x: float, y: float):
        lon, lat = to_lonlat.transform(x, y)
        return net.convertLonLat2XY(lon, lat)

    candidates = largest_scc_edges(net)
    print(f"passenger edges in largest SCC: {len(candidates)} / {len(net.getEdges())} edges")
    major = [e for e in candidates if e.getSpeed() >= args.major_speed]
    print(f"major-road fallback candidates (speed >= {args.major_speed} m/s): {len(major)}")

    radii = [r for r in (250.0, 500.0, 1000.0, args.max_snap_dist) if r <= args.max_snap_dist]

    root = ET.Element("tazs")
    snap_dists: dict[str, float] = {}
    fallback_zones: list[tuple[str, str, float]] = []
    for zone_no in sorted(zones, key=int):
        name, cx, cy = zones[zone_no]
        anchor_coords = [nodes[n] for n in connectors.get(zone_no, []) if n in nodes] or [(cx, cy)]

        zone_edges: dict = {}
        best_dist = math.inf
        for ax, ay in anchor_coords:
            x, y = to_net_xy(ax, ay)
            for edge, dist in snap_anchor(net, candidates, x, y, radii, args.edges_per_anchor):
                zone_edges.setdefault(edge, dist)
                best_dist = min(best_dist, dist)

        if not zone_edges:
            # external zone: nearest major edge to the (single) closest anchor
            x, y = to_net_xy(*anchor_coords[0])
            edge = min(major, key=lambda e: point_to_edge_distance(x, y, e))
            best_dist = point_to_edge_distance(x, y, edge)
            zone_edges[edge] = best_dist
            fallback_zones.append((zone_no, name, best_dist))

        snap_dists[zone_no] = best_dist
        taz = ET.SubElement(root, "taz", {"id": zone_no})
        for edge in sorted(zone_edges, key=lambda e: e.getID()):
            ET.SubElement(taz, "tazSource", {"id": edge.getID(), "weight": "1.00"})
            ET.SubElement(taz, "tazSink", {"id": edge.getID(), "weight": "1.00"})

    tree = ET.ElementTree(root)
    if hasattr(ET, "indent"):
        ET.indent(tree, space="  ")
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {len(zones)} TAZ to {output_file}")

    for mtx in args.mtx:
        matrix_zones = read_matrix_zone_ids(Path(mtx))
        missing = [z for z in matrix_zones if z not in zones]
        if missing:
            print(f"ERROR: {mtx}: {len(missing)} matrix zones missing from TAZ: {missing[:10]}")
            sys.exit(1)
        print(f"{mtx}: all {len(matrix_zones)} matrix zones covered")

    buckets = [(100, 0), (500, 0), (1000, 0), (2000, 0), (math.inf, 0)]
    counts = [0] * len(buckets)
    for dist in snap_dists.values():
        for i, (limit, _) in enumerate(buckets):
            if dist <= limit:
                counts[i] += 1
                break
    labels = ["<=100m", "100-500m", "0.5-1km", "1-2km", ">2km (fringe fallback)"]
    print("snap distance of zones (anchor -> nearest edge):")
    for label, count in zip(labels, counts):
        print(f"  {label:>24}: {count}")
    if fallback_zones:
        fallback_zones.sort(key=lambda item: -item[2])
        print(f"zones on major-road fallback ({len(fallback_zones)}):")
        for zone_no, name, dist in fallback_zones[:15]:
            print(f"  {zone_no}  {name:<30} {dist / 1000:6.1f} km from network")
        if len(fallback_zones) > 15:
            print(f"  ... and {len(fallback_zones) - 15} more")


if __name__ == "__main__":
    main()
