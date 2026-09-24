"""Colours, line weights and feature classes shared by every map."""
from __future__ import annotations

# ---------------------------------------------------------------- palettes

STYLES: dict[str, dict] = {
    # Purpose-built for black-and-white laser printing.
    "bw": dict(
        water="#e8e8e8", land="#ffffff", beach="#f4f4f4",
        residential="#fbfbfb", grass="#f6f6f6", school="#f2f2f2", industrial="#f2f2f2",
        building="#e6e6e6", building_edge="#c4c4c4", building_lw=0.15,
        road_main="#f0f0f0", road_main_edge="#3d3d3d",
        road_sec="#f7f7f7", road_sec_edge="#6a6a6a",
        road_minor="#ffffff", road_minor_edge="#9c9c9c",
        track="#b4b4b4",
        hh_marker="#000000", hh_text="#000000", hh_text_neighbour="#5a5a5a",
        ea_line="#000000", ea_other="#555555",
        landmark="#000000", landmark_text="#000000",
        fade=0.0,
    ),
    # Faded OpenStreetMap-standard lookalike (colour), like a transparent
    # OSM basemap in QGIS.
    "osm": dict(
        water="#cfe3ef", land="#f4f2ef", beach="#f5efd0",
        residential="#eeeae6", grass="#e4eed7", school="#f5f0dc", industrial="#ece5e3",
        building="#ded5d0", building_edge="none", building_lw=0.0,
        road_main="#f0a882", road_main_edge="#d98f6b",
        road_sec="#fbf3d6", road_sec_edge="#d8cfa8",
        road_minor="#ffffff", road_minor_edge="#cfcac4",
        track="#c9b79f",
        hh_marker="#000000", hh_text="#000000", hh_text_neighbour="#5a5a5a",
        ea_line="#000000", ea_other="#3c3c3c",
        landmark="#b58900", landmark_text="#4a3800",
        fade=0.42,
    ),
}

# ---------------------------------------------------------------- basemap classes

LANDUSE_FILL = {   # OSM landuse value -> palette key
    "residential": "residential", "grass": "grass", "meadow": "grass",
    "orchard": "grass", "farmland": "grass", "farmyard": "grass",
    "cemetery": "grass", "industrial": "industrial", "retail": "industrial",
    "school": "school", "religious": "school",
}

ROAD_CLASS = {     # OSM highway value -> drawing class
    "motorway": "main", "trunk": "main", "primary": "main",
    "secondary": "sec", "tertiary": "sec",
    "unclassified": "minor", "residential": "minor", "service": "minor",
    "living_street": "minor", "road": "minor",
    "track": "track", "path": "track", "footway": "track", "pedestrian": "track",
}
ROAD_ORDER = ("track", "minor", "sec", "main")          # drawn bottom to top
ROAD_WIDTH_M = {"main": 3.6, "sec": 2.4, "minor": 1.5, "track": 0.8}
ROAD_MIN_MM = {"main": 1.9, "sec": 1.25, "minor": 0.7, "track": 0.35}
ROAD_FILL_KEY = {"main": "road_main", "sec": "road_sec", "minor": "road_minor", "track": "track"}
ROAD_EDGE_KEY = {"main": "road_main_edge", "sec": "road_sec_edge",
                 "minor": "road_minor_edge", "track": "track"}
