from __future__ import annotations

from pathlib import Path

import yaml

from app.models import SourceConfig

# Project root is three levels up from this file (src/app/config.py -> project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"
SITE_DIR = PROJECT_ROOT / "site"


def load_sources(config_path: Path | None = None) -> list[SourceConfig]:
    """Load and validate all sources from sources.yml."""
    if config_path is None:
        config_path = CONFIG_DIR / "sources.yml"
    raw = yaml.safe_load(config_path.read_text())
    return [SourceConfig(**s) for s in raw["sources"]]


def get_enabled_sources(config_path: Path | None = None) -> list[SourceConfig]:
    """Load only enabled sources."""
    return [s for s in load_sources(config_path) if s.enabled]


def get_source_by_id(source_id: str, config_path: Path | None = None) -> SourceConfig:
    """Look up a single source by ID. Raises KeyError if not found."""
    for s in load_sources(config_path):
        if s.id == source_id:
            return s
    available = [s.id for s in load_sources(config_path)]
    raise KeyError(f"Source '{source_id}' not found. Available: {available}")
