---
name: json-incremental-read
description: "Use when reading large JSON files, Zarr metadata, or any structured data where loading the full file into the agent context would be wasteful. Discover available metadata files and keys first; then use jq for targeted extraction without assuming a Zarr version, file layout, variable name, or dimension names."
license: MIT
metadata:
  hermes:
    tags: [json, jq, incremental-read, zarr-metadata, context-management, large-files]
    related_skills: [xarray-zarr]
---

# Incremental JSON Reading with jq

## Overview

When an agent reads a file with `read_file`, the full content enters the context window. For large JSON files — Zarr metadata (`*.zarray`, `*.zmetadata`, `*.zarr`), API responses, config dumps — this wastes tokens on irrelevant data. **jq** is a lightweight JSON processor that extracts only the fields you need, one command at a time.

The pattern is: **peek with `keys` or `length`, then drill into what's relevant.**

## Installation

```bash
# Download the jq binary directly (no package manager needed)
curl -fsSL https://github.com/jqlang/jq/releases/download/jq-1.7/jq-linux-amd64 -o ~/.local/bin/jq
chmod +x ~/.local/bin/jq
```

## How It Works

| Agent action | What enters context |
|---|---|
| `read_file("big.json")` | Entire file — every key and value |
| `jq '.key' big.json` | Only the extracted value |
| `jq 'keys' big.json` | Just the top-level key names |
| `jq 'length' big.json` | Just the count — one number |

Use jq in a terminal call or `execute_code` to peek at sections before committing to a full read.

## Zarr Metadata: The Primary Use Case

Zarr stores contain JSON metadata files. These are the ones you'll inspect most:

| File | Contents | Size concern |
|------|----------|-------------|
| `.zattrs` | Dataset/group-level attributes | Small (KB) — safe to read full |
| `.zarray` | Array metadata: shape, chunks, dtype, compressor | Small — safe to read full |
| `.zgroup` | Zarr group marker (`{"zarr_format": 2}`) | Tiny |
| `.zmetadata` | Consolidated metadata for all arrays in store | Can be **large** (MB) |
| `<variable>/.zattrs` | Per-variable attributes (units, long_name, etc.) | Small |
| `<variable>/.zarray` | Per-variable shape/chunk info | Small |

### Consolidated metadata (`.zmetadata`)

Large Zarr stores often consolidate all array metadata into a single `.zmetadata` file. **This is the main file where incremental reading matters** — a 40-variable cube can have a `.zmetadata` well over 100KB.
It remains Zarr metadata: inspect `metadata[".zgroup"].zarr_format` (often
`2`) and `metadata[".zattrs"]` to identify the store and its product-specific
attributes. Do not describe a store as NetCDF unless an actual NetCDF file was
found in the scope being documented.

### Discover before querying

Never assume that a store has `.zmetadata`, that it is Zarr v2, or that a
variable has a particular name. First discover metadata files without reading
array chunks:

```bash
# Zarr v2 markers and per-array metadata
find /path/to/store -maxdepth 3 \( -name '.zgroup' -o -name '.zattrs' -o -name '.zarray' -o -name '.zmetadata' \) -print

# Zarr v3 uses zarr.json rather than .zgroup/.zarray.
find /path/to/store -maxdepth 3 -name 'zarr.json' -print
```

If `.zmetadata` exists, discover its layout before selecting a path:

```bash
jq 'keys' /path/to/store/.zmetadata
jq 'if has("metadata") then .metadata | keys else keys end' /path/to/store/.zmetadata
```

For a store without consolidated metadata, enumerate individual `.zarray` and
`.zattrs` files and inspect a representative one. For Zarr v3, inspect the
discovered `zarr.json` first. Use Xarray if the metadata layout is unclear.

## jq Quick Reference

### Inspecting structure — no data

```bash
# List top-level keys
jq 'keys' file.json

# List keys only if the object has that key
jq 'if has("metadata") then .metadata | keys else empty end' file.json

# Count items in an array
jq '.variables | length' file.json

# Discover nested objects before querying a path
jq 'to_entries[] | select(.value | type == "object") | .key' file.json
```

### Reading specific fields

```bash
# Single key
jq '.shape' array.zarray
jq '.dtype' array.zarray
jq '.chunks' array.zarray

# Multiple keys at once
jq '{shape, chunks, dtype, compressor}' array.zarray

# Use a key discovered in the previous step.
jq '.metadata["<discovered-key>"] | {shape: .zarray.shape, chunks: .zarray.chunks}' .zmetadata
```

### Zarr-specific patterns

