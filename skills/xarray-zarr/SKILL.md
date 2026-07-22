---
name: xarray-zarr
description: "Use when reading, inspecting, or processing Zarr data stores with xarray. Covers dimension and coordinate discovery, lazy loading, chunking strategies, safe subsetting, and common operations on arbitrary chunked array data; do not assume lat/lon/time dimension names."
license: MIT
metadata:
  hermes:
    tags: [zarr, xarray, chunked-arrays, data-cubes, lazy-loading]
    related_skills: []
---

# Reading Zarr Stores with Xarray

## Overview

Zarr is a format for chunked, compressed, N-dimensional arrays. Xarray provides labeled wrappers (Dataset, DataArray) with a Zarr backend, enabling lazy reading of terabyte-scale arrays. The primary entry point is `xr.open_zarr()`.

**Key API reference:** https://docs.xarray.dev/en/stable/generated/xarray.open_zarr.html

## How Zarr Stores Work

- **Store:** a directory tree (or remote store) containing array chunks as individual binary blobs.
- **Chunks:** arrays are divided into fixed-size chunks, each compressed independently.
- **Metadata:** each array has `.zattrs` (attributes including `_ARRAY_DIMENSIONS`) and `.zarray` (dtype, shape, chunks, compressor, fill_value).
- **Lazy by default:** `open_zarr()` returns an xarray Dataset backed by Zarr arrays — no data is read until `.compute()` or `.values` is called.
- **Formats:** Zarr v2 (`zarr_format=2`) is most common; Zarr v3 (`zarr_format=3`) is newer. `xr.open_zarr()` auto-detects unless `zarr_format` is set explicitly.
- **Consolidated metadata:** `.zmetadata` is a JSON metadata index for a Zarr
    store, not a separate data format. Inspect its root `zarr_format` and `.zattrs`
    before opening the store. A store with `zarr_format: 2` is Zarr v2 even when
    the store contains many variables and groups.

## Installation

```bash
source /net/home/jpeters/.virtualenvs/oasis_agent/bin/activate
python -m pip install xarray zarr dask
# Optional: netcdf4 for NetCDF files
# Run the commands below with this environment activated.
```

## Opening a Zarr Store

Inspect no more than three representative stores for a large product
collection. Select stores from distinct product families or explicitly named
locations; do not open every minicube merely to enumerate its variables.

### Basic open (lazy)

```python
import xarray as xr

ds = xr.open_zarr('/path/to/data.zarr')
print(ds)
# <xarray.Dataset>
# Dimensions and coordinates depend on the store.
# Examples: (time, lat, lon), (time, y, x), (band, y, x), or (sample, feature)
# Data variables: var1, var2, ...
```

### Open with manual chunking (dask)

```python
# First inspect dimensions. Rechunk only a confirmed dimension for the task.
ds = xr.open_zarr('/path/to/data.zarr', chunks={'time': 50})
```

### Open specific variables only

```python
# Only open a subset of variables to reduce metadata overhead
ds = xr.open_zarr('/path/to/data.zarr', drop_variables=['unused_var'])
```

### Open a group within a zarr store

```python
ds = xr.open_zarr('/path/to/data.zarr', group='group_name')
```

## Inspecting the Dataset

```python
# Never infer dimension roles from names alone.
print("sizes:", dict(ds.sizes))
print("coordinates:", list(ds.coords))
print("variables:", list(ds.data_vars))

for name, coord in ds.coords.items():
    print(name, {
        "dims": coord.dims,
        "dtype": str(coord.dtype),
        "attrs": dict(coord.attrs),
    })

var = ds['some_variable']
print("variable:", var.name, "dims:", var.dims, "shape:", var.shape)
print("attributes:", dict(var.attrs))
```

Use coordinate attributes (`standard_name`, `axis`, `units`, `long_name`) and
the coordinate values to establish roles. Typical but non-binding conventions
include `latitude`/`longitude`, projected `x`/`y`, `time`, `band`, `layer`,
`sample`, and `feature`. A dimension can have no same-named coordinate. Do not
call an `x`/`y` grid geographic unless its CRS or coordinate metadata proves it.

## Subsetting

### Dimension-aware subsetting

```python
# Inspect first, then use the names actually present in this dataset.
# Label-based slice on projected coordinates:
region = ds.sel(y=slice(y_min, y_max), x=slice(x_min, x_max))

# Nearest point on the same coordinates:
point = ds.sel(y=target_y, x=target_x, method='nearest')

# Index-based selection works even without coordinate variables:
first_50 = ds.isel(frame=slice(0, 50))
```

