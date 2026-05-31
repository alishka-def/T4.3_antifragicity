# T4.3 Antifragility — Larissa SUMO Traffic Model

This repository builds microscopic [SUMO](https://eclipse.dev/sumo/) traffic
simulations for several European cities from open data. **Larissa (Greece)** is
the first city to be fully worked through end-to-end and serves as the reference
example throughout this README. The same pipeline is being applied to three
further cities — **Bratislava**, **Odessa**, and **Thessaloniki** — which are
already configured in the OD-matrix stage (see `multi-config.json`) and will get
their own SUMO builds next. Everywhere below, just substitute the city name and
its boundary/graph files to reproduce the workflow for another city.

The project contains two loosely coupled parts:

1. **`OD-matrix-main/`** — a Python pipeline that estimates a synthetic,
   gravity/entropy-based **Origin–Destination (OD) matrix** per hour of the day.
   It already covers all four cities (Larissa, Bratislava, Odessa, Thessaloniki)
   and produces, for each, an Excel workbook with one OD matrix per hour over a
   regular grid of zones.
2. **`data/`** — the SUMO model and the conversion scripts that turn the OSM road
   network and the hourly OD matrix into the files SUMO needs (network,
   traffic-assignment zones / TAZ, trips, routes). This stage is **complete for
   Larissa**; the other three cities follow the identical steps.

The end goal, per city, is to open `sumo-gui` with the city network, the routed
vehicles, and the zone polygons drawn on top — done for Larissa, planned for
Bratislava, Odessa, and Thessaloniki.

---

## 1. Repository structure

```
T4.3_antifragicity/
├── README.md                     ← this file
├── .gitignore                    ← large/generated files kept out of git (see note)
│
├── OD-matrix-main/               ← OD-matrix estimation pipeline (upstream of SUMO)
│   ├── main.py                   ← entry point; loops over cities in multi-config.json
│   ├── multi-config.json         ← per-city settings (grid size, trips, hourly profile…)
│   ├── modules/                  ← pipeline modules
│   │   ├── zones_utils.py        ← build grid zones, snap to network nodes
│   │   ├── od_utils.py           ← distance matrix, OD generation, save xlsx, plots
│   │   ├── assignment_utils.py   ← stochastic assignment to nodes
│   │   ├── validation_utils.py   ← compare against sensor counts (optional)
│   │   ├── clustering.py / od_viz.py / plot_academic_od_heatmap.py
│   │   └── app_streamlit.py      ← optional Streamlit viewer
│   ├── data/
│   │   ├── city_boundaries/<City>/<City>-v1.geojson   ← admin boundary (lon/lat)
│   │   ├── graphs/<City>/<City>-v1.graphml            ← OSM routing graph
│   │   │   └── (population rasters & sensor CSVs are referenced but git-ignored)
│   │   └── city_boundaries/osm2graphml.py             ← helper to build the graphml
│   └── outputs/
│       ├── hourly_od_<City>.xlsx ← **the OD matrix** (one sheet per hour: hour_0…hour_23)
│       └── <City>_OD_academic.(png|pdf)              ← heatmap figures
│
└── data/                         ← SUMO model + conversion scripts
                                   ←   (currently populated for Larissa; the
                                   ←    same layout repeats per city)
    ├── scripts/                  ← conversion utilities (run with python)
    │   ├── crop_net_to_boundary.py     ← keep only edges inside the city boundary
    │   ├── geojson_to_sumo_poly.py     ← grid GeoJSON → SUMO polygon (.poly.xml)
    │   ├── build_grid_taz_zones.py     ← rebuild the SAME grid zones as the OD pipeline
    │   ├── od_xlsx_to_od2trips.py      ← hourly OD xlsx → VISUM O-format .od files
    │   └── run_simulation.py           ← headless 24h run: progress bar, timing, VKT/VHT
    │
    ├── raw/                      ← raw OSM input
    │   └── larissa.osm.xml       ← OSM extract for Larissa (greece-latest.osm.pbf is git-ignored)
    ├── net/
    │   ├── keep_edges.txt        ← list of edge IDs inside the boundary (intermediate)
    │   └── larissa.net.xml       ← **the SUMO network** (git-ignored, you rebuild it)
    ├── zones/
    │   ├── larissa_grid_zones.geojson  ← grid zones (lon/lat), ids Z0…Zn
    │   └── larissa_zones.poly.xml      ← same zones as SUMO polygons (the --additional-files)
    ├── taz/
    │   └── larissa.taz.xml        ← Traffic Assignment Zones: each Z* mapped to its edges
    ├── od/
    │   └── larissa_hour_0.od … larissa_hour_23.od   ← per-hour O-format OD matrices
    ├── routes/
    │   ├── larissa.odtrips.xml   ← raw trips from od2trips (origin/destination edges)
    │   └── larissa.rou.xml       ← **routed vehicles** for SUMO (git-ignored, you rebuild it)
    └── sim/                      ← simulation outputs (git-ignored)
        └── larissa.tripinfo.xml  ← per-vehicle results used for VKT/VHT
```

> **Note on git-ignored files.** Large or generated artefacts are listed in
> `.gitignore` and are **not** committed: `data/net/larissa.net.xml`,
> `data/net/larissa_full.net.xml`, `data/raw/greece-latest.osm.pbf`,
> `data/routes/larissa.rou.xml`, and `data/routes/larissa.rou.alt.xml`.
> You regenerate them locally by following Section 4. The committed
> `larissa.odtrips.xml`, `*.od`, `*.taz.xml`, and `*.poly.xml` let you skip
> straight to routing if you wish.

---

## 2. Requirements

### Software
- **SUMO ≥ 1.20** (provides `sumo-gui`, `netconvert`, `od2trips`, `duarouter`,
  and the tools `edgesInDistricts.py`). Set the `SUMO_HOME` environment variable
  to your SUMO install (the examples below use `$env:SUMO_HOME`).
- **Python ≥ 3.10** (the project was developed on 3.12).

### Python packages
For the **conversion scripts** in `data/scripts/`:
```
sumolib            # ships with SUMO; ensure it is importable
shapely
geopandas
pandas
openpyxl           # read the .xlsx OD matrix
```
For the **OD-matrix pipeline** (`OD-matrix-main/`), additionally:
```
networkx
osmnx
numpy
rasterio           # population rasters
matplotlib
streamlit          # only for the optional viewer
```

Install, e.g. with conda (recommended because of geopandas/shapely):
```powershell
conda create -n t43 python=3.12
conda activate t43
conda install -c conda-forge geopandas shapely sumolib osmnx rasterio networkx pandas openpyxl matplotlib
```

Make sure `sumolib` resolves to your SUMO version, and that
`$env:SUMO_HOME\tools` is on `PYTHONPATH` so `edgesInDistricts.py` is found.

---

## 3. Step-by-step: build the network and run the simulation

All commands below are written for **Windows PowerShell** (matching the deployment
on the Remote Desktop). On macOS/Linux, swap `\` for `/`, replace
`& "$env:SUMO_HOME\bin\<tool>.exe"` with just `<tool>`, and call tools scripts as
`python $SUMO_HOME/tools/edgesInDistricts.py …`.

Run everything from the repository root:
```powershell
cd C:\Users\<you>\Documents\GitHub\T4.3_antifragicity
```

### Step 0 — (optional) Generate the OD matrix
Only needed if `OD-matrix-main/outputs/hourly_od_Larissa.xlsx` is missing or you
changed the inputs. This requires the population rasters and graphml (some are
git-ignored). From inside `OD-matrix-main/`:
```powershell
cd OD-matrix-main
python main.py
cd ..
```
**What it does:** for each city in `multi-config.json` it loads the OSM routing
graph, lays a regular square grid (`cell_size`, default 3000 m) over the city
boundary, snaps each zone to the nearest network node, computes an inter-zone
distance matrix, then generates a synthetic hourly OD using an entropy/gravity
model scaled to `total_trips`. The result is saved as
`outputs/hourly_od_Larissa.xlsx` — **one sheet per hour** (`hour_0`…`hour_23`),
each an origin×destination matrix indexed by zone ids `Z0…Zn-1`. These zone ids
are the contract that ties the matrix to the SUMO TAZ.

---

### Step 1 — Download the OSM data and build the full SUMO network

**1a. Get the raw OSM extract.** First you need the OpenStreetMap road data for
the area as an `.osm`/`.osm.xml` file in `data/raw/`. Two easy ways:

- **BBBike extract** (used for Larissa): draw a bounding box around the city at
  <https://extract.bbbike.org/>, choose the **OSM XML** format, and download the
  resulting extract (save it as e.g. `data\raw\larissa.osm.xml`).
- **Directly via SUMO** with the `osmGet.py` tool, which calls the OSM API for a
  bounding box for you:
  ```powershell
  python "$env:SUMO_HOME\tools\osmGet.py" `
      --bbox <minLon,minLat,maxLon,maxLat> `
      --prefix larissa --output-dir data\raw
  ```

**1b. Convert the OSM extract into a SUMO network.** `netconvert` imports the road
geometry, infers lanes/speeds/connections, and builds junctions. Here
`--keep-edges.by-vclass passenger` keeps only edges drivable by cars (dropping
footpaths, cycleways, etc.), `--geometry.remove` simplifies/merges edge geometry,
`--junctions.join` merges clustered junctions, and `--remove-edges.isolated`
drops unconnected stubs:
```powershell
& "$env:SUMO_HOME\bin\netconvert.exe" `
    --osm-files data\raw\larissa.osm.xml `
    -o data\net\larissa_full.net.xml `
    --geometry.remove `
    --junctions.join `
    --keep-edges.by-vclass passenger `
    --remove-edges.isolated
```
**Result:** `data/net/larissa_full.net.xml` — the whole OSM extract, usually larger
than the administrative city. It is cropped to the boundary in Step 2.

> The BBBike/`osmGet` extract is a rectangular bounding box, so it's wider than
> the city; Step 2 clips it to the official boundary and writes the final
> `larissa.net.xml`. If you don't need an exact-boundary clip, you can instead set
> `-o data\net\larissa.net.xml` here and skip Step 2 entirely.

---

### Step 2 — Crop the network to the city boundary
The OSM extract overshoots the city. This step keeps only edges whose centre falls
inside the official boundary polygon.

**2a. Compute the keep-list** (writes the IDs of edges inside the boundary):
```powershell
python data\scripts\crop_net_to_boundary.py `
    --net-file data\net\larissa_full.net.xml `
    --geojson-file OD-matrix-main\data\city_boundaries\Larissa\Larissa-v1.geojson `
    --output data\net\keep_edges.txt
```
**What it does:** reads the network with `sumolib`, computes each edge's centroid,
converts it from network XY to lon/lat, and tests whether it lies inside the
(union of the) boundary polygon. The surviving edge IDs are written to
`keep_edges.txt`. The script prints the exact `netconvert` command for the next
step.

**2b. Re-run netconvert with the keep-list** to produce the cropped network. The
`--keep-edges.components 1` flag drops any disconnected fragments so the network
stays routable:
```powershell
& "$env:SUMO_HOME\bin\netconvert.exe" `
    -s data\net\larissa_full.net.xml `
    --keep-edges.input-file data\net\keep_edges.txt `
    --keep-edges.components 1 `
    -o data\net\larissa.net.xml
```
**Result:** `data/net/larissa.net.xml` — **the network used by the simulation.**

---

### Step 3 — Build the zone polygons (for display + TAZ)
The OD matrix is defined over a grid of zones `Z0…Zn`. We rebuild **exactly the
same grid** as a GeoJSON, then convert it to a SUMO polygon file.

**3a. Rebuild the grid zones** (must use the same `--cell-size` as
`multi-config.json`, i.e. 3000):
```powershell
python data\scripts\build_grid_taz_zones.py `
    --city-shp OD-matrix-main\data\city_boundaries\Larissa\Larissa-v1.geojson `
    --cell-size 3000 `
    --output data\zones\larissa_grid_zones.geojson
```
**What it does:** lays the same square grid over the boundary, clips it to the
city, and labels cells `Z0…Zn-1` **in the same row order** the OD pipeline uses —
so zone `Z5` here is the same `Z5` in the matrix. The count it prints must match
the number of zones in the xlsx.

**3b. Convert the grid GeoJSON to SUMO polygons.** This reprojects the lon/lat
polygons into the network's coordinate system using `sumolib`:
```powershell
python data\scripts\geojson_to_sumo_poly.py `
    --net-file data\net\larissa.net.xml `
    --geojson-file data\zones\larissa_grid_zones.geojson `
    --id-column zone_id `
    --output data\zones\larissa_zones.poly.xml
```
**Result:** `data/zones/larissa_zones.poly.xml` — the red zone polygons you'll see
in the GUI, and the input for building the TAZ in the next step.

---

### Step 4 — Build the TAZ (map each zone to its edges)
SUMO's `od2trips` needs to know which **edges** belong to each zone so it can pick
real start/end edges for trips. `edgesInDistricts.py` (a SUMO tool) assigns every
edge to the zone polygon that contains it.
```powershell
python "$env:SUMO_HOME\tools\edgesInDistricts.py" `
    -n data\net\larissa.net.xml `
    -t data\zones\larissa_zones.poly.xml `
    --merge-separator _ `
    -o data\taz\larissa.taz.xml
```
**What it does:** for each zone polygon it collects the network edges inside it and
writes a `<taz id="Z…">` element listing those edges. (`--merge-separator _`
merges the `Zn_0`, `Zn_1` parts of any multi-part polygon back into one TAZ `Zn`.)
**Result:** `data/taz/larissa.taz.xml`. Zones that ended up with no edges (e.g.
fringe cells removed during cropping) simply won't appear here — the OD converter
in Step 5 drops trips referencing them.

---

### Step 5 — Convert the OD matrix to trips
**5a. Turn the xlsx matrix into per-hour O-format `.od` files.** Pass the TAZ file
so relations referencing a zone that has no edges are dropped (this avoids
`od2trips` "missing district" errors):
```powershell
python data\scripts\od_xlsx_to_od2trips.py `
    --xlsx OD-matrix-main\outputs\hourly_od_Larissa.xlsx `
    --out-dir data\od `
    --prefix larissa `
    --taz-file data\taz\larissa.taz.xml
```
**What it does:** reads each `hour_*` sheet and writes a VISUM **O-format** file
(`$OR;D2`) per hour, e.g. `larissa_hour_8.od`, each carrying its own time window
(`8.00 9.00`) and `origin dest count` rows. **Result:** `data/od/larissa_hour_0.od`
… `larissa_hour_23.od`.

**5b. Run `od2trips`** to expand the matrices into individual trips. We feed all 24
hourly files at once so each trip gets a departure time inside the right hour:
```powershell
$ods = ((0..23) | ForEach-Object { "data\od\larissa_hour_$_.od" }) -join ","
& "$env:SUMO_HOME\bin\od2trips.exe" `
    -n data\taz\larissa.taz.xml `
    -d $ods `
    -o data\routes\larissa.odtrips.xml `
    --ignore-errors
```
**Result:** `data/routes/larissa.odtrips.xml` — trips defined by origin/destination
**TAZ** (not yet routed). `--ignore-errors` skips any remaining unmatched zones.

---

### Step 6 — Route the trips
`od2trips` gives origin/destination zones; `duarouter` computes the actual edge
path each vehicle drives through the network.
```powershell
& "$env:SUMO_HOME\bin\duarouter.exe" `
    -n data\net\larissa.net.xml `
    --route-files data\routes\larissa.odtrips.xml `
    -o data\routes\larissa.rou.xml `
    --ignore-errors
```
**Result:** `data/routes/larissa.rou.xml` — the routed vehicles SUMO simulates.
(`duarouter` also writes `larissa.rou.alt.xml` with route alternatives.)

---

### Step 7 — Run the simulation in SUMO-GUI
Open the GUI with the network, the routes, and the zone polygons as an additional
visual layer:
```powershell
& "$env:SUMO_HOME\bin\sumo-gui.exe" `
    -n data\net\larissa.net.xml `
    -r data\routes\larissa.rou.xml `
    --additional-files data\zones\larissa_zones.poly.xml
```
This is the full form of the command from the project's Remote Desktop. Press the
green ▶ **play** button in the GUI to start; the red polygons are the OD zones.

> **Quick run (skip the build).** Because the committed repo already includes
> `larissa.taz.xml`, the `*.od` files, `larissa.odtrips.xml`, and
> `larissa_zones.poly.xml`, you only need to regenerate the two git-ignored network
> files (Steps 1–2) and the routes (Step 6), then launch Step 7.

---

### Step 8 — Run the full 24-hour simulation headless + measure VKT / VHT
For the actual experiment you want the **headless** `sumo` binary (faster than the
GUI), a progress bar, the wall-clock runtime, and the network performance metrics
**VKT** (Vehicle-Kilometres Travelled) and **VHT** (Vehicle-Hours Travelled).
`data/scripts/run_simulation.py` drives `sumo` over TraCI to do all of this:
```powershell
python data\scripts\run_simulation.py `
    --net data\net\larissa.net.xml `
    --routes data\routes\larissa.rou.xml `
    --tripinfo data\sim\larissa.tripinfo.xml `
    --horizon 86400
```
**What it does:**
- Launches the **headless** `sumo` binary (via `sumolib.checkBinary("sumo")`),
  *not* `sumo-gui`.
- Shows a live progress bar with percentage, simulated time / 24 h, the number of
  vehicles currently in the network, and elapsed wall-clock time, e.g.
  `[################------] 41.7% | sim 10.00h (36000s) | veh running: 4821 | elapsed 0:02:13`.
  The 24-hour demand window (`--horizon 86400`) drives the percentage; once past it
  the bar switches to a **drain** phase while the last trips finish.
- Writes per-vehicle results to `data/sim/larissa.tripinfo.xml`
  (`--tripinfo-output.write-unfinished` so vehicles still en route at the end are
  also counted), then computes:
  - **VKT** = Σ `routeLength` ÷ 1000  (veh-km)
  - **VHT** = Σ `duration` ÷ 3600  (veh-h)  — cross-checked against a live integral
    of the vehicle count
  - **network mean speed** = VKT ÷ VHT  (km/h)
- Reports the **wall-clock runtime in seconds** (and `H:MM:SS`).

It prints a summary block at the end:
```
========================  SIMULATION SUMMARY  ========================
  Simulation steps       : 90,123  (step length 1s)
  Simulated end time     : 90,123s  (25.03h)
  Peak vehicles in net   : 6,540
  Vehicles in tripinfo   : 248,401
  -------------------------------------------------------------------
  VKT (Vehicle-Km Travel): 1,234,567.8 veh-km
  VHT (Vehicle-Hr Travel): 34,567.12 veh-h   (live check: 34,560.40 veh-h)
  Network mean speed     : 35.71 km/h
  -------------------------------------------------------------------
  Wall-clock runtime     : 642.18 s   (0:10:42)
======================================================================
```
Useful options: `--step-length 0.5` (finer steps), `--end 90000` (hard stop time
passed to SUMO), `--additional data\zones\larissa_zones.poly.xml` (load the zone
polygons too). Requires `SUMO_HOME` to be set so `traci`/`sumolib` import.

> **Note.** The 24-hour demand finishes injecting vehicles at 86 400 s, but trips
> that depart late keep driving past that, so the simulation runs a little beyond
> 24 h until the network empties — that tail is the "drain" phase and is included
> in VKT/VHT. Use `--end 86400` if you instead want a hard cut-off at exactly 24 h.

---

## 4. Applying the pipeline to the other cities

Larissa is the completed reference; **Bratislava**, **Odessa**, and
**Thessaloniki** are next and follow the exact same steps. Each already has its
boundary, routing graph, and OD configuration in the OD-matrix stage
(`OD-matrix-main/multi-config.json` and `OD-matrix-main/data/...`), so their
`hourly_od_<City>.xlsx` matrices can be produced today.

To build the SUMO model for another city, repeat Section 4 with these
substitutions:

- Use that city's OSM extract in `data/raw/` for **Step 1**.
- Point `--geojson-file` / `--city-shp` at
  `OD-matrix-main/data/city_boundaries/<City>/<City>-v1.geojson` in **Steps 2–3**.
- Replace the `larissa` filename prefix and the `--xlsx
  …/hourly_od_<City>.xlsx` path with the target city in **Steps 3–6**.
- Keep `--cell-size 3000` (or whatever matches that city in `multi-config.json`)
  so the zone ids `Z0…Zn` still line up with the OD matrix.

A practical convention is to keep per-city files side by side, e.g.
`data/net/bratislava.net.xml`, `data/zones/bratislava_zones.poly.xml`,
`data/routes/bratislava.rou.xml`, and so on.

---

## 5. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `sumolib`/`edgesInDistricts.py` not found | `SUMO_HOME` not set, or `$env:SUMO_HOME\tools` not on `PYTHONPATH`. |
| Zone count from Step 3a ≠ zones in xlsx | `--cell-size` differs from `multi-config.json` (must be 3000), or a different boundary file was used. |
| `od2trips` "missing district / no edges" | A zone has no edges after cropping. Re-run Step 5a **with** `--taz-file` so those relations are dropped. |
| Network looks disconnected / vehicles teleport | Re-run Step 2b with `--keep-edges.components 1`; consider keeping more edges. |
| Empty / tiny simulation | Check `od2trips`/`duarouter` console for dropped trips; verify the OD xlsx is non-empty. |
