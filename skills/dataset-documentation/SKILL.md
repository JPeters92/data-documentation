---
name: dataset-documentation
description: "Use when inspecting datasets under /net/data on the phaestos cluster, bootstrapping missing README.toml files, or creating and enriching dataset documentation. Detects common cube formats, extracts verifiable metadata, preserves the required TOML schema, and logs each documented change."
license: MIT
metadata:
  tags: [phaestos, dataset-documentation, toml, zarr, netcdf, geospatial-data, metadata]
  related_skills: [inspect]
---

# Phaestos Dataset Documentation

## Purpose

Create or enrich the machine-readable `README.toml` at the top level of
datasets below `/net/data` on the `phaestos` cluster. The file feeds an
automatic documentation system. Base every value on information that can be
verified from the dataset, its embedded metadata, or accompanying documents.

## Scope and access

- Run directly on the `phaestos` host; do not SSH back into `phaestos`.
- Use `/net/home/jpeters/.virtualenvs/oasis_agent/bin/python` for Python
  inspection and validation. The environment provides Python 3.12 and should
  contain `xarray`, `zarr`, and `dask` for cube inspection.
- Keep project Python source under `src/`; do not create separate root-level
  validation or ad-hoc analysis scripts. Run focused checks inline with the
  canonical interpreter or add reusable implementation code under `src/`.
- Treat all data files as read-only.
- The only intended remote writes are `<dataset>/README.toml` files and their
  appended `[[log]]` entries.
- Work one dataset at a time. The user authorizes comprehensive read-only
  inspection of all files and nested directories within that dataset to infer
  documentation. Search documentation, notebooks, scripts, registries, and
  metadata as needed. Still avoid materializing complete cubes or making
  needless repeated reads of large binary data.
- Treat the top-level README as an audit target as well as an output file.
  For a batch quality pass, parse every immediate `/net/data/*/README.toml`,
  identify descriptions containing generated phrases such as `no detected data
  files`, `file_count`, `store_count`, or bare file totals, and inspect those
  dataset roots before editing. A file count is inventory evidence, not a
  scientific description.
- Use the published Data overview at
  `https://readme.hpc.rsc4earth.intern.uni-leipzig.de/` to identify dataset
  directories whose overview entry is `MISSING`, then verify the filesystem
  before acting because the page may lag behind recent README updates.
- If `/net/data/<dataset>/README.toml` is absent, copy the canonical
  `/net/data/README-template.toml` into that dataset directory with the exact
  name `README.toml` before filling metadata in that copied file. Do not
  replace this copy with a separately generated file. Never overwrite an existing
  `README.toml`, even when it is incomplete; read it first and preserve its
  values.
- For a batch request covering all datasets, inspect only the immediate child
  directories of `/net/data` and classify each top-level `README.toml` as
  missing, empty, or non-empty. Process only missing or empty files. A
  non-empty template containing `TODO` placeholders is still an existing file
  and must not be replaced unless the user explicitly requests enrichment.
- Inspect no more than three representative Zarr stores per documentation
  pass. Prefer explicit paths from different product families when the user
  provides them; do not open every minicube in a large collection.
- Never invent a citation, licence, temporal coverage, resolution, owner, or
  scientific description. Use `license = "unknown"` and an empty citation when
  no reliable source is present.
- Preserve an existing `manager` value. When creating a new file without a
  user-supplied manager, use `manager = [""]`.
- Leave an existing, valid, sufficiently documented `README.toml` unchanged.
  Add a log entry only when content actually changes.

## Required TOML contract

Every document must contain these four sections. Do not remove, rename, or
change the required keys in `[general]`.

```toml
[general]
name = "TODO"
description = ""
citation = ""
manager = [""]
keywords = [""]
license = "unknown"

[details]

[publication]

[[log]]
date = 2025-07-17
comment = "toml file created"
```

`keywords` should contain meaningful, evidence-based terms such as a product
name, measured variable, sensor, region, or processing method. Do not use
`dataset`, `metadata`, or `documentation` as placeholder keywords. An empty
list is preferable to invented or generic keywords when the content cannot be
determined reliably. Preserve existing values that are more specific than
newly observed information. Dates in log entries are TOML dates, e.g.
`date = 2026-07-22`, not quoted strings.

## Safe workflow

### 0. Bootstrap missing dataset documentation

