# Canopy SQL and Raster Roadmap

## What has started

- Added an experimental local SQLite backend.
- Added a `storage/canopy.sqlite` database location.
- Added a `rasters/` folder convention for GeoTIFF, IMG, VRT, TIFF, and JP2 files.
- Added raster layer discovery in the app.

## SQL path

The current app now defaults to a local SQLite backend for filtering.
Advanced options still allow switching back to pandas as a fallback.
When SQL is enabled, Canopy syncs the selected CSV into SQLite and runs deterministic filters through SQL.

This is a stepping stone toward PostgreSQL/PostGIS:

1. Keep pandas as the trusted fallback.
2. Validate SQL query behavior against the current pandas results.
3. Move the same query templates from SQLite to PostgreSQL.
4. Add PostGIS geometry columns for points and polygons.
5. Replace Python point-in-polygon checks with spatial SQL.

## Raster path

The app now looks for raster files in `rasters/`.

Supported discovery extensions:

- `.tif`
- `.tiff`
- `.img`
- `.vrt`
- `.jp2`

Raster metadata is basic until Rasterio/GDAL is installed. Once Rasterio is available, Canopy can inspect CRS, bounds, dimensions, bands, and driver information.

Recommended raster features:

1. Raster layer inventory.
2. Raster preview on the map.
3. Sample raster values at matching tree points.
4. Summarize raster values inside drawn polygons.
5. Connect raster summaries to natural-language questions.

Example future questions:

- What is the average elevation of hazardous trees?
- What is the canopy-height range inside this polygon?
- Which live oaks are in areas with high NDVI?
- Summarize land-cover classes inside this drawn area.

## Dependencies to add later

- `rasterio` for local raster reading and sampling.
- `shapely` for robust geometry operations.
- `geopandas` for vector file loading and spatial joins.
- `sqlalchemy` for database connection management.
- `psycopg` for PostgreSQL.
- PostgreSQL + PostGIS for production spatial queries.
