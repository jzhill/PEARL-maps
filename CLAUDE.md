# CLAUDE.md

Guidance for Claude Code working in this repository. Read README.md first.

## What this is

A four-stage pipeline that renders printable A4 maps for household
enumeration teams in South Tarawa, Kiribati. The maps are used in the field,
in black and white, alongside a household list printed from REDCap.
Legibility and completeness of household-head names matter more than looks.

## Commands

```
uv sync
uv run pytest
uv run python scripts/01_prepare.py
uv run python scripts/02_plan.py [--village NAME] [--ea ID] [--include-mapped]
uv run python scripts/03_render_ea_maps.py [--only ID] [--date yymmdd] [--verbose]
uv run python scripts/04_render_village_maps.py [--only VILLAGE]
uv run python scripts/sync_status.py --maps-dir PATH [--dry-run]
```

## Rules

- **Never commit data.** `data/raw`, `data/processed` and `outputs` contain
  household names. Do not add them to git, paste their contents into issues
  or commit messages, or create test fixtures from real names.
- **Stages communicate only through files.** 01 writes `data/processed`;
  02 writes `plan.csv`; 03/04 read those. Renderers never read the raw CSV
  or GeoJSON. Keep scripts thin: logic lives in `src/pearl_maps`.
- **Settings belong in `config.yaml`,** not as new constants in code, when a
  user might reasonably want to change them.
- **Map invariants** (agreed with the programme lead; do not change silently):
  - every focus-EA household with a usable name is labelled; a page that
    cannot do this is logged `complete=0`, never silently dropped
  - household markers are never moved; labels move, with no leader lines
  - focus-EA names never sit inside a neighbouring EA (open water is fine)
  - 10 pt Arial is the target; nothing below 8 pt; A4 only (no A3)
  - north-up unless rotating buys a larger font; arrow points to true north
  - split EAs use `a`, `b`, ... suffixes in the existing file-name convention
  - greyscale by default; output must read on a black-and-white laser printer
- Fonts: Arial on Windows, Liberation Sans on Linux (metric-identical), so
  layouts are reproducible across machines.

## Architecture

- `labels.py` — the label engine. Candidate boxes on expanding rings around
  each marker, greedy most-constrained-first seating, one-blocker repair.
  Everything is in page millimetres.
- `geometry.py` — `Proj` (local metres, optional rotation) and
  `PageTransform` (metres -> mm in a frame). All drawing goes lon/lat ->
  `PageTransform` -> mm.
- `layout.py` — picks page orientation and rotation for a target geometry.
- `ea_map.py` — `EAMapRenderer.render()` tries layouts, steps font sizes,
  then splits (`split_bands`) if needed. `_render_page()` draws one page.
- `village_map.py` — stacked strip panels for long villages.
- `landmarks.py` — landmark record and per-page selection. The list comes from
  `data/raw/landmarks.csv` (hand-edited) via stage 01 -> `landmarks.geojson`;
  the renderers never read the CSV or the OSM amenity layers for landmarks.
- `gpkg.py` — reads the OSM GeoPackage directly via SQLite R-tree queries.

## Checking your work

After changing anything that affects rendering, render a known hard case and
look at it (rasterise with pypdfium2 and view the PNG):

- `70502220` (Bikenibeu) — densest EA; fits at 10 pt only when rotated
- `70501800` (Bikenibeu) — thin coastal strip; splits into 2 pages
- `70502302` (Bikenibeu) — 1 km ribbon; splits into 4 pages
- village sheet `Bikenibeu` — two panels

Compare the `_build_log.csv` rows (font, rotation, scale, parts) before and
after your change.
