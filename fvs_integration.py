"""FVS stand-result querying and spatial visualization for Canopy.

The FVS CSV is the queryable attribute table, MU_ID identifies stand polygons in
the accompanying shapefile, and TM_Value links records to TreeMap raster cells.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import folium
import numpy as np
import pandas as pd
from PIL import Image


FVS_NUMERIC_FIELDS = {
    "Age": ["age", "stand age"],
    "Acres": ["acres", "acreage", "area"],
    "TCuFt": ["tcuft", "cubic feet", "cubic foot", "cubic volume", "volume"],
    "Tpa": ["tpa", "trees per acre"],
    "BA": ["basal area", " ba"],
    "SDI": ["sdi", "stand density index"],
    "RDSDI": ["rdsdi", "relative density"],
    "CCF": ["ccf", "crown competition"],
    "TopHt": ["top height", "topht", "height"],
    "QMD": ["qmd", "quadratic mean diameter"],
    "GMD": ["gmd", "geometric mean diameter"],
    "MAI": ["mai", "mean annual increment"],
    "Mort": ["mortality", "mort"],
    "BdFt": ["board feet", "bdft"],
}

DISPLAY_COLUMNS = [
    "MU_ID",
    "Age",
    "Age_class",
    "Acres",
    "COMPOSITIO",
    "TCuFt",
    "Tpa",
    "BA",
    "SDI",
    "TopHt",
    "OWN_TYPE",
    "TM_Value",
]


def discover_fvs_csvs(data_dir: Path) -> List[Path]:
    """Return FVS CSVs that have a complete shapefile geometry pair."""
    fvs_dir = data_dir / "fvs"
    if not fvs_dir.exists():
        return []
    return sorted(
        csv_path
        for csv_path in fvs_dir.glob("*.csv")
        if not csv_path.name.startswith("._")
        and csv_path.with_suffix(".shp").exists()
        and csv_path.with_suffix(".shx").exists()
        and csv_path.with_suffix(".dbf").exists()
    )


def fvs_bundle_paths(csv_path: Path) -> Dict[str, Path]:
    paths = {"csv": csv_path}
    for suffix, label in [
        (".shp", "shapefile"),
        (".shx", "shape_index"),
        (".dbf", "shape_attributes"),
        (".prj", "projection"),
        (".cpg", "encoding"),
        (".shp.xml", "metadata"),
    ]:
        candidate = csv_path.with_suffix(suffix)
        if candidate.exists():
            paths[label] = candidate
    return paths


def blank_fvs_spec() -> Dict[str, Any]:
    return {
        "filters": [],
        "intent": "summary",
        "chart_group": None,
        "make_map": False,
        "make_raster": False,
        "limit": 200,
    }


def _number_after(text: str, phrases: Sequence[str]) -> Optional[Tuple[str, float]]:
    joined = "|".join(re.escape(phrase) for phrase in phrases)
    patterns = [
        ("gt", rf"(?:{joined})\s+(?:is\s+)?(?:greater than|more than|over|above|older than)\s+([0-9]+(?:\.[0-9]+)?)"),
        ("lt", rf"(?:{joined})\s+(?:is\s+)?(?:less than|under|below|younger than)\s+([0-9]+(?:\.[0-9]+)?)"),
        ("gte", rf"(?:minimum|min)\s+(?:{joined})\s+(?:of\s+)?([0-9]+(?:\.[0-9]+)?)"),
        ("lte", rf"(?:maximum|max)\s+(?:{joined})\s+(?:of\s+)?([0-9]+(?:\.[0-9]+)?)"),
    ]
    for operator, pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return operator, float(match.group(1))
    return None


def parse_fvs_question(question: str) -> Dict[str, Any]:
    """Translate common forestry wording into a safe, structured SQL query spec."""
    spec = blank_fvs_spec()
    lowered = " " + re.sub(r"\s+", " ", question.lower()).strip() + " "

    if any(term in lowered for term in ["map", "where are", "show stands", "stand locations"]):
        spec["make_map"] = True
        spec["intent"] = "map"
    if any(term in lowered for term in ["raster", "treemap", "pixel", "tif", "geotiff"]):
        spec["make_raster"] = True
        spec["make_map"] = True
        spec["intent"] = "raster"
    if any(term in lowered for term in ["chart", "graph", "distribution", "histogram"]):
        spec["intent"] = "chart"
        if "age class" in lowered:
            spec["chart_group"] = "Age_class"
        elif any(term in lowered for term in ["composition", "species", "forest type"]):
            spec["chart_group"] = "COMPOSITIO"
        elif "ownership" in lowered or "owner" in lowered:
            spec["chart_group"] = "OWN_TYPE"
        else:
            spec["chart_group"] = "Age"
    elif any(term in lowered for term in ["how many", "count of", "number of stands"]):
        spec["intent"] = "count"
    elif any(term in lowered for term in ["list", "table", "which stands"]):
        spec["intent"] = "list"

    categories = [
        ("COMPOSITIO", "Coniferous", ["conifer", "softwood"]),
        ("COMPOSITIO", "Deciduous", ["deciduous", "hardwood"]),
        ("COMPOSITIO", "Mixed", ["mixed"]),
        ("Age_class", "Young", ["young"]),
        ("Age_class", "Intermediate", ["intermediate"]),
        ("Age_class", "Mature", ["mature"]),
        ("Age_class", "Old", ["old"]),
    ]
    for column, value, terms in categories:
        if any(re.search(rf"\b{re.escape(term)}\w*\b", lowered) for term in terms):
            spec["filters"].append({"column": column, "operator": "eq", "value": value})

    mu_match = re.search(r"\bmu[_\s-]*id\s*(?:is|=|number)?\s*([0-9]+)\b", lowered)
    if mu_match:
        spec["filters"].append({"column": "MU_ID", "operator": "eq", "value": int(mu_match.group(1))})

    # Age wording is commonly adjective-first ("older than 60"), so handle it explicitly.
    for operator, pattern in [
        ("gt", r"\b(?:stands?\s+)?older than\s+([0-9]+(?:\.[0-9]+)?)"),
        ("lt", r"\b(?:stands?\s+)?younger than\s+([0-9]+(?:\.[0-9]+)?)"),
        ("gte", r"\bage\s*(?:>=|at least)\s*([0-9]+(?:\.[0-9]+)?)"),
        ("lte", r"\bage\s*(?:<=|at most)\s*([0-9]+(?:\.[0-9]+)?)"),
    ]:
        match = re.search(pattern, lowered)
        if match:
            spec["filters"].append({"column": "Age", "operator": operator, "value": float(match.group(1))})
            if operator == "gt" and "older than" in lowered:
                spec["filters"] = [
                    item for item in spec["filters"]
                    if not (item["column"] == "Age_class" and item["value"] == "Old")
                ]
            break

    existing_columns = {item["column"] for item in spec["filters"]}
    for column, aliases in FVS_NUMERIC_FIELDS.items():
        if column in existing_columns:
            continue
        comparison = _number_after(lowered, aliases)
        if comparison:
            operator, value = comparison
            spec["filters"].append({"column": column, "operator": operator, "value": value})

    limit_match = re.search(r"\b(?:top|first|limit)\s+([0-9]{1,4})\b", lowered)
    if limit_match:
        spec["limit"] = max(1, min(int(limit_match.group(1)), 1000))
    return spec


def build_fvs_sql(table_name: str, spec: Dict[str, Any]) -> Tuple[str, List[Any]]:
    allowed_columns = set(DISPLAY_COLUMNS) | set(FVS_NUMERIC_FIELDS) | {
        "COMPOSITIO", "Age_class", "OWN_TYPE", "Map_class", "MU_ID", "TM_Value"
    }
    operator_sql = {"eq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    where_parts: List[str] = []
    params: List[Any] = []
    for item in spec.get("filters", []):
        column = str(item.get("column", ""))
        operator = str(item.get("operator", ""))
        if column not in allowed_columns or operator not in operator_sql:
            continue
        where_parts.append(f'"{column}" {operator_sql[operator]} ?')
        params.append(item.get("value"))

    sql = f'SELECT * FROM "{table_name}"'
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)
    sql += ' ORDER BY "MU_ID"'
    return sql, params


def execute_fvs_sql(database_path: Path, table_name: str, spec: Dict[str, Any]) -> Tuple[pd.DataFrame, str, List[Any]]:
    sql, params = build_fvs_sql(table_name, spec)
    with sqlite3.connect(database_path) as conn:
        result = pd.read_sql_query(sql, conn, params=params)
    if "__rowid" in result.columns:
        result = result.drop(columns=["__rowid"])
    return result, sql, params


def format_fvs_filters(spec: Dict[str, Any]) -> str:
    symbols = {"eq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    filters = spec.get("filters", [])
    if not filters:
        return "all stands"
    return ", ".join(
        f"{item['column']} {symbols.get(item['operator'], item['operator'])} {item['value']}"
        for item in filters
    )


def summarize_fvs_result(result: pd.DataFrame, spec: Dict[str, Any]) -> str:
    if result.empty:
        return f"No FVS stands matched {format_fvs_filters(spec)}."
    acres = float(pd.to_numeric(result["Acres"], errors="coerce").sum())
    mean_age = float(pd.to_numeric(result["Age"], errors="coerce").mean())
    weighted_volume = float(
        (pd.to_numeric(result["TCuFt"], errors="coerce") * pd.to_numeric(result["Acres"], errors="coerce")).sum()
    )
    return (
        f"Found {len(result):,} stands covering {acres:,.1f} acres. "
        f"Their mean age is {mean_age:,.1f} years and their estimated total cubic-foot volume "
        f"(`TCuFt × Acres`) is {weighted_volume:,.0f}."
    )


def build_fvs_chart(result: pd.DataFrame, group_column: str) -> pd.DataFrame:
    if result.empty or group_column not in result.columns:
        return pd.DataFrame()
    chart = (
        result.assign(Acres=pd.to_numeric(result["Acres"], errors="coerce"))
        .groupby(group_column, dropna=False, as_index=False)["Acres"]
        .sum()
        .rename(columns={"Acres": "Sum of Acres"})
    )
    if group_column == "Age":
        chart = chart.sort_values(group_column)
    else:
        chart = chart.sort_values("Sum of Acres", ascending=False)
    return chart


def _transform_nested_coordinates(value: Any, transformer: Any) -> Any:
    if not value:
        return value
    first = value[0]
    if isinstance(first, (int, float)):
        lon, lat = transformer.transform(float(value[0]), float(value[1]))
        return [lon, lat]
    return [_transform_nested_coordinates(item, transformer) for item in value]


def selected_stand_geojson(shapefile_path: Path, mu_ids: Iterable[int], maximum: int = 500) -> Dict[str, Any]:
    """Read only selected stand polygons and transform EPSG:5070 to WGS84."""
    import shapefile
    from pyproj import Transformer

    selected = {int(value) for value in list(mu_ids)[:maximum]}
    if not selected:
        return {"type": "FeatureCollection", "features": []}
    transformer = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    reader = shapefile.Reader(str(shapefile_path))
    field_names = [field[0] for field in reader.fields[1:]]
    mu_index = field_names.index("MU_ID")
    features = []
    for shape_record in reader.iterShapeRecords():
        mu_id = int(shape_record.record[mu_index])
        if mu_id not in selected:
            continue
        geometry = shape_record.shape.__geo_interface__
        geometry = {
            "type": geometry["type"],
            "coordinates": _transform_nested_coordinates(geometry["coordinates"], transformer),
        }
        attributes = dict(zip(field_names, shape_record.record))
        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "MU_ID": mu_id,
                "Age": attributes.get("Age"),
                "Acres": attributes.get("Acres"),
                "Composition": attributes.get("COMPOSITIO"),
                "TCuFt": attributes.get("TCuFt"),
                "TM_Value": attributes.get("TM_Value"),
            },
        })
        if len(features) >= maximum:
            break
    reader.close()
    return {"type": "FeatureCollection", "features": features}


@lru_cache(maxsize=24)
def make_selected_raster_overlay(
    raster_path_text: str,
    modified_time: float,
    selected_values: Tuple[int, ...],
    max_edge: int = 1400,
) -> Dict[str, Any]:
    """Make a transparent WGS84 PNG that highlights selected TreeMap IDs."""
    del modified_time
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import calculate_default_transform, reproject, transform_bounds

    if not selected_values:
        return {}
    selected_array = np.asarray(selected_values, dtype=np.int64)
    with rasterio.open(raster_path_text) as src:
        scale = min(1.0, max_edge / max(src.width, src.height))
        source_width = max(1, int(src.width * scale))
        source_height = max(1, int(src.height * scale))
        values = src.read(
            1,
            out_shape=(source_height, source_width),
            resampling=Resampling.nearest,
            masked=False,
        )
        source_transform = src.transform * src.transform.scale(
            src.width / source_width,
            src.height / source_height,
        )
        selected_mask = np.isin(values, selected_array).astype("uint8")
        if not selected_mask.any():
            return {}

        transform, projected_width, projected_height = calculate_default_transform(
            src.crs, "EPSG:4326", source_width, source_height, *src.bounds
        )
        destination = np.zeros((projected_height, projected_width), dtype="uint8")
        reproject(
            source=selected_mask,
            destination=destination,
            src_transform=source_transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs="EPSG:4326",
            src_nodata=0,
            dst_nodata=0,
            resampling=Resampling.nearest,
        )
        west, south, east, north = transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)

    rgba = np.zeros((*destination.shape, 4), dtype=np.uint8)
    rgba[..., 0] = 29
    rgba[..., 1] = 122
    rgba[..., 2] = 75
    rgba[..., 3] = np.where(destination == 1, 210, 0).astype(np.uint8)
    image_buffer = BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(image_buffer, format="PNG")
    encoded = base64.b64encode(image_buffer.getvalue()).decode("ascii")
    return {
        "data_url": f"data:image/png;base64,{encoded}",
        "bounds": [[south, west], [north, east]],
    }


def make_fvs_map(
    geojson: Dict[str, Any],
    raster_overlay: Optional[Dict[str, Any]] = None,
) -> Optional[folium.Map]:
    features = geojson.get("features", [])
    if not features and not raster_overlay:
        return None
    map_object = folium.Map(location=[30.25, -82.7], zoom_start=9, tiles="CartoDB positron")
    if raster_overlay:
        folium.raster_layers.ImageOverlay(
            image=raster_overlay["data_url"],
            bounds=raster_overlay["bounds"],
            name="Matching TreeMap raster cells",
            opacity=0.82,
            zindex=2,
        ).add_to(map_object)
    if features:
        layer = folium.GeoJson(
            geojson,
            name="Matching FVS stands",
            style_function=lambda _: {
                "color": "#173f2b",
                "weight": 1.2,
                "fillColor": "#76ad5b",
                "fillOpacity": 0.34,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["MU_ID", "Age", "Acres", "Composition", "TCuFt", "TM_Value"],
                aliases=["Stand", "Age", "Acres", "Composition", "TCuFt/acre", "TreeMap value"],
                localize=True,
            ),
        )
        layer.add_to(map_object)
        bounds = layer.get_bounds()
        if bounds and bounds[0] != bounds[1]:
            map_object.fit_bounds(bounds)
    folium.LayerControl(collapsed=False).add_to(map_object)
    return map_object
