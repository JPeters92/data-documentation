#!/usr/bin/env python3
"""Collect evidence for a dataset README without modifying the dataset."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any


INTERESTING_SUFFIXES = {
    ".csv",
    ".cdf",
    ".h5",
    ".hdf",
    ".hdf5",
    ".md",
    ".nc",
    ".nc4",
    ".parquet",
    ".tif",
    ".tiff",
    ".txt",
    ".zarr",
}

FORMAT_NAMES = {
    "cdf": "NetCDF",
    "nc": "NetCDF",
    "nc4": "NetCDF",
    "tif": "GeoTIFF",
    "tiff": "GeoTIFF",
    "h5": "HDF5",
    "hdf": "HDF5",
    "hdf5": "HDF5",
    "parquet": "Parquet",
    "csv": "CSV",
    "zarr": "Zarr",
}

TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*")
GENERIC_TOKENS = {
    "data", "dataset", "file", "files", "readme", "metadata", "version",
    "final", "latest", "copy", "temp", "tmp",
}


def discover_files(
    dataset: Path,
    max_zarr_stores: int,
    explicit_stores: list[Path] | None = None,
    max_depth: int | None = None,
) -> dict[str, list[str]]:
    products: list[str] = []
    metadata: list[str] = []
    supporting: list[str] = []

    if explicit_stores:
        for store_path in explicit_stores:
            products.append(str(store_path.relative_to(dataset)))
            for marker in (".zgroup", ".zattrs", ".zmetadata", "zarr.json"):
                marker_path = store_path / marker
                if marker_path.exists():
                    metadata.append(str(marker_path.relative_to(dataset)))

    for root, directories, filenames in os.walk(dataset):
        depth = len(Path(root).relative_to(dataset).parts)
        directories[:] = sorted(
            name for name in directories if not name.startswith(".")
        )
        root_path = Path(root)
        zarr_directories = [
            name for name in directories if name.endswith(".zarr")
        ]
        for name in zarr_directories:
            store_path = root_path / name
            directories.remove(name)
            if explicit_stores or len(products) >= max_zarr_stores:
                continue
            products.append(str(store_path.relative_to(dataset)))
            for marker in (".zgroup", ".zattrs", ".zmetadata", "zarr.json"):
                marker_path = store_path / marker
                if marker_path.exists():
                    metadata.append(str(marker_path.relative_to(dataset)))
        if max_depth is not None and depth >= max_depth:
            directories.clear()
        for name in filenames:
            path = root_path / name
            if path.suffix.lower() in INTERESTING_SUFFIXES or path.name.startswith(
                ("README", "ReadMe", "LICENSE", "CITATION")
            ):
                supporting.append(str(path.relative_to(dataset)))

    return {
        "zarr_stores": sorted(set(products)),
        "metadata_markers": sorted(set(metadata)),
        "supporting_files": sorted(set(supporting)),
    }


def discover_source_documents(dataset: Path, max_depth: int | None = None) -> list[Path]:
    """Find small documentation files without entering array chunk trees."""
    documents: list[Path] = []
    names = {"README", "README.md", "ReadMe.md", "README.toml", "CITATION.md"}
    for root, directories, filenames in os.walk(dataset):
        depth = len(Path(root).relative_to(dataset).parts)
        directories[:] = [
            name for name in directories
            if not name.startswith(".") and not name.endswith(".zarr")
        ]
        if max_depth is not None and depth >= max_depth:
            directories.clear()
        for name in filenames:
            if name in names:
                path = Path(root) / name
                if path != dataset / "README.toml":
                    documents.append(path)
    return sorted(documents)


def infer_filename_evidence(files: list[str]) -> dict[str, Any]:
    """Extract repeated, non-generic filename tokens as weak evidence."""
    token_counts: dict[str, int] = {}
    patterns: set[str] = set()
    for relative_path in files:
        name = Path(relative_path).stem
        patterns.add(name)
        for token in TOKEN_PATTERN.findall(name):
            normalized = token.strip("-_ ").lower()
            if len(normalized) < 3 or normalized in GENERIC_TOKENS:
                continue
            token_counts[normalized] = token_counts.get(normalized, 0) + 1
    ranked = sorted(
        token_counts,
        key=lambda token: (-token_counts[token], token),
    )
    return {
        "tokens": ranked[:30],
        "repeated_tokens": [
            token for token in ranked if token_counts[token] >= 2
        ][:30],
        "representative_patterns": sorted(patterns)[:20],
    }


def sample_csv(path: Path) -> dict[str, Any]:
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.reader(handle)
        header = next(reader, [])
        sample = next(reader, [])
    return {
        "path": str(path),
        "columns": header,
        "sample_values": sample,
        "size_bytes": path.stat().st_size,
    }


def zarr_json_fallback(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "source": "zarr-json"}
    metadata_path = path / ".zmetadata"
    if not metadata_path.exists():
        result["error"] = "No consolidated .zmetadata found"
        return result

    with metadata_path.open(encoding="utf-8") as handle:
        document = json.load(handle)
    entries = document.get("metadata", {})
    arrays: dict[str, Any] = {}
    for name, entry in entries.items():
        if not name.endswith("/.zarray"):
            continue
        array_name = name[: -len("/.zarray")]
        arrays[array_name] = {
            key: entry.get(key)
            for key in ("shape", "chunks", "dtype", "compressor", "fill_value")
        }
        attrs = entries.get(f"{array_name}/.zattrs", {})
        if attrs:
            arrays[array_name]["attrs"] = attrs
    result["zarr_format"] = entries.get(".zgroup", {}).get("zarr_format")
    result["arrays"] = arrays
    result["attrs"] = entries.get(".zattrs", {})
    return result


def inspect_zarr(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "markers": {}}
    for marker in (".zgroup", ".zattrs", ".zmetadata", "zarr.json"):
        result["markers"][marker] = (path / marker).exists()

    try:
        import xarray as xr
    except ImportError as error:
        result["xarray_error"] = str(error)
        return zarr_json_fallback(path) | result

    try:
        dataset = xr.open_zarr(path, consolidated=True)
    except Exception as error:
        result["xarray_error"] = str(error)
        return zarr_json_fallback(path) | result

    try:
        result["source"] = "xarray"
        result["sizes"] = dict(dataset.sizes)
        result["attrs"] = dict(dataset.attrs)
        result["coordinates"] = {
            name: {"dims": value.dims, "attrs": dict(value.attrs)}
            for name, value in dataset.coords.items()
        }
        result["variables"] = {
            name: {
                "dims": value.dims,
                "dtype": str(value.dtype),
                "chunks": value.chunks,
                "attrs": dict(value.attrs),
            }
            for name, value in dataset.data_vars.items()
        }
    finally:
        dataset.close()
    return result


def build_report(
    dataset: Path,
    max_zarr_stores: int,
    explicit_stores: list[Path] | None = None,
    max_depth: int | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "dataset": str(dataset),
        "inventory": discover_files(
            dataset, max_zarr_stores, explicit_stores, max_depth
        ),
        "source_documents": [
            str(path.relative_to(dataset))
            for path in discover_source_documents(dataset, max_depth)
        ],
        "csv_samples": [],
        "zarr": [],
    }
    report["filename_evidence"] = infer_filename_evidence(
        report["inventory"]["supporting_files"]
    )
    for relative_path in report["inventory"]["supporting_files"]:
        path = dataset / relative_path
        if path.suffix.lower() == ".csv":
            report["csv_samples"].append(sample_csv(path))
    for relative_path in report["inventory"]["zarr_stores"]:
        report["zarr"].append(inspect_zarr(dataset / relative_path))
    return report


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def write_proposal(report: dict[str, Any]) -> Path:
    dataset_name = Path(report["dataset"]).name
    zarr_stores = report["inventory"]["zarr_stores"]
    supporting_files = report["inventory"]["supporting_files"]
    source_documents = report.get("source_documents", [])
    suffix_counts: dict[str, int] = {"Zarr": len(zarr_stores)}
    for path in supporting_files:
        format_name = FORMAT_NAMES.get(Path(path).suffix.lstrip(".").lower())
        if format_name:
            suffix_counts[format_name] = suffix_counts.get(format_name, 0) + 1
    formats = [name for name, _ in sorted(
        ((name, count) for name, count in suffix_counts.items() if count),
        key=lambda item: (-item[1], item[0]),
    )[:3]]
    keywords = report["filename_evidence"]["tokens"][:12]
    description = (
        "Description requires review against source documentation."
        if not source_documents
        else f"Source documentation available in {source_documents[0]}."
    )
    lines = [
        "# Evidence-backed proposal generated by src/document_dataset.py",
        "# Review against source metadata before writing to the dataset.",
        "",
        "[general]",
        f"name = {toml_string(dataset_name)}",
        f"description = {toml_string(description)}",
        "citation = \"\"",
        "manager = [\"\"]",
        f"keywords = [{', '.join(toml_string(value) for value in keywords)}]",
        "license = \"unknown\"",
        "",
        "[details]",
        f"zarr_stores = [{', '.join(toml_string(path) for path in zarr_stores)}]",
        f"supporting_files = [{', '.join(toml_string(path) for path in supporting_files)}]",
        f"source_documents = [{', '.join(toml_string(path) for path in source_documents)}]",
        f"formats = [{', '.join(toml_string(value) for value in formats)}]",
        f"zarr_sources = [{', '.join(toml_string(item.get('source', 'unknown')) for item in report['zarr'])}]",
        f"filename_evidence = {toml_string(json.dumps(report['filename_evidence']))}",
        "",
        "[publication]",
        "",
        "[[log]]",
        f"date = {date.today().isoformat()}",
        "comment = \"Proposal generated for review; dataset README.toml not modified.\"",
        "",
    ]
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".toml", prefix="dataset-proposal-", delete=False
    ) as handle:
        handle.write("\n".join(lines))
        return Path(handle.name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Dataset directory to inspect")
    parser.add_argument(
        "--max-zarr-stores",
        type=int,
        default=3,
        help="Maximum number of Zarr stores to inspect (default: 3)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Optional directory-depth limit; recurse to all depths by default",
    )
    parser.add_argument(
        "--zarr-store",
        action="append",
        default=[],
        help="Explicit Zarr store path; repeat up to three times",
    )
    parser.add_argument(
        "--proposal",
        action="store_true",
        help="Write a temporary evidence-backed README.toml proposal",
    )
    args = parser.parse_args()
    dataset = args.dataset.resolve()
    if not dataset.is_dir():
        parser.error(f"dataset directory does not exist: {dataset}")
    if args.max_zarr_stores < 1:
        parser.error("--max-zarr-stores must be at least 1")
    if args.max_depth is not None and args.max_depth < 0:
        parser.error("--max-depth must be non-negative")
    if len(args.zarr_store) > 3:
        parser.error("--zarr-store may be supplied at most three times")
    explicit_stores = []
    for raw_path in args.zarr_store:
        store_path = Path(raw_path)
        if not store_path.is_absolute():
            store_path = dataset / store_path
        store_path = store_path.resolve()
        try:
            store_path.relative_to(dataset)
        except ValueError:
            parser.error(f"Zarr store must be inside the dataset: {raw_path}")
        if not store_path.is_dir() or not store_path.name.endswith(".zarr"):
            parser.error(f"Zarr store directory not found: {raw_path}")
        explicit_stores.append(store_path)
    report = build_report(
        dataset, args.max_zarr_stores, explicit_stores or None, args.max_depth
    )
    if args.proposal:
        proposal_path = write_proposal(report)
        print(f"proposal: {proposal_path}", file=sys.stderr)
    json.dump(report, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
