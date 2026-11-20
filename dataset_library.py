"""PANDA dataset library: built-in datasets plus uploads kept on persistent storage.

Built-in datasets ship with the app image (`data/`, `rasters/`) and are read-only.
Uploaded datasets are saved under `<PANDA_STORAGE_DIR>/library/` so they survive
redeploys when that folder is on a Railway volume (mounted at /app/storage):

    library/csv/<name>.csv
    library/fvs/<name>.csv + .shp/.shx/.dbf (+ .prj, .cpg, ...)   FVS stand results with polygons
    library/rasters/<name>.tif (+ .tfw, .aux.xml, .vat.dbf, ...)

The SQLite database (chats and query tables) lives next to it in
`<PANDA_STORAGE_DIR>/canopy.sqlite`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

CSV_EXTENSIONS = {".csv"}
RASTER_EXTENSIONS = {".tif", ".tiff", ".img", ".vrt", ".jp2"}
SHAPE_REQUIRED = (".shp", ".shx", ".dbf")
SHAPE_OPTIONAL = (".prj", ".cpg", ".sbn", ".sbx", ".shp.xml", ".csv.xml")
RASTER_COMPANIONS = (".tfw", ".tifw", ".aux.xml", ".vat.dbf", ".vat.cpg", ".xml", ".ovr", ".prj")
UPLOAD_TYPES = sorted({ext.lstrip(".") for ext in CSV_EXTENSIONS | RASTER_EXTENSIONS}
                      | {"shp", "shx", "dbf", "prj", "cpg", "sbn", "sbx", "xml", "tfw", "ovr"})
MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # matches Streamlit's default server.maxUploadSize


def storage_dir() -> Path:
    return Path(os.environ.get("PANDA_STORAGE_DIR", "storage"))


def library_dir() -> Path:
    return storage_dir() / "library"


def storage_status() -> Dict[str, object]:
    """Where PANDA keeps chats/uploads and whether that location survives redeploys.

    Railway sets RAILWAY_VOLUME_MOUNT_PATH when a volume is attached. Outside
    Railway, a storage folder on a different device than the app is also treated
    as a mounted volume.
    """
    root = storage_dir().resolve()
    mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
    on_railway = any(os.environ.get(k) for k in ("RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_PROJECT_ID"))
    persistent: Optional[bool]
    if mount:
        try:
            persistent = root == Path(mount).resolve() or Path(mount).resolve() in root.parents
        except OSError:
            persistent = False
    elif on_railway:
        persistent = False
    else:
        try:
            root.mkdir(parents=True, exist_ok=True)
            persistent = os.stat(root).st_dev != os.stat(Path.cwd()).st_dev or None
        except OSError:
            persistent = None
    return {"path": str(root), "volume_mount": mount or None, "on_railway": on_railway, "persistent": persistent}


@dataclass(frozen=True)
class LibraryItem:
    kind: str          # "fvs" | "csv" | "raster"
    path: Path
    source: str        # "Built-in" | "Uploaded"
    size_bytes: int
    added: datetime

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def kind_label(self) -> str:
        return {"fvs": "FVS stands + polygons", "csv": "CSV table", "raster": "Raster"}[self.kind]


def _unique_by_name(items: Iterable[LibraryItem]) -> List[LibraryItem]:
    seen = set()
    result = []
    for item in items:
        key = (item.kind, item.name.lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _item(kind: str, path: Path, source: str) -> LibraryItem:
    stat = path.stat()
    size = stat.st_size
    if kind == "fvs":
        size += sum(path.with_suffix(ext).stat().st_size for ext in SHAPE_REQUIRED if path.with_suffix(ext).exists())
    return LibraryItem(kind, path, source, size, datetime.fromtimestamp(stat.st_mtime, timezone.utc))


def _fvs_csvs(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    return sorted(p for p in folder.glob("*.csv") if not p.name.startswith("._")
                  and all(p.with_suffix(ext).exists() for ext in SHAPE_REQUIRED))


def _csvs(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    return sorted(p for p in folder.glob("*.csv")
                  if not p.name.startswith("._") and "Column_Headers" not in p.name)


def list_items(builtin_data: Path, builtin_rasters: Path, raster_files: Sequence[Path]) -> List[LibraryItem]:
    """Every dataset PANDA can analyze. `raster_files` comes from the app's raster discovery."""
    lib = library_dir()
    items: List[LibraryItem] = []
    items += [_item("fvs", p, "Built-in") for p in _fvs_csvs(builtin_data / "fvs")]
    items += [_item("fvs", p, "Uploaded") for p in _fvs_csvs(lib / "fvs")]
    items += [_item("csv", p, "Built-in") for p in _csvs(builtin_data)]
    items += [_item("csv", p, "Uploaded") for p in _csvs(lib / "csv")]
    lib_rasters = (lib / "rasters").resolve()
    for path in raster_files:
        try:
            source = "Uploaded" if lib_rasters in path.resolve().parents else "Built-in"
        except OSError:
            source = "Built-in"
        items.append(_item("raster", path, source))
    return _unique_by_name(items)


