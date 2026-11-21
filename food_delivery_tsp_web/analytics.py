"""Measured summaries for the supplied day-wise matrices."""

from functools import lru_cache
from pathlib import Path

from dataset_loader import PREFIX, ROOT, available_matrices, days, load, summary


@lru_cache(maxsize=1)
def daily_matrix_summaries():
    records = []
    for day in days():
        row = {"day": day, "nodes": None, "matrices": {kind: None for kind in PREFIX}}
        for kind in PREFIX:
            path = available_matrices(day)[kind]
            if path is None:
                continue
            try:
                matrix = load(day, kind)
                row["matrices"][kind] = summary(matrix)
                if kind == "distance":
                    row["nodes"] = len(matrix.nodes)
            except (OSError, ValueError):
                row["matrices"][kind] = {"error": "Matrix unavailable or invalid."}
        records.append(row)
    return tuple(records)


def dataset_inventory():
    available_days = days()
    matrix_files = {day: available_matrices(day) for day in available_days}
    by_kind = {
        kind: sum(1 for paths in matrix_files.values() if paths[kind] is not None)
        for kind in PREFIX
    }
    files = sum(by_kind.values())
    node_counts = []
    for day in available_days:
        if available_matrices(day)["distance"] is None:
            continue
        try:
            node_counts.append(len(load(day, "distance").nodes))
        except (OSError, ValueError):
            continue
    return {
        "days": len(available_days),
        "day_numbers": available_days,
        "matrix_files": files,
        "matrix_counts": by_kind,
        "nodes_min": min(node_counts) if node_counts else None,
        "nodes_max": max(node_counts) if node_counts else None,
    }


def order_characteristics_file():
    """Find a non-matrix tabular dataset, if one is present in the project."""
    if not ROOT.parent.exists():
        return None
    for path in sorted(ROOT.parent.rglob("*")):
        if not path.is_file() or ROOT in path.parents:
            continue
        if path.suffix.lower() in {".xlsx", ".xlsm", ".csv", ".tsv"}:
            return path
    return None