Start with the Data overview page when the task is to find datasets lacking
documentation. Treat an entry with `MISSING` as a candidate, not as proof that
the local file is absent. For each candidate, check only the dataset's top
directory:

```bash
test -f /net/data/<dataset>/README.toml
```

If the check fails, create the dataset-level file from the shared template:

```bash
cp /net/data/README-template.toml /net/data/<dataset>/README.toml
```

After copying, fill that exact template-derived file in place. Preserve its
required sections and initial log, replacing only supported placeholder values
and appending a dated log entry for the fill.

Do not copy the template into nested product directories or individual cube
stores. Do not run the copy command when the target already exists. After
bootstrapping, continue with the normal workflow below and replace only fields
supported by verified dataset evidence. A newly copied template must retain
the required `[general]`, `[details]`, `[publication]`, and `[[log]]` sections;
the initial template log may be retained and supplemented when metadata is
filled.

For a batch bootstrap, use a guarded loop that checks the target immediately
before copying and reports every created path. The guard must reject any
existing file, including a non-empty template:

```python
from pathlib import Path
import shutil

root = Path("/net/data")
template = root / "README-template.toml"
for dataset in sorted(path for path in root.iterdir() if path.is_dir()):
  target = dataset / "README.toml"
  if target.exists() and target.stat().st_size > 0:
    continue
  if target.exists():
    target.unlink()
  shutil.copyfile(template, target)
  print(target)
```

Run this only with the canonical `oasis_agent` Python interpreter. The empty
file case is the only existing-file case that may be replaced; parseable or
non-empty documents must remain untouched.

### 1. Discover, without modifying

For a requested dataset, inspect the current documentation and map its nested
layout before opening any data. The dataset-level `README.toml` belongs at
`/net/data/<dataset>/README.toml`; do not add README files beside individual
cubes unless explicitly requested.

```bash
cd /net/data/<dataset> && pwd && test -f README.toml && sed -n "1,240p" README.toml || true

# Find data containers recursively, but prune containers so chunk files are not traversed.
cd /net/data/<dataset> && find . -type d \( -name "*.zarr" -o -name "*.zarr.zip" \) -prune -print

# Discover Zarr hierarchy markers without traversing array chunks. A `.zmetadata`
# file is consolidated Zarr metadata; inspect its `zarr_format` and root
# attributes before using xarray.
cd /net/data/<dataset> && find . -type f \( -name ".zgroup" -o -name "zarr.json" \) -print

# Find representative non-Zarr products and supporting documents recursively,
# but keep the traversal bounded. The tool uses the same bounded-depth rule.
cd /net/data/<dataset> && find . -maxdepth 8 -type f \( -iname "*.nc" -o -iname "*.nc4" -o -iname "*.tif" -o -iname "*.tiff" -o -iname "*.h5" -o -iname "*.hdf5" -o -iname "*.csv" -o -iname "*.parquet" -o -iname "README*" -o -iname "LICENSE*" -o -iname "CITATION*" \) -print | head -n 300
```

Look first for supporting sources such as `README*`, `ReadMe*`, `LICENSE*`,
`CITATION*`, `*.md`, `*.txt`, `*.json`, or data-specific metadata. A nested
product README may be the best available source for a parent collection; use
it only for facts that clearly apply to the collection and record its relative
path as `source_document`. Prefer source descriptions, names, keywords,
license, and publication information over generic file-count descriptions.
Do not infer a licence merely from an upstream product name.

Nested paths are normal. For example, a dataset can contain training material
and several scientific products at different depths, or continent-specific
folders containing many similar minicubes. Group discovered cubes by product
family/path. Inspect one representative per identical family, then inspect a
second only when filenames, format markers, or metadata suggest a difference.
Do not open every minicube merely because it exists.

Use directory names and filenames as evidence for product families before
concluding that no data were detected. A parent collection may contain several
unrelated branches, for example a global elevation branch alongside a
European soil-moisture branch. Record each verified family in `details` and
describe the collection as a whole. Product tokens such as `DEM`, `SWI1km`,
`MCD43C4`, `TOCR`, or `GLO-30` can support keywords and descriptions when they
are corroborated by representative metadata. Do not collapse a collection to
the first branch found. Treat directory labels as organization hints rather
than definitive product names: a directory such as `glo90` must be checked
against the actual `Copernicus_DSM_COG_30_*_DEM.tif` names and raster metadata.