For curvilinear grids, `lat` and `lon` can be two-dimensional auxiliary
coordinates rather than dimensions. Do not use a simple `.sel(lat=..., lon=...)`
until verifying that it is supported; use a mask or the dataset's spatial
indexing method instead.

### Time operations (only when a temporal coordinate is confirmed)

```python
# Replace `time` with the verified coordinate name.
recent = ds.sel(time=slice('2020-01-01', '2021-12-31'))

# Single time step
t0 = ds.sel(time='2020-06-01', method='nearest')

# Resample to coarser temporal resolution
monthly = ds.resample(time='1ME').mean()
annual = ds.resample(time='1YE').mean()
```

### Variable selection

```python
# Select one variable (returns DataArray)
temp = ds['temperature']

# Select multiple variables (returns Dataset)
subset = ds[['temperature', 'precipitation']]
```

## Lazy vs Eager Loading

| Pattern | What happens |
|---------|-------------|
| `ds = open_zarr(...)` | Lazy: no data loaded, only metadata |
| `var = ds['temp']` | Lazy: returns a DataArray backed by zarr chunks |
| `arr = var.sel(time='2020').compute()` | Eager: loads that slice into memory |
| `arr = var.values` | Eager: loads the full variable into memory |
| `ds = open_zarr(..., chunks={}).compute()` | Eager: loads entire dataset |

**Warning:** calling `.compute()` or `.values` on a full multi-GB variable will consume memory proportional to its uncompressed size. Always subset first.

## Common Operations

### Area-weighted spatial mean (geographic grids only)

Use this only after confirming a regular latitude/longitude grid. For projected,
irregular, curvilinear, or equal-area grids, obtain cell areas from metadata or
calculate appropriate weights; cosine-latitude weighting is not generally valid.

```python
import numpy as np

weights = np.cos(np.deg2rad(ds.lat))
weights.name = 'weights'
global_mean = ds['variable'].weighted(weights).mean(dim=('lat', 'lon'))
```

### Monthly climatology

```python
climatology = ds['variable'].groupby('time.month').mean(dim='time')
```

### Anomaly from climatology

```python
clim = ds['variable'].groupby('time.month').mean('time')
anomaly = ds['variable'].groupby('time.month') - clim
```

### Linear trend across time

```python
from scipy import stats

# Convert time to numeric years
td = ds.time.values.astype('datetime64[D]').astype(float) / 365.25
td -= td[0]

slope, intercept, r_value, p_value, std_err = stats.linregress(
    td, global_mean.values
)
print(f"Trend: {slope*10:+.3f} per decade, p={p_value:.2e}")
```

## Common Pitfalls

1. **Memory exhaustion** — Always subset before `.compute()`. Estimate size from the actual dimension sizes and dtype; do not assume a `(time, lat, lon)` layout.

2. **Chunking mismatch** — Disk chunks may not match your access pattern. Inspect `var.dims` and chunk sizes before rechunking; no dimension name or order is guaranteed.

3. **NaN fill values** — Zarr stores often use `NaN` as a fill value for missing data. Operations that include NaNs propagate them — use `skipna=True` (default) or `dropna()`.

4. **`_ARRAY_DIMENSIONS` attribute** — Xarray requires each variable to have a `_ARRAY_DIMENSIONS` attribute listing its dimension names. Missing this attribute causes an error on open.

5. **Consolidated metadata** — Some Zarr stores use consolidated metadata (`.zmetadata` file). `xr.open_zarr()` auto-detects and reads it; passing `consolidated=False` forces reading per-array metadata.

6. **Dimension order** — Variables are always `_ARRAY_DIMENSIONS` ordered. The chunk shape matches this order. Verify with `var.shape` before operations.

7. **Zarr v2 vs v3** — `zarr_format=None` (default) auto-detects. Set `zarr_format=2` or `zarr_format=3` explicitly if auto-detection fails.

## Verification Checklist

- [ ] `xr.open_zarr(path)` returns an xarray Dataset (no errors)
- [ ] `ds.sizes` shows expected dimensions
- [ ] Coordinate roles were verified from metadata/values rather than assumed from names
- [ ] `list(ds.data_vars)` returns expected variables
- [ ] Subsetting uses dimensions or coordinate names that exist in this dataset
- [ ] Time operations are used only when a temporal coordinate exists
- [ ] `.compute()` on a small subset returns real numeric values
- [ ] Any spatial weighting matches the verified grid geometry
