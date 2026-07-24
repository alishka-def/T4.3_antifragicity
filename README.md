# T4.3 Antifragility — Multi-City SUMO Traffic Models

This repository builds microscopic [SUMO](https://eclipse.dev/sumo/) traffic
simulations for several European cities from open data. It currently covers
three cities — **Larissa** (Greece), **Bratislava** (Slovakia), and **Odessa**
(Ukraine) — each taken end-to-end from a synthetic Origin–Destination (OD)
matrix and an OpenStreetMap road network to a runnable `sumo-gui` scenario.

The project has **two loosely-coupled stages**:

1. **`od-matrix/`** — a Python pipeline that estimates a synthetic,
   gravity/entropy-based **OD matrix per hour of the day** over a regular grid of
   zones. It produces, per city, an Excel workbook with one OD matrix per hour
   (`hourly_od_<City>.xlsx`). This is the *upstream* stage.
2. **`data/`** — the SUMO models plus the conversion scripts that turn the OSM
   road network and the hourly OD matrix into the files SUMO needs (network,
   traffic-assignment zones / TAZ, trips, routes, config). This is the
   *downstream* stage and is organised **one folder per city**.

The end goal, per city, is to open `sumo-gui` with the city network, the routed
vehicles, and the zone polygons drawn on top.

---

## 1. Repository structure

```
T4.3_antifragicity/
├── README.md                     ← this file
├── .gitignore                    ← large/generated files kept out of git (see §5)
│
├── od-matrix/               ← STAGE 1: OD-matrix estimation (upstream of SUMO)
│   ├── main.py                   ← entry point; loops over cities in multi-config.json
│   ├── multi-config.json         ← per-city settings (grid size, trips, hourly profile…)
│   ├── modules/                  ← pipeline modules (zones, OD generation, plots, …)
│   ├── data/
│   │   ├── city_boundaries/<City>/<City>-v1.geojson   ← admin boundary (lon/lat)
│   │   └── graphs/<City>/<City>-v1.graphml            ← OSM routing graph
│   └── outputs/
│       └── hourly_od_<City>.xlsx ← THE OD MATRIX (one sheet per hour: hour_0…hour_23)
│
└── data/                         ← STAGE 2: SUMO models + conversion scripts
    ├── scripts/                  ← shared, city-agnostic conversion utilities
    │   ├── crop_net_to_boundary.py   ← keep only edges inside the city boundary
    │   ├── build_grid_taz_zones.py   ← rebuild the SAME grid zones as the OD pipeline
    │   ├── geojson_to_sumo_poly.py   ← grid GeoJSON → SUMO polygons (.poly.xml)
    │   ├── od_xlsx_to_od2trips.py    ← hourly OD xlsx → VISUM O-format .od files
    │   ├── tls_actuated_to_static.py ← derive fixed-time (static) TLS net + config
    │   └── sim_outputs.py            ← print the summary of a finished run (VKT, VHT, …)
    │
    ├── larissa/                  ← one self-contained folder per city
    │   ├── larissa.sumocfg       ← SUMO config, full 24 h day (paths relative to this folder)
    │   ├── larissa_static.sumocfg    ← same, on the fixed-time-TLS network variant
    │   ├── larissa_peak.sumocfg      ← morning peak 06:00–11:00 (peak-only routes)
    │   ├── net/
    │   │   ├── <city>_full.net.xml   ← full network from OSM         (git-ignored)
    │   │   ├── keep_edges.txt        ← edge IDs inside the boundary
    │   │   └── <city>.net.xml        ← THE cropped network            (git-ignored)
    │   ├── raw/                  ← raw OSM input (.osm / .osm.pbf — .pbf git-ignored)
    │   ├── zones/
    │   │   ├── <city>_grid_zones.geojson  ← grid zones (lon/lat), ids Z0…Zn
    │   │   └── <city>_zones.poly.xml      ← same zones as SUMO polygons
    │   ├── taz/  <city>.taz.xml       ← Traffic Assignment Zones (each Z* → its edges)
    │   ├── od/   <city>_hour_0.od … _23.od   ← per-hour O-format OD matrices
    │   ├── routes/
    │   │   ├── <city>.odtrips.xml    ← raw trips from od2trips
    │   │   ├── <city>.rou.xml        ← ROUTED vehicles for SUMO       (git-ignored)
    │   │   └── <city>.rou.alt.xml    ← route alternatives             (git-ignored)
    │   └── sim/  <city>.tripinfo.xml ← per-vehicle results for VKT/VHT (git-ignored)
    │
    ├── bratislava/               ← same layout
    └── odessa/                   ← same layout
```

`data/scripts/` is **shared** across all cities (the scripts take the city's
paths as CLI arguments). Everything else under `data/<city>/` is that city's own
inputs and outputs.

> **Naming convention.** The OD-matrix stage uses **Capitalised** city names
> (`Larissa`, `Bratislava`, `Odessa`) in paths and filenames; the SUMO stage uses
> **lower-case** folder names and file prefixes (`data/larissa/…`,
> `larissa.net.xml`). Keep both straight when substituting a city.

---

## 2. Requirements

### Software
- **SUMO ≥ 1.20** — provides `sumo`, `sumo-gui`, `netconvert`, `od2trips`,
  `duarouter`, and the tools `osmWebWizard.py` and `edgesInDistricts.py`.
  Set the `SUMO_HOME` environment variable to your SUMO install and make sure the
  binaries are on your `PATH`. `osmWebWizard.py` (Step 1) also needs a **web
  browser** and **outbound internet** (it downloads OSM via the Overpass API).
- **Python ≥ 3.10**.

### Python packages
For the **conversion scripts** in `data/scripts/`:
```
sumolib   shapely   geopandas   pandas   openpyxl   matplotlib
```
For the **OD-matrix pipeline** (`od-matrix/`), additionally:
```
networkx   osmnx   numpy   rasterio   rasterstats   scipy   seaborn
```
Conda is recommended because of geopandas/shapely:
```bash
conda create -n t43 python=3.12
conda activate t43
conda install -c conda-forge geopandas shapely sumolib osmnx rasterio rasterstats networkx scipy pandas openpyxl matplotlib seaborn
```
Make sure `sumolib` resolves to your SUMO version and that `$SUMO_HOME/tools` is
importable so `edgesInDistricts.py` is found.

> All commands below are written for **macOS / Linux (zsh/bash)** and assume the
> SUMO binaries are on `PATH`. Run everything **from the repository root**. On
> Windows PowerShell, swap `/` for `\` and call binaries as
> `& "$env:SUMO_HOME\bin\<tool>.exe"`.

---

## 3. From a city to a SUMO config — the full pipeline

Below, replace `<city>` with the lower-case city folder (e.g. `bratislava`) and
`<City>` with the Capitalised name used by the OD stage (e.g. `Bratislava`).

The pipeline turns three inputs into a running simulation:

| Input | Where it comes from |
|---|---|
| City boundary GeoJSON | `od-matrix/data/city_boundaries/<City>/<City>-v1.geojson` |
| Hourly OD matrix      | `od-matrix/outputs/hourly_od_<City>.xlsx` (Stage 0) |
| Raw OSM road network  | downloaded in Step 1 (the only thing you fetch fresh) |

### Stage 0 — (optional) Generate the OD matrix
Only needed if `hourly_od_<City>.xlsx` is missing or its inputs changed. It needs
the city's routing graph and a population raster. The WorldPop `*_ppp_2020.tif`
rasters are git-ignored — download each country's 2020 UN-adjusted 100 m raster
from https://hub.worldpop.org/ into `data/<city>/`.
```bash
cd od-matrix && python main.py && cd ..
```
For each city in `multi-config.json` this lays a regular square grid
(`cell_size`, default **3000 m**) over the boundary, snaps zones to network
nodes, and generates a synthetic hourly OD scaled to `total_trips`. Output:
`outputs/hourly_od_<City>.xlsx` with one sheet per hour (`hour_0`…`hour_23`),
each an origin×destination matrix indexed by zone ids `Z0…Zn-1`. **These zone ids
are the contract that ties the matrix to the SUMO TAZ** — keep `--cell-size`
consistent everywhere downstream.

> The three current cities already have their `hourly_od_<City>.xlsx` committed,
> so you can skip Stage 0.

### Step 1 — Download OSM & build the full network
Use SUMO's **OSMWebWizard** (browser-driven download + `netconvert` in one):
```bash
python "$SUMO_HOME/tools/osmWebWizard.py"
```
In the browser at `http://localhost:8010`:
- **Select Area** → pan to the city → drag the rectangle to **cover the whole
  admin boundary + a small margin** (Step 2 clips it to the exact boundary).
- **Network:** tick **Car-only Network** (keeps car-drivable roads only).
- **Demand:** **untick every mode** — we build demand from the OD matrix.
- **Generate Scenario** → writes a timestamped folder (e.g. `2026-06-29-12-26-42/`)
  containing `osm.net.xml.gz`.

Promote the wizard network into the city folder (replace `<TS>`):
```bash
netconvert -s "<TS>/osm.net.xml.gz" -o data/<city>/net/<city>_full.net.xml
```
> **Scripted alternative (no browser):** download a regional extract from
> [Geofabrik](https://download.geofabrik.de/) (e.g. *slovakia*, *ukraine*) into
> `data/<city>/raw/`, then
> `netconvert --osm-files <file>.osm.pbf --geometry.remove --junctions.join --keep-edges.by-vclass passenger --remove-edges.isolated -o data/<city>/net/<city>_full.net.xml`.

### Step 2 — Crop the network to the city boundary
```bash
python data/scripts/crop_net_to_boundary.py \
  --net-file data/<city>/net/<city>_full.net.xml \
  --geojson-file od-matrix/data/city_boundaries/<City>/<City>-v1.geojson \
  --output data/<city>/net/keep_edges.txt

netconvert -s data/<city>/net/<city>_full.net.xml \
  --keep-edges.input-file data/<city>/net/keep_edges.txt \
  --keep-edges.components 1 \
  -o data/<city>/net/<city>.net.xml
```
`--keep-edges.components 1` drops disconnected fragments so the network stays
routable. **Result:** `data/<city>/net/<city>.net.xml` — the network the
simulation uses. The crop script also prints a ready-to-paste `netconvert`
command with the correct per-city output name.

### Step 3 — Build the zone polygons
Rebuild **the same grid** the OD pipeline used (must match `--cell-size`), then
convert it to SUMO polygons in the network's coordinate system:
```bash
python data/scripts/build_grid_taz_zones.py \
  --city-shp od-matrix/data/city_boundaries/<City>/<City>-v1.geojson \
  --cell-size 3000 \
  --output data/<city>/zones/<city>_grid_zones.geojson

python data/scripts/geojson_to_sumo_poly.py \
  --net-file data/<city>/net/<city>.net.xml \
  --geojson-file data/<city>/zones/<city>_grid_zones.geojson \
  --id-column zone_id \
  --output data/<city>/zones/<city>_zones.poly.xml
```
The zone count printed by `build_grid_taz_zones.py` **must match** the number of
zones (`Z0…Zn-1`) in `hourly_od_<City>.xlsx`.

### Step 4 — Build the TAZ (map each zone to its edges)
`od2trips` needs to know which edges belong to each zone. `edgesInDistricts.py`
(a SUMO tool) assigns each edge to the zone polygon that contains it:
```bash
python "$SUMO_HOME/tools/edgesInDistricts.py" \
  -n data/<city>/net/<city>.net.xml \
  -t data/<city>/zones/<city>_zones.poly.xml \
  --merge-separator _ \
  -o data/<city>/taz/<city>.taz.xml
```
Zones left with no edges (e.g. fringe cells removed during cropping) simply won't
appear — the next step drops trips referencing them.

### Step 5 — Convert the OD matrix to trips
Turn each `hour_*` sheet into a VISUM **O-format** `.od` file (passing the TAZ so
relations referencing edge-less zones are dropped), then expand to trips:
```bash
python data/scripts/od_xlsx_to_od2trips.py \
  --xlsx od-matrix/outputs/hourly_od_<City>.xlsx \
  --out-dir data/<city>/od --prefix <city> \
  --taz-file data/<city>/taz/<city>.taz.xml

ods=$(ls data/<city>/od/<city>_hour_*.od | paste -sd, -)
od2trips -n data/<city>/taz/<city>.taz.xml -d "$ods" \
  -o data/<city>/routes/<city>.odtrips.xml --ignore-errors
```
Each `.od` carries its own one-hour time window, so the 24 files together span a
full day. **Result:** `data/<city>/routes/<city>.odtrips.xml` (trips by
origin/destination TAZ, not yet routed).

### Step 6 — Route the trips
`duarouter` computes the actual edge path each vehicle drives:
```bash
duarouter -n data/<city>/net/<city>.net.xml \
  --route-files data/<city>/routes/<city>.odtrips.xml \
  -o data/<city>/routes/<city>.rou.xml --ignore-errors
```
**Result:** `data/<city>/routes/<city>.rou.xml` — the routed vehicles SUMO
simulates (`duarouter` also writes `<city>.rou.alt.xml` with alternatives).

### Step 7 — The SUMO config
Each city has a `data/<city>/<city>.sumocfg` wiring the three pieces together,
with paths **relative to its own folder**:
```xml
<input>
    <net-file value="net/<city>.net.xml"/>
    <route-files value="routes/<city>.rou.xml"/>
    <additional-files value="zones/<city>_zones.poly.xml"/>
</input>
```
To create one for a new city, copy an existing `.sumocfg` and swap the prefix.

---

## 4. Running the simulation

**GUI** (from the repo root; SUMO resolves the relative paths against the config's
folder):
```bash
sumo-gui -c data/<city>/<city>.sumocfg
```
Press the green ▶ to start. The red polygons are the OD zones.

**Headless:**
```bash
sumo -c data/<city>/<city>.sumocfg
```

### Scenario variants

Each city ships three configs:

| Config | What it is |
|---|---|
| `<city>.sumocfg` | full 24 h day, network as imported from OSM (actuated TLS) |
| `<city>_static.sumocfg` | same day on the fixed-time-TLS network variant |
| `<city>_peak.sumocfg` | morning peak **06:00–11:00** (`begin` 21600 s, `end` 39600 s) with peak-only routes and dynamic rerouting; a `<scale>` factor in `<processing>` sets the demand level |

- The **static** network (`net/<city>_static.net.xml`) and config are generated
  from the normal ones with
  `python data/scripts/tls_actuated_to_static.py` (all cities at once).
- The **peak** routes (`routes/<city>_peak.rou.xml`) are built exactly like
  Steps 5–6 but feeding only the peak-hour matrices
  (`<city>_hour_6.od … <city>_hour_10.od`) to `od2trips`.

### Reading the results

After any run, print a clear summary of its outputs (steps, peak vehicles,
arrived/unfinished, teleports, VKT, VHT, mean speed, mean trip, delay, waiting):
```bash
python data/scripts/sim_outputs.py data/<city>/<city>_peak.sumocfg   # paths from the config
python data/scripts/sim_outputs.py data/<city>/sim/<run_prefix>      # or a run prefix
```
It only reads the `tripinfo` / `stats` / `summary` XML files a finished run has
written — it never starts SUMO itself.

---

## 5. Git-ignored files

Large or generated artefacts are **not** committed (see `.gitignore`); regenerate
them locally with the steps above:

- `data/*/net/*.net.xml` — the full and cropped networks (Steps 1–2)
- `data/*/raw/*.osm.pbf`, `*.osm.xml` — raw OSM extracts
- `data/*/routes/*.odtrips.xml`, `*.rou.xml`, `*.rou.alt.xml` — trips and routed vehicles (Steps 5–6)
- `data/*/sim/*.xml` — simulation outputs (tripinfo)
- `data/*/*_ppp_2020.tif` — WorldPop population rasters
- `.DS_Store`, `Thumbs.db`, `__pycache__/`, `*.pyc` — OS/Python junk

The committed inputs (`*.od`, `*.taz.xml`, `*.poly.xml`, `keep_edges.txt`,
`*_grid_zones.geojson`, `*.sumocfg`) let you skip the OD estimation and zone
building: regenerate the network (Steps 1–2), then the trips and routes
(Steps 5–6), and run.