Do not rely only on a shallow listing or a narrow extension allowlist. Traverse
ordinary nested product directories to a bounded depth (normally 8), while
pruning `.zarr` stores and obvious chunk trees. Recognize scientific files and
archives by both extension and filename pattern. If the root contains only
archives or uncommon formats, inspect archive names and one safe header or
sidecar rather than reporting no data.

### Filename-derived evidence

Filenames are often the most informative source when a collection has little
documentation. Parse repeated filename tokens systematically and record only
what the naming convention supports:

| Filename evidence | Potential meaning | Example |
|---|---|---|
| Product token | Product family or measured variable | `DEM`, `SWI1km`, `TOCR`, `MCD43C4` |
| Sensor/platform token | Acquisition instrument or platform | `SCATSAR`, `TROPOMI`, `SPOT-4`, `VEGETATION` |
| Region token | Geographic subset | `CEURO`, `EUROPE`, a country or tile code |
| Timestamp token | Observation or product date/time | `201608051200` |
| Version token | Processing or product release | `V1.0.1`, `V1.5.1` |
| Resolution token | Nominal spatial or temporal scale | `30`, `1km`, `8-day` |
| Tile token | Spatial tile position | `N59_00_E004_00` |

For example, `Copernicus_DSM_COG_30_N59_00_E004_00_DEM.tif` supports a
Copernicus 30 m DEM product and a latitude/longitude tile identifier, while
`c_gls_SWI1km_201608051200_CEURO_SCATSAR_V1.0.1.nc` supports a 1 km European
SWI product, its timestamp, SCATSAR source, and version. Treat `glo90` or
similar directory labels as organizational context only when they disagree
with the product token in the filename. Confirm ambiguous tokens against a
representative file's global attributes, XML sidecar, raster metadata, or
several consistently named files.

Use filename-derived facts in `details` and meaningful `keywords`, not as a
replacement for scientific interpretation. Do not infer an unverified unit,
algorithm, coverage period, accuracy, or licensing condition from a filename.
Do not mistake timestamps or tile coordinates for counts, and do not turn the
number of matching filenames into the public description. Keep representative
filename patterns compact rather than publishing a long list of individual
paths.

A single Zarr store can contain a hierarchy of groups. Paths such as `s2lta`,
`dem`, `lcc`, or `lcc/subgroup` are independent products in the same store,
not interchangeable names for one fixed cube. Discover the actual group paths
first and inspect each relevant group independently. Groups may have different
dimensions, variables, coordinate systems, spatial extents, or temporal
coverage.

### 2. Identify the data format

Use filenames and directory markers to select a minimal inspection method.

| Marker | Format | First inspection |
|---|---|---|
| `*.zarr`, `.zgroup`, `.zmetadata`, `zarr.json` | Zarr | Inspect `.zmetadata` or `zarr.json` first, record the actual Zarr format, then open lazily with Xarray if possible. |
| `*.nc`, `*.nc4`, `*.cdf` | NetCDF | `xarray.open_dataset(..., decode_cf=True)` on one representative file. |
| `*.tif`, `*.tiff` | GeoTIFF | `rasterio.open()` on one representative file. |
| `*.csv`, `*.parquet` | Tabular data | Read schema/sample only. |
| `*.h5`, `*.hdf`, `*.hdf5` | HDF | Inspect keys and attributes without loading arrays. |
| `*.hdr` + `*.img` | ENVI raster | Read the header and pair it with the image; inspect one raster safely. |
| `*.RData` | R serialized data | Inspect only with an available R/Python reader or document the verified collection and file naming. |
| `*.npy`, `*.npz` | NumPy array/training data | Inspect keys, shapes, dtypes, and one small sample only. |
| `*.xml` | Product metadata | Read targeted product fields; do not treat XML sidecars as the primary data format. |
| archives such as `*.zip`, `*.7z`, `*.rar` | Packaged data | Record the archive and infer contents only from verified names or safe listing. |

