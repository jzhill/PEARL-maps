# PEARL-maps

Systematically creating EA household maps for the PEARL enumeration teams in
South Tarawa, Kiribati.

The pipeline produces two printable products, both A4 and designed for
black-and-white laser printing:

- **EA enumeration maps** — one enumeration area per page with every occupied
  household marked and its head's name printed, legibly and without overlap.
  Teams use these with the household list printed from REDCap to find each
  household on the ground.
- **Village orientation sheets** — one sheet per village showing every EA
  boundary and number over roads, landmarks and household density, so teams
  can see how the EAs fit together.

Everything is drawn from three local files (no web tiles, no GIS software):
the 2020 census EA boundaries, the PEARL household listing, and a curated
OpenStreetMap GeoPackage.

---

## Quick start

Requires [uv](https://docs.astral.sh/uv/) (it installs the right Python for you).

```powershell
uv sync                                        # create .venv and install

# copy the three source files into data/raw/  (see data/raw/README.md)

uv run python scripts/01_prepare.py            # clean inputs, write QA report
uv run python scripts/02_plan.py --village Temaiku
uv run python scripts/03_render_ea_maps.py
uv run python scripts/04_render_village_maps.py
```

Maps land in `outputs/`. Check them, copy the ones you want into your field-map
folders, then record what was delivered:

```powershell
uv run python scripts/sync_status.py --maps-dir "<folder of delivered maps>"
```

---

## Pipeline

Each stage reads only what the previous stage wrote, so any stage can be
rerun on its own.

| stage | reads | writes |
|---|---|---|
| `01_prepare.py` | `data/raw/*` | `data/processed/eas.geojson`, `households.csv`, `landmarks.geojson`, `qa_report.md`, `qa_issues.csv` |
| `02_plan.py` | processed data, `config/ea_status.csv` | `data/processed/plan.csv` |
| `03_render_ea_maps.py` | processed data, plan, OSM GeoPackage | `outputs/ea_maps/<village>/*.pdf`, `_build_log.csv` |
| `04_render_village_maps.py` | processed data, plan, OSM GeoPackage | `outputs/village_maps/*.pdf`, `_build_log.csv` |
| `sync_status.py` (utility) | a folder of delivered map PDFs | `config/ea_status.csv` |

### 01 — prepare

Keeps the EAs in scope (South Tarawa plus Buota, see `scope` in
`config.yaml`), cleans household-head names for printing, and flags data
problems. **Read `data/processed/qa_report.md` after every new extract.** It
reports, by village:

| check | what the maps do about it |
|---|---|
| `ea_bad_geometry` | EA excluded from all maps |
| `ea_no_households` | EA cannot be mapped (e.g. Buota in the Aug 2025 extract) |
| `hh_unknown_ea` | household's EA id is not in the boundary file; not mapped |
| `hh_no_name` | placeholder name such as `##N/A##`; marker drawn, no label |
| `hh_outside_own_ea` | point falls outside its EA polygon; still mapped with its EA |

Only occupied private households are mapped (`households` in `config.yaml`).

### 02 — plan

Chooses what to render. With no options it plans every EA marked `pending`
in `config/ea_status.csv`, plus one orientation sheet per village involved.

```powershell
uv run python scripts/02_plan.py                                   # all pending EAs
uv run python scripts/02_plan.py --village Bonriki --village Tanaea
uv run python scripts/02_plan.py --village Bikenibeu --include-mapped   # redo a village
uv run python scripts/02_plan.py --ea 70502220 --ea 70502230            # specific EAs
uv run python scripts/02_plan.py --village Eita --village-sheets-only   # sheet only
```

Village names are as they appear in the census file, e.g. `Betio_East`,
`Ananau Causeway`.

### 03 — render EA maps

```powershell
uv run python scripts/03_render_ea_maps.py                  # everything in the plan
uv run python scripts/03_render_ea_maps.py --only 70502220  # one job
uv run python scripts/03_render_ea_maps.py --date 260920    # fix the file-name date
```

File names follow the existing convention:
`<ea_id>_enumeration_map_<yymmdd>.pdf`, with `a`, `b`, … suffixes when an EA
is split across pages. Every page gets a row in the village's
`_build_log.csv`; **`complete=0` means some names did not fit** and the
script exits with code 2.

### 04 — render village orientation sheets

```powershell
uv run python scripts/04_render_village_maps.py
uv run python scripts/04_render_village_maps.py --only Temaiku
```

### The status register

`config/ea_status.csv` is the single record of which EAs have maps. It is your
own working record, so it is in `.gitignore` and is not pushed. Start from
`config/ea_status.example.csv`, or run `sync_status.py`, which builds it:

```
ea_id,village,status,map_date,note
70502220,Bikenibeu,mapped,2026-09-20,
61401401,Buota,blocked,,no households in PEARL listing (Aug 2025 extract)
```

`status` is `pending`, `mapped` or `blocked`. Edit it by hand (for example to
block an EA or add a note), or let `sync_status.py` mark EAs `mapped` from the
PDFs in your delivery folders. Sync never downgrades a status and never
touches `blocked`.

---

## How the maps are made

These rules came out of matching the hand-made QGIS maps and field feedback.
They are implemented in `src/pearl_maps/ea_map.py` and tuned in `config.yaml`.

**EA enumeration maps**

- A4, portrait or landscape, whichever gives the larger scale. North-up is
  preferred; the page is rotated only when that lets every name print at the
  largest font. The north arrow always points to true north.
- The page is sized to the EA plus its households, with lagoon/ocean parts of
  the EA polygon ignored so offshore boundaries don't shrink the scale.
- Household markers (`+`) sit at their recorded position and never move.
- Every focus-EA name is printed. Names are placed without overlap and
  without leader lines, drifting away from their marker only as far as needed
  (`max_displacement_mm`). Focus-EA names stay inside the EA or over open
  water, never inside a neighbouring EA.
- Font steps down through `label_sizes_pt` (10 → 8 pt, Arial) until every
  name fits. If only a small font works, or nothing fits, the EA is split
  across pages along its long axis with a small overlap; a grey dash-dot line
  shows where the next page continues.
- Neighbouring households near the boundary are named one point smaller in
  grey, so teams can tell which side of the line a house is on. Neighbours
  further than `neighbour_halo_mm` from the boundary are shown as markers only.
- The EA boundary is heavy dashed; neighbouring boundaries lighter, each
  labelled with its EA number. Up to eight landmarks (schools, clinics,
  churches, maneabas, government offices and a few chosen businesses) are
  starred and named. They come
  from `data/raw/landmarks.csv`; see "Landmarks" below.

**Village orientation sheets**

- One A4 landscape sheet per village. Long atoll villages are cut into one to
  three stacked west-to-east panels, whichever gives the largest scale. A sheet
  is rotated only when that gives a larger scale, and never more than 90° from
  north-up (the north arrow always points to true north).
- EA numbers are printed inside each EA without the shared leading digits
  (the footer states the prefix), because full eight-digit numbers do not fit
  inside small EAs at village scale.
- A small locator map of South Tarawa and Buota sits in the bottom band, with a
  box around the ground the sheet covers (true north up; a very small village is
  drawn as a minimum-size box so it can still be seen).
- Households appear as dots for density only; no names.

---

## Landmarks

Both map types star and name the well-known orientation features listed in
`data/raw/landmarks.csv` (South Tarawa and Buota: schools, clinics and hospitals,
churches, maneabas, ministries and other government offices, and a hand-picked
short list of well-known private businesses). Edit that file by
hand, then rerun `01_prepare.py`; stage 01 checks it and stops with the line
numbers of any bad row. It also writes `data/processed/landmarks.geojson`,
which opens directly in QGIS.

| column | meaning |
|---|---|
| `landmark_id`, `name`, `alt_name` | identifier, full name, other names in use |
| `label` | short text printed on the maps (e.g. `MFED`); falls back to `name` if blank |
| `category` | `school`, `health`, `church`, `maneaba`, `gov`, `business` or `community` |
| `lon`, `lat` | WGS 84 decimal degrees |
| `confidence` | `high`, `medium` or `check` |
| `village`, `subtype`, `code`, `source`, `source_id`, `notes` | provenance, for reference only |

`landmarks.min_confidence` in `config.yaml` sets which rows may print (default
`medium`, so `check` rows stay off the maps), and `landmarks.priority` sets which
categories win when a page has more landmarks than it can label. A landmark whose
point lies in the lagoon or ocean is moved onto the nearest land by stage 01 (a
few metres in from the shore) if it is within `landmarks.snap_to_land_m`; stage 01
reports each one, and `landmarks.csv` itself is left as you wrote it. Names longer
than 42 characters (40 on village sheets) are skipped, so give long names a
short `label`.

---

## Repository layout

```
config.yaml                 all settings: input file names, scope, map rules
config/ea_status.csv        which EAs are mapped / pending / blocked (local, gitignored)
config/ea_status.example.csv  a template for that file (tracked)
data/raw/                   source files, copied in by hand (gitignored)
data/processed/             written by stages 01-02 (gitignored)
outputs/                    rendered PDFs and build logs (gitignored)
scripts/                    the pipeline stages, run in order
src/pearl_maps/
    config.py               config loading and path resolution
    data.py                 raw loading, name cleaning, processed datasets
    qa.py                   data-quality checks and report
    plan.py                 status register, render plan, file-name parsing
    gpkg.py                 GeoPackage reader (SQLite + R-tree; no GDAL)
    geometry.py             local projection, page transform, splitting
    layout.py               page sizes, orientation and rotation choice
    labels.py               fonts, text metrics, label placement
    landmarks.py            landmark record and per-page selection
    style.py                colours and road classes
    draw.py                 basemap and map furniture
    ea_map.py               EA enumeration maps
    village_map.py          village orientation sheets
tests/                      unit tests (no data needed): uv run pytest
```

## Data protection

The household listing and every map contain household-head names. `data/`
and `outputs/` are gitignored; keep it that way, and do not commit PDFs, CSV
extracts or screenshots of maps.

## Development

```powershell
uv run pytest                      # unit tests
uv run python scripts/03_render_ea_maps.py --only 70502220 --verbose
```

`pypdfium2` (dev dependency) can rasterise a PDF for a quick visual check:

```python
import pypdfium2 as pdfium
pdfium.PdfDocument("outputs/ea_maps/bikenibeu/70502220_enumeration_map_260920.pdf")[0] \
    .render(scale=2).to_pil().save("check.png")
```