```bash
# List metadata entry names only after confirming that .metadata exists
jq '.metadata | keys[]' .zmetadata

# List only variable entries (exclude .zattrs/.zgroup keys)
jq '.metadata | to_entries | map(select(.key | test("^[^.]"))) | map(.key) | .[]' .zmetadata

# Get shape + dtype for every variable
jq '.metadata | to_entries | map(select(.key | test("^[^.]"))) | map({(.key): {shape: .value.zarray.shape, dtype: .value.zarray.dtype}}) | add' .zmetadata

# See compressor details for the first variable
jq '.metadata | to_entries | map(select(.key | test("^[^.]"))) | first | {name: .key, compressor: .value.zarray.compressor}' .zmetadata

# Check a key found during discovery
jq '.metadata | has("<discovered-key>")' .zmetadata

# Get fill value and any filters
jq '{fill_value, filters}' array.zarray
```

### Array metadata (`.zarray`)

```json
{
  "shape": [100, 200, 300],       // roles come from dimensions/attributes
  "chunks": [1, 200, 300],
  "dtype": "<f4",                  // float32 little-endian
  "compressor": {
    "id": "blosc",
    "cname": "lz4",
    "clevel": 5,
    "shuffle": 1
  },
  "fill_value": "NaN",
  "order": "C",
  "filters": null,
  "zarr_format": 2
}
```

```bash
# Read the whole thing — it's small
jq '.' array.zarray

# Or just the parts you need
jq '{shape, chunks, dtype}' array.zarray
```

### Attribute metadata (`.zattrs`)

```bash
# List attribute keys at a discovered path
jq 'keys' /path/to/discovered/.zattrs

# Read common attributes only when present
jq '{units, long_name, standard_name, axis, coordinates}' /path/to/discovered/.zattrs

# Read processing history
jq '.processing_steps' variable/.zattrs

# Inspect available attributes; do not presume a temporal coordinate
jq 'keys' /path/to/discovered/.zattrs
```

## Typical Zarr Inspection Workflow

```bash
# 1. Discover metadata files before assuming a Zarr layout.
find /path/to/store -maxdepth 3 \( -name '.zmetadata' -o -name '.zarray' -o -name '.zattrs' -o -name 'zarr.json' \) -print

# 2. If .zmetadata exists, discover its entry names.
jq 'if has("metadata") then .metadata | keys[] else keys[] end' /path/to/store/.zmetadata

# 3. Inspect one entry selected from that output.
jq '.metadata["<discovered-key>"]' /path/to/store/.zmetadata

# 4. For non-consolidated Zarr v2 metadata, inspect a discovered sidecar file.
jq '{shape, chunks, dtype, compressor}' /path/to/discovered/.zarray
```

## Avoiding Context Bloat

### Do this (incremental):

```bash
# Only the info you actually need
jq '{shape, chunks, dtype}' .zarray
jq 'keys' file.json
```

### Not this (wasteful):

```bash
# Full file in context
read_file .zmetadata
```

### Sizing before reading

```bash
# Check file size first — if small, just read it
ls -lh file.json

# Check how many top-level keys
jq 'length' file.json

# Get total chars of a value
jq '.large_field | length' file.json
```

## Common Pitfalls

1. **Quoting in shell** — Use single quotes for the jq filter to avoid shell expansion: `jq '.key' file.json`. Double quotes will expand shell variables.

2. **Keys with dots or special characters** — Use bracket notation with a discovered name: `jq '.["<discovered-key>"]' file.json`

3. **Consolidated vs per-variable metadata** — `.zmetadata` may not exist if the store wasn't created with consolidated metadata. Fall back to reading individual `variable/.zarray` and `variable/.zattrs` files.

4. **Large `.zmetadata` can still be big** — Even with jq, the output of `jq '.' .zmetadata` is the full file. Always filter first: start with `keys`, then drill down.

5. **jq output to multi-line** — Use `-r` (raw output) and `-c` (compact) for pipeable single-line output: `jq -rc '.key' file.json`

6. **`read_file` with `offset` and `limit`** — For JSON files that are small enough to read but you only need a specific region, `read_file(path, offset=N, limit=M)` is an alternative to jq.

## Verification Checklist

- [ ] `jq --version` returns a version number
- [ ] Metadata files were discovered before querying them
- [ ] A `.zmetadata` query was used only when that file exists
- [ ] The selected key/path was discovered from the actual metadata
- [ ] `jq '.shape' /path/to/discovered/.zarray` returns an array shape when a v2 array exists
- [ ] `jq -r 'keys | .[]' /path/to/discovered/.zattrs` lists attribute names when present
- [ ] `jq 'length' file.json` returns the count of top-level elements
- [ ] `ls -lh file.json` shows file size before deciding how to read
