# data/raw

Copy the source files here by hand. Everything in this folder except
this README is gitignored — the household listing contains personal names and
must never be committed.

| config key (`config.yaml` → `inputs`) | current file | what it is |
|---|---|---|
| `ea_boundaries` | `KIR_EA_Census2020FINAL.geojson` | 2020 census enumeration-area polygons for Kiribati (CRS84). Uses `ea_2020`, `vid_name`, `iid_name`. |
| `households` | `hhlisting23_pearl_request_2025_08.csv` | PEARL household listing. Uses `interview__key`, `eaid_corr`, `head_string`, `dwell_type`, `occupancy`, `x_final`, `y_final`, `vid_name`. |
| `osm` | `kiribati_curated_osm_sprep.gpkg` | Curated OpenStreetMap extract (SPREP). Uses layers `land`, `natural`, `landuse`, `buildings`, `highway_ln`. |
| `landmarks` | `landmarks.csv` | Curated orientation landmarks (names, categories, coordinates, confidence). Edited by hand; see "Landmarks" in the main README. |

Keep the master copies of these files in a backed-up location outside this
repository.

When a new household extract arrives, copy it here, update
`inputs.households` (and `sources.households`, which is printed on every
map) in `config.yaml`, then rerun `scripts/01_prepare.py` and read
`data/processed/qa_report.md`.