If several formats or product families occur, describe the dataset as a whole
and list the important product types in `details`. Report formats at the
correct scope: a Zarr-only minicube directory must not be described as
NetCDF, while a parent dataset may contain both Zarr and NetCDF products.
Use readable names such as `NetCDF`, `GeoTIFF`, `HDF5`, `Parquet`, `CSV`, and
`Zarr`, not raw suffixes such as `NC` or `TIF`.
The `formats` list is reserved for dominant formats only. Do not list every
minor or ancillary format there; record secondary formats only in a separate
evidence field when they matter to the dataset description. For a collection
dominated by Zarr stores with a few CSV tables and one ancillary file, use
`formats = ["Zarr"]`.
Prefer a summary such as `type = "zarr"`, `sensor = "Sentinel 2"`,
`projection = "UTM"`, or `chunking = "slice-wise"` when verified. Do not
create one huge variable list from thousands of similar minicubes. If the
format cannot be determined, document only verifiable filesystem facts and
mark the missing information in the log.

### 3. Inspect cubes lazily and minimally

For Xarray-compatible cubes, use a small Python program with the configured
oasis_agent interpreter. It must first
analyze the actual store and its groups, then use that analysis as the input to
TOML generation. It must print metadata, not materialize the data:

```python
import json
from pathlib import Path
import xarray as xr

store = Path("/net/data/<dataset>/<cube>.zarr")

# Zarr v2 groups use .zgroup; Zarr v3 groups use zarr.json.
# The root is inspected separately from discovered child groups.
group_paths = []
for marker in store.rglob("*"):
  if not marker.is_file() or marker.parent == store:
    continue
  if marker.name == ".zgroup":
    group_paths.append(marker.parent.relative_to(store).as_posix())
  elif marker.name == "zarr.json":
    metadata = json.loads(marker.read_text())
    if metadata.get("node_type") == "group":
      group_paths.append(marker.parent.relative_to(store).as_posix())
group_paths = sorted(set(group_paths))

analysis = []
for group in [None, *group_paths]:
  try:
    ds = xr.open_zarr(store, group=group, chunks={})
  except Exception as error:
    analysis.append({"group": group or ".", "error": str(error)})
    continue

  group_analysis = {
    "group": group or ".",
    "sizes": dict(ds.sizes),
    "coordinates": {
      name: {"dims": coord.dims, "attrs": dict(coord.attrs)}
      for name, coord in ds.coords.items()
    },
    "variables": {},
    "attrs": dict(ds.attrs),
  }
  for name, da in ds.data_vars.items():
    group_analysis["variables"][name] = {
      "dims": da.dims,
      "dtype": str(da.dtype),
      "chunks": da.chunks,
      "attrs": dict(da.attrs),
    }
  analysis.append(group_analysis)
  ds.close()

for group_analysis in analysis:
  print(group_analysis)
```

The root entry is useful for flat stores. For hierarchical stores, treat each
discovered group path as an independent analysis result. Dimension names come
from the store and may be `x`, `y`, `time`, `band`, `sample`, `feature`, or
something else; never substitute `lat`, `lon`, or `time` without verifying the
coordinates and their attributes. If a group cannot be opened by xarray,
retain its discoverable Zarr metadata and record the limitation.

For NetCDF, use `xr.open_dataset(path, chunks={})`. Select one representative
file first; only inspect more files where time coverage or variables differ.
Search nested product layouts to a bounded depth when the dataset organizes
files by product, ensemble, resolution, and temporal frequency. Do not stop
after the first directory level, because valid data files may be several
levels below the dataset root.
For Zarr metadata too large for a normal read, use targeted `jq` queries (keys,
`zarr_format`, shape, chunks, dtype, and root/variable attributes), never dump
the full `.zmetadata`. `.zmetadata` is not a data format distinct from Zarr;
it is consolidated metadata for the Zarr store, commonly with
`zarr_format = 2`.

Derive spatial and temporal coverage only from the coordinates and metadata of
the relevant root or group. Record group-specific CRS, projection, extent,
resolution, and temporal coverage under that group when they differ. Record
all variables only when the list is reasonably short; for large catalogs use a
count plus a representative or documented list.

### 4. Write concise, evidence-based fields

Before writing, compare the current document with the verified findings. Do
not add optional fields merely to make documents look uniform. If `sensor`,
projection, coverage, citation, or another field cannot be supported by the
data or accompanying material, omit it (or retain its current empty value).
An already complete and valid document needs no edit and no new log record.

Keep the published README compact. Use representative stores and detailed
inspection traces as internal evidence for validation, not as large nested
TOML tables in the public document. Summarize repeated collections at the
dataset level; retain concise facts such as dominant format, product
families, coverage, resolution, and a short note that coverage or variables
may vary by location. Do not publish per-store paths, full variable dumps,
backend error messages, or individual minicube metadata unless the user
explicitly requests an audit record.

