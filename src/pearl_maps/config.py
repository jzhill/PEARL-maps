"""Load config.yaml and resolve every path the pipeline touches."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config.yaml"


@dataclass(frozen=True)
class Paths:
    root: Path
    raw: Path
    processed: Path
    outputs: Path
    status: Path

    # ---- raw inputs -------------------------------------------------------
    def raw_input(self, cfg: "Config", key: str) -> Path:
        return self.raw / cfg.inputs[key]

    # ---- processed (written by 01_prepare / 02_plan) ----------------------
    @property
    def eas(self) -> Path:
        return self.processed / "eas.geojson"

    @property
    def households(self) -> Path:
        return self.processed / "households.csv"

    @property
    def qa_report(self) -> Path:
        return self.processed / "qa_report.md"

    @property
    def qa_issues(self) -> Path:
        return self.processed / "qa_issues.csv"

    @property
    def plan(self) -> Path:
        return self.processed / "plan.csv"

    # ---- outputs ----------------------------------------------------------
    @property
    def ea_maps(self) -> Path:
        return self.outputs / "ea_maps"

    @property
    def village_maps(self) -> Path:
        return self.outputs / "village_maps"


@dataclass(frozen=True)
class Config:
    paths: Paths
    inputs: dict
    sources: dict
    scope: dict
    households: dict
    ea_map: dict
    village_map: dict


def load_config(path: Path | str | None = None) -> Config:
    path = Path(path) if path else DEFAULT_CONFIG
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    root = path.resolve().parent
    p = raw["paths"]
    paths = Paths(
        root=root,
        raw=(root / p["raw"]).resolve(),
        processed=(root / p["processed"]).resolve(),
        outputs=(root / p["outputs"]).resolve(),
        status=(root / p["status"]).resolve(),
    )
    return Config(
        paths=paths,
        inputs=raw["inputs"],
        sources=raw["sources"],
        scope=raw["scope"],
        households=raw["households"],
        ea_map=raw["ea_map"],
        village_map=raw["village_map"],
    )


def date_stamp(d: date | None = None) -> str:
    """yymmdd, matching the existing map file names."""
    return (d or date.today()).strftime("%y%m%d")


def village_slug(village: str) -> str:
    return village.strip().lower().replace(" ", "_")
