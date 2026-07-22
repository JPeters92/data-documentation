# Dataset Documentation

Agent skills for inspecting datasets and creating evidence-based `README.toml`
documentation.

## Workflow

The documentation process has two distinct phases:

1. Connect to the server and analyze the requested dataset read-only.
2. Generate or enrich the dataset-level `README.toml` from the verified analysis.

The workflow discovers the actual data layout before documenting it. It does
not assume that a cube uses `lat`, `lon`, or `time`, and it supports different
dimensions, formats, and hierarchical Zarr groups within one store.

For a hierarchical Zarr store, each discovered group is analyzed separately.
Groups may have different variables, dimensions, coordinate systems, spatial
extents, resolutions, or temporal coverage. Group-specific facts remain tied to
their group in the generated TOML.

## Skills

| Skill | Purpose |
|---|---|
| `documentation` | Main workflow for server access, dataset discovery, lazy inspection, TOML generation, validation, and change logging. |
| `inspection` | Safe inspection and processing of scientific data stores and cubes, including Zarr with xarray, arbitrary dimensions, and lazy loading. |

## Repository Structure

```text
README.md
src/
└── document_dataset.py
skills/
├── documentation/SKILL.md
└── inspection/SKILL.md
```

## Environment Setup

Use Python 3.12 or newer. Create and activate a dedicated virtual environment
for the documentation and inspection workflows:

```bash
python3 --version  # must be Python 3.12 or newer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install xarray zarr dask
# Optional: netcdf4 for NetCDF files
```

Keep `.venv` activated while running the commands below. The environment is
local to the user and can be replaced with another environment path if needed.

## Documentation Tool POC

`src/document_dataset.py` is a read-only evidence collector. It recursively
inventories the dataset, samples supporting CSV files, and inspects at most
three representative Zarr stores by default. Zarr stores are pruned during
discovery so chunk trees are not traversed. Xarray is used for lazy inspection
when possible; consolidated Zarr JSON metadata is used as a fallback.

Run it with the configured environment:

```bash
python \
    src/document_dataset.py \
    --proposal \
    --zarr-store data_from_mpi/ERA5Data.zarr \
    --zarr-store data_from_mpi/EventCube_ranked_pot0.01_ne0.1.zarr \
    --zarr-store deepextremes-minicubes/mc_10.00_50.09_1.1_20230611_0.zarr \
    /path/to/dataset > /tmp/dataset_report.json
```

Use `--zarr-store` up to three times to choose representative products. When
`--proposal` is supplied, the tool writes a temporary evidence-backed
`README.toml` proposal outside the dataset and prints its path to stderr. The
JSON report is evidence for review; the tool never replaces an existing
dataset `README.toml`. Keep the final README compact by publishing concise
collection-level metadata rather than per-store paths, full variable dumps, or
detailed inspection traces.

Discovery recurses through nested directories to arbitrary depth by default.
Use `--max-depth N` only when an explicit traversal limit is needed. Repeated
filename tokens are retained as `filename_evidence` and used for meaningful
`[general].keywords`; format names such as `Zarr`, `NetCDF`, `GeoTIFF`, and
`HDF5` are inferred from discovered data files.

## TOML Contract

Every generated document contains:

- `[general]` with the required identity, description, citation, manager,
  keywords, and license fields
- `[details]` for dataset-wide verified metadata
- `[publication]` for verified publication information
- `[[log]]` entries for documentation changes

Unknown facts remain empty, omitted, or explicitly recorded as unknown. The
workflow never invents a license, citation, resolution, temporal range, or
scientific description.
