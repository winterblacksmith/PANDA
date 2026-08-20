---
id: fvs-treemap
title: FVS stands and TreeMap raster
description: Schema, joins, examples, and limitations of the FVS and TreeMap integration.
---

# FVS stands and TreeMap raster

The supplied FVS package contains a CSV attribute table and a complete ESRI shapefile. It has **20,069 rows**, and every row represents one stand with a unique `MU_ID`.

![Age and species composition example](/img/age-species-2022.jpg)

## What is in the stand table

The table includes 40 fields. The fields most useful for initial questions are:

| Field | Meaning in this integration |
|---|---|
| `MU_ID` | Unique management-unit/stand identifier; joins to the shapefile |
| `Acres` | Stand area used as the weight in area-distribution charts |
| `Age` | Stand age; used for exact-age distributions |
| `Age_class` | Young, Intermediate, Mature, or Old |
| `COMPOSITIO` | Coniferous, Mixed, or Deciduous |
| `TCuFt` | Cubic-foot volume per acre from the simulation output |
| `Tpa`, `BA`, `SDI`, `TopHt` | Stand structure measures |
| `TM_Value` | TreeMap profile code that links the stand result to raster Band 1 |

Across the supplied file there are 873,483.45 total acres, ages from 0 to 145, and 315 distinct `TM_Value` profiles.

## The two spatial joins

These joins answer different questions and should not be confused:

```text
FVS SQL row
   |
   +-- MU_ID ---- exact stand identity ----> FVS shapefile polygon
   |
   +-- TM_Value - modeled plot profile ----> TreeMap GeoTIFF Band 1 cells
```

`MU_ID` is the correct stand-to-polygon join. It is not the raster pixel code.

`TM_Value` is the correct FVS-to-TreeMap join. All 315 `TM_Value` codes used by the supplied FVS output occur in the raster. The raster contains 693 codes overall, so the FVS results cover a subset of the available TreeMap profiles.

## The complete TreeMap package

Canopy uses the packaged raster under `rasters/TreeMap_2022/`, which contains:

- `TreeMap_2022.tif` — the actual GeoTIFF cells;
- `TreeMap_2022.tfw` — an accompanying world file;
- `TreeMap_2022.tif.aux.xml` — ArcGIS/GDAL auxiliary metadata;
- `TreeMap_2022.tif.xml` — product and lineage metadata; and
- `TreeMap_2022.tif.vat.dbf` — a value-attribute table describing TreeMap profiles.

The GeoTIFF is one-band, `EPSG:5070` (NAD83 / CONUS Albers), 4,381 × 3,596 cells. Canopy reprojects a downsampled display mask to WGS84 for the interactive web map while keeping nearest-neighbor resampling so categorical codes are not averaged.

## Example questions

```text
Chart the sum of acres by age
Show stands older than 60 with TCuFt above 3000
Map old hardwood stands
Visualize the TreeMap raster for stands older than 60
Chart acres by composition
How many mature coniferous stands are there?
```

For the supervisor's requested age distribution, Canopy groups by exact `Age` and sums `Acres`. This reproduces the intended “Sum of Acres by Age” calculation rather than counting stands.

![Supplied sum-of-acres-by-age example](/img/sum-acres-by-age.png)

## What the supervisor's data adds

This package materially advances Canopy because it provides a realistic bridge from stand simulation to spatial decision support:

- natural-language questions can target FVS output variables, not only tree-inventory CSV columns;
- each result can be shown as its actual management-unit polygon;
- acreage-weighted distributions can identify age-class imbalance in stand creation;
- `TM_Value` allows the same selection to be shown as related TreeMap raster cells; and
- future FVS runs with the same schema can be imported without redesigning the question interface.

## Interpretation limits

Several stands may share one `TM_Value`. In the supplied data, `Age` and `Age_class` are constant within each TreeMap profile, but composition and volume can vary among stands sharing that code. Canopy therefore highlights raster cells by matching profile code; it does **not** claim that every pixel has a unique `MU_ID` or an unaggregated stand-level `TCuFt`.

For a raster colored by a varying stand field such as `TCuFt`, the method must be declared—for example, acreage-weighted mean `TCuFt` per `TM_Value`. This prevents a plausible-looking map from silently choosing an arbitrary stand value.
