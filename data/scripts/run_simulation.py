r"""
Usage
-----
    python data/scripts/run_simulation.py \
        --net data/net/larissa.net.xml \
        --routes data/routes/larissa.rou.xml \
        --additional data/zones/larissa_zones.poly.xml \
        --tripinfo data/sim/larissa.tripinfo.xml \
        --horizon 86400
"""
from __future__ import annotations
import argparse
import os
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

if "SUMO_HOME" in os.environ:
    sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))

import sumolib
import traci

def fmt_hms(seconds: float) -> str:
    """Format a number of seconds as H:MM:SS."""
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}"


def render_bar(frac: float, sim_time: float, running: int,
               elapsed: float, width: int, draining: bool) -> None:
    """Draw an in-place progress bar on stderr."""
    frac = max(0.0, min(frac, 1.0))
    filled = int(round(frac * width))
    bar = "#" * filled + "-" * (width - filled)
    phase = "drain" if draining else "sim  "
    msg = (
        f"\r[{bar}] {100.0 * frac:5.1f}% | {phase} "
        f"{sim_time / 3600.0:5.2f}h ({sim_time:8.0f}s) | "
        f"veh running: {running:6d} | elapsed {fmt_hms(elapsed)}"
    )
    sys.stderr.write(msg)
    sys.stderr.flush()


class TripStats:
    """Aggregates streamed over the tripinfo file (see parse_tripinfo)."""
    total_m = 0.0          # Σ routeLength (m)            -> VKT
    total_s = 0.0          # Σ duration (s)               -> VHT / time spent
    total_timeloss = 0.0   # Σ timeLoss (s)               -> delay vs free-flow
    total_waiting = 0.0    # Σ waitingTime (s)            -> standstill time
    n = 0                  # vehicles in tripinfo
    n_unfinished = 0       # vehicles still en route at sim end


