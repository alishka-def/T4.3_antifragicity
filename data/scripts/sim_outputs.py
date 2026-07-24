#!/usr/bin/env python3
"""Summarize the output files of an already-run SUMO simulation.

Does NOT run sumo. It only reads the tripinfo / statistics / summary XML
files a finished run has written and prints the summary block:

    Simulation steps, simulated end time, peak vehicles in net,
    vehicles in tripinfo (arrived / unfinished), teleports,
    VKT, VHT (+ live check from the per-step summary), mean speed,
    mean trip, total delay (timeLoss), total waiting.

Usage (from the repository root):
    python3 data/scripts/sim_outputs.py data/bratislava/bratislava_peak.sumocfg
        -> output paths are read from the config's <output> section
    python3 data/scripts/sim_outputs.py data/bratislava/sim/bratislava_peak_scale024
        -> run prefix: reads <prefix>.tripinfo.xml / .stats.xml / .summary.xml
           (passing one of those files directly also works)
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

OUTPUT_SUFFIXES = (".tripinfo.xml", ".stats.xml", ".summary.xml")


def cfg_value(root, tag, default=None):
    """Return the value="..." of the first <tag .../> element in the sumocfg."""
    el = root.find(f".//{tag}")
    return el.get("value") if el is not None else default


def fmt(x, dec=0):
    """1234567.89 -> '1,234,567.89' (dec decimals)."""
    return f"{x:,.{dec}f}"


def parse_tripinfo(path):
    """Stream-parse tripinfo.xml (can be large). Returns aggregate dict."""
    agg = {
        "count": 0, "arrived": 0,
        "route_m": 0.0, "duration_s": 0.0,
        "waiting_s": 0.0, "timeloss_s": 0.0,
    }
    for _, el in ET.iterparse(str(path)):
        if el.tag != "tripinfo":
            continue
        agg["count"] += 1
        if float(el.get("arrival", -1)) >= 0:
            agg["arrived"] += 1
        agg["route_m"] += float(el.get("routeLength", 0))
        agg["duration_s"] += float(el.get("duration", 0))
        agg["waiting_s"] += float(el.get("waitingTime", 0))
        agg["timeloss_s"] += float(el.get("timeLoss", 0))
        el.clear()
    return agg


def parse_summary(path):
    """Stream-parse summary.xml (one <step> per simulation step).

    Returns (peak_running, live_veh_h, begin, end, step_length) — begin,
    end and step length are taken from the step timestamps themselves,
    so no config file is needed.
    """
    peak = 0
    running_sum = 0
    first = second = last = None
    for _, el in ET.iterparse(str(path)):
        if el.tag != "step":
            continue
        t = float(el.get("time"))
        if first is None:
            first = t
        elif second is None:
            second = t
        last = t
        running = int(float(el.get("running", 0)))
        peak = max(peak, running)
        running_sum += running
        el.clear()
    step_length = (second - first) if second is not None else 1.0
    live_vh = running_sum * step_length / 3600.0
    return peak, live_vh, first, last, step_length


def print_run_summary(begin, step_length, tripinfo_f, stats_f, summary_f):
    """Parse the SUMO output files and print the formatted summary.

    begin / step_length may be None — they are then taken from summary.xml.
    """
    trip = parse_tripinfo(tripinfo_f) if tripinfo_f and tripinfo_f.exists() else None

    peak = live_vh = end_time = None
    if summary_f and summary_f.exists():
        peak, live_vh, sum_begin, end_time, sum_step = parse_summary(summary_f)
        begin = begin if begin is not None else sum_begin
        step_length = step_length if step_length is not None else sum_step

    teleports = None
    if stats_f and stats_f.exists():
        stats_root = ET.parse(stats_f).getroot()
        tel = stats_root.find("teleports")
        if tel is not None:
            teleports = int(float(tel.get("total", 0)))
        perf = stats_root.find("performance")
        if end_time is None and perf is not None and perf.get("end"):
            end_time = float(perf.get("end"))

    line = "-" * 62
    print(line)
    if end_time is not None and begin is not None and step_length:
        steps = (end_time - begin) / step_length
        print(f"Simulation steps      : {fmt(steps)}  (step length {step_length:g}s)")
        print(f"Simulated end time    : {fmt(end_time)}s  ({end_time / 3600:.2f}h)")
    if peak is not None:
        print(f"Peak vehicles in net  : {fmt(peak)}")
    if trip:
        unfinished = trip["count"] - trip["arrived"]
        print(f"Vehicles in tripinfo  : {fmt(trip['count'])}  "
              f"(arrived {fmt(trip['arrived'])}, unfinished {fmt(unfinished)})")
    if teleports is not None:
        print(f"Teleports (jam escapes): {fmt(teleports)}")
    print(line)
    if trip and trip["count"]:
        vkt = trip["route_m"] / 1000.0
        vht = trip["duration_s"] / 3600.0
        live = f"   (live check: {fmt(live_vh, 2)} veh-h)" if live_vh is not None else ""
        print(f"VKT (Vehicle-Km Travel): {fmt(vkt, 1)} veh-km")
        print(f"VHT (Vehicle-Hr Travel): {fmt(vht, 2)} veh-h{live}")
        if vht > 0:
            print(f"Network mean speed    : {vkt / vht:.2f} km/h")
        mean_km = trip["route_m"] / trip["count"] / 1000.0
        mean_min = trip["duration_s"] / trip["count"] / 60.0
        print(f"Mean trip             : {mean_km:.2f} km / {mean_min:.1f} min")
        print(f"Total delay (timeLoss): {fmt(trip['timeloss_s'] / 3600.0, 2)} veh-h")
        print(f"Total waiting (stops) : {fmt(trip['waiting_s'] / 3600.0, 2)} veh-h")
    else:
        print("No tripinfo file found — nothing to aggregate.")
    print(line)
    if stats_f:
        print(f"SUMO statistics XML   : {stats_f}")


def resolve_files(run):
    """Map the CLI argument to the three output files (+ begin/step if known)."""
    p = Path(run)

    # form 1: a .sumocfg — take paths and begin/step-length from it
    if p.suffix == ".sumocfg":
        if not p.exists():
            sys.exit(f"config not found: {p}")
        root = ET.parse(p).getroot()

        def out(tag):
            v = cfg_value(root, tag)
            return (p.parent / v).resolve() if v else None

        begin = cfg_value(root, "begin")
        step = cfg_value(root, "step-length")
        return (out("tripinfo-output"), out("statistic-output"),
                out("summary-output"),
                float(begin) if begin else None,
                float(step) if step else None)

    # form 2: a run prefix (or one of the output files themselves)
    prefix = str(p)
    for suf in OUTPUT_SUFFIXES:
        if prefix.endswith(suf):
            prefix = prefix[: -len(suf)]
            break
    trip_f, stats_f, summ_f = (Path(prefix + suf) for suf in OUTPUT_SUFFIXES)
    return trip_f, stats_f, summ_f, None, None


def main():
    ap = argparse.ArgumentParser(
        description="Print the post-run summary of a finished SUMO simulation "
                    "(reads its output files; does not run sumo).")
    ap.add_argument("run",
                    help="a .sumocfg (output paths are read from it) or a run "
                         "prefix like data/bratislava/sim/bratislava_peak_scale024")
    args = ap.parse_args()

    tripinfo_f, stats_f, summary_f, begin, step_length = resolve_files(args.run)

    if not any((tripinfo_f, stats_f, summary_f)):
        sys.exit(f"{args.run} defines no <output> files — pass a run prefix "
                 "instead (e.g. data/<city>/sim/<run>).")
    existing = [f for f in (tripinfo_f, stats_f, summary_f) if f and f.exists()]
    if not existing:
        print("No output files found. Expected:", file=sys.stderr)
        for f in (tripinfo_f, stats_f, summary_f):
            print(f"  {f}", file=sys.stderr)
        sys.exit("Run the simulation first (sumo -c <config>), then re-run this script.")
    for f in (tripinfo_f, stats_f, summary_f):
        if f and not f.exists():
            print(f"note: {f.name} not found — some lines will be skipped",
                  file=sys.stderr)

    print_run_summary(begin, step_length, tripinfo_f, stats_f, summary_f)


if __name__ == "__main__":
    main()