Never expose internal counter names such as `file_count` or `store_count` in
the public description. Render counts as natural language only when they add
useful context, and prefer a one-sentence scientific or product description
from a verified source document.

Counts belong, when useful, in a structured detail such as `tile_count` or
`product_count`, never as the main identity of a dataset. For example, a
collection containing thousands of files named
`Copernicus_DSM_COG_30_*_DEM.tif` should be documented as Copernicus DEM
GLO-30 elevation tiles, with the tile count as secondary evidence. Likewise,
`SWI_europe_1km` should be recognized as a daily European 1 km Soil Water
Index product when representative NetCDF metadata confirms that interpretation.

Use stable keys where applicable, but populate them from the completed
analysis rather than from this illustrative example:

```toml
[details]
format = "Zarr"
dimensions = ["<discovered_dimension>"]
variables = ["<discovered_variable>"]
# Include only when the store actually contains groups.
groups = ["<discovered_group_path>"]

[details."<discovered_group_path>"]
dimensions = ["<group_dimension>"]
variables = ["<group_variable>"]
# Add group-specific CRS, extent, or coverage only when verified.
spatial_coverage = "global"
spatial_resolution = "0.25 degrees"
temporal_coverage = "1979-01-01 to 2021-12-27"
temporal_resolution = "8 days"
```

For a hierarchical store, generate one quoted `[details."<group_path>"]`
subtable per discovered group path. Do not predefine names such as `s2lta`,
`dem`, or `lcc`; those are examples only. A group may have completely different
dimensions and variables from its siblings. Keep group-specific metadata in
that subtable instead of promoting it to `[details]`. Keys in `[details]` and
`[publication]` may be adapted to the dataset. Keep values short and
descriptive. Do not overwrite a non-empty existing field unless the new value
is demonstrably more accurate; note only such corrections or additions in the
log.

Use `[publication]` only for verified publication-specific information, for
example:

```toml
[publication]
title = "Verified title"
year = 2024
doi = "10.xxxx/example"
```

### 5. Validate and log

Before and after every edit, validate the exact file locally on `phaestos`:

```bash
/net/home/jpeters/.virtualenvs/oasis_agent/bin/python -c "import sys, tomllib; tomllib.load(open(sys.argv[1], \"rb\")); print(\"valid TOML\")" /net/data/<dataset>/README.toml
```

If and only if the document changed, append exactly one `[[log]]` record for
that documentation pass, for example:

```toml
[[log]]
date = 2026-07-22
comment = "Added metadata from Zarr and dataset-level attributes."
```

After editing, re-read the changed file, confirm the four required sections,
confirm that every keyword is meaningful (or that an empty list is justified),
and report both completed and still-unknown fields. For a batch pass, parse all
top-level README files after the edits and verify that no generated description
patterns or placeholder keywords remain. Do not make unrelated data changes.

## Completion checklist

- [ ] Dataset path and primary format were verified.
- [ ] The store was analyzed before any TOML content was created or changed.
- [ ] Flat stores and relevant discovered Zarr groups were distinguished.
- [ ] No more than three representative Zarr stores were inspected.
- [ ] `.zmetadata`/`zarr.json` format and root attributes were checked before xarray.
- [ ] Each selected store was inspected lazily or through metadata fallback; no complete array was loaded.
- [ ] Actual dimensions, variables, and group-specific metadata were preserved; none were assumed from a fixed template.
- [ ] `[general]`, `[details]`, `[publication]`, and `[[log]]` exist.
- [ ] Required `[general]` keys are unchanged; `manager` remains empty unless supplied.
- [ ] `keywords` contains meaningful evidence-based values, or is empty when
  no reliable keywords can be derived.
- [ ] Product families were discovered from all relevant nested branches, not
  inferred from only the first directory or a file count.
- [ ] Repeated filename tokens were checked for product, sensor, region, date,
  version, resolution, and tile evidence where applicable.
- [ ] Filename-derived facts were corroborated where ambiguous and were not
  used to infer unsupported units, algorithms, coverage, or licences.
- [ ] Generated phrases and internal counter names were removed from revised
  descriptions.
- [ ] Citation and licence are present only when verified.
- [ ] `README.toml` parses with `tomllib` after the edit.
- [ ] A single, accurate log entry was added only when the file changed.