def parse_tripinfo(path: Path) -> TripStats:
    """Stream the tripinfo file and accumulate per-vehicle network metrics.

    Uses iterparse so large files are not loaded whole. Vehicles still running at
    the end (written via --tripinfo-output.write-unfinished) carry arrival="-1".
    """
    s = TripStats()
    for _event, elem in ET.iterparse(str(path), events=("end",)):
        if elem.tag != "tripinfo":
            continue
        s.total_m += max(float(elem.get("routeLength", 0.0) or 0.0), 0.0)
        s.total_s += max(float(elem.get("duration", 0.0) or 0.0), 0.0)
        s.total_timeloss += max(float(elem.get("timeLoss", 0.0) or 0.0), 0.0)
        s.total_waiting += max(float(elem.get("waitingTime", 0.0) or 0.0), 0.0)
        if float(elem.get("arrival", 0.0) or 0.0) < 0:
            s.n_unfinished += 1
        s.n += 1
        elem.clear()  # free memory as we go
    return s


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--net", default="data/net/larissa.net.xml",
                        help="SUMO network file.")
    parser.add_argument("--routes", default="data/routes/larissa.rou.xml",
                        help="Routed vehicles (duarouter output).")
    parser.add_argument("--additional", default=None,
                        help="Optional additional file(s), e.g. zone polygons.")
    parser.add_argument("--tripinfo", default="data/sim/larissa.tripinfo.xml",
                        help="Where to write per-vehicle tripinfo (used for VKT/VHT).")
    parser.add_argument("--statistic-output", default="data/sim/larissa.stats.xml",
                        help="Where to write SUMO's own aggregate statistics XML "
                             "(authoritative cross-check; '' to disable).")
    parser.add_argument("--summary-output", default=None,
                        help="Optional per-step summary XML (running/halting "
                             "vehicles, mean speed) for an hourly congestion profile.")
    parser.add_argument("--step-length", type=float, default=1.0,
                        help="Simulation step length in seconds.")
    parser.add_argument("--horizon", type=float, default=86400.0,
                        help="Demand window in seconds (24h=86400). Drives the "
                             "progress bar; the sim then drains until empty.")
    parser.add_argument("--end", type=float, default=None,
                        help="Optional hard stop time (s) passed to SUMO. If set, "
                             "vehicles still running at --end are cut off.")
    parser.add_argument("--bar-width", type=int, default=40,
                        help="Progress-bar width in characters.")
    parser.add_argument("--sumo-binary", default="sumo",
                        help="SUMO binary to use ('sumo' = headless; not sumo-gui).")
    parser.add_argument("--no-warnings", action="store_true",
                        help="Suppress SUMO warning messages (e.g. teleport spam).")
    parser.add_argument("--time-to-teleport", type=float, default=300.0,
                        help="Seconds a vehicle may be stuck before SUMO teleports "
                             "it (-1 disables teleporting). Default 300.")
    args = parser.parse_args()

    net_file = Path(args.net)
    routes_file = Path(args.routes)
    tripinfo_file = Path(args.tripinfo)

    if not net_file.exists():
        raise FileNotFoundError(f"Network not found: {net_file}")
    if not routes_file.exists():
        raise FileNotFoundError(f"Route file not found: {routes_file}")
    tripinfo_file.parent.mkdir(parents=True, exist_ok=True)

    stats_file = Path(args.statistic_output) if args.statistic_output else None
    if stats_file:
        stats_file.parent.mkdir(parents=True, exist_ok=True)

    # Resolve the headless binary explicitly so we never start the GUI.
    sumo_bin = sumolib.checkBinary(args.sumo_binary)

    cmd = [
        sumo_bin,
        "-n", str(net_file),
        "-r", str(routes_file),
        "--step-length", str(args.step_length),
        "--tripinfo-output", str(tripinfo_file),
        "--tripinfo-output.write-unfinished",  # capture vehicles still en route
        "--no-step-log", "true",               # silence SUMO's own step log
        "--duration-log.statistics", "true",   # SUMO prints its own veh stats too
        "--time-to-teleport", str(args.time_to_teleport),
    ]
    if stats_file:
        cmd += ["--statistic-output", str(stats_file)]
    if args.summary_output:
        cmd += ["--summary-output", str(args.summary_output)]
    if args.no_warnings:
        cmd += ["--no-warnings", "true"]       # silence teleport/jam warnings
    if args.additional:
        cmd += ["--additional-files", str(args.additional)]
    if args.end is not None:
        cmd += ["--end", str(args.end)]

    print(f"Launching: {' '.join(cmd)}\n")

    horizon = args.horizon
    step_length = args.step_length
    update_every = max(1, int((horizon / step_length) / 500))  # ~500 bar refreshes

    vht_seconds_live = 0.0   # integral of running-vehicle count * step_length
    steps = 0
    max_running = 0
    teleports = 0            # vehicles teleported past jams (masks gridlock)

    wall_start = time.perf_counter()
    traci.start(cmd)
    try:
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            steps += 1

            sim_time = traci.simulation.getTime()
            running = traci.vehicle.getIDCount()
            vht_seconds_live += running * step_length
            teleports += traci.simulation.getStartingTeleportNumber()
            if running > max_running:
                max_running = running

            if steps % update_every == 0:
                elapsed = time.perf_counter() - wall_start
                draining = sim_time > horizon
                frac = 1.0 if draining else sim_time / horizon
                render_bar(frac, sim_time, running, elapsed, args.bar_width, draining)
    finally:
        sim_end_time = traci.simulation.getTime()
        traci.close()

    wall_seconds = time.perf_counter() - wall_start
    # finish the progress line
    render_bar(1.0, sim_end_time, 0, wall_seconds, args.bar_width, draining=False)
    sys.stderr.write("\n")
    sys.stderr.flush()

    # --- Authoritative network metrics from tripinfo ------------------------
    vkt = vht = 0.0
    n_veh = n_arrived = 0
    mean_dist_km = mean_dur_min = delay_h = waiting_h = float("nan")
    if tripinfo_file.exists():
        t = parse_tripinfo(tripinfo_file)
        n_veh = t.n
        n_arrived = t.n - t.n_unfinished
        vkt = t.total_m / 1000.0
        vht = t.total_s / 3600.0
        delay_h = t.total_timeloss / 3600.0
        waiting_h = t.total_waiting / 3600.0
        if t.n:
            mean_dist_km = (t.total_m / t.n) / 1000.0
            mean_dur_min = (t.total_s / t.n) / 60.0

    vht_live = vht_seconds_live / 3600.0
    mean_speed = (vkt / vht) if vht > 0 else float("nan")

    print("\n========================  SIMULATION SUMMARY  ========================")
    print(f"  Network                : {net_file}")
    print(f"  Routes                 : {routes_file}")
    print(f"  Simulation steps       : {steps:,}  (step length {step_length:g}s)")
    print(f"  Simulated end time     : {sim_end_time:,.0f}s  ({sim_end_time / 3600.0:.2f}h)")
    print(f"  Peak vehicles in net   : {max_running:,}")
    print(f"  Vehicles in tripinfo   : {n_veh:,}  (arrived {n_arrived:,}, "
          f"unfinished {n_veh - n_arrived:,})")
    print(f"  Teleports (jam escapes): {teleports:,}")
    print("  -------------------------------------------------------------------")
    print(f"  VKT (Vehicle-Km Travel): {vkt:,.1f} veh-km")
    print(f"  VHT (Vehicle-Hr Travel): {vht:,.2f} veh-h   (live check: {vht_live:,.2f} veh-h)")
    print(f"  Network mean speed     : {mean_speed:,.2f} km/h")
    print(f"  Mean trip             : {mean_dist_km:,.2f} km / {mean_dur_min:,.1f} min")
    print(f"  Total delay (timeLoss) : {delay_h:,.2f} veh-h")
    print(f"  Total waiting (stops)  : {waiting_h:,.2f} veh-h")
    print("  -------------------------------------------------------------------")
    print(f"  Wall-clock runtime     : {wall_seconds:,.2f} s   ({fmt_hms(wall_seconds)})")
    if stats_file and stats_file.exists():
        print(f"  SUMO statistics XML    : {stats_file}")
    print("======================================================================")


if __name__ == "__main__":
    main()