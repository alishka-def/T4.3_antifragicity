#!/usr/bin/env python3
"""
Convert a SUMO network's ACTUATED traffic lights into STATIC (fixed-time) ones.

Every ``<tlLogic ... type="actuated">`` becomes ``type="static"``. Static control
uses each phase's existing ``duration`` as the fixed green/yellow time, so the cycle
structure, timings and offsets are preserved exactly (a faithful "same plan, but
fixed-time" conversion). The now-inert ``minDur``/``maxDur`` phase attributes are
stripped by default (they only apply to actuated control and would otherwise trigger
SUMO warnings); pass ``--keep-min-max`` to retain them.

The original ``<city>.net.xml`` is NEVER modified: a new ``<city>_static.net.xml`` is
written next to it. A matching ``<city>_static.sumocfg`` is written too (net-file and
sim outputs redirected), so the static scenario can be run immediately:

    sumo -c data/<city>/<city>_static.sumocfg

The file is processed as a text stream, so it scales to the 40-150 MB networks here
without loading the whole DOM. ``type="actuated"`` occurs only on ``<tlLogic>`` lines
(verified: its count equals the tlLogic count), so the rewrite is unambiguous.

Usage
-----
    # all three cities (bratislava, larissa, odessa):
    python data/scripts/tls_actuated_to_static.py

    # a single explicit file:
    python data/scripts/tls_actuated_to_static.py \
        --net data/larissa/net/larissa.net.xml \
        --out data/larissa/net/larissa_static.net.xml
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CITIES = ["bratislava", "larissa", "odessa"]

_MINMAX = re.compile(r'\s+(?:minDur|maxDur)="[^"]*"')


def convert_net(src: Path, dst: Path, strip_min_max: bool = True) -> tuple[int, int]:
    """Write `dst` from `src` with actuated tlLogic flipped to static.

    Returns (tlLogic_converted, phase_lines_stripped).
    """
    n_tl = 0
    n_phase = 0
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    with src.open("r", encoding="utf-8") as fin, tmp.open("w", encoding="utf-8") as fout:
        for line in fin:
            if "<tlLogic " in line and 'type="actuated"' in line:
                line = line.replace('type="actuated"', 'type="static"')
                n_tl += 1
            elif strip_min_max and "<phase " in line and ("minDur=" in line or "maxDur=" in line):
                new = _MINMAX.sub("", line)
                if new != line:
                    n_phase += 1
                line = new
            fout.write(line)
    tmp.replace(dst)
    return n_tl, n_phase


def write_static_sumocfg(city: str) -> Path | None:
    """Copy <city>.sumocfg -> <city>_static.sumocfg, pointing at the static net
    and redirecting any sim/ outputs so the actuated run is not clobbered."""
    src = DATA / city / f"{city}.sumocfg"
    if not src.exists():
        return None
    text = src.read_text(encoding="utf-8")
    text = text.replace(f"net/{city}.net.xml", f"net/{city}_static.net.xml")
    text = text.replace(f"sim/{city}.", f"sim/{city}_static.")
    dst = DATA / city / f"{city}_static.sumocfg"
    dst.write_text(text, encoding="utf-8")
    return dst


def process_city(city: str, strip_min_max: bool) -> None:
    src = DATA / city / "net" / f"{city}.net.xml"
    if not src.exists():
        print(f"[{city}] SKIP: {src} not found")
        return
    dst = DATA / city / "net" / f"{city}_static.net.xml"
    n_tl, n_phase = convert_net(src, dst, strip_min_max)
    cfg = write_static_sumocfg(city)
    print(f"[{city}] {n_tl} actuated tlLogic -> static, "
          f"{n_phase} phase line(s) stripped of minDur/maxDur")
    print(f"[{city}]   net  -> {dst.relative_to(ROOT)}")
    if cfg:
        print(f"[{city}]   cfg  -> {cfg.relative_to(ROOT)}  (run: sumo -c {cfg.relative_to(ROOT)})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--net", help="Single input net.xml (with --out).")
    ap.add_argument("--out", help="Output net.xml for --net.")
    ap.add_argument("--keep-min-max", action="store_true",
                    help="Keep the (inert) minDur/maxDur phase attributes.")
    args = ap.parse_args()

    strip = not args.keep_min_max
    if args.net:
        if not args.out:
            ap.error("--net requires --out")
        n_tl, n_phase = convert_net(Path(args.net), Path(args.out), strip)
        print(f"{n_tl} actuated tlLogic -> static, {n_phase} phase line(s) stripped "
              f"-> {args.out}")
    else:
        for city in CITIES:
            process_city(city, strip)


if __name__ == "__main__":
    main()
