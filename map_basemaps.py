"""Shared authenticated CARTO tiles for inventory, raster and FVS maps."""

import json
import os
from pathlib import Path
from urllib.parse import urlencode


def carto_basemap(style="light_all"):
    """Read a deployment environment key or this project's ignored local config."""
    key = os.environ.get("CARTO_API_KEY", "").strip()
    if not key:
        config = Path(__file__).resolve().parent / "storage" / "carto_config.json"
        if config.exists():
            key = str(json.loads(config.read_text())["CARTO_API_KEY"]).strip()
    if not key:
        return {"tiles": "OpenStreetMap", "attr": None}
    if style not in {"light_all", "dark_all"}:
        raise ValueError("Unsupported CARTO style")
    return {
        "tiles": "https://basemaps.cartocdn.com/" + style
        + "/{z}/{x}/{y}.png?" + urlencode({"key": key}),
        "attr": '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
        '&copy; <a href="https://carto.com/attributions">CARTO</a>',
    }