def library_raster_dir() -> Path:
    return library_dir() / "rasters"


def _safe_name(name: str) -> str:
    return Path(str(name)).name.replace("\x00", "")


def _ext(name: str) -> str:
    lower = name.lower()
    for compound in (".shp.xml", ".csv.xml", ".aux.xml", ".vat.dbf", ".vat.cpg"):
        if lower.endswith(compound):
            return compound
    return Path(lower).suffix


def _stem(name: str) -> str:
    """Dataset stem shared by a file and its companions: map.tif, map.tfw and map.tif.aux.xml -> map."""
    ext = _ext(name)
    stem = name[: -len(ext)] if ext else name
    inner = Path(stem).suffix.lower()
    if inner in RASTER_EXTENSIONS or inner in CSV_EXTENSIONS:
        stem = stem[: -len(inner)]
    return stem


def save_uploads(files: Sequence[Tuple[str, bytes]], existing_names: Iterable[str]) -> Tuple[List[Path], List[str]]:
    """Save uploaded files into the library, grouping companions by file stem.

    Returns (saved primary dataset paths, error messages). A CSV that arrives with
    .shp/.shx/.dbf of the same name becomes an FVS dataset with polygons.
    """
    import pandas as pd

    existing = {n.lower() for n in existing_names}
    groups: Dict[str, Dict[str, Tuple[str, bytes]]] = {}
    errors: List[str] = []
    for raw_name, data in files:
        name = _safe_name(raw_name)
        if not data:
            errors.append(f"`{name}` is empty.")
            continue
        if len(data) > MAX_UPLOAD_BYTES:
            errors.append(f"`{name}` is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
            continue
        groups.setdefault(_stem(name).lower(), {})[_ext(name)] = (name, data)

    saved: List[Path] = []
    for stem, parts in groups.items():
        csv = parts.get(".csv")
        raster_ext = next((e for e in parts if e in RASTER_EXTENSIONS), None)
        primary = csv or (parts[raster_ext] if raster_ext else None)
        if primary is None:
            names = ", ".join(n for n, _ in parts.values())
            errors.append(f"{names}: add the main CSV or raster file with the same name.")
            continue
        if primary[0].lower() in existing:
            errors.append(f"A dataset named `{primary[0]}` is already in the library. Rename the file first.")
            continue
        if csv:
            try:
                pd.read_csv(BytesIO(csv[1]), nrows=5)
            except Exception as exc:
                errors.append(f"`{csv[0]}` could not be read as CSV: {exc}")
                continue
            has_shape = all(ext in parts for ext in SHAPE_REQUIRED)
            target = library_dir() / ("fvs" if has_shape else "csv")
            keep = (".csv",) + ((SHAPE_REQUIRED + SHAPE_OPTIONAL) if has_shape else ())
        else:
            target = library_raster_dir()
            keep = (raster_ext,) + RASTER_COMPANIONS
        target.mkdir(parents=True, exist_ok=True)
        for ext, (name, data) in parts.items():
            if ext in keep:
                (target / name).write_bytes(data)  # original names: GDAL/shapefile readers rely on them
        saved.append(target / primary[0])
        existing.add(primary[0].lower())
    return saved, errors


def delete_item(item: LibraryItem) -> None:
    """Delete an uploaded dataset and its companions. Built-in datasets cannot be deleted."""
    if item.source != "Uploaded":
        raise PermissionError("Built-in datasets are part of the app and cannot be deleted.")
    root = library_dir().resolve()
    if root not in item.path.resolve().parents:
        raise PermissionError("Only files inside the library folder can be deleted.")
    stem = _stem(item.path.name)
    for sibling in item.path.parent.iterdir():
        if sibling.is_file() and _stem(sibling.name) == stem:
            sibling.unlink()


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:,.0f} {unit}" if unit == "B" else f"{value:,.1f} {unit}"
        value /= 1024
    return f"{size} B"
